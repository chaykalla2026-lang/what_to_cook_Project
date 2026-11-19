CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 80),
    name_key TEXT NOT NULL UNIQUE,
    unit TEXT NOT NULL CHECK(unit IN ('г', 'мл', 'шт')),
    calories REAL CHECK(calories BETWEEN 0 AND 99999.99),
    protein REAL CHECK(protein BETWEEN 0 AND 99999.99),
    fat REAL CHECK(fat BETWEEN 0 AND 99999.99),
    carbs REAL CHECK(carbs BETWEEN 0 AND 99999.99),
    CHECK((calories IS NULL AND protein IS NULL AND fat IS NULL AND carbs IS NULL)
       OR (calories IS NOT NULL AND protein IS NOT NULL AND fat IS NOT NULL AND carbs IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
    category TEXT NOT NULL CHECK(category IN ('Завтраки', 'Супы', 'Основные блюда', 'Салаты', 'Десерты', 'Другое')),
    instructions TEXT NOT NULL CHECK(length(trim(instructions)) BETWEEN 1 AND 10000),
    base_portions INTEGER NOT NULL CHECK(base_portions BETWEEN 1 AND 20),
    cooking_minutes INTEGER NOT NULL CHECK(cooking_minutes BETWEEN 1 AND 1440),
    image_path TEXT,
    is_favorite INTEGER NOT NULL DEFAULT 0 CHECK(is_favorite IN (0, 1))
);
CREATE TABLE IF NOT EXISTS recipe_ingredients (
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity BETWEEN 0.01 AND 999999.99),
    PRIMARY KEY(recipe_id, ingredient_id)
);
CREATE TABLE IF NOT EXISTS fridge (
    ingredient_id INTEGER PRIMARY KEY REFERENCES ingredients(id) ON DELETE RESTRICT,
    quantity REAL NOT NULL CHECK(quantity BETWEEN 0 AND 999999.99)
);
CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    preferred_servings INTEGER NOT NULL DEFAULT 2 CHECK(preferred_servings BETWEEN 1 AND 20)
);
