"""Проверки данных, связей, расчётов и экспорта на временной базе."""

import csv
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

from database import Database
from file_tools import export_recipes, export_shopping
from logic import calculate, sort_recipes


def ingredient(name="Мука", unit="г", known=True):
    return {
        "name": name,
        "unit": unit,
        "calories": 100 if known else None,
        "protein": 2 if known else None,
        "fat": 3 if known else None,
        "carbs": 4 if known else None,
    }


def recipe(name="Рецепт", portions=2):
    return {
        "name": name,
        "category": "Другое",
        "instructions": "Приготовить блюдо.",
        "base_portions": portions,
        "cooking_minutes": 30,
        "image_path": None,
    }


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.filename = os.path.join(self.temp.name, "recipes.sqlite3")
        self.db = Database(self.filename)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_first_start_and_persistence(self):
        tables = self.db.query(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        self.assertEqual(
            {row["name"] for row in tables},
            {
                "recipes",
                "ingredients",
                "recipe_ingredients",
                "fridge",
                "app_settings",
            },
        )
        self.assertEqual(self.db.recipes(), [])
        self.assertEqual(self.db.persons(), 2)
        item = self.db.save_ingredient(ingredient())
        rid = self.db.save_recipe(
            recipe(), [{"ingredient_id": item, "quantity": 200}]
        )
        self.db.set_favorite(rid, True)
        self.db.save_persons(3)
        self.db.save_stock(item, "150,25")
        self.db.close()
        self.db = Database(self.filename)
        self.assertEqual(self.db.recipe(rid)["is_favorite"], 1)
        self.assertEqual(self.db.persons(), 3)
        self.assertEqual(self.db.stocks()[item], 150.25)

    def test_theme_migration_preserves_existing_database(self):
        item = self.db.save_ingredient(ingredient())
        rid = self.db.save_recipe(
            recipe(), [{"ingredient_id": item, "quantity": 200}]
        )
        self.db.set_favorite(rid, True)
        self.db.save_stock(item, "100.25")
        self.db.save_persons(5)
        with self.db.connection:
            self.db.connection.execute(
                "ALTER TABLE app_settings RENAME TO old_settings"
            )
            self.db.connection.execute(
                "CREATE TABLE app_settings (id INTEGER PRIMARY KEY, "
                "preferred_servings INTEGER NOT NULL)"
            )
            self.db.connection.execute(
                "INSERT INTO app_settings SELECT id, preferred_servings "
                "FROM old_settings"
            )
            self.db.connection.execute("DROP TABLE old_settings")
        self.db.close()
        self.db = Database(self.filename)
        self.assertEqual(self.db.theme(), "light")
        self.assertEqual(self.db.persons(), 5)
        self.assertEqual(self.db.recipe(rid)["is_favorite"], 1)
        self.assertEqual(len(self.db.composition(rid)), 1)
        self.assertEqual(self.db.stocks()[item], 100.25)
        self.db.save_settings(4, "dark")
        self.db.close()
        self.db = Database(self.filename)
        self.assertEqual((self.db.persons(), self.db.theme()), (4, "dark"))
        self.assertEqual(
            self.db.connection.execute("PRAGMA foreign_key_check").fetchall(),
            [],
        )

    def test_settings_validation_is_atomic(self):
        self.db.save_settings(6, "dark")
        for persons, theme in [(0, "light"), (3, "pink")]:
            with self.assertRaises(ValueError):
                self.db.save_settings(persons, theme)
            self.assertEqual((self.db.persons(), self.db.theme()), (6, "dark"))
        self.db.save_persons(2)
        self.assertEqual(self.db.theme(), "dark")

    def test_ingredient_duplicate_and_unit(self):
        item = self.db.save_ingredient(ingredient(" Мука  пшеничная "))
        with self.assertRaises(ValueError):
            self.db.save_ingredient(ingredient("мука пшеничная"))
        values = ingredient("Мука пшеничная", "мл")
        with self.assertRaises(ValueError):
            self.db.save_ingredient(values, item)
        self.assertEqual(len(self.db.ingredients()), 1)

    def test_unknown_is_not_zero_and_partial_is_rejected(self):
        item = self.db.save_ingredient(ingredient(known=False))
        self.assertIsNone(self.db.ingredient(item)["calories"])
        values = ingredient()
        values.update(calories=0, protein=0, fat=0, carbs=0)
        self.db.save_ingredient(values, item)
        self.assertEqual(self.db.ingredient(item)["calories"], 0)
        values["fat"] = None
        with self.assertRaises(ValueError):
            self.db.save_ingredient(values, item)

    def test_recipe_update_rolls_back_on_foreign_key_error(self):
        item = self.db.save_ingredient(ingredient())
        rid = self.db.save_recipe(
            recipe("Старый"), [{"ingredient_id": item, "quantity": 200}]
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.save_recipe(
                recipe("Новый"), [{"ingredient_id": 99999, "quantity": 5}], rid
            )
        self.assertEqual(self.db.recipe(rid)["name"], "Старый")
        self.assertEqual(self.db.composition(rid)[0]["quantity"], 200)

    def test_many_to_many_delete_cascade_and_restrict(self):
        item = self.db.save_ingredient(ingredient())
        first = self.db.save_recipe(
            recipe("Первый"), [{"ingredient_id": item, "quantity": 200}]
        )
        second = self.db.save_recipe(
            recipe("Второй"), [{"ingredient_id": item, "quantity": 100}]
        )
        self.db.save_stock(item, 150)
        with self.assertRaises(ValueError):
            self.db.delete_ingredient(item)
        self.db.delete_recipe(first)
        self.assertEqual(len(self.db.composition()), 1)
        self.assertEqual(self.db.stocks()[item], 150)
        self.db.delete_stock(item)
        self.assertIsNotNone(self.db.ingredient(item))
        self.db.delete_recipe(second)
        self.db.delete_ingredient(item)
        self.assertEqual(self.db.ingredients(), [])

    def test_stock_replaces_and_empty_composition_rejected(self):
        item = self.db.save_ingredient(ingredient())
        self.db.save_stock(item, 150)
        self.db.save_stock(item, 200)
        self.assertEqual(self.db.stocks()[item], 200)
        with self.assertRaises(ValueError):
            self.db.save_recipe(recipe(), [])
        with self.assertRaises(ValueError):
            self.db.save_recipe(
                recipe(), [{"ingredient_id": item, "quantity": -1}]
            )
        self.assertEqual(self.db.recipes(), [])

    def test_portions_shortage_and_fractional_pieces(self):
        item = self.db.save_ingredient(ingredient())
        rid = self.db.save_recipe(
            recipe(portions=4), [{"ingredient_id": item, "quantity": 400}]
        )
        result = calculate(
            self.db.recipe(rid), self.db.composition(rid), {item: 150}, 2
        )
        self.assertEqual(result["rows"][0]["required"], Decimal("200"))
        self.assertEqual(result["rows"][0]["missing"], Decimal("50"))
        self.assertEqual(self.db.composition(rid)[0]["quantity"], 400)
        self.assertEqual(result["per_portion"]["calories"], Decimal("100"))
        self.assertEqual(result["selected"]["calories"], Decimal("200"))
        egg = self.db.save_ingredient(ingredient("Яйцо", "шт"))
        erid = self.db.save_recipe(
            recipe(), [{"ingredient_id": egg, "quantity": 3}]
        )
        value = calculate(
            self.db.recipe(erid), self.db.composition(erid), {}, 1
        )
        self.assertEqual(value["rows"][0]["required"], Decimal("1.50"))
        self.assertEqual(value["per_portion"]["calories"], Decimal("150"))

    def test_millilitres_and_rounding_up(self):
        item = self.db.save_ingredient(ingredient("Молоко", "мл"))
        rid = self.db.save_recipe(
            recipe(portions=3), [{"ingredient_id": item, "quantity": 300}]
        )
        value = calculate(self.db.recipe(rid), self.db.composition(rid), {}, 1)
        self.assertEqual(value["per_portion"]["calories"], Decimal("100"))
        self.db.save_recipe(
            recipe(portions=3), [{"ingredient_id": item, "quantity": 1}], rid
        )
        value = calculate(
            self.db.recipe(rid), self.db.composition(rid), {item: 0.33}, 1
        )
        self.assertEqual(value["rows"][0]["required"], Decimal("0.34"))
        self.assertEqual(value["rows"][0]["missing"], Decimal("0.01"))

    def test_unknown_sort_always_last(self):
        a = self.db.save_ingredient(ingredient("Известно"))
        b = self.db.save_ingredient(ingredient("Неизвестно", known=False))
        for name, item, quantity in [
            ("Мало", a, 100),
            ("Много", a, 200),
            ("Без КБЖУ", b, 100),
        ]:
            self.db.save_recipe(
                recipe(name, 1),
                [{"ingredient_id": item, "quantity": quantity}],
            )
        views = self.db.recipe_views()
        self.assertEqual(
            [r["name"] for r in sort_recipes(views, "calories")],
            ["Мало", "Много", "Без КБЖУ"],
        )
        self.assertEqual(
            [r["name"] for r in sort_recipes(views, "calories", True)],
            ["Много", "Мало", "Без КБЖУ"],
        )

    def test_export_formats_and_atomic_failure(self):
        item = self.db.save_ingredient(ingredient())
        rid = self.db.save_recipe(
            recipe('Блюдо; "вариант"'),
            [{"ingredient_id": item, "quantity": 200}],
        )
        path = os.path.join(self.temp.name, "recipes.csv")
        export_recipes(path, self.db.recipe_views())
        with open(path, encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file, delimiter=";"))
        self.assertEqual(rows[1][1], 'Блюдо; "вариант"')
        self.assertEqual(len(rows[1]), 10)
        result = calculate(
            self.db.recipe(rid), self.db.composition(rid), {item: 150}, 2
        )
        txt = os.path.join(self.temp.name, "shopping.txt")
        export_shopping(txt, self.db.recipe(rid), 2, result)
        with open(txt, encoding="utf-8") as file:
            self.assertIn("50,00 г", file.read())
        with open(path, "rb") as file:
            old = file.read()
        with patch(
            "file_tools.os.replace", side_effect=OSError("Нет доступа")
        ):
            with self.assertRaises(OSError):
                export_recipes(path, [])
        with open(path, "rb") as file:
            self.assertEqual(file.read(), old)

    def test_corrupt_database_not_overwritten(self):
        path = os.path.join(self.temp.name, "broken.sqlite3")
        with open(path, "wb") as file:
            file.write(b"broken database content")
        with self.assertRaises(sqlite3.DatabaseError):
            Database(path)
        with open(path, "rb") as file:
            self.assertEqual(file.read(), b"broken database content")


if __name__ == "__main__":
    unittest.main()
