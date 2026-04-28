"""Tests for backend/main.py — FastAPI endpoints (TDD)."""
import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.graph import RecipeKnowledgeGraph
from backend.main import app, get_kg, get_openai_client
from backend.models import NutritionPer100g, Recipe, WikidataEntity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nutrition_chicken():
    return NutritionPer100g(
        protein_per_100g=17.4, fat_per_100g=9.6, carbs_per_100g=0.0, kcal_per_100g=177.0
    )


@pytest.fixture
def nutrition_tahini():
    return NutritionPer100g(
        protein_per_100g=17.0, fat_per_100g=53.0, carbs_per_100g=21.0, kcal_per_100g=595.0
    )


@pytest.fixture
def entity_chicken():
    return WikidataEntity(
        qid="Q192628",
        uri="http://www.wikidata.org/entity/Q192628",
        label="chicken thigh",
        food_category="poultry",
        origin_country="United States",
        dietary_flags=[],
    )


@pytest.fixture
def entity_tahini():
    return WikidataEntity(
        qid="Q806723",
        uri="http://www.wikidata.org/entity/Q806723",
        label="tahini",
        food_category="condiment",
        origin_country="Middle East",
        dietary_flags=["vegan", "vegetarian"],
    )


@pytest.fixture
def test_kg(nutrition_chicken, nutrition_tahini, entity_chicken, entity_tahini):
    kg = RecipeKnowledgeGraph()
    kg.add_recipe(
        Recipe(
            slug="tahini-chicken",
            title="Tahini Chicken",
            cuisine="middle-eastern",
            servings=2,
            total_time_minutes=45,
            tags=["Quick", "Healthy"],
            ingredients=["400g Chicken thighs", "2 tbsp Tahini"],
        ),
        {"400g Chicken thighs": "chicken thigh", "2 tbsp Tahini": "tahini"},
        {"chicken thigh": entity_chicken, "tahini": entity_tahini},
        {"chicken thigh": nutrition_chicken, "tahini": nutrition_tahini},
    )
    kg.add_recipe(
        Recipe(
            slug="pasta-bolognese",
            title="Pasta Bolognese",
            cuisine="italian",
            servings=4,
            total_time_minutes=90,
            ingredients=["500g Pasta"],
        ),
        {"500g Pasta": "pasta"},
        {},
        {},
    )
    return kg


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps({"cuisine": "middle-eastern"})))]
    )
    return mock


@pytest.fixture
def client(test_kg):
    app.dependency_overrides[get_kg] = lambda: test_kg
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_mock_llm(test_kg, mock_llm):
    app.dependency_overrides[get_kg] = lambda: test_kg
    app.dependency_overrides[get_openai_client] = lambda: mock_llm
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/recipes
# ---------------------------------------------------------------------------


def test_list_recipes_returns_200(client):
    assert client.get("/api/v1/recipes").status_code == 200


def test_list_recipes_returns_list(client):
    assert isinstance(client.get("/api/v1/recipes").json(), list)


def test_list_recipes_returns_two_recipes(client):
    assert len(client.get("/api/v1/recipes").json()) == 2


def test_list_recipes_has_tahini_chicken_slug(client):
    slugs = {r["slug"] for r in client.get("/api/v1/recipes").json()}
    assert "tahini-chicken" in slugs


def test_list_recipes_summary_has_camel_case_total_time(client):
    data = client.get("/api/v1/recipes").json()
    tahini = next(r for r in data if r["slug"] == "tahini-chicken")
    assert "totalTimeMinutes" in tahini
    assert tahini["totalTimeMinutes"] == 45


# ---------------------------------------------------------------------------
# GET /api/v1/recipes/filter
# ---------------------------------------------------------------------------


def test_filter_recipes_returns_200(client):
    assert client.get("/api/v1/recipes/filter").status_code == 200


def test_filter_by_cuisine_returns_match(client):
    data = client.get("/api/v1/recipes/filter?cuisine=middle-eastern").json()
    assert data["count"] == 1
    assert data["results"][0]["slug"] == "tahini-chicken"


def test_filter_response_has_filters_applied(client):
    data = client.get("/api/v1/recipes/filter?cuisine=middle-eastern&max_time=60").json()
    assert data["filters_applied"]["cuisine"] == "middle-eastern"
    assert data["filters_applied"]["max_time"] == 60


def test_filter_no_params_returns_all(client):
    assert client.get("/api/v1/recipes/filter").json()["count"] == 2


def test_filter_no_match_returns_empty_results(client):
    data = client.get("/api/v1/recipes/filter?cuisine=japanese").json()
    assert data["count"] == 0
    assert data["results"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/recipes/{slug}
# ---------------------------------------------------------------------------


def test_get_recipe_by_slug_returns_200(client):
    assert client.get("/api/v1/recipes/tahini-chicken").status_code == 200


def test_get_recipe_by_slug_returns_title(client):
    data = client.get("/api/v1/recipes/tahini-chicken").json()
    assert data["slug"] == "tahini-chicken"
    assert data["title"] == "Tahini Chicken"


def test_get_recipe_by_slug_has_two_ingredients(client):
    data = client.get("/api/v1/recipes/tahini-chicken").json()
    assert len(data["ingredients"]) == 2


def test_get_recipe_by_slug_ingredient_has_nutrition(client):
    data = client.get("/api/v1/recipes/tahini-chicken").json()
    chicken = next(i for i in data["ingredients"] if i.get("normalised") == "chicken thigh")
    assert chicken["nutrition"]["proteinPer100g"] == pytest.approx(17.4)


def test_get_recipe_by_slug_has_total_time_camel_case(client):
    data = client.get("/api/v1/recipes/tahini-chicken").json()
    assert "totalTimeMinutes" in data
    assert data["totalTimeMinutes"] == 45


def test_get_recipe_by_slug_not_found_returns_404(client):
    assert client.get("/api/v1/recipes/does-not-exist").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/ingredients/{ingredient}/nutrition
# ---------------------------------------------------------------------------


def test_get_ingredient_nutrition_returns_200(client):
    assert client.get("/api/v1/ingredients/tahini/nutrition").status_code == 200


def test_get_ingredient_nutrition_has_ingredient_name(client):
    data = client.get("/api/v1/ingredients/tahini/nutrition").json()
    assert data["ingredient"] == "tahini"


def test_get_ingredient_nutrition_has_protein(client):
    data = client.get("/api/v1/ingredients/tahini/nutrition").json()
    assert data["nutrition"]["proteinPer100g"] == pytest.approx(17.0)


def test_get_ingredient_nutrition_has_wikidata_qid(client):
    data = client.get("/api/v1/ingredients/tahini/nutrition").json()
    assert data["wikidataQid"] == "Q806723"


def test_get_ingredient_nutrition_not_found_returns_404(client):
    assert client.get("/api/v1/ingredients/nonexistent/nutrition").status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/ingredients/{ingredient}/wikidata
# ---------------------------------------------------------------------------


def test_get_ingredient_wikidata_returns_200(client):
    assert client.get("/api/v1/ingredients/tahini/wikidata").status_code == 200


def test_get_ingredient_wikidata_has_qid(client):
    data = client.get("/api/v1/ingredients/tahini/wikidata").json()
    assert data["wikidataQid"] == "Q806723"


def test_get_ingredient_wikidata_has_food_category(client):
    data = client.get("/api/v1/ingredients/tahini/wikidata").json()
    assert data["foodCategory"] == "condiment"


def test_get_ingredient_wikidata_has_dietary_flags(client):
    data = client.get("/api/v1/ingredients/tahini/wikidata").json()
    assert "vegan" in data["dietaryFlags"]


def test_get_ingredient_wikidata_not_found_returns_404(client):
    assert client.get("/api/v1/ingredients/nonexistent/wikidata").status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/query
# ---------------------------------------------------------------------------


def test_nl_query_returns_200(client_with_mock_llm):
    resp = client_with_mock_llm.post(
        "/api/v1/query", json={"question": "Show me middle-eastern recipes"}
    )
    assert resp.status_code == 200


def test_nl_query_echoes_question(client_with_mock_llm):
    data = client_with_mock_llm.post(
        "/api/v1/query", json={"question": "Show me middle-eastern recipes"}
    ).json()
    assert data["question"] == "Show me middle-eastern recipes"


def test_nl_query_returns_matching_results(client_with_mock_llm):
    data = client_with_mock_llm.post(
        "/api/v1/query", json={"question": "Show me middle-eastern recipes"}
    ).json()
    assert len(data["results"]) == 1
    assert data["results"][0]["slug"] == "tahini-chicken"


def test_nl_query_returns_interpreted_filters(client_with_mock_llm):
    data = client_with_mock_llm.post(
        "/api/v1/query", json={"question": "Show me middle-eastern recipes"}
    ).json()
    assert data["interpreted_filters"].get("cuisine") == "middle-eastern"
