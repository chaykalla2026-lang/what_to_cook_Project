"""Небольшие формы черновика. Сохранение и расчёты пока не подключены."""

from PyQt6 import uic
from PyQt6.QtWidgets import QHeaderView, QTableWidgetItem, QWidget

from data_loader import CATEGORIES, find_record, project_file


def fill_table(table, rows):
    table.setRowCount(len(rows))
    for row_number, row in enumerate(rows):
        for column_number, value in enumerate(row):
            table.setItem(row_number, column_number, QTableWidgetItem(str(value)))
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setStretchLastSection(True)


def ingredient_rows(data, recipe_id):
    rows = []
    for link in data['recipe_ingredients']:
        if link['recipe_id'] == recipe_id:
            ingredient = find_record(data['ingredients'], link['ingredient_id'])
            if ingredient:
                rows.append([ingredient['name'], link['quantity'],
                             ingredient['unit']])
    return rows


class DraftWindow(QWidget):
    def __init__(self, filename):
        super().__init__()
        uic.loadUi(project_file('ui', filename), self)
        self.closeButton.clicked.connect(self.close)


class RecipeCard(DraftWindow):
    def __init__(self, data):
        super().__init__('recipe_card.ui')
        self.data = data
        self.recipe_id = None

    def show_recipe(self, recipe, persons):
        self.recipe_id = recipe['id']
        self.nameLabel.setText(recipe['name'])
        self.categoryLabel.setText(recipe['category'])
        self.detailsLabel.setText(
            f"Время: {recipe['cooking_minutes']} мин. "
            f"Базовые порции: {recipe['base_portions']}"
        )
        self.personsSpin.setValue(persons)
        self.instructionsBrowser.setPlainText(recipe['instructions'])
        rows = []
        for name, quantity, unit in ingredient_rows(self.data, recipe['id']):
            # Потребность и нехватка появятся вместе с алгоритмом подбора.
            rows.append([name, '—', '—', '—', unit])
        fill_table(self.ingredientsTable, rows)
        self.show()


class RecipeEditor(DraftWindow):
    def __init__(self, data):
        super().__init__('recipe_editor.ui')
        self.data = data
        self.categoryCombo.addItems(CATEGORIES)

    def show_recipe(self, recipe=None):
        self.nameEdit.setText(recipe['name'] if recipe else '')
        self.instructionsEdit.setPlainText(recipe['instructions'] if recipe else '')
        self.minutesEdit.setText(recipe['cooking_minutes'] if recipe else '')
        self.portionsSpin.setValue(int(recipe['base_portions']) if recipe else 2)
        category = recipe['category'] if recipe else 'Другое'
        self.categoryCombo.setCurrentIndex(CATEGORIES.index(category))
        rows = ingredient_rows(self.data, recipe['id']) if recipe else []
        fill_table(self.ingredientsTable, rows)
        self.setWindowTitle('Редактирование рецепта' if recipe else 'Новый рецепт')
        self.show()


class IngredientEditor(DraftWindow):
    def __init__(self):
        super().__init__('ingredient_editor.ui')
        self.unitCombo.currentTextChanged.connect(self.update_basis)
        self.knownCheck.clicked.connect(self.kbjuGroup.setEnabled)
        self.update_basis('г')

    def update_basis(self, unit):
        bases = {'г': 'на 100 г', 'мл': 'на 100 мл', 'шт': 'на 1 штуку'}
        self.basisLabel.setText('КБЖУ ' + bases[unit])

    def show_ingredient(self, ingredient=None):
        self.nameEdit.setText(ingredient['name'] if ingredient else '')
        unit = ingredient['unit'] if ingredient else 'г'
        self.unitCombo.setCurrentIndex(['г', 'мл', 'шт'].index(unit))
        self.unitCombo.setEnabled(ingredient is None)
        known = bool(ingredient and ingredient['calories'] != '')
        self.knownCheck.setChecked(known)
        self.kbjuGroup.setEnabled(known)
        for key, field in [('calories', self.caloriesEdit),
                           ('protein', self.proteinEdit), ('fat', self.fatEdit),
                           ('carbs', self.carbsEdit)]:
            field.setText(ingredient[key] if ingredient else '')
        self.show()


class StockEditor(DraftWindow):
    def __init__(self, data):
        super().__init__('stock_editor.ui')
        self.data = data
        self.ingredientCombo.currentTextChanged.connect(self.update_unit)

    def update_unit(self, name):
        for ingredient in self.data['ingredients']:
            if ingredient['name'] == name:
                self.unitLabel.setText(ingredient['unit'])
                return
        self.unitLabel.setText('—')

    def show_stock(self, stock=None):
        self.ingredientCombo.clear()
        if stock:
            ingredient = find_record(self.data['ingredients'], stock['ingredient_id'])
            self.ingredientCombo.addItems([ingredient['name']])
        else:
            self.ingredientCombo.addItems([
                ingredient['name'] for ingredient in self.data['ingredients']
            ])
        self.ingredientCombo.setEnabled(stock is None)
        self.quantitySpin.setValue(float(stock['quantity']) if stock else 0)
        self.show()


class SettingsWindow(DraftWindow):
    def __init__(self, persons):
        super().__init__('settings.ui')
        self.personsSpin.setValue(persons)


class TimerWindow(DraftWindow):
    def __init__(self):
        super().__init__('timer.ui')
        self.timeDisplay.display('10:00')


class HelpWindow(DraftWindow):
    def __init__(self):
        super().__init__('help.ui')
        with open(project_file('data', 'help.txt'), encoding='utf-8') as file:
            self.helpBrowser.setPlainText(file.read())
