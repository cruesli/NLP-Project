from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.models import NutritionPer100g
from backend.nutrition import _pick_best, fetch_nutrition


# --- helpers ---

def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.headers = {}
    resp.raise_for_status = MagicMock()
    return resp


def _session(*responses):
    s = MagicMock(spec=requests.Session)
    s.get.side_effect = list(responses)
    return s


# --- fixtures ---

ALL_NUTRIENTS = [
    {"nutrientId": 1003, "value": 25.9},   # protein
    {"nutrientId": 1004, "value": 9.6},    # fat
    {"nutrientId": 1005, "value": 0.0},    # carbohydrates
    {"nutrientId": 1008, "value": 189.0},  # kcal
    {"nutrientId": 1079, "value": 0.3},    # fibre
    {"nutrientId": 2000, "value": 0.0},    # sugar
    {"nutrientId": 1258, "value": 2.6},    # saturated fat
    {"nutrientId": 1093, "value": 79.0},   # sodium
    {"nutrientId": 1253, "value": 91.0},   # cholesterol
]

SR_LEGACY_FOOD = {
    "fdcId": 782222,
    "description": "Chicken, thigh, meat only, cooked, roasted",
    "dataType": "SR Legacy",
    "foodNutrients": ALL_NUTRIENTS,
}

FOUNDATION_FOOD = {
    "fdcId": 999001,
    "description": "Chicken thigh, Foundation",
    "dataType": "Foundation",
    "foodNutrients": [
        {"nutrientId": 1003, "value": 24.0},
        {"nutrientId": 1004, "value": 8.0},
        {"nutrientId": 1005, "value": 0.0},
        {"nutrientId": 1008, "value": 172.0},
        {"nutrientId": 1079, "value": 0.0},
    ],
}

BRANDED_FOOD = {
    "fdcId": 111111,
    "description": "Brand-X Chicken Thighs",
    "dataType": "Branded",
    "foodNutrients": [
        {"nutrientId": 1003, "value": 10.0},
        {"nutrientId": 1004, "value": 5.0},
        {"nutrientId": 1005, "value": 2.0},
        {"nutrientId": 1008, "value": 90.0},
    ],
}

FOOD_RESPONSE = {"foods": [SR_LEGACY_FOOD]}
EMPTY_RESPONSE = {"foods": []}


# --- return type and field mapping ---

def test_fetch_nutrition_returns_nutrition_model():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert isinstance(result, NutritionPer100g)


def test_fetch_nutrition_maps_protein():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.protein_per_100g == pytest.approx(25.9)


def test_fetch_nutrition_maps_fat():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.fat_per_100g == pytest.approx(9.6)


def test_fetch_nutrition_maps_carbs():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.carbs_per_100g == pytest.approx(0.0)


def test_fetch_nutrition_maps_kcal():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.kcal_per_100g == pytest.approx(189.0)


def test_fetch_nutrition_maps_fibre():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.fibre_per_100g == pytest.approx(0.3)


def test_fetch_nutrition_maps_sugar():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.sugar_per_100g == pytest.approx(0.0)


def test_fetch_nutrition_maps_saturated_fat():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.saturated_fat_per_100g == pytest.approx(2.6)


def test_fetch_nutrition_maps_sodium():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.sodium_mg_per_100g == pytest.approx(79.0)


def test_fetch_nutrition_maps_cholesterol():
    s = _session(_mock_response(FOOD_RESPONSE))
    result = fetch_nutrition("chicken thigh", s)
    assert result.cholesterol_mg_per_100g == pytest.approx(91.0)


# --- food type preference ---

def test_fetch_nutrition_prefers_foundation_over_sr_legacy():
    response = {"foods": [SR_LEGACY_FOOD, FOUNDATION_FOOD]}
    s = _session(_mock_response(response))
    result = fetch_nutrition("chicken thigh", s)
    assert result.kcal_per_100g == pytest.approx(172.0)


def test_fetch_nutrition_prefers_sr_legacy_over_branded():
    response = {"foods": [BRANDED_FOOD, SR_LEGACY_FOOD]}
    s = _session(_mock_response(response))
    result = fetch_nutrition("chicken thigh", s)
    assert result.kcal_per_100g == pytest.approx(189.0)


def test_fetch_nutrition_falls_back_to_branded_when_no_preferred():
    response = {"foods": [BRANDED_FOOD]}
    s = _session(_mock_response(response))
    result = fetch_nutrition("chicken thigh", s)
    assert result is not None
    assert result.kcal_per_100g == pytest.approx(90.0)


# --- no results ---

def test_fetch_nutrition_returns_none_for_empty_results():
    s = _session(_mock_response(EMPTY_RESPONSE))
    assert fetch_nutrition("xyzzy_unknown_food", s) is None


# --- http etiquette ---

def test_fetch_nutrition_sends_user_agent():
    s = _session(_mock_response(FOOD_RESPONSE))
    fetch_nutrition("chicken thigh", s)
    headers = s.get.call_args.kwargs.get("headers", {})
    assert "User-Agent" in headers


def test_fetch_nutrition_includes_ingredient_in_query():
    s = _session(_mock_response(FOOD_RESPONSE))
    fetch_nutrition("tahini", s)
    params = s.get.call_args.kwargs.get("params", {})
    assert "tahini" in params.get("query", "")


# --- zero-macro skipping ---

ZERO_MACRO_FOUNDATION = {
    "fdcId": 10001,
    "description": "Water, bottled",
    "dataType": "Foundation",
    "foodNutrients": [
        {"nutrientId": 1003, "value": 0.0},
        {"nutrientId": 1004, "value": 0.0},
        {"nutrientId": 1005, "value": 0.0},
        {"nutrientId": 1008, "value": 0.0},
    ],
}

NONZERO_SR_LEGACY = {
    "fdcId": 10002,
    "description": "Chicken thigh, cooked",
    "dataType": "SR Legacy",
    "foodNutrients": [
        {"nutrientId": 1003, "value": 25.0},
        {"nutrientId": 1004, "value": 9.0},
        {"nutrientId": 1005, "value": 0.0},
        {"nutrientId": 1008, "value": 185.0},
    ],
}


def test_pick_best_skips_zero_macro_preferred_food():
    result = _pick_best([ZERO_MACRO_FOUNDATION, NONZERO_SR_LEGACY])
    assert result == NONZERO_SR_LEGACY


def test_pick_best_returns_zero_macro_food_when_all_have_zero_macros():
    result = _pick_best([ZERO_MACRO_FOUNDATION])
    assert result == ZERO_MACRO_FOUNDATION


def test_fetch_nutrition_skips_zero_macro_candidate():
    response = {"foods": [ZERO_MACRO_FOUNDATION, NONZERO_SR_LEGACY]}
    s = _session(_mock_response(response))
    result = fetch_nutrition("water", s)
    assert result is not None
    assert result.protein_per_100g == pytest.approx(25.0)


# --- retry logic ---

def test_retries_on_429_then_succeeds():
    rate_limited = _mock_response({}, status_code=429)
    rate_limited.headers = {"Retry-After": "0"}
    ok = _mock_response(FOOD_RESPONSE)

    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [rate_limited, ok]

    with patch("backend.nutrition.time.sleep"):
        result = fetch_nutrition("chicken thigh", s)

    assert s.get.call_count == 2
    assert result is not None


def test_retries_on_503_then_succeeds():
    unavailable = _mock_response({}, status_code=503)
    ok = _mock_response(FOOD_RESPONSE)

    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [unavailable, ok]

    with patch("backend.nutrition.time.sleep"):
        result = fetch_nutrition("chicken thigh", s)

    assert s.get.call_count == 2
    assert result is not None


def test_raises_after_max_retries_exceeded():
    always_429 = _mock_response({}, status_code=429)
    always_429.headers = {}

    s = MagicMock(spec=requests.Session)
    s.get.return_value = always_429

    with patch("backend.nutrition.time.sleep"):
        with pytest.raises(requests.HTTPError):
            fetch_nutrition("chicken thigh", s)


def test_exponential_backoff_increases_delay():
    r429 = _mock_response({}, status_code=429)
    r429.headers = {}
    ok = _mock_response(FOOD_RESPONSE)

    s = MagicMock(spec=requests.Session)
    s.get.side_effect = [r429, r429, ok]

    sleep_calls = []
    with patch("backend.nutrition.time.sleep", side_effect=sleep_calls.append):
        fetch_nutrition("chicken thigh", s)

    assert len(sleep_calls) == 2
    assert sleep_calls[1] > sleep_calls[0]
