"""Приёмочные примеры ТЗ и проверки исправлений от 24 ноября."""

# ruff: noqa: E402 -- Qt настраивается до импорта виджетов.
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import csv
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QMessageBox,
)

from data_loader import NUTRIENTS
from database import Database
from file_tools import export_recipes, photo_filename, validate_photo
from forms import YES
from logic import calculate, checked_number, number_text, sort_recipes
from main import MainWindow


class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.warning_patch = patch.object(QMessageBox, "warning")
        self.info_patch = patch.object(QMessageBox, "information")
        self.question_patch = patch.object(
            QMessageBox, "question", return_value=YES
        )
        self.warning = self.warning_patch.start()
        self.info = self.info_patch.start()
        self.question_patch.start()
        self.w = MainWindow(str(self.path / "recipes.sqlite3"))
        self.w.show()
        self.app.processEvents()
        self.db = self.w.database

    def tearDown(self):
        self.w.close()
        self.app.processEvents()
        self.warning_patch.stop()
        self.info_patch.stop()
        self.question_patch.stop()
        self.temp.cleanup()

    def ingredient(self, name="Продукт", unit="г", numbers=(100, 2, 3, 4)):
        values = dict(name=name, unit=unit)
        values.update(zip(NUTRIENTS, numbers or [None] * 4))
        return self.db.save_ingredient(values)

    def recipe(self, items, name="Рецепт", portions=2, minutes=40):
        rid = self.db.save_recipe(
            dict(
                name=name,
                category="Другое",
                instructions="Приготовить.",
                base_portions=portions,
                cooking_minutes=minutes,
            ),
            [dict(ingredient_id=item, quantity=qty) for item, qty in items],
        )
        self.w.data_changed()
        return rid

    def result(self, rid, persons=2, stocks=None):
        return calculate(
            self.db.recipe(rid),
            self.db.composition(rid),
            self.db.stocks() if stocks is None else stocks,
            persons,
        )

    def image(self, name):
        path = str(self.path / name)
        pixmap = QPixmap(60, 40)
        pixmap.fill(Qt.GlobalColor.green)
        self.assertTrue(pixmap.save(path))
        return path

    def test_tc01_tc02_blank_known_nutrition_and_field_errors(self):
        self.ingredient("Мука")
        editor = self.w.ingredient_editor
        editor.show_ingredient()
        editor.nameEdit.setText("  мУка ")
        editor.saveButton.click()
        self.assertEqual(len(self.db.ingredients()), 1)
        self.assertIn("Мука", editor.nameError.text())
        editor.nameEdit.setText("Другой продукт")
        editor.knownCheck.setChecked(True)
        editor.saveButton.click()
        self.assertTrue(editor.isVisible())
        self.assertEqual(len(self.db.ingredients()), 1)
        self.assertTrue(editor.caloriesEdit.styleSheet())
        self.assertFalse(editor.caloriesError.isHidden())
        editor.caloriesEdit.setText("100")
        editor.proteinEdit.setText("2")
        editor.fatEdit.setText("3")
        editor.saveButton.click()
        self.assertIn("углеводы", editor.carbsError.text())
        self.assertEqual(editor.caloriesEdit.text(), "100")
        editor.carbsEdit.setText("4")
        editor.saveButton.click()
        self.assertFalse(editor.isVisible())
        editor.show_ingredient()
        self.assertFalse(editor.nameEdit.styleSheet())
        self.assertTrue(editor.nameError.isHidden())

    def test_tc03_recipe_defaults_and_empty_composition(self):
        self.w.new_recipe()
        editor = self.w.recipe_editor
        self.assertEqual(editor.categoryCombo.currentText(), "Другое")
        self.assertEqual(editor.minutesEdit.text(), "")
        self.assertEqual(editor.portionsSpin.value(), 2)
        editor.nameEdit.setText("Без состава")
        editor.instructionsEdit.setPlainText("Приготовить.")
        editor.minutesEdit.setText("20")
        editor.saveButton.click()
        self.assertEqual(self.db.recipes(), [])
        self.assertIn("ингредиентов", editor.compositionError.text())
        self.assertTrue(editor.isVisible())

    def test_tc04_tc05_tc28_photo_copy_replace_invalid_and_missing(self):
        item = self.ingredient()
        rid = self.recipe([(item, 200)])
        editor = self.w.recipe_editor
        editor.show_recipe(self.db.recipe(rid))
        original = self.image("first.png")
        with patch.object(
            QFileDialog, "getOpenFileName", return_value=(original, "")
        ):
            editor.choosePhotoButton.click()
        editor.saveButton.click()
        first = self.db.recipe(rid)["image_path"]
        Path(original).unlink()
        self.w.recipe_card.show_recipe(self.db.recipe(rid), 2)
        self.assertFalse(self.w.recipe_card.photoGroupLabel.pixmap().isNull())
        editor.show_recipe(self.db.recipe(rid))
        broken = self.path / "broken.jpg"
        broken.write_text("Это не фотография", encoding="utf-8")
        with patch.object(
            QFileDialog, "getOpenFileName", return_value=(str(broken), "")
        ):
            editor.choosePhotoButton.click()
        self.assertEqual(editor.existing_photo, first)
        self.assertTrue(editor.isVisible())
        self.assertIn("изображение", editor.photoError.text())
        editor.saveButton.click()
        self.assertEqual(self.db.recipe(rid)["image_path"], first)
        editor.show_recipe(self.db.recipe(rid))
        second_file = self.image("second.png")
        with patch.object(
            QFileDialog, "getOpenFileName", return_value=(second_file, "")
        ):
            editor.choosePhotoButton.click()
        editor.saveButton.click()
        second = self.db.recipe(rid)["image_path"]
        self.assertNotEqual(first, second)
        self.assertFalse(Path(photo_filename(self.db, first)).exists())
        self.assertEqual(len(self.db.recipes()), 1)
        Path(photo_filename(self.db, second)).unlink()
        self.w.recipe_card.refresh()
        self.assertIn("недоступна", self.w.recipe_card.photoGroupLabel.text())

    def test_tc06_quantities_dot_comma_and_invalid_input(self):
        item = self.ingredient()
        editor = self.w.stock_editor
        for text in ["1.25", "1,25"]:
            editor.show_stock()
            editor.quantityEdit.setText(text)
            editor.saveButton.click()
            self.assertEqual(self.db.stocks()[item], 1.25)
        for text in ["-2", "0.001", "1.234", "1000000", "NaN", "1 000"]:
            with self.subTest(text=text):
                editor.show_stock()
                editor.quantityEdit.setText(text)
                editor.saveButton.click()
                self.assertTrue(editor.isVisible())
                self.assertEqual(editor.quantityEdit.text(), text)
                self.assertEqual(self.db.stocks()[item], 1.25)
                self.assertTrue(editor.quantityEdit.styleSheet())
        editor.quantityEdit.setText("200")
        editor.saveButton.click()
        self.assertEqual(self.db.stocks()[item], 200)
        self.assertEqual(len(self.db.fridge()), 1)

    def test_tc07_tc29_favorite_and_preference_after_restart(self):
        item = self.ingredient()
        rid = self.recipe([(item, 200)])
        card = self.w.recipe_card
        card.show_recipe(self.db.recipe(rid), 2)
        card.favoriteButton.click()
        editor = self.w.recipe_editor
        editor.show_recipe(self.db.recipe(rid))
        editor.instructionsEdit.setPlainText("Новая инструкция.")
        editor.saveButton.click()
        self.w.settings_window.open_settings()
        self.w.settings_window.personsSpin.setValue(3)
        self.w.settings_window.saveButton.click()
        self.assertEqual(card.personsSpin.value(), 2)
        self.w.close()
        self.w = MainWindow(str(self.path / "recipes.sqlite3"))
        self.db = self.w.database
        self.w.mainTabs.setCurrentIndex(3)
        self.assertEqual(self.w.personsSpin.value(), 3)
        self.w.recipe_card.show_recipe(self.db.recipe(rid), self.db.persons())
        self.assertEqual(self.w.recipe_card.personsSpin.value(), 3)
        self.assertEqual(self.db.recipe(rid)["is_favorite"], 1)
        self.assertEqual(self.db.recipe(rid)["base_portions"], 2)

    def test_tc08_to_tc12_portions_pieces_and_shortages(self):
        item = self.ingredient()
        rid = self.recipe([(item, 400)], portions=4)
        for available, shortage in [(200, 0), (150, 50), (0, 200)]:
            with self.subTest(available=available):
                value = self.result(rid, stocks={item: available})
                self.assertEqual(value["rows"][0]["required"], 200)
                self.assertEqual(value["rows"][0]["missing"], shortage)
                self.assertEqual(value["missing_count"], int(shortage > 0))
        self.assertEqual(self.db.composition(rid)[0]["quantity"], 400)
        egg = self.ingredient("Яйцо", "шт")
        rid = self.recipe([(egg, 3)])
        self.assertEqual(
            self.result(rid, 1)["rows"][0]["required"], Decimal("1.50")
        )

    def test_tc13_time_boundary_in_catalog_and_picker(self):
        item = self.ingredient()
        self.recipe([(item, 100)], minutes=40)
        self.w.limitCheck.setChecked(True)
        self.w.selectionLimitCheck.setChecked(True)
        for limit, expected in [(40, 1), (39, 0)]:
            self.w.limitSpin.setValue(limit)
            self.w.selectionLimitSpin.setValue(limit)
            self.w.selectButton.click()
            self.assertEqual(len(self.w.current_recipes), expected)
            self.assertEqual(len(self.w.selection_rows), expected)

    def test_tc14_to_tc17_exact_nutrition_examples_and_rounding(self):
        examples = [
            ("г", (100, 2, 3, 4), 200, 2, (100, 2, 3, 4)),
            ("мл", (50, 1, 2, 3), 300, 3, (50, 1, 2, 3)),
            ("шт", (80, 6, 5, 1), 3, 2, (120, 9, 7.5, 1.5)),
        ]
        for unit, numbers, quantity, portions, expected in examples:
            with self.subTest(unit=unit):
                item = self.ingredient(unit, unit, numbers)
                rid = self.recipe([(item, quantity)], portions=portions)
                self.assertEqual(
                    list(self.result(rid)["per_portion"].values()),
                    [Decimal(str(x)) for x in expected],
                )
        item = self.ingredient("Малая потребность")
        rid = self.recipe([(item, 1)], portions=3)
        result = self.result(rid, 1, {item: 0.33})
        self.assertEqual(result["rows"][0]["required"], Decimal(".34"))
        self.assertEqual(result["rows"][0]["missing"], Decimal(".01"))
        self.assertEqual(number_text(Decimal("1.25"), 1), "1,3")

    def test_tc18_tc19_tc30_unknown_zero_and_all_nutrition_sorts(self):
        item = self.ingredient()
        unknown = self.ingredient("Неизвестно", numbers=None)
        zero = self.ingredient("Ноль", numbers=(0, 0, 0, 0))
        low = self.recipe([(item, 100)], "Мало", portions=1)
        high = self.recipe([(item, 200)], "Много", portions=1)
        missing = self.recipe([(item, 100), (unknown, 1)], "Нет КБЖУ")
        rid_zero = self.recipe([(zero, 1)], "Нулевой")
        views = self.db.recipe_views()
        for key in NUTRIENTS:
            self.assertEqual(
                [r["id"] for r in sort_recipes(views, key)],
                [rid_zero, low, high, missing],
            )
            self.assertEqual(
                [r["id"] for r in sort_recipes(views, key, True)],
                [high, low, rid_zero, missing],
            )
        self.assertIsNone(self.result(missing)["per_portion"])
        self.assertEqual(self.result(rid_zero)["per_portion"]["calories"], 0)
        row = [r["id"] for r in self.w.current_recipes].index(missing)
        self.assertIn(
            "не рассчитано", self.w.recipesTable.item(row, 4).toolTip()
        )

    def test_tc20_tc21_csv_filtered_order_and_escaping(self):
        item = self.ingredient()
        self.recipe([(item, 200)], 'Выбор; "Б"')
        self.recipe([(item, 100)], "Выбор А")
        self.recipe([(item, 50)], "Другое")
        self.w.recipeSearch.setText("ВЫБОР")
        self.w.recipeOrder.setCurrentIndex(1)
        path = self.path / "recipes.csv"
        export_recipes(str(path), self.w.current_recipes)
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.reader(file, delimiter=";"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(
            [row[1] for row in rows[1:]],
            [row["name"] for row in self.w.current_recipes],
        )
        self.assertTrue(all(len(row) == 10 for row in rows))

    def test_tc22_tc33_shopping_no_shortage_and_file_cancel_failure(self):
        item = self.ingredient()
        rid = self.recipe([(item, 200)])
        self.db.save_stock(item, 200)
        self.w.recipe_card.show_recipe(self.db.recipe(rid), 2)
        with patch.object(QFileDialog, "getSaveFileName") as dialog:
            self.w.recipe_card.shoppingButton.click()
            dialog.assert_not_called()
        self.assertIn("Все продукты есть", str(self.info.call_args))
        before = self.db.recipes()
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=("", "")
        ):
            self.w.exportButton.click()
        path = self.path / "existing.csv"
        path.write_text("Старый файл", encoding="utf-8")
        with (
            patch.object(
                QFileDialog, "getSaveFileName", return_value=(str(path), "")
            ),
            patch("file_tools.os.replace", side_effect=OSError("Нет доступа")),
        ):
            self.w.exportButton.click()
        self.assertEqual(path.read_text(encoding="utf-8"), "Старый файл")
        self.assertEqual(self.db.recipes(), before)
        self.assertTrue(self.warning.called)

    def test_tc23_to_tc25_timer_pauses_and_finishes_once(self):
        item = self.ingredient()
        rid = self.recipe([(item, 200)])
        self.w.recipe_card.show_recipe(self.db.recipe(rid), 2)
        timer = self.w.timer_window
        with patch("forms.time.monotonic", return_value=100):
            timer.startButton.click()
        self.w.recipe_card.close()
        self.assertTrue(timer.active())
        timer.close()
        self.w.timerStatusButton.click()
        self.assertTrue(timer.isVisible())
        with patch("forms.time.monotonic", return_value=125):
            timer.pauseButton.click()
        self.assertEqual(timer.remaining, 575)
        self.assertFalse(timer.timer.isActive())
        with patch("forms.time.monotonic", return_value=180):
            timer.tick()
        self.assertEqual(timer.remaining, 575)
        self.assertIn("пауза", self.w.timerStatusButton.text())
        with patch("forms.time.monotonic", return_value=200):
            timer.pauseButton.click()
        with patch("forms.time.monotonic", return_value=210):
            timer.tick()
        self.assertEqual(timer.remaining, 565)
        self.info.reset_mock()
        with patch("forms.time.monotonic", return_value=800):
            timer.tick()
            timer.tick()
        self.assertEqual(timer.remaining, 0)
        self.assertEqual(self.info.call_count, 1)
        timer.startButton.click()
        self.assertEqual(timer.remaining, 600)
        timer.resetButton.click()
        timer.durationSpin.setValue(180)
        self.assertIn("180:00", self.w.timerStatusButton.text())

    def test_tc26_tc27_many_to_many_and_stock_delete_guards(self):
        item = self.ingredient()
        a = self.recipe([(item, 200)], "А")
        b = self.recipe([(item, 300)], "Б")
        self.db.save_stock(item, 150)
        with self.assertRaises(ValueError):
            self.db.delete_ingredient(item)
        self.db.delete_recipe(a)
        self.assertIsNotNone(self.db.recipe(b))
        self.assertEqual(self.db.stocks()[item], 150)
        self.db.delete_recipe(b)
        with self.assertRaises(ValueError):
            self.db.delete_ingredient(item)
        self.db.delete_stock(item)
        self.assertIsNotNone(self.db.ingredient(item))

    def test_tc31_fill_unknown_updates_card_and_invalidates_picker(self):
        item = self.ingredient(numbers=None)
        rid = self.recipe([(item, 200)])
        self.w.recipe_card.show_recipe(self.db.recipe(rid), 2)
        self.w.selectButton.click()
        self.assertTrue(self.w.selection_valid)
        editor = self.w.ingredient_editor
        editor.show_ingredient(self.db.ingredient(item))
        editor.knownCheck.setChecked(True)
        for field, value in [
            (editor.caloriesEdit, "100"),
            (editor.proteinEdit, "2"),
            (editor.fatEdit, "3"),
            (editor.carbsEdit, "4"),
        ]:
            field.setText(value)
        editor.saveButton.click()
        self.assertIn("100,0 ккал", self.w.recipe_card.nutritionLabel.text())
        self.assertFalse(self.w.selection_valid)
        self.assertIn("Условия изменились", self.w.selectionHint.text())

    def test_tc32_failed_composition_save_rolls_back_and_keeps_draft(self):
        item = self.ingredient()
        rid = self.recipe([(item, 200)])
        old = self.db.recipe(rid)
        old_composition = self.db.composition(rid)
        self.db.connection.execute("""CREATE TRIGGER fail_recipe_save
            BEFORE INSERT ON recipe_ingredients
            BEGIN SELECT RAISE(ABORT, 'Проверка ошибки записи'); END""")
        editor = self.w.recipe_editor
        editor.show_recipe(old)
        editor.nameEdit.setText("Несохранённое новое имя")
        editor.composition[0]["quantity"] = 300
        editor.pending_photo = self.image("pending.png")
        editor.saveButton.click()
        self.assertTrue(editor.isVisible())
        self.assertEqual(editor.nameEdit.text(), "Несохранённое новое имя")
        self.assertEqual(self.db.recipe(rid), old)
        self.assertEqual(self.db.composition(rid), old_composition)
        self.assertEqual(list((self.path / "images").glob("*")), [])

    def test_ingredient_search_and_creation_preserves_recipe(self):
        self.ingredient("Мука")
        milk = self.ingredient("Молоко", "мл")
        self.w.new_recipe()
        editor = self.w.recipe_editor
        editor.nameEdit.setText("Черновик")
        editor.ingredientSearch.setText("МОЛО")
        self.assertEqual([row["id"] for row in editor.ingredients], [milk])
        self.assertEqual(editor.amountUnitLabel.text(), "мл")
        editor.ingredientSearch.setText("Несуществующий")
        self.assertFalse(editor.addRowButton.isEnabled())
        editor.newIngredientButton.click()
        ingredient = self.w.ingredient_editor
        ingredient.nameEdit.setText("Яйцо")
        ingredient.unitCombo.setCurrentIndex(2)
        ingredient.saveButton.click()
        self.assertEqual(editor.ingredientSearch.text(), "")
        self.assertEqual(editor.ingredientCombo.currentText(), "Яйцо")
        self.assertEqual(editor.nameEdit.text(), "Черновик")
        editor.amountEdit.setText("1.25")
        editor.addRowButton.click()
        self.assertEqual(editor.composition[0]["quantity"], 1.25)
        editor.ingredientsTable.selectRow(0)
        self.assertTrue(editor.removeRowButton.isEnabled())
        with patch.object(
            QInputDialog, "getText", return_value=("1,50", True)
        ):
            editor.editAmountButton.click()
        self.assertEqual(editor.composition[0]["quantity"], 1.5)
        editor.ingredientsTable.selectRow(0)
        with patch.object(
            QInputDialog, "getText", return_value=("1.234", True)
        ):
            editor.editAmountButton.click()
        self.assertEqual(editor.composition[0]["quantity"], 1.5)
        self.assertEqual(self.db.fridge(), [])

    def test_limits_large_results_and_precise_input(self):
        item = self.ingredient()
        rid = self.recipe([(item, 999999.99)], portions=1)
        value = self.result(rid, 20)["rows"][0]["required"]
        self.assertEqual(value, Decimal("19999999.80"))
        self.assertEqual(number_text(value), "19999999,80")
        for text in ["NaN", "Infinity", "-1", "1.234", "1000000"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                checked_number(text, "Количество")
        items = [(self.ingredient(f"Дополнение {i}"), 1) for i in range(50)]
        self.recipe(items)
        with self.assertRaises(ValueError):
            self.recipe(items + [(item, 1)])

    def test_minimum_size_table_width_and_empty_favorites(self):
        self.assertEqual(self.w.minimumWidth(), 1024)
        self.assertEqual(self.w.minimumHeight(), 700)
        self.w.favoritesCheck.setChecked(True)
        self.assertIn("В избранном пока нет", self.w.recipesHint.text())
        self.assertFalse(self.w.exportButton.isEnabled())
        header = self.w.recipesTable.horizontalHeader()
        self.assertEqual(
            header.sectionResizeMode(0), QHeaderView.ResizeMode.Interactive
        )

    def test_database_error_contains_path(self):
        path = self.path / "broken.sqlite3"
        path.write_bytes(b"broken database")
        with self.assertRaises(sqlite3.DatabaseError) as raised:
            Database(str(path))
        self.assertIn(str(path), str(raised.exception))
        self.assertEqual(path.read_bytes(), b"broken database")

    def test_text_numeric_and_photo_boundaries(self):
        item = self.ingredient("А" * 80)
        with self.assertRaises(ValueError):
            self.ingredient("Б" * 81)
        values = dict(
            name="А" * 100,
            category="Другое",
            instructions="А" * 10000,
            base_portions=20,
            cooking_minutes=1440,
        )
        composition = [dict(ingredient_id=item, quantity=0.01)]
        self.db.save_recipe(values, composition)
        invalid = [
            ("name", "А" * 101),
            ("instructions", "А" * 10001),
            ("base_portions", 0),
            ("base_portions", 21),
            ("cooking_minutes", 0),
            ("cooking_minutes", 1441),
            ("cooking_minutes", "1.5"),
        ]
        for field, value in invalid:
            with self.subTest(field=field, value=str(value)[:20]):
                candidate = dict(values)
                candidate[field] = value
                with self.assertRaises(ValueError):
                    self.db.save_recipe(candidate, composition)
        with self.assertRaises(ValueError):
            self.db.save_stock(item, -1)
        with self.assertRaises(ValueError):
            self.db.save_persons(21)
        photo = self.image("boundary.png")
        with open(photo, "r+b") as file:
            file.truncate(10 * 1024 * 1024)
        validate_photo(photo)
        with open(photo, "ab") as file:
            file.write(b"0")
        with self.assertRaises(ValueError):
            validate_photo(photo)


if __name__ == "__main__":
    unittest.main()
