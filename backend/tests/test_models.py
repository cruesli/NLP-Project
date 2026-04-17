import pytest
from backend.models import (
    NutritionPer100g,
    NutritionPerServing,
    EnrichedIngredient,
    RecipeSummary,
    RecipeDetail,
    IngredientNutritionResponse,
    WikidataResponse,
    FilterResponse,
    QueryRequest,
    QueryResponse,
)


# --- NutritionPer100g ---

def test_nutrition_per_100g_required_fields():
    n = NutritionPer100g(
        protein_per_100g=17.4,
        fat_per_100g=9.6,
        carbs_per_100g=0.0,
        kcal_per_100g=177,
    )
    assert n.protein_per_100g == 17.4
    assert n.fat_per_100g == 9.6
    assert n.carbs_per_100g == 0.0
    assert n.kcal_per_100g == 177
    assert n.fibre_per_100g is None


def test_nutrition_per_100g_with_fibre():
    n = NutritionPer100g(
        protein_per_100g=8.9,
        fat_per_100g=2.6,
        carbs_per_100g=27.4,
        kcal_per_100g=164,
        fibre_per_100g=7.6,
    )
    assert n.fibre_per_100g == 7.6


def test_nutrition_per_100g_serializes_camel_case():
    n = NutritionPer100g(
        protein_per_100g=8.9, fat_per_100g=2.6, carbs_per_100g=27.4, kcal_per_100g=164
    )
    data = n.model_dump(by_alias=True)
    assert "proteinPer100g" in data
    assert "fatPer100g" in data
    assert "carbsPer100g" in data
    assert "kcalPer100g" in data


# --- NutritionPerServing ---

def test_nutrition_per_serving_fields():
    n = NutritionPerServing(protein_g=42.1, fat_g=18.3, carbs_g=55.4, kcal=610)
    assert n.protein_g == 42.1
    assert n.fat_g == 18.3
    assert n.carbs_g == 55.4
    assert n.kcal == 610


def test_nutrition_per_serving_serializes_camel_case():
    n = NutritionPerServing(protein_g=42.1, fat_g=18.3, carbs_g=55.4, kcal=610)
    data = n.model_dump(by_alias=True)
    assert "proteinG" in data
    assert "fatG" in data
    assert "carbsG" in data
    assert "kcal" in data


def test_nutrition_per_serving_partial_fields():
    n = NutritionPerServing(protein_g=38.5, kcal=520)
    assert n.protein_g == 38.5
    assert n.kcal == 520
    assert n.fat_g is None
    assert n.carbs_g is None


# --- EnrichedIngredient ---

def test_enriched_ingredient_raw_only():
    i = EnrichedIngredient(raw="400g Chicken")
    assert i.raw == "400g Chicken"
    assert i.normalised is None
    assert i.wikidata_qid is None
    assert i.food_category is None
    assert i.origin_country is None
    assert i.nutrition is None


def test_enriched_ingredient_fully_populated():
    n = NutritionPer100g(
        protein_per_100g=17.4, fat_per_100g=9.6, carbs_per_100g=0.0, kcal_per_100g=177
    )
    i = EnrichedIngredient(
        raw="400g Chicken",
        normalised="chicken thigh",
        wikidata_qid="Q192628",
        food_category="poultry",
        origin_country="United States",
        nutrition=n,
    )
    assert i.normalised == "chicken thigh"
    assert i.wikidata_qid == "Q192628"
    assert i.food_category == "poultry"
    assert i.origin_country == "United States"
    assert i.nutrition.kcal_per_100g == 177


def test_enriched_ingredient_serializes_camel_case():
    i = EnrichedIngredient(raw="Tahini", normalised="tahini", wikidata_qid="Q806723")
    data = i.model_dump(by_alias=True)
    assert "wikidataQid" in data
    assert "foodCategory" in data
    assert "originCountry" in data


# --- RecipeSummary ---

def test_recipe_summary_fields():
    r = RecipeSummary(
        slug="tahini-chicken-with-butternut-hummus-and-bulgur-salad",
        title="Tahini Chicken with Butternut Hummus and Bulgur Salad",
        cuisine="middle-eastern",
        total_time_minutes=45,
        tags=["Quick", "Healthy"],
    )
    assert r.slug == "tahini-chicken-with-butternut-hummus-and-bulgur-salad"
    assert r.total_time_minutes == 45
    assert r.tags == ["Quick", "Healthy"]


def test_recipe_summary_optional_fields():
    r = RecipeSummary(slug="simple", title="Simple", cuisine="italian")
    assert r.total_time_minutes is None
    assert r.tags == []


def test_recipe_summary_serializes_camel_case():
    r = RecipeSummary(slug="s", title="T", cuisine="c", total_time_minutes=30)
    data = r.model_dump(by_alias=True)
    assert "totalTimeMinutes" in data


# --- RecipeDetail ---

def test_recipe_detail_includes_ingredients_and_nutrition():
    n_per_serving = NutritionPerServing(protein_g=42.1, fat_g=18.3, carbs_g=55.4, kcal=610)
    ing = EnrichedIngredient(raw="400g Chicken", normalised="chicken thigh")
    r = RecipeDetail(
        slug="tahini-chicken",
        title="Tahini Chicken",
        cuisine="middle-eastern",
        servings=2,
        total_time_minutes=45,
        ingredients=[ing],
        nutrition_per_serving=n_per_serving,
    )
    assert r.servings == 2
    assert len(r.ingredients) == 1
    assert r.nutrition_per_serving.kcal == 610


def test_recipe_detail_defaults():
    r = RecipeDetail(slug="s", title="T", cuisine="c")
    assert r.servings is None
    assert r.ingredients == []
    assert r.nutrition_per_serving is None


def test_recipe_detail_serializes_camel_case():
    r = RecipeDetail(slug="s", title="T", cuisine="c", servings=4, total_time_minutes=20)
    data = r.model_dump(by_alias=True)
    assert "totalTimeMinutes" in data
    assert "nutritionPerServing" in data


# --- IngredientNutritionResponse ---

def test_ingredient_nutrition_response():
    n = NutritionPer100g(
        protein_per_100g=8.9, fat_per_100g=2.6, carbs_per_100g=27.4,
        kcal_per_100g=164, fibre_per_100g=7.6,
    )
    r = IngredientNutritionResponse(
        ingredient="chickpeas", wikidata_qid="Q23768", nutrition=n
    )
    assert r.ingredient == "chickpeas"
    assert r.wikidata_qid == "Q23768"
    assert r.nutrition.fibre_per_100g == 7.6


def test_ingredient_nutrition_response_serializes_camel_case():
    n = NutritionPer100g(protein_per_100g=1.0, fat_per_100g=0.1, carbs_per_100g=5.0, kcal_per_100g=25)
    r = IngredientNutritionResponse(ingredient="spinach", nutrition=n)
    data = r.model_dump(by_alias=True)
    assert "wikidataQid" in data
    assert "nutrition" in data


# --- WikidataResponse ---

def test_wikidata_response():
    r = WikidataResponse(
        ingredient="tahini",
        wikidata_qid="Q806723",
        wikidata_uri="http://www.wikidata.org/entity/Q806723",
        label="tahini",
        food_category="condiment",
        origin_country="Middle East",
        dietary_flags=["vegan", "vegetarian"],
    )
    assert r.wikidata_qid == "Q806723"
    assert r.dietary_flags == ["vegan", "vegetarian"]


def test_wikidata_response_optional_fields():
    r = WikidataResponse(ingredient="tahini")
    assert r.wikidata_qid is None
    assert r.wikidata_uri is None
    assert r.label is None
    assert r.food_category is None
    assert r.origin_country is None
    assert r.dietary_flags == []


def test_wikidata_response_serializes_camel_case():
    r = WikidataResponse(ingredient="tahini", wikidata_qid="Q806723")
    data = r.model_dump(by_alias=True)
    assert "wikidataQid" in data
    assert "wikidataUri" in data
    assert "foodCategory" in data
    assert "originCountry" in data
    assert "dietaryFlags" in data


# --- FilterResponse ---

def test_filter_response():
    result = RecipeSummary(
        slug="lebanese-chicken",
        title="Lebanese Chicken",
        cuisine="middle-eastern",
        total_time_minutes=20,
    )
    r = FilterResponse(
        filters_applied={"min_protein": 30, "max_time": 30, "cuisine": "middle-eastern"},
        count=1,
        results=[result],
    )
    assert r.count == 1
    assert r.results[0].slug == "lebanese-chicken"
    assert r.filters_applied["min_protein"] == 30


def test_filter_response_empty():
    r = FilterResponse(filters_applied={}, count=0, results=[])
    assert r.count == 0
    assert r.results == []


# --- QueryRequest ---

def test_query_request():
    q = QueryRequest(question="Show me a high-protein recipe that takes less than 30 minutes")
    assert "high-protein" in q.question


# --- QueryResponse ---

def test_query_response():
    result = RecipeSummary(
        slug="lebanese-chicken",
        title="Lebanese Chicken, Hummus and Grilled Vegetables",
        cuisine="middle-eastern",
        total_time_minutes=20,
    )
    r = QueryResponse(
        question="Show me a high-protein recipe",
        interpreted_filters={"min_protein_per_serving_g": 30, "max_total_time_minutes": 30},
        results=[result],
    )
    assert r.interpreted_filters["min_protein_per_serving_g"] == 30
    assert len(r.results) == 1


def test_query_response_empty_results():
    r = QueryResponse(question="impossible query", interpreted_filters={}, results=[])
    assert r.results == []
