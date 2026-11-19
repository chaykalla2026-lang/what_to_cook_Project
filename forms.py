"""Редакторы и дополнительные окна приложения."""

import math
import sqlite3
import time

from PyQt6 import uic
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from data_loader import CATEGORIES, NUTRIENTS, UNITS, project_file
from file_tools import (
    copy_photo,
    export_shopping,
    photo_filename,
    remove_unused_photo,
    show_photo,
    validate_photo,
)
from logic import calculate, number_text, recipe_values

YES = QMessageBox.StandardButton.Yes
NO = QMessageBox.StandardButton.No


def fill_table(table, rows):
    table.setRowCount(0)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(str(value)))
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setStretchLastSection(True)


def selected_row(table):
    items = table.selectedItems()
    return items[0].row() if items else -1


def nutrition_text(values):
    if values is None:
        return (
            "КБЖУ не рассчитано: заполните данные всех ингредиентов "
            "в справочнике."
        )
    return (
        f"{number_text(values['calories'], 1)} ккал; "
        f"белки {number_text(values['protein'])} г; "
        f"жиры {number_text(values['fat'])} г; "
        f"углеводы {number_text(values['carbs'])} г"
    )


class SimpleWindow(QWidget):
    def __init__(self, filename):
        super().__init__()
        uic.loadUi(project_file("ui", filename), self)
        self.closeButton.clicked.connect(self.close)


class EditorWindow(SimpleWindow):
    def __init__(self, filename):
        super().__init__(filename)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.initial_state = None
        self.saved = False

    def open_editor(self):
        self.saved = False
        self.initial_state = self.state()
        self.show()

    def warning(self, error):
        QMessageBox.warning(self, "Проверьте данные", str(error))

    def closeEvent(self, event):
        if (
            not self.saved
            and self.initial_state is not None
            and self.state() != self.initial_state
        ):
            answer = QMessageBox.question(
                self,
                "Несохранённые изменения",
                "Закрыть окно без сохранения?",
                YES | NO,
                NO,
            )
            if answer != YES:
                event.ignore()
                return
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


class IngredientEditor(EditorWindow):
    def __init__(self, database, on_change):
        super().__init__("ingredient_editor.ui")
        self.database, self.on_change = database, on_change
        self.ingredient_id = None
        self.unitCombo.currentTextChanged.connect(self.update_basis)
        self.knownCheck.toggled.connect(self.kbjuGroup.setEnabled)
        self.saveButton.clicked.connect(self.save)

    def update_basis(self, unit):
        self.basisLabel.setText(
            "КБЖУ "
            + {"г": "на 100 г", "мл": "на 100 мл", "шт": "на 1 штуку"}[unit]
        )

    def state(self):
        return (
            self.nameEdit.text(),
            self.unitCombo.currentText(),
            self.knownCheck.isChecked(),
            self.caloriesEdit.text(),
            self.proteinEdit.text(),
            self.fatEdit.text(),
            self.carbsEdit.text(),
        )

    def show_ingredient(self, ingredient=None):
        self.ingredient_id = ingredient["id"] if ingredient else None
        self.nameEdit.setText(ingredient["name"] if ingredient else "")
        self.unitCombo.setCurrentIndex(
            UNITS.index(ingredient["unit"]) if ingredient else 0
        )
        self.unitCombo.setEnabled(ingredient is None)
        known = ingredient is not None and ingredient["calories"] is not None
        self.knownCheck.setChecked(known)
        self.kbjuGroup.setEnabled(known)
        for key, field in zip(
            NUTRIENTS,
            [
                self.caloriesEdit,
                self.proteinEdit,
                self.fatEdit,
                self.carbsEdit,
            ],
        ):
            field.setText(number_text(ingredient[key]) if known else "")
        self.open_editor()

    def save(self):
        values = {
            "name": self.nameEdit.text(),
            "unit": self.unitCombo.currentText(),
        }
        for key, field in zip(
            NUTRIENTS,
            [
                self.caloriesEdit,
                self.proteinEdit,
                self.fatEdit,
                self.carbsEdit,
            ],
        ):
            values[key] = field.text() if self.knownCheck.isChecked() else None
        try:
            ingredient_id = self.database.save_ingredient(
                values, self.ingredient_id
            )
        except (ValueError, sqlite3.Error) as error:
            self.warning(error)
            return
        self.saved = True
        self.close()
        self.on_change(ingredient_id=ingredient_id)


class RecipeEditor(EditorWindow):
    def __init__(self, database, on_change):
        super().__init__("recipe_editor.ui")
        self.database, self.on_change = database, on_change
        self.categoryCombo.addItems(CATEGORIES)
        self.recipe_id = None
        self.composition = []
        self.existing_photo = None
        self.pending_photo = None
        self.ingredients = []
        self.ingredientCombo.currentIndexChanged.connect(
            self.update_amount_unit
        )
        self.addRowButton.clicked.connect(self.add_ingredient)
        self.removeRowButton.clicked.connect(self.remove_ingredient)
        self.editAmountButton.clicked.connect(self.change_amount)
        self.ingredientsTable.cellDoubleClicked.connect(self.change_amount)
        self.saveButton.clicked.connect(self.save)
        self.choosePhotoButton.clicked.connect(self.choose_photo)
        self.removePhotoButton.clicked.connect(self.remove_photo)

    def state(self):
        return (
            self.nameEdit.text(),
            self.categoryCombo.currentText(),
            self.minutesEdit.text(),
            self.portionsSpin.value(),
            self.instructionsEdit.toPlainText(),
            self.existing_photo,
            self.pending_photo,
            tuple(
                (row["ingredient_id"], str(row["quantity"]))
                for row in self.composition
            ),
        )

    def refresh_ingredients(self, preferred_id=None):
        current = self.ingredientCombo.currentIndex()
        selected = (
            self.ingredients[current]["id"]
            if 0 <= current < len(self.ingredients)
            else None
        )
        self.ingredients = self.database.ingredients()
        self.ingredientCombo.clear()
        self.ingredientCombo.addItems(
            [row["name"] for row in self.ingredients]
        )
        ids = [row["id"] for row in self.ingredients]
        wanted = preferred_id if preferred_id is not None else selected
        if wanted in ids:
            self.ingredientCombo.setCurrentIndex(ids.index(wanted))
        self.addRowButton.setEnabled(bool(self.ingredients))
        self.update_amount_unit()
        self.draw_composition()

    def update_amount_unit(self):
        index = self.ingredientCombo.currentIndex()
        unit = (
            self.ingredients[index]["unit"]
            if 0 <= index < len(self.ingredients)
            else "—"
        )
        self.amountUnitLabel.setText(unit)

    def draw_composition(self):
        ingredients = {row["id"]: row for row in self.database.ingredients()}
        fill_table(
            self.ingredientsTable,
            [
                [
                    ingredients[row["ingredient_id"]]["name"],
                    number_text(row["quantity"]),
                    ingredients[row["ingredient_id"]]["unit"],
                ]
                for row in self.composition
                if row["ingredient_id"] in ingredients
            ],
        )

    def show_recipe(self, recipe=None):
        self.recipe_id = recipe["id"] if recipe else None
        self.nameEdit.setText(recipe["name"] if recipe else "")
        self.instructionsEdit.setPlainText(
            recipe["instructions"] if recipe else ""
        )
        self.minutesEdit.setText(
            str(recipe["cooking_minutes"]) if recipe else ""
        )
        self.portionsSpin.setValue(recipe["base_portions"] if recipe else 2)
        self.categoryCombo.setCurrentIndex(
            CATEGORIES.index(recipe["category"]) if recipe else 5
        )
        self.composition = (
            [
                {
                    "ingredient_id": row["ingredient_id"],
                    "quantity": row["quantity"],
                }
                for row in self.database.composition(self.recipe_id)
            ]
            if recipe
            else []
        )
        self.existing_photo = recipe["image_path"] if recipe else None
        self.pending_photo = None
        self.refresh_ingredients()
        self.update_photo()
        self.setWindowTitle(
            "Редактирование рецепта" if recipe else "Новый рецепт"
        )
        self.open_editor()

    def add_ingredient(self):
        index = self.ingredientCombo.currentIndex()
        if index < 0:
            self.warning("Сначала добавьте ингредиент в справочник.")
            return
        ingredient_id = self.ingredients[index]["id"]
        if any(
            row["ingredient_id"] == ingredient_id for row in self.composition
        ):
            self.warning(
                "Ингредиент уже добавлен. "
                "Выберите строку и измените количество."
            )
            return
        if len(self.composition) >= 50:
            self.warning("В рецепте может быть не более 50 ингредиентов.")
            return
        self.composition.append(
            {
                "ingredient_id": ingredient_id,
                "quantity": self.amountSpin.value(),
            }
        )
        self.draw_composition()

    def change_amount(self):
        index = selected_row(self.ingredientsTable)
        if index < 0:
            return
        value, accepted = QInputDialog.getDouble(
            self,
            "Количество",
            "Новое количество:",
            float(self.composition[index]["quantity"]),
            0.01,
            999999.99,
            2,
        )
        if accepted:
            self.composition[index]["quantity"] = value
            self.draw_composition()

    def remove_ingredient(self):
        index = selected_row(self.ingredientsTable)
        if index >= 0:
            self.composition.pop(index)
            self.draw_composition()

    def choose_photo(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Фотография блюда", "", "Изображения (*.png *.jpg *.jpeg)"
        )
        if filename:
            try:
                validate_photo(filename)
            except (OSError, ValueError) as error:
                self.warning(error)
                return
            self.pending_photo = filename
            self.update_photo()

    def remove_photo(self):
        self.pending_photo = None
        self.existing_photo = None
        self.update_photo()

    def update_photo(self):
        show_photo(
            self.editorPhotoGroupLabel,
            self.pending_photo
            or photo_filename(self.database, self.existing_photo),
        )

    def save(self):
        values = {
            "name": self.nameEdit.text(),
            "category": self.categoryCombo.currentText(),
            "instructions": self.instructionsEdit.toPlainText(),
            "base_portions": self.portionsSpin.value(),
            "cooking_minutes": self.minutesEdit.text(),
            "image_path": self.existing_photo,
        }
        created_photo = None
        old_recipe = (
            self.database.recipe(self.recipe_id) if self.recipe_id else None
        )
        old_photo = old_recipe["image_path"] if old_recipe else None
        try:
            recipe_values(values, self.composition)
            if self.pending_photo:
                created_photo = copy_photo(self.database, self.pending_photo)
                values["image_path"] = created_photo
            self.database.save_recipe(values, self.composition, self.recipe_id)
        except (ValueError, OSError, sqlite3.Error) as error:
            remove_unused_photo(self.database, created_photo)
            self.warning(error)
            return
        remove_unused_photo(self.database, old_photo)
        self.saved = True
        self.close()
        self.on_change()


class StockEditor(EditorWindow):
    def __init__(self, database, on_change):
        super().__init__("stock_editor.ui")
        self.database, self.on_change = database, on_change
        self.ingredients = []
        self.ingredient_id = None
        self.ingredientCombo.currentIndexChanged.connect(self.update_unit)
        self.saveButton.clicked.connect(self.save)

    def state(self):
        return (self.ingredientCombo.currentText(), self.quantitySpin.value())

    def refresh_ingredients(self, preferred_id=None):
        if self.ingredient_id is not None:
            rows = [self.database.ingredient(self.ingredient_id)]
            self.ingredients = [row for row in rows if row]
        else:
            self.ingredients = self.database.ingredients()
        self.ingredientCombo.clear()
        self.ingredientCombo.addItems(
            [row["name"] for row in self.ingredients]
        )
        ids = [row["id"] for row in self.ingredients]
        if preferred_id in ids and self.ingredient_id is None:
            self.ingredientCombo.setCurrentIndex(ids.index(preferred_id))
        self.saveButton.setEnabled(bool(self.ingredients))
        self.update_unit()

    def update_unit(self):
        index = self.ingredientCombo.currentIndex()
        self.unitLabel.setText(
            self.ingredients[index]["unit"]
            if 0 <= index < len(self.ingredients)
            else "—"
        )

    def show_stock(self, stock=None):
        self.ingredient_id = stock["ingredient_id"] if stock else None
        self.refresh_ingredients()
        self.ingredientCombo.setEnabled(stock is None)
        self.quantitySpin.setValue(stock["quantity"] if stock else 0)
        self.open_editor()

    def save(self):
        index = self.ingredientCombo.currentIndex()
        if index < 0:
            self.warning("Сначала создайте ингредиент в справочнике.")
            return
        ingredient_id = self.ingredients[index]["id"]
        existing = self.database.stocks().get(ingredient_id)
        if self.ingredient_id is None and existing is not None:
            answer = QMessageBox.question(
                self,
                "Запас уже существует",
                f"Сейчас имеется {number_text(existing)} "
                f"{self.unitLabel.text()}. "
                "Заменить количество новым?",
                YES | NO,
                NO,
            )
            if answer != YES:
                return
        try:
            self.database.save_stock(ingredient_id, self.quantitySpin.value())
        except (ValueError, sqlite3.Error) as error:
            self.warning(error)
            return
        self.saved = True
        self.close()
        self.on_change()


class SettingsWindow(EditorWindow):
    def __init__(self, database, on_change):
        super().__init__("settings.ui")
        self.database, self.on_change = database, on_change
        self.saveButton.clicked.connect(self.save)

    def state(self):
        return self.personsSpin.value()

    def open_settings(self):
        self.personsSpin.setValue(self.database.persons())
        self.open_editor()

    def save(self):
        try:
            self.database.save_persons(self.personsSpin.value())
        except (ValueError, sqlite3.Error) as error:
            self.warning(error)
            return
        self.saved = True
        self.close()
        self.on_change()


class RecipeCard(SimpleWindow):
    def __init__(self, database, on_change):
        super().__init__("recipe_card.ui")
        self.database, self.on_change = database, on_change
        self.recipe_id = None
        self.personsSpin.valueChanged.connect(self.refresh)
        self.favoriteButton.clicked.connect(self.toggle_favorite)
        self.shoppingButton.clicked.connect(self.save_shopping)

    def show_recipe(self, recipe, persons):
        self.recipe_id = recipe["id"]
        self.personsSpin.setValue(persons)
        self.refresh()
        self.show()

    def refresh(self):
        recipe = self.database.recipe(self.recipe_id)
        if not recipe:
            self.close()
            return
        self.nameLabel.setText(recipe["name"])
        self.categoryLabel.setText(recipe["category"])
        self.detailsLabel.setText(
            f"Время: {recipe['cooking_minutes']} мин. "
            f"Базовые порции: {recipe['base_portions']}"
        )
        self.instructionsBrowser.setPlainText(recipe["instructions"])
        self.favoriteButton.setText(
            "Убрать из избранного" if recipe["is_favorite"] else "В избранное"
        )
        result = calculate(
            recipe,
            self.database.composition(self.recipe_id),
            self.database.stocks(),
            self.personsSpin.value(),
        )
        fill_table(
            self.ingredientsTable,
            [
                [
                    row["name"],
                    number_text(row["required"]),
                    number_text(row["available"]),
                    number_text(row["missing"]),
                    row["unit"],
                ]
                for row in result["rows"]
            ],
        )
        self.nutritionLabel.setText(
            "На одну порцию: "
            + nutrition_text(result["per_portion"])
            + "\nНа выбранное число персон: "
            + nutrition_text(result["selected"])
        )
        show_photo(
            self.photoGroupLabel,
            photo_filename(self.database, recipe["image_path"]),
        )

    def toggle_favorite(self):
        recipe = self.database.recipe(self.recipe_id)
        if recipe:
            try:
                self.database.set_favorite(
                    self.recipe_id, not recipe["is_favorite"]
                )
            except sqlite3.Error as error:
                QMessageBox.warning(self, "Не удалось сохранить", str(error))
                return
            self.on_change(favorite_only=True)

    def save_shopping(self):
        recipe = self.database.recipe(self.recipe_id)
        if not recipe:
            return
        result = calculate(
            recipe,
            self.database.composition(self.recipe_id),
            self.database.stocks(),
            self.personsSpin.value(),
        )
        if result["missing_count"] == 0:
            QMessageBox.information(
                self, "Список покупок", "Все продукты есть дома."
            )
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Список покупок", "shopping_list.txt", "Текст (*.txt)"
        )
        if filename:
            try:
                export_shopping(
                    filename, recipe, self.personsSpin.value(), result
                )
            except OSError as error:
                QMessageBox.warning(
                    self, "Не удалось сохранить файл", str(error)
                )


class TimerWindow(SimpleWindow):
    def __init__(self, on_tick):
        super().__init__("timer.ui")
        self.on_tick = on_tick
        self.state = "idle"
        self.remaining = 600
        self.deadline = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.startButton.clicked.connect(self.start)
        self.pauseButton.clicked.connect(self.pause)
        self.resetButton.clicked.connect(self.reset)
        self.durationSpin.valueChanged.connect(self.duration_changed)
        self.update_view()

    def active(self):
        return self.state in ["running", "paused"]

    def duration_changed(self):
        if not self.active():
            self.remaining = self.durationSpin.value() * 60
            self.update_view()

    def start(self):
        if self.state == "running":
            return
        self.remaining = self.durationSpin.value() * 60
        self.deadline = time.monotonic() + self.remaining
        self.state = "running"
        self.timer.start(200)
        self.update_view()

    def pause(self):
        if self.state == "running":
            self.remaining = max(0, self.deadline - time.monotonic())
            if self.remaining <= 0:
                self.tick()
                return
            self.timer.stop()
            self.state = "paused"
        elif self.state == "paused":
            self.deadline = time.monotonic() + self.remaining
            self.state = "running"
            self.timer.start(200)
        self.update_view()

    def reset(self):
        self.timer.stop()
        self.state = "idle"
        self.remaining = self.durationSpin.value() * 60
        self.update_view()

    def tick(self):
        if self.state != "running":
            return
        self.remaining = max(0, self.deadline - time.monotonic())
        if self.remaining <= 0:
            self.timer.stop()
            self.state = "finished"
            self.update_view()
            QMessageBox.information(
                self, "Таймер", "Время приготовления истекло."
            )
        else:
            self.update_view()

    def update_view(self):
        seconds = math.ceil(self.remaining)
        text = f"{seconds // 60:02}:{seconds % 60:02}"
        self.timeDisplay.display(text)
        self.durationSpin.setEnabled(not self.active())
        self.startButton.setEnabled(not self.active())
        self.pauseButton.setEnabled(self.active())
        self.pauseButton.setText(
            "Продолжить" if self.state == "paused" else "Пауза"
        )
        self.on_tick(text + (" (пауза)" if self.state == "paused" else ""))


class HelpWindow(SimpleWindow):
    def __init__(self):
        super().__init__("help.ui")
        with open(project_file("data", "help.txt"), encoding="utf-8") as file:
            self.helpBrowser.setPlainText(file.read())
