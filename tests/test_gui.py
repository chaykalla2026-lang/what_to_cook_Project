"""Сквозные проверки окон на временной БД, без пользовательских данных."""

# ruff: noqa: E402 -- платформа выбирается до импорта Qt.
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import time
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from forms import NO, YES
from main import MainWindow


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.filename = os.path.join(self.temp.name, "recipes.sqlite3")
        self.patches = [
            patch.object(QMessageBox, "warning"),
            patch.object(QMessageBox, "information"),
            patch.object(QMessageBox, "question", return_value=YES),
        ]
        self.warning, self.info, self.question = [
            p.start() for p in self.patches
        ]
        self.w = MainWindow(self.filename)
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.question.return_value = YES
        self.w.close()
        self.app.processEvents()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def add_ingredient(self, name="Мука", unit="г", known=True):
        self.w.new_ingredient()
        editor = self.w.ingredient_editor
        editor.nameEdit.setText(name)
        editor.unitCombo.setCurrentIndex(["г", "мл", "шт"].index(unit))
        editor.knownCheck.setChecked(known)
        if known:
            for field, value in [
                (editor.caloriesEdit, "100"),
                (editor.proteinEdit, "2"),
                (editor.fatEdit, "3"),
                (editor.carbsEdit, "4"),
            ]:
                field.setText(value)
        editor.saveButton.click()
        self.app.processEvents()
        self.assertFalse(editor.isVisible())
        return next(
            row["id"]
            for row in self.w.database.ingredients()
            if row["name"] == name
        )

    def add_recipe(
        self, item, name="Рецепт", quantity=400, portions=4, minutes=30
    ):
        self.w.new_recipe()
        editor = self.w.recipe_editor
        editor.nameEdit.setText(name)
        editor.instructionsEdit.setPlainText("Приготовить блюдо.")
        editor.minutesEdit.setText(str(minutes))
        editor.portionsSpin.setValue(portions)
        ids = [row["id"] for row in editor.ingredients]
        editor.ingredientCombo.setCurrentIndex(ids.index(item))
        editor.amountSpin.setValue(quantity)
        editor.addRowButton.click()
        editor.saveButton.click()
        self.app.processEvents()
        self.assertFalse(editor.isVisible(), self.warning.call_args)
        return next(
            row["id"]
            for row in self.w.database.recipes()
            if row["name"] == name
        )

    def select_recipe(self, rid):
        index = [row["id"] for row in self.w.current_recipes].index(rid)
        self.w.recipesTable.selectRow(index)
        self.assertTrue(self.w.openRecipeButton.isEnabled())

    def test_creation_edit_favorite_settings_and_restart(self):
        self.assertEqual(self.w.recipesTable.rowCount(), 0)
        item = self.add_ingredient()
        rid = self.add_recipe(item)
        self.select_recipe(rid)
        self.w.openRecipeButton.click()
        card = self.w.recipe_card
        self.assertTrue(card.isVisible())
        self.assertIn("100,0", card.nutritionLabel.text())
        self.assertEqual(card.ingredientsTable.item(0, 1).text(), "200,00")
        card.favoriteButton.click()
        self.assertEqual(self.w.database.recipe(rid)["is_favorite"], 1)
        card.editButton.click()
        editor = self.w.recipe_editor
        editor.nameEdit.setText("Обновлённый рецепт")
        editor.saveButton.click()
        self.assertEqual(
            self.w.database.recipe(rid)["name"], "Обновлённый рецепт"
        )
        self.assertEqual(self.w.database.recipe(rid)["is_favorite"], 1)
        self.w.settings_window.open_settings()
        self.w.settings_window.personsSpin.setValue(3)
        self.w.settings_window.saveButton.click()
        self.assertEqual(card.personsSpin.value(), 2)
        card.close()
        self.select_recipe(rid)
        self.w.openRecipeButton.click()
        self.assertEqual(card.personsSpin.value(), 3)
        self.w.close()
        self.w = MainWindow(self.filename)
        self.assertEqual(self.w.database.persons(), 3)
        self.assertEqual(self.w.recipesTable.rowCount(), 1)
        self.assertEqual(self.w.database.recipe(rid)["is_favorite"], 1)

    def test_new_ingredient_from_recipe_preserves_draft(self):
        self.w.new_recipe()
        editor = self.w.recipe_editor
        editor.nameEdit.setText("Не потерять название")
        editor.newIngredientButton.click()
        ingredient = self.w.ingredient_editor
        ingredient.nameEdit.setText("Яйцо")
        ingredient.unitCombo.setCurrentIndex(2)
        ingredient.saveButton.click()
        self.assertEqual(editor.nameEdit.text(), "Не потерять название")
        self.assertEqual(editor.ingredientCombo.currentText(), "Яйцо")
        self.assertEqual(self.w.database.fridge(), [])
        self.assertEqual(self.w.database.recipes(), [])
        self.question.return_value = NO
        self.assertFalse(editor.close())
        self.assertTrue(editor.isVisible())
        self.question.return_value = YES
        self.assertTrue(editor.close())
        self.assertEqual(len(self.w.database.ingredients()), 1)

    def test_validation_does_not_lose_form(self):
        self.add_ingredient()
        self.w.new_recipe()
        editor = self.w.recipe_editor
        editor.nameEdit.setText("Название сохранено в форме")
        editor.saveButton.click()
        self.assertTrue(editor.isVisible())
        self.assertEqual(editor.nameEdit.text(), "Название сохранено в форме")
        self.assertEqual(self.w.database.recipes(), [])
        self.assertTrue(self.warning.called)

    def test_stock_picker_search_and_export(self):
        item = self.add_ingredient()
        a = self.add_recipe(item, "Быстрый", 200, 2, 40)
        self.add_recipe(item, "Долгий", 400, 2, 60)
        self.w.new_stock()
        stock = self.w.stock_editor
        stock.quantitySpin.setValue(150)
        stock.saveButton.click()
        self.assertEqual(self.w.database.stocks()[item], 150)
        self.w.new_stock()
        stock.quantitySpin.setValue(200)
        self.question.return_value = NO
        stock.saveButton.click()
        self.assertEqual(self.w.database.stocks()[item], 150)
        self.question.return_value = YES
        stock.saveButton.click()
        self.assertEqual(self.w.database.stocks()[item], 200)
        self.w.mainTabs.setCurrentIndex(3)
        self.w.selectionLimitCheck.setChecked(True)
        self.w.selectionLimitSpin.setValue(40)
        self.w.availableCheck.setChecked(True)
        self.w.selectButton.click()
        self.assertEqual(len(self.w.selection_rows), 1)
        self.assertEqual(self.w.selection_rows[0]["id"], a)
        self.w.selectionTable.selectRow(0)
        self.w.openSelectionButton.click()
        self.assertEqual(self.w.recipe_card.personsSpin.value(), 2)
        self.w.new_stock()
        stock.quantitySpin.setValue(100)
        stock.saveButton.click()
        self.assertFalse(self.w.selection_valid)
        self.assertEqual(self.w.selectionTable.rowCount(), 0)
        path = os.path.join(self.temp.name, "shopping.txt")
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=(path, "")
        ):
            self.w.recipe_card.shoppingButton.click()
        with open(path, encoding="utf-8") as file:
            self.assertIn("100,00 г", file.read())
        self.w.recipe_card.close()
        self.w.mainTabs.setCurrentIndex(0)
        self.w.recipeSearch.setText("БЫСТ")
        self.assertEqual(len(self.w.current_recipes), 1)
        path = os.path.join(self.temp.name, "recipes.csv")
        with patch.object(
            QFileDialog, "getSaveFileName", return_value=(path, "")
        ):
            self.w.exportButton.click()
        with open(path, encoding="utf-8-sig") as file:
            text = file.read()
        self.assertIn("Быстрый", text)
        self.assertNotIn("Долгий", text)

    def test_photograph_add_later_replace_and_remove(self):
        item = self.add_ingredient()
        rid = self.add_recipe(item)
        self.assertIsNone(self.w.database.recipe(rid)["image_path"])
        original = os.path.join(self.temp.name, "original.png")
        pixmap = QPixmap(40, 30)
        pixmap.fill(Qt.GlobalColor.green)
        pixmap.save(original)
        self.select_recipe(rid)
        self.w.editRecipeButton.click()
        editor = self.w.recipe_editor
        with patch.object(
            QFileDialog, "getOpenFileName", return_value=(original, "")
        ):
            editor.choosePhotoButton.click()
        editor.saveButton.click()
        relative = self.w.database.recipe(rid)["image_path"]
        self.assertTrue(relative.startswith("images"))
        target = os.path.join(self.w.database.directory, relative)
        self.assertTrue(os.path.exists(target))
        os.remove(original)
        self.select_recipe(rid)
        self.w.openRecipeButton.click()
        self.assertFalse(self.w.recipe_card.photoGroupLabel.pixmap().isNull())
        self.w.recipe_card.editButton.click()
        editor.removePhotoButton.click()
        editor.saveButton.click()
        self.assertIsNone(self.w.database.recipe(rid)["image_path"])
        self.assertFalse(os.path.exists(target))

    def test_deletion_guards_and_ingredient_update(self):
        item = self.add_ingredient()
        rid = self.add_recipe(item)
        self.w.ingredientsTable.selectRow(0)
        self.w.deleteIngredientButton.click()
        self.assertIsNotNone(self.w.database.ingredient(item))
        self.assertTrue(self.warning.called)
        self.w.ingredientsTable.selectRow(0)
        self.w.editIngredientButton.click()
        editor = self.w.ingredient_editor
        self.assertFalse(editor.unitCombo.isEnabled())
        editor.caloriesEdit.setText("200")
        editor.saveButton.click()
        self.assertEqual(
            self.w.current_recipes[0]["nutrition"]["calories"], 200
        )
        self.select_recipe(rid)
        self.question.return_value = NO
        self.w.deleteRecipeButton.click()
        self.assertIsNotNone(self.w.database.recipe(rid))
        self.question.return_value = YES
        self.w.deleteRecipeButton.click()
        self.assertIsNone(self.w.database.recipe(rid))
        self.assertEqual(self.w.database.composition(), [])
        self.assertIsNotNone(self.w.database.ingredient(item))

    def test_timer_background_pause_finish_and_exit_cancel(self):
        timer = self.w.timer_window
        timer.startButton.click()
        self.assertEqual(timer.state, "running")
        timer.close()
        self.assertTrue(timer.active())
        self.w.actionTimer.trigger()
        self.assertEqual(timer.state, "running")
        timer.pauseButton.click()
        left = timer.remaining
        time.sleep(0.02)
        self.assertEqual(timer.remaining, left)
        self.assertEqual(timer.state, "paused")
        self.question.return_value = NO
        self.assertFalse(self.w.close())
        self.assertEqual(self.w.database.persons(), 2)
        timer.pauseButton.click()
        timer.deadline = time.monotonic() - 1
        self.info.reset_mock()
        timer.tick()
        timer.tick()
        self.assertEqual(timer.state, "finished")
        self.assertEqual(self.info.call_count, 1)
        self.assertFalse(timer.timer.isActive())
        timer.resetButton.click()
        self.assertEqual(timer.state, "idle")
        self.assertEqual(timer.remaining, 600)


if __name__ == "__main__":
    unittest.main()
