"""Главное окно приложения «Что приготовить?»."""

import sqlite3
import sys

from PyQt6 import uic
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
)

from data_loader import CATEGORIES, NUTRIENTS, project_file
from database import Database
from file_tools import export_recipes, remove_unused_photo
from forms import (
    NO,
    YES,
    HelpWindow,
    IngredientEditor,
    RecipeCard,
    RecipeEditor,
    SettingsWindow,
    StockEditor,
    TimerWindow,
    fill_table,
    selected_row,
)
from logic import calculate, normalized_name, number_text, sort_recipes


class MainWindow(QMainWindow):
    def __init__(self, database_path=None):
        super().__init__()
        uic.loadUi(project_file("ui", "main_window.ui"), self)
        self.database = Database(database_path)
        self.closed = False
        self.changing_filters = False
        self.views = []
        self.current_recipes = []
        self.ingredient_rows = []
        self.stock_rows = []
        self.selection_rows = []
        self.selection_valid = False
        self.selection_ever_calculated = False
        self.categoryCombo.addItems(["Все"] + CATEGORIES)
        self.personsSpin.setValue(self.database.persons())
        self.limitSpin.setEnabled(False)
        self.selectionLimitSpin.setEnabled(False)
        self.timerStatusButton = QPushButton("Таймер: 10:00")
        self.statusBar().addPermanentWidget(self.timerStatusButton)
        self.recipe_card = RecipeCard(self.database, self.data_changed)
        self.recipe_editor = RecipeEditor(self.database, self.data_changed)
        self.ingredient_editor = IngredientEditor(
            self.database, self.data_changed
        )
        self.stock_editor = StockEditor(self.database, self.data_changed)
        self.settings_window = SettingsWindow(self.database, self.data_changed)
        self.timer_window = TimerWindow(self.timer_status)
        self.help_window = HelpWindow()
        self.windows = [
            self.ingredient_editor,
            self.stock_editor,
            self.recipe_editor,
            self.settings_window,
            self.recipe_card,
            self.timer_window,
            self.help_window,
        ]
        self.connect_buttons()
        self.data_changed()
        self.statusBar().showMessage(
            "Данные сохраняются автоматически после нажатия «Сохранить»."
        )

    def connect_buttons(self):
        self.addRecipeButton.clicked.connect(self.new_recipe)
        self.openRecipeButton.clicked.connect(self.open_recipe)
        self.editRecipeButton.clicked.connect(self.edit_recipe)
        self.deleteRecipeButton.clicked.connect(self.delete_recipe)
        self.exportButton.clicked.connect(self.save_csv)
        self.addIngredientButton.clicked.connect(self.new_ingredient)
        self.editIngredientButton.clicked.connect(self.edit_ingredient)
        self.deleteIngredientButton.clicked.connect(self.delete_ingredient)
        self.addStockButton.clicked.connect(self.new_stock)
        self.editStockButton.clicked.connect(self.edit_stock)
        self.deleteStockButton.clicked.connect(self.delete_stock)
        self.selectButton.clicked.connect(self.select_recipes)
        self.openSelectionButton.clicked.connect(self.open_selected_recipe)
        self.resetFiltersButton.clicked.connect(self.reset_filters)
        for table in [
            self.recipesTable,
            self.ingredientsTable,
            self.fridgeTable,
            self.selectionTable,
        ]:
            table.itemSelectionChanged.connect(self.update_buttons)
        self.recipesTable.cellDoubleClicked.connect(self.open_recipe)
        self.ingredientsTable.cellDoubleClicked.connect(self.edit_ingredient)
        self.fridgeTable.cellDoubleClicked.connect(self.edit_stock)
        self.selectionTable.cellDoubleClicked.connect(
            self.open_selected_recipe
        )
        self.recipeSearch.textChanged.connect(self.render_recipes)
        self.categoryCombo.currentIndexChanged.connect(self.render_recipes)
        self.favoritesCheck.toggled.connect(self.render_recipes)
        self.limitCheck.toggled.connect(self.recipe_limit_changed)
        self.limitSpin.valueChanged.connect(self.render_recipes)
        self.recipeSort.currentIndexChanged.connect(self.render_recipes)
        self.recipeOrder.currentIndexChanged.connect(self.render_recipes)
        self.ingredientSearch.textChanged.connect(self.render_ingredients)
        self.fridgeSearch.textChanged.connect(self.render_fridge)
        self.personsSpin.valueChanged.connect(self.invalidate_selection)
        self.selectionLimitCheck.toggled.connect(self.selection_limit_changed)
        self.selectionLimitSpin.valueChanged.connect(self.invalidate_selection)
        self.availableCheck.toggled.connect(self.invalidate_selection)
        self.selectionSort.currentIndexChanged.connect(self.render_selection)
        self.selectionOrder.currentIndexChanged.connect(self.render_selection)
        self.mainTabs.currentChanged.connect(self.tab_changed)
        self.recipe_card.editButton.clicked.connect(self.edit_open_recipe)
        self.recipe_card.timerButton.clicked.connect(self.timer_window.show)
        self.recipe_editor.newIngredientButton.clicked.connect(
            self.new_ingredient
        )
        self.stock_editor.newIngredientButton.clicked.connect(
            self.new_ingredient
        )
        self.actionNewRecipe.triggered.connect(self.new_recipe)
        self.actionExport.triggered.connect(self.save_csv)
        self.actionExit.triggered.connect(self.close)
        self.actionSettings.triggered.connect(
            self.settings_window.open_settings
        )
        self.actionTimer.triggered.connect(self.timer_window.show)
        self.timerStatusButton.clicked.connect(self.timer_window.show)
        self.actionHelp.triggered.connect(self.help_window.show)
        self.actionAbout.triggered.connect(self.show_about)

    def data_changed(self, ingredient_id=None, favorite_only=False):
        self.views = self.database.recipe_views()
        self.render_recipes()
        if not favorite_only:
            self.render_ingredients()
            self.render_fridge()
            self.invalidate_selection()
            if self.recipe_editor.isVisible():
                self.recipe_editor.refresh_ingredients(ingredient_id)
            if self.stock_editor.isVisible():
                self.stock_editor.refresh_ingredients(ingredient_id)
            if self.mainTabs.currentIndex() != 3:
                self.personsSpin.setValue(self.database.persons())
        if self.recipe_card.isVisible():
            self.recipe_card.refresh()

    def nutrition_cells(self, recipe):
        values = recipe["nutrition"]
        return (
            ["—"] * 4
            if values is None
            else [
                number_text(values[key], 1 if key == "calories" else 2)
                for key in NUTRIENTS
            ]
        )

    def render_recipes(self):
        if self.changing_filters:
            return
        text = normalized_name(self.recipeSearch.text())
        category = self.categoryCombo.currentText()
        recipes = [
            row
            for row in self.views
            if text in normalized_name(row["name"])
            and (category == "Все" or row["category"] == category)
            and (not self.favoritesCheck.isChecked() or row["is_favorite"])
            and (
                not self.limitCheck.isChecked()
                or row["cooking_minutes"] <= self.limitSpin.value()
            )
        ]
        fields = ["name", "cooking_minutes"] + NUTRIENTS
        self.current_recipes = sort_recipes(
            recipes,
            fields[self.recipeSort.currentIndex()],
            self.recipeOrder.currentIndex() == 1,
        )
        fill_table(
            self.recipesTable,
            [
                [
                    row["name"],
                    row["category"],
                    row["cooking_minutes"],
                    row["base_portions"],
                ]
                + self.nutrition_cells(row)
                + ["Да" if row["is_favorite"] else "Нет"]
                for row in self.current_recipes
            ],
        )
        if self.current_recipes:
            message = f"Найдено рецептов: {len(self.current_recipes)}"
            if any(row["nutrition"] is None for row in self.current_recipes):
                message += ". «—» — КБЖУ не рассчитано."
        elif self.favoritesCheck.isChecked() and not any(
            row["is_favorite"] for row in self.views
        ):
            message = "В избранном пока нет рецептов. Добавьте их в карточке."
        elif self.views:
            message = (
                "Рецепты не найдены. Измените условия или сбросьте фильтры."
            )
        else:
            message = (
                "Рецептов пока нет. Добавьте ингредиенты в справочник "
                "и создайте первый рецепт."
            )
        self.recipesHint.setText(message)
        self.exportButton.setEnabled(bool(self.current_recipes))
        self.actionExport.setEnabled(bool(self.current_recipes))
        self.update_buttons()

    def render_ingredients(self):
        text = normalized_name(self.ingredientSearch.text())
        ingredients = self.database.ingredients()
        self.ingredient_rows = [
            row for row in ingredients if text in normalized_name(row["name"])
        ]
        rows = []
        for ingredient in self.ingredient_rows:
            base = (
                "на 1 шт"
                if ingredient["unit"] == "шт"
                else "на 100 " + ingredient["unit"]
            )
            numbers = (
                ["—"] * 4
                if ingredient["calories"] is None
                else [
                    number_text(ingredient[key], 1 if key == "calories" else 2)
                    for key in NUTRIENTS
                ]
            )
            rows.append(
                [ingredient["name"], ingredient["unit"], base] + numbers
            )
        fill_table(self.ingredientsTable, rows)
        self.ingredientsHint.setText(
            ""
            if rows
            else (
                "Ингредиенты не найдены. Измените поиск."
                if ingredients
                else "Добавьте ингредиенты здесь или при создании рецепта."
            )
        )
        self.update_buttons()

    def render_fridge(self):
        text = normalized_name(self.fridgeSearch.text())
        stocks = self.database.fridge()
        self.stock_rows = [
            row for row in stocks if text in normalized_name(row["name"])
        ]
        fill_table(
            self.fridgeTable,
            [
                [row["name"], number_text(row["quantity"]), row["unit"]]
                for row in self.stock_rows
            ],
        )
        self.fridgeHint.setText(
            "Все домашние запасы."
            if self.stock_rows
            else (
                "Запасы не найдены. Измените поиск."
                if stocks
                else "Запасов пока нет. При подборе доступное количество "
                "продуктов считается нулевым."
            )
        )
        self.update_buttons()

    def recipe_limit_changed(self):
        self.limitSpin.setEnabled(self.limitCheck.isChecked())
        self.render_recipes()

    def selection_limit_changed(self):
        self.selectionLimitSpin.setEnabled(
            self.selectionLimitCheck.isChecked()
        )
        self.invalidate_selection()

    def reset_filters(self):
        self.changing_filters = True
        self.recipeSearch.clear()
        self.categoryCombo.setCurrentIndex(0)
        self.favoritesCheck.setChecked(False)
        self.limitCheck.setChecked(False)
        self.changing_filters = False
        self.render_recipes()

    def tab_changed(self, index):
        if index == 3:
            self.personsSpin.setValue(self.database.persons())
            self.invalidate_selection()

    def invalidate_selection(self):
        self.selection_valid = False
        self.selection_rows = []
        fill_table(self.selectionTable, [])
        self.selectionHint.setText(
            "Условия изменились. Нажмите «Подобрать»."
            if self.selection_ever_calculated
            else (
                "Нажмите «Подобрать», чтобы рассчитать блюда "
                "по текущим запасам."
            )
        )
        self.update_buttons()

    def select_recipes(self):
        stocks = self.database.stocks()
        results = []
        for recipe in self.views:
            if (
                self.selectionLimitCheck.isChecked()
                and recipe["cooking_minutes"] > self.selectionLimitSpin.value()
            ):
                continue
            result = calculate(
                recipe, recipe["composition"], stocks, self.personsSpin.value()
            )
            if self.availableCheck.isChecked() and result["missing_count"]:
                continue
            results.append(dict(recipe, missing_count=result["missing_count"]))
        self.selection_rows = results
        self.selection_ever_calculated = True
        self.selection_valid = True
        self.render_selection()

    def render_selection(self):
        if not self.selection_valid:
            return
        fields = ["missing_count", "cooking_minutes"] + NUTRIENTS
        self.selection_rows = sort_recipes(
            self.selection_rows,
            fields[self.selectionSort.currentIndex()],
            self.selectionOrder.currentIndex() == 1,
        )
        fill_table(
            self.selectionTable,
            [
                [
                    row["name"],
                    row["cooking_minutes"],
                    "Нужно купить" if row["missing_count"] else "Всё есть",
                    row["missing_count"],
                ]
                + self.nutrition_cells(row)
                for row in self.selection_rows
            ],
        )
        self.selectionHint.setText(
            f"Найдено рецептов: {len(self.selection_rows)}"
            if self.selection_rows
            else "Нет рецептов по выбранным условиям."
        )
        self.update_buttons()

    def selected_record(self, table, records):
        index = selected_row(table)
        return records[index] if 0 <= index < len(records) else None

    def update_buttons(self):
        recipe = self.selected_record(self.recipesTable, self.current_recipes)
        self.openRecipeButton.setEnabled(recipe is not None)
        self.editRecipeButton.setEnabled(recipe is not None)
        self.deleteRecipeButton.setEnabled(recipe is not None)
        ingredient = self.selected_record(
            self.ingredientsTable, self.ingredient_rows
        )
        self.editIngredientButton.setEnabled(ingredient is not None)
        self.deleteIngredientButton.setEnabled(ingredient is not None)
        stock = self.selected_record(self.fridgeTable, self.stock_rows)
        self.editStockButton.setEnabled(stock is not None)
        self.deleteStockButton.setEnabled(stock is not None)
        self.openSelectionButton.setEnabled(
            self.selected_record(self.selectionTable, self.selection_rows)
            is not None
        )

    def new_recipe(self):
        self.recipe_editor.show_recipe()

    def open_recipe(self):
        recipe = self.selected_record(self.recipesTable, self.current_recipes)
        if recipe:
            self.recipe_card.show_recipe(recipe, self.database.persons())

    def edit_recipe(self):
        recipe = self.selected_record(self.recipesTable, self.current_recipes)
        if recipe:
            self.recipe_editor.show_recipe(recipe)

    def edit_open_recipe(self):
        recipe = self.database.recipe(self.recipe_card.recipe_id)
        if recipe:
            self.recipe_editor.show_recipe(recipe)

    def open_selected_recipe(self):
        recipe = self.selected_record(self.selectionTable, self.selection_rows)
        if recipe:
            self.recipe_card.show_recipe(recipe, self.personsSpin.value())

    def new_ingredient(self):
        self.ingredient_editor.show_ingredient()

    def edit_ingredient(self):
        ingredient = self.selected_record(
            self.ingredientsTable, self.ingredient_rows
        )
        if ingredient:
            self.ingredient_editor.show_ingredient(ingredient)

    def new_stock(self):
        self.stock_editor.show_stock()

    def edit_stock(self):
        stock = self.selected_record(self.fridgeTable, self.stock_rows)
        if stock:
            self.stock_editor.show_stock(stock)

    def confirm_delete(self, title):
        return (
            QMessageBox.question(
                self, "Подтвердите удаление", title, YES | NO, NO
            )
            == YES
        )

    def delete_recipe(self):
        recipe = self.selected_record(self.recipesTable, self.current_recipes)
        if recipe and self.confirm_delete(
            f"Удалить рецепт «{recipe['name']}»?"
        ):
            try:
                self.database.delete_recipe(recipe["id"])
                remove_unused_photo(self.database, recipe["image_path"])
            except sqlite3.Error as error:
                QMessageBox.warning(self, "Не удалось удалить", str(error))
                return
            self.data_changed()

    def delete_ingredient(self):
        ingredient = self.selected_record(
            self.ingredientsTable, self.ingredient_rows
        )
        if ingredient and self.confirm_delete(
            f"Удалить ингредиент «{ingredient['name']}»?"
        ):
            try:
                self.database.delete_ingredient(ingredient["id"])
            except (ValueError, sqlite3.Error) as error:
                QMessageBox.warning(self, "Не удалось удалить", str(error))
                return
            self.data_changed()

    def delete_stock(self):
        stock = self.selected_record(self.fridgeTable, self.stock_rows)
        if stock and self.confirm_delete(
            f"Убрать «{stock['name']}» из холодильника?"
        ):
            try:
                self.database.delete_stock(stock["ingredient_id"])
            except sqlite3.Error as error:
                QMessageBox.warning(self, "Не удалось удалить", str(error))
                return
            self.data_changed()

    def save_csv(self):
        if not self.current_recipes:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Экспорт рецептов", "recipes.csv", "CSV (*.csv)"
        )
        if filename:
            try:
                export_recipes(filename, self.current_recipes)
            except OSError as error:
                QMessageBox.warning(
                    self, "Не удалось сохранить файл", str(error)
                )

    def timer_status(self, text):
        self.timerStatusButton.setText("Таймер: " + text)

    def show_about(self):
        QMessageBox.information(
            self,
            "О программе",
            "Что приготовить?\nВерсия 0.3 — проверка по ТЗ и исправления.\n"
            "Папка пользовательских данных:\n" + self.database.directory,
        )

    def closeEvent(self, event):
        if self.closed:
            event.accept()
            return
        if (
            self.timer_window.active()
            and QMessageBox.question(
                self,
                "Работает таймер",
                "Остановить таймер и выйти?",
                YES | NO,
                NO,
            )
            != YES
        ):
            event.ignore()
            return
        for window in self.windows:
            if not window.close():
                event.ignore()
                return
        self.timer_window.timer.stop()
        self.database.close()
        self.closed = True
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("WhatToCook")
    try:
        window = MainWindow()
    except (OSError, ValueError, sqlite3.Error, KeyError, IndexError) as error:
        QMessageBox.critical(
            None,
            "Не удалось открыть данные",
            "Проверьте доступ к папке данных. Существующая база не заменена.\n"
            + str(error),
        )
        sys.exit(1)
    window.show()
    sys.exit(app.exec())
