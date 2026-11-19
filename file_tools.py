"""Сохранение отчётов и пользовательских фотографий."""

import csv
import io
import os
import shutil
import tempfile
import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from data_loader import NUTRIENTS
from logic import number_text


def atomic_write(filename, text, encoding="utf-8"):
    folder = os.path.dirname(os.path.abspath(filename))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, newline="", dir=folder, delete=False
        ) as file:
            temporary = file.name
            file.write(text)
        os.replace(temporary, filename)
    finally:
        if temporary and os.path.exists(temporary):
            os.remove(temporary)


def export_recipes(filename, recipes):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "recipe_id",
            "name",
            "category",
            "cooking_minutes",
            "base_portions",
            "is_favorite",
            "calories_per_portion",
            "protein_per_portion",
            "fat_per_portion",
            "carbs_per_portion",
        ]
    )
    for recipe in recipes:
        nutrition = recipe["nutrition"]
        numbers = (
            [""] * 4
            if nutrition is None
            else [
                number_text(
                    nutrition[key], 1 if key == "calories" else 2
                ).replace(",", ".")
                for key in NUTRIENTS
            ]
        )
        writer.writerow(
            [
                recipe["id"],
                recipe["name"],
                recipe["category"],
                recipe["cooking_minutes"],
                recipe["base_portions"],
                recipe["is_favorite"],
            ]
            + numbers
        )
    atomic_write(filename, output.getvalue(), "utf-8-sig")


def export_shopping(filename, recipe, persons, calculation):
    lines = [recipe["name"], f"Число персон: {persons}", "", "Нужно купить:"]
    for row in calculation["rows"]:
        if row["missing"] > 0:
            lines.append(
                f"{row['name']} — {number_text(row['missing'])} {row['unit']}"
            )
    atomic_write(filename, "\n".join(lines) + "\n")


def photo_filename(database, relative):
    return os.path.join(database.directory, relative) if relative else None


def validate_photo(filename):
    if os.path.splitext(filename)[1].lower() not in [".png", ".jpg", ".jpeg"]:
        raise ValueError("Выберите фотографию PNG, JPG или JPEG.")
    if os.path.getsize(filename) > 10 * 1024 * 1024:
        raise ValueError("Фотография должна занимать не более 10 МиБ.")
    if QPixmap(filename).isNull():
        raise ValueError("Не удалось прочитать изображение.")


def copy_photo(database, filename):
    validate_photo(filename)
    relative = (
        "images/" + uuid.uuid4().hex + os.path.splitext(filename)[1].lower()
    )
    target = photo_filename(database, relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        shutil.copyfile(filename, target)
    except OSError:
        try:
            os.remove(target)
        except OSError:
            pass
        raise
    return relative


def remove_unused_photo(database, relative):
    if not relative or database.query(
        "SELECT id FROM recipes WHERE image_path=?", (relative,)
    ):
        return
    target = os.path.abspath(photo_filename(database, relative))
    folder = os.path.abspath(os.path.join(database.directory, "images"))
    if os.path.commonpath([folder, target]) == folder:
        try:
            os.remove(target)
        except OSError:
            pass


def show_photo(label, filename):
    label.clear()
    if filename and os.path.isfile(filename):
        pixmap = QPixmap(filename)
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    640,
                    160,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return
    label.setText(
        "Фотографии пока нет" if not filename else "Фотография недоступна"
    )
