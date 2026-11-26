"""Одна SQLite-база: справочник, рецепты, состав, запасы и настройки."""

import os
import sqlite3

from data_loader import data_directory, project_file
from logic import (
    ValidationError,
    calculate,
    checked_integer,
    checked_number,
    ingredient_values,
    normalized_name,
    recipe_values,
)


class Database:
    def __init__(self, filename=None):
        self.filename = os.path.abspath(
            filename or os.path.join(data_directory(), "recipes.sqlite3")
        )
        self.directory = os.path.dirname(self.filename)
        self.connection = None
        try:
            os.makedirs(self.directory, exist_ok=True)
            self.connection = sqlite3.connect(self.filename)
            self.connection.execute("PRAGMA foreign_keys = ON")
            if (
                self.connection.execute("PRAGMA quick_check").fetchone()[0]
                != "ok"
            ):
                raise sqlite3.DatabaseError("Повреждён файл базы данных.")
            with open(
                project_file("data", "schema.sql"), encoding="utf-8"
            ) as file:
                statements = file.read().split(";")
            with self.connection:
                for statement in statements:
                    if statement.strip():
                        self.connection.execute(statement)
                columns = self.connection.execute(
                    "PRAGMA table_info(app_settings)"
                ).fetchall()
                if "theme" not in [column[1] for column in columns]:
                    self.connection.execute(
                        "ALTER TABLE app_settings ADD COLUMN theme TEXT "
                        "NOT NULL DEFAULT 'light' "
                        "CHECK(theme IN ('light', 'dark'))"
                    )
                if not self.connection.execute(
                    "SELECT id FROM app_settings"
                ).fetchone():
                    self.connection.execute(
                        "INSERT INTO app_settings "
                        "(id, preferred_servings) VALUES (1, 2)"
                    )
        except (OSError, sqlite3.Error) as error:
            if self.connection is not None:
                self.connection.close()
            raise type(error)(
                f"Файл базы данных: {self.filename}\n{error}"
            ) from error
        except Exception:
            if self.connection is not None:
                self.connection.close()
            raise

    def query(self, sql, parameters=()):
        cursor = self.connection.execute(sql, parameters)
        fields = [column[0] for column in cursor.description]
        return [dict(zip(fields, row)) for row in cursor.fetchall()]

    def ingredients(self):
        return sorted(
            self.query("SELECT * FROM ingredients"),
            key=lambda row: normalized_name(row["name"]),
        )

    def ingredient(self, ingredient_id):
        rows = self.query(
            "SELECT * FROM ingredients WHERE id = ?", (ingredient_id,)
        )
        return rows[0] if rows else None

    def save_ingredient(self, values, ingredient_id=None):
        parameters = ingredient_values(values)
        existing = self.query(
            "SELECT id, name FROM ingredients WHERE name_key = ?",
            (parameters[1],),
        )
        if existing and existing[0]["id"] != ingredient_id:
            raise ValidationError(
                f"Ингредиент «{existing[0]['name']}» уже есть. "
                "Выберите его в справочнике.",
                "name",
            )
        if ingredient_id is not None:
            old = self.ingredient(ingredient_id)
            if not old:
                raise ValueError("Ингредиент уже удалён.")
            if old["unit"] != parameters[2]:
                raise ValueError(
                    "Единицу существующего ингредиента менять нельзя."
                )
        with self.connection:
            if ingredient_id is None:
                cursor = self.connection.execute(
                    "INSERT INTO ingredients "
                    "(name, name_key, unit, calories, protein, fat, carbs) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    parameters,
                )
                ingredient_id = cursor.lastrowid
            else:
                self.connection.execute(
                    "UPDATE ingredients SET "
                    "name=?, name_key=?, unit=?, calories=?, "
                    "protein=?, fat=?, carbs=? WHERE id=?",
                    parameters + [ingredient_id],
                )
        return ingredient_id

    def delete_ingredient(self, ingredient_id):
        if self.query(
            "SELECT recipe_id FROM recipe_ingredients WHERE ingredient_id=?",
            (ingredient_id,),
        ):
            raise ValueError("Ингредиент используется в рецептах.")
        if self.query(
            "SELECT ingredient_id FROM fridge WHERE ingredient_id=?",
            (ingredient_id,),
        ):
            raise ValueError("Сначала удалите продукт из холодильника.")
        with self.connection:
            self.connection.execute(
                "DELETE FROM ingredients WHERE id=?", (ingredient_id,)
            )

    def recipes(self):
        return self.query("SELECT * FROM recipes")

    def recipe(self, recipe_id):
        rows = self.query("SELECT * FROM recipes WHERE id=?", (recipe_id,))
        return rows[0] if rows else None

    def composition(self, recipe_id=None):
        sql = (
            "SELECT ri.recipe_id, ri.ingredient_id, ri.quantity, "
            "i.name, i.unit, i.calories, i.protein, i.fat, i.carbs "
            "FROM recipe_ingredients AS ri "
            "JOIN ingredients AS i ON i.id=ri.ingredient_id"
        )
        parameters = ()
        if recipe_id is not None:
            sql += " WHERE ri.recipe_id=?"
            parameters = (recipe_id,)
        return self.query(sql + " ORDER BY ri.ingredient_id", parameters)

    def save_recipe(self, values, composition, recipe_id=None):
        parameters, rows = recipe_values(values, composition)
        if recipe_id is not None and not self.recipe(recipe_id):
            raise ValueError("Рецепт уже удалён.")
        with self.connection:
            if recipe_id is None:
                cursor = self.connection.execute(
                    "INSERT INTO recipes "
                    "(name, category, instructions, base_portions, "
                    "cooking_minutes, image_path) VALUES (?, ?, ?, ?, ?, ?)",
                    parameters,
                )
                recipe_id = cursor.lastrowid
            else:
                self.connection.execute(
                    "UPDATE recipes SET name=?, category=?, instructions=?, "
                    "base_portions=?, cooking_minutes=?, "
                    "image_path=? WHERE id=?",
                    parameters + [recipe_id],
                )
                self.connection.execute(
                    "DELETE FROM recipe_ingredients WHERE recipe_id=?",
                    (recipe_id,),
                )
            for ingredient_id, quantity in rows:
                self.connection.execute(
                    "INSERT INTO recipe_ingredients VALUES (?, ?, ?)",
                    (recipe_id, ingredient_id, quantity),
                )
        return recipe_id

    def delete_recipe(self, recipe_id):
        with self.connection:
            self.connection.execute(
                "DELETE FROM recipes WHERE id=?", (recipe_id,)
            )

    def set_favorite(self, recipe_id, favorite):
        with self.connection:
            self.connection.execute(
                "UPDATE recipes SET is_favorite=? WHERE id=?",
                (int(favorite), recipe_id),
            )

    def fridge(self):
        return self.query(
            "SELECT f.ingredient_id, f.quantity, i.name, i.unit "
            "FROM fridge AS f JOIN ingredients AS i "
            "ON i.id=f.ingredient_id ORDER BY i.name"
        )

    def stocks(self):
        return {row["ingredient_id"]: row["quantity"] for row in self.fridge()}

    def save_stock(self, ingredient_id, quantity):
        quantity = float(
            checked_number(quantity, "Доступное количество", field="quantity")
        )
        if not self.ingredient(ingredient_id):
            raise ValueError("Сначала выберите ингредиент из справочника.")
        with self.connection:
            existing = self.connection.execute(
                "SELECT ingredient_id FROM fridge WHERE ingredient_id=?",
                (ingredient_id,),
            ).fetchone()
            if existing:
                self.connection.execute(
                    "UPDATE fridge SET quantity=? WHERE ingredient_id=?",
                    (quantity, ingredient_id),
                )
            else:
                self.connection.execute(
                    "INSERT INTO fridge VALUES (?, ?)",
                    (ingredient_id, quantity),
                )

    def delete_stock(self, ingredient_id):
        with self.connection:
            self.connection.execute(
                "DELETE FROM fridge WHERE ingredient_id=?", (ingredient_id,)
            )

    def persons(self):
        return self.connection.execute(
            "SELECT preferred_servings FROM app_settings WHERE id=1"
        ).fetchone()[0]

    def save_persons(self, persons):
        persons = checked_integer(persons, "Число персон", 1, 20)
        with self.connection:
            self.connection.execute(
                "UPDATE app_settings SET preferred_servings=? WHERE id=1",
                (persons,),
            )

    def theme(self):
        return self.connection.execute(
            "SELECT theme FROM app_settings WHERE id=1"
        ).fetchone()[0]

    def save_settings(self, persons, theme):
        persons = checked_integer(persons, "Число персон", 1, 20)
        if theme not in ("light", "dark"):
            raise ValueError("Выберите светлую или тёмную тему.")
        with self.connection:
            self.connection.execute(
                "UPDATE app_settings SET preferred_servings=?, theme=? "
                "WHERE id=1",
                (persons, theme),
            )

    def recipe_views(self):
        compositions = {}
        for row in self.composition():
            compositions.setdefault(row["recipe_id"], []).append(row)
        stocks = self.stocks()
        result = []
        for recipe in self.recipes():
            composition = compositions.get(recipe["id"], [])
            nutrition = calculate(recipe, composition, stocks, 1)[
                "per_portion"
            ]
            result.append(
                dict(recipe, composition=composition, nutrition=nutrition)
            )
        return result

    def close(self):
        self.connection.close()
