"""Главное окно: вкладки, просмотр CSV и переходы между формами."""

import sys

from PyQt6 import uic
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox

from data_loader import CATEGORIES, find_record, load_data, project_file
from forms import (HelpWindow, IngredientEditor, RecipeCard, RecipeEditor,
                   SettingsWindow, StockEditor, TimerWindow, fill_table)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi(project_file('ui', 'main_window.ui'), self)
        self.data = load_data()
        settings = self.data['app_settings']
        self.persons = int(settings[0]['preferred_servings']) if settings else 2
        self.categoryCombo.addItems(['Все'] + CATEGORIES)
        self.personsSpin.setValue(self.persons)

        # Ссылки на формы хранятся в главном окне, как в первом уроке.
        self.recipe_card = RecipeCard(self.data)
        self.recipe_editor = RecipeEditor(self.data)
        self.ingredient_editor = IngredientEditor()
        self.stock_editor = StockEditor(self.data)
        self.settings_window = SettingsWindow(self.persons)
        self.timer_window = TimerWindow()
        self.help_window = HelpWindow()
        self.windows = [self.recipe_card, self.recipe_editor,
                        self.ingredient_editor, self.stock_editor,
                        self.settings_window, self.timer_window,
                        self.help_window]
        self.connect_buttons()
        self.fill_tables()
        self.update_buttons()
        self.statusBar().showMessage('Черновой интерфейс. Таймер: не запущен')

    def connect_buttons(self):
        self.addRecipeButton.clicked.connect(self.new_recipe)
        self.openRecipeButton.clicked.connect(self.open_recipe)
        self.editRecipeButton.clicked.connect(self.edit_recipe)
        self.addIngredientButton.clicked.connect(self.new_ingredient)
        self.editIngredientButton.clicked.connect(self.edit_ingredient)
        self.addStockButton.clicked.connect(self.new_stock)
        self.editStockButton.clicked.connect(self.edit_stock)
        self.recipesTable.clicked.connect(self.update_buttons)
        self.ingredientsTable.clicked.connect(self.update_buttons)
        self.fridgeTable.clicked.connect(self.update_buttons)
        self.recipe_card.editButton.clicked.connect(self.edit_open_recipe)
        self.recipe_card.timerButton.clicked.connect(self.timer_window.show)
        self.recipe_editor.newIngredientButton.clicked.connect(self.new_ingredient)
        self.stock_editor.newIngredientButton.clicked.connect(self.new_ingredient)
        self.actionNewRecipe.triggered.connect(self.new_recipe)
        self.actionExit.triggered.connect(self.close)
        self.actionSettings.triggered.connect(self.settings_window.show)
        self.actionTimer.triggered.connect(self.timer_window.show)
        self.actionHelp.triggered.connect(self.help_window.show)
        self.actionAbout.triggered.connect(self.show_about)

    def fill_tables(self):
        recipe_rows = []
        for recipe in self.data['recipes']:
            recipe_rows.append([
                recipe['name'], recipe['category'], recipe['cooking_minutes'],
                recipe['base_portions'], '—', '—', '—', '—',
                'Да' if recipe['is_favorite'] == '1' else 'Нет'
            ])
        fill_table(self.recipesTable, recipe_rows)
        ingredient_rows = []
        for ingredient in self.data['ingredients']:
            unit = ingredient['unit']
            basis = 'на 1 шт' if unit == 'шт' else 'на 100 ' + unit
            ingredient_rows.append([
                ingredient['name'], unit, basis,
                ingredient['calories'] or '—', ingredient['protein'] or '—',
                ingredient['fat'] or '—', ingredient['carbs'] or '—'
            ])
        fill_table(self.ingredientsTable, ingredient_rows)
        fridge_rows = []
        for stock in self.data['fridge']:
            ingredient = find_record(self.data['ingredients'], stock['ingredient_id'])
            if ingredient:
                fridge_rows.append([
                    ingredient['name'], stock['quantity'], ingredient['unit']
                ])
        fill_table(self.fridgeTable, fridge_rows)

    def update_buttons(self):
        recipe_selected = bool(self.recipesTable.selectedItems())
        self.openRecipeButton.setEnabled(recipe_selected)
        self.editRecipeButton.setEnabled(recipe_selected)
        self.editIngredientButton.setEnabled(
            bool(self.ingredientsTable.selectedItems())
        )
        self.editStockButton.setEnabled(bool(self.fridgeTable.selectedItems()))

    def selected_record(self, table, name):
        items = table.selectedItems()
        if items:
            return self.data[name][items[0].row()]
        return None

    def new_recipe(self):
        self.recipe_editor.show_recipe()

    def open_recipe(self):
        recipe = self.selected_record(self.recipesTable, 'recipes')
        if recipe:
            self.recipe_card.show_recipe(recipe, self.persons)

    def edit_recipe(self):
        recipe = self.selected_record(self.recipesTable, 'recipes')
        if recipe:
            self.recipe_editor.show_recipe(recipe)

    def edit_open_recipe(self):
        recipe = find_record(self.data['recipes'], self.recipe_card.recipe_id)
        if recipe:
            self.recipe_editor.show_recipe(recipe)

    def new_ingredient(self):
        self.ingredient_editor.show_ingredient()

    def edit_ingredient(self):
        ingredient = self.selected_record(self.ingredientsTable, 'ingredients')
        if ingredient:
            self.ingredient_editor.show_ingredient(ingredient)

    def new_stock(self):
        self.stock_editor.show_stock()

    def edit_stock(self):
        stock = self.selected_record(self.fridgeTable, 'fridge')
        if stock:
            self.stock_editor.show_stock(stock)

    def show_about(self):
        QMessageBox.information(
            self, 'О программе',
            'Что приготовить?\nУчебный проект на PyQt6.\nЧерновой интерфейс.'
        )

    def closeEvent(self, event):
        for window in self.windows:
            window.close()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except (OSError, ValueError, KeyError, IndexError) as error:
        QMessageBox.critical(None, 'Не удалось открыть примеры',
                             f'Проверьте файлы в папке data.\n{error}')
        sys.exit(1)
    window.show()
    sys.exit(app.exec())
