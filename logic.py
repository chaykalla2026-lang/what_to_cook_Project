"""Проверка данных и расчёты, которые можно проверять без окон."""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

from data_loader import CATEGORIES, NUTRIENTS, UNITS


def normalized_name(text):
    return " ".join(text.split()).casefold()


def checked_text(text, title, maximum):
    text = text.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{title}: введите от 1 до {maximum} символов.")
    return text


def checked_integer(value, title, minimum, maximum):
    text = str(value).strip()
    if not text.isdecimal() or not minimum <= int(text) <= maximum:
        raise ValueError(
            f"{title}: введите целое число от {minimum} до {maximum}."
        )
    return int(text)


def checked_number(value, title, minimum="0", maximum="999999.99"):
    text = str(value).strip().replace(",", ".")
    if not text or any(char not in "0123456789." for char in text):
        raise ValueError(f"{title}: введите неотрицательное число.")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{title}: неверное число.") from None
    if not number.is_finite() or not Decimal(minimum) <= number <= Decimal(
        maximum
    ):
        raise ValueError(f"{title}: допустимо от {minimum} до {maximum}.")
    if number.as_tuple().exponent < -2:
        raise ValueError(
            f"{title}: допускается максимум два знака после запятой."
        )
    return number


def number_text(value, places=2):
    value = Decimal(str(value)).quantize(
        Decimal("1").scaleb(-places), rounding=ROUND_HALF_UP
    )
    return format(value, "f").replace(".", ",")


def ingredient_values(values):
    name = checked_text(" ".join(values["name"].split()), "Название", 80)
    unit = values["unit"]
    if unit not in UNITS:
        raise ValueError("Выберите граммы, миллилитры или штуки.")
    numbers = [values.get(key) for key in NUTRIENTS]
    missing = [value is None or str(value).strip() == "" for value in numbers]
    if any(missing) and not all(missing):
        raise ValueError(
            "Заполните все четыре показателя КБЖУ или отключите их."
        )
    numbers = (
        [None] * 4
        if all(missing)
        else [
            float(checked_number(value, "КБЖУ", maximum="99999.99"))
            for value in numbers
        ]
    )
    return [name, normalized_name(name), unit] + numbers


def recipe_values(values, composition):
    name = checked_text(values["name"], "Название рецепта", 100)
    instructions = checked_text(values["instructions"], "Инструкция", 10000)
    if values["category"] not in CATEGORIES:
        raise ValueError("Выберите категорию рецепта.")
    portions = checked_integer(
        values["base_portions"], "Базовые порции", 1, 20
    )
    minutes = checked_integer(values["cooking_minutes"], "Время", 1, 1440)
    if not 1 <= len(composition) <= 50:
        raise ValueError("Добавьте от 1 до 50 ингредиентов.")
    ids = [int(row["ingredient_id"]) for row in composition]
    if len(set(ids)) != len(ids):
        raise ValueError("Один ингредиент нельзя добавлять в рецепт дважды.")
    rows = [
        (
            ingredient_id,
            float(checked_number(row["quantity"], "Количество", "0.01")),
        )
        for ingredient_id, row in zip(ids, composition)
    ]
    return [
        name,
        values["category"],
        instructions,
        portions,
        minutes,
        values.get("image_path"),
    ], rows


def calculate(recipe, composition, stocks, persons):
    persons = checked_integer(persons, "Число персон", 1, 20)
    portions = Decimal(str(recipe["base_portions"]))
    totals = dict.fromkeys(NUTRIENTS, Decimal("0"))
    known = bool(composition)
    rows = []
    for ingredient in composition:
        quantity = Decimal(str(ingredient["quantity"]))
        required = (quantity * persons / portions).quantize(
            Decimal("0.01"), rounding=ROUND_CEILING
        )
        available = Decimal(str(stocks.get(ingredient["ingredient_id"], 0)))
        rows.append(
            dict(
                ingredient,
                required=required,
                available=available,
                missing=max(Decimal("0"), required - available),
            )
        )
        if any(ingredient[key] is None for key in NUTRIENTS):
            known = False
        else:
            base = (
                Decimal("1") if ingredient["unit"] == "шт" else Decimal("100")
            )
            for key in NUTRIENTS:
                totals[key] += quantity / base * Decimal(str(ingredient[key]))
    per_portion = (
        {key: value / portions for key, value in totals.items()}
        if known
        else None
    )
    selected = (
        {key: value * persons for key, value in per_portion.items()}
        if known
        else None
    )
    return {
        "rows": rows,
        "per_portion": per_portion,
        "selected": selected,
        "missing_count": sum(row["missing"] > 0 for row in rows),
    }


def sort_recipes(recipes, field="name", descending=False):
    ordered = sorted(
        recipes, key=lambda row: (normalized_name(row["name"]), row["id"])
    )
    if field == "name":
        return list(reversed(ordered)) if descending else ordered
    if field in NUTRIENTS:
        known = [row for row in ordered if row["nutrition"] is not None]
        unknown = [row for row in ordered if row["nutrition"] is None]
        known.sort(key=lambda row: row["nutrition"][field], reverse=descending)
        return known + unknown
    return sorted(ordered, key=lambda row: row[field], reverse=descending)
