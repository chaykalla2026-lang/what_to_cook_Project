"""Чтение примеров из CSV. Позже здесь появятся запросы к SQLite."""

import csv
import os


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CATEGORIES = [
    'Завтраки', 'Супы', 'Основные блюда', 'Салаты', 'Десерты', 'Другое'
]


def project_file(folder, filename):
    return os.path.join(PROJECT_DIR, folder, filename)


def read_csv(filename):
    with open(project_file('data', filename), encoding='utf-8-sig', newline='') as file:
        rows = list(csv.reader(file, delimiter=';'))
    if not rows:
        return []
    for row in rows[1:]:
        if row and len(row) != len(rows[0]):
            raise ValueError(f'В файле {filename} строка не совпадает с заголовком')
    return [dict(zip(rows[0], row)) for row in rows[1:] if row]


def load_data():
    data = {}
    for name in ['recipes', 'ingredients', 'recipe_ingredients', 'fridge',
                 'app_settings']:
        data[name] = read_csv(name + '.csv')
    return data


def find_record(records, record_id):
    for record in records:
        if record['id'] == record_id:
            return record
    return None
