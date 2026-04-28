import time
from typing import Optional
import os
import requests

from backend.models import NutritionPer100g

# nutrient IDs from USDA FoodData Central
NUTRIENT_IDS = {
    "protein":        1003,
    "fat":            1004,
    "carbohydrates":  1005,
    "kcal":           1008,
    "fibre":          1079,
    "sugar":          2000,
    "saturated_fat":  1258,
    "sodium":         1093,
    "cholesterol":    1253,
}

_PREFERRED_DATA_TYPES = ["Foundation", "SR Legacy"]
_USDA_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
_USER_AGENT = "recipe-kg/1.0 (geirdunma@gmail.com)"
_MAX_RETRIES = 3


def fetch_nutrition(ingredient: str, session: Optional[requests.Session] = None) -> Optional[NutritionPer100g]:
    if session is None:
        session = requests.Session()
    data = _search(ingredient, session)
    food = _pick_best(data.get("foods", []))
    if food is None:
        return None
    return _extract_nutrition(food)


def _search(ingredient: str, session: requests.Session) -> dict:
    params = {
        "query": ingredient,
        "pageSize": 5,
        "api_key": os.getenv("USDA_API_KEY", "DEMO_KEY")  # fallback for testing
    }
    headers = {"User-Agent": _USER_AGENT}

    for attempt in range(_MAX_RETRIES):
        resp = session.get(_USDA_URL, params=params, headers=headers)
        if resp.status_code in (429, 503):
            if attempt == _MAX_RETRIES - 1:
                raise requests.HTTPError(
                    f"HTTP {resp.status_code} after {_MAX_RETRIES} retries", response=resp
                )
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else (2 ** attempt)
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()

    resp.raise_for_status()
    return {}


def _pick_best(foods: list) -> Optional[dict]:
    for preferred in _PREFERRED_DATA_TYPES:
        for food in foods:
            if food.get("dataType") == preferred:
                return food
    return foods[0] if foods else None


def _extract_nutrition(food: dict) -> NutritionPer100g:
    nutrients = {n["nutrientId"]: n["value"] for n in food.get("foodNutrients", [])}
    ids = NUTRIENT_IDS
    return NutritionPer100g(
        protein_per_100g=nutrients.get(ids["protein"], 0.0),
        fat_per_100g=nutrients.get(ids["fat"], 0.0),
        carbs_per_100g=nutrients.get(ids["carbohydrates"], 0.0),
        kcal_per_100g=nutrients.get(ids["kcal"], 0.0),
        fibre_per_100g=nutrients.get(ids["fibre"]),
        sugar_per_100g=nutrients.get(ids["sugar"]),
        saturated_fat_per_100g=nutrients.get(ids["saturated_fat"]),
        sodium_mg_per_100g=nutrients.get(ids["sodium"]),
        cholesterol_mg_per_100g=nutrients.get(ids["cholesterol"]),
    )
