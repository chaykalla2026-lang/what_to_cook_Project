"""Общие пути и постоянные значения приложения."""

import os

from PyQt6.QtCore import QStandardPaths

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = [
    "Завтраки",
    "Супы",
    "Основные блюда",
    "Салаты",
    "Десерты",
    "Другое",
]
UNITS = ["г", "мл", "шт"]
NUTRIENTS = ["calories", "protein", "fat", "carbs"]


def project_file(folder, filename):
    return os.path.join(PROJECT_DIR, folder, filename)


def data_directory():
    # При проверке используется отдельная временная папка.
    path = os.environ.get("WHAT_TO_COOK_DATA_DIR")
    if not path:
        path = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    if not path:
        raise OSError("Не удалось определить папку для сохранения данных.")
    return path
