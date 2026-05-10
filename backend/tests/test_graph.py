"""Tests for backend/graph.py — written before implementation (TDD)."""

import pytest
from pathlib import Path

from rdflib import Graph, Namespace, RDF, URIRef

from backend.models import (
    EnrichedIngredient,
    FilterResponse,
    NutritionPer100g,
    NutritionPerServing,
    Recipe,
    RecipeDetail,
    RecipeSummary,
    WikidataEntity,
)
from backend.graph import RecipeKnowledgeGraph, load_graph, save_graph

EX = Namespace("http://example.org/recipe-kg/")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nutrition_chicken():
    return NutritionPer100g(
        protein_per_100g=17.4,
        fat_per_100g=9.6,
        carbs_per_100g=0.0,
        kcal_per_100g=177.0,
        fibre_per_100g=0.3,
        sugar_per_100g=0.0,
        saturated_fat_per_100g=2.6,
        sodium_mg_per_100g=79.0,
        cholesterol_mg_per_100g=91.0,
    )


@pytest.fixture
def nutrition_tahini():
    return NutritionPer100g(
        protein_per_100g=17.0,
        fat_per_100g=53.0,
        carbs_per_100g=21.0,
        kcal_per_100g=595.0,
        fibre_per_100g=9.3,
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
def recipe_tahini():
    return Recipe(
        slug="tahini-chicken",
        title="Tahini Chicken",
        cuisine="middle-eastern",
        food_type="Main",
        tags=["Quick", "Healthy"],
        servings=2,
        total_time_minutes=45,
        ingredients=["400g Chicken thighs", "2 tbsp Tahini"],
    )


@pytest.fixture
def recipe_pasta():
    return Recipe(
        slug="pasta-bolognese",
        title="Pasta Bolognese",
        cuisine="italian",
        food_type="Main",
        tags=["Comfort"],
        servings=4,
        total_time_minutes=90,
        ingredients=["500g Pasta"],
    )


@pytest.fixture
def normalised_map():
    return {
        "400g Chicken thighs": "chicken thigh",
        "2 tbsp Tahini": "tahini",
    }


@pytest.fixture
def entity_map(entity_chicken, entity_tahini):
    return {
        "chicken thigh": entity_chicken,
        "tahini": entity_tahini,
    }


@pytest.fixture
def nutrition_map(nutrition_chicken, nutrition_tahini):
    return {
        "chicken thigh": nutrition_chicken,
        "tahini": nutrition_tahini,
    }


@pytest.fixture
def kg(recipe_tahini, normalised_map, entity_map, nutrition_map):
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe_tahini, normalised_map, entity_map, nutrition_map)
    return g


@pytest.fixture
def kg_two_recipes(recipe_tahini, recipe_pasta, normalised_map, entity_map, nutrition_map):
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe_tahini, normalised_map, entity_map, nutrition_map)
    g.add_recipe(
        recipe_pasta,
        {"500g Pasta": "pasta"},
        {},
        {},
    )
    return g


# ---------------------------------------------------------------------------
# Graph construction — recipe node
# ---------------------------------------------------------------------------


def test_recipe_node_has_rdf_type(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    assert (recipe_node, RDF.type, EX.Recipe) in kg.graph


def test_recipe_node_has_title(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    titles = list(kg.graph.objects(recipe_node, EX.title))
    assert len(titles) == 1
    assert str(titles[0]) == "Tahini Chicken"


def test_recipe_node_has_slug(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    slugs = list(kg.graph.objects(recipe_node, EX.slug))
    assert str(slugs[0]) == "tahini-chicken"


def test_recipe_node_has_cuisine(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    cuisines = list(kg.graph.objects(recipe_node, EX.cuisine))
    assert str(cuisines[0]) == "middle-eastern"


def test_recipe_node_has_food_type(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    food_types = list(kg.graph.objects(recipe_node, EX.foodType))
    assert str(food_types[0]) == "Main"


def test_recipe_node_has_servings(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    servings = list(kg.graph.objects(recipe_node, EX.servings))
    assert int(servings[0]) == 2


def test_recipe_node_has_total_time(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    times = list(kg.graph.objects(recipe_node, EX.totalTimeMinutes))
    assert int(times[0]) == 45


def test_recipe_node_has_tags(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    tags = {str(t) for t in kg.graph.objects(recipe_node, EX.tag)}
    assert tags == {"Quick", "Healthy"}


def test_recipe_without_optional_fields_still_added():
    minimal = Recipe(slug="minimal", title="Minimal", cuisine="italian")
    g = RecipeKnowledgeGraph()
    g.add_recipe(minimal, {}, {}, {})
    assert (EX["recipe_minimal"], RDF.type, EX.Recipe) in g.graph


# ---------------------------------------------------------------------------
# Graph construction — hasIngredient links
# ---------------------------------------------------------------------------


def test_recipe_has_ingredient_links(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    ingredients = list(kg.graph.objects(recipe_node, EX.hasIngredient))
    assert len(ingredients) == 2


def test_ingredient_node_has_raw_string(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    ing_nodes = list(kg.graph.objects(recipe_node, EX.hasIngredient))
    raw_strings = set()
    for ing in ing_nodes:
        for raw in kg.graph.objects(ing, EX.rawString):
            raw_strings.add(str(raw))
    assert "400g Chicken thighs" in raw_strings
    assert "2 tbsp Tahini" in raw_strings


def test_ingredient_node_has_normalised_name(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    ing_nodes = list(kg.graph.objects(recipe_node, EX.hasIngredient))
    normalised = set()
    for ing in ing_nodes:
        for n in kg.graph.objects(ing, EX.normalisedName):
            normalised.add(str(n))
    assert "chicken thigh" in normalised
    assert "tahini" in normalised


# ---------------------------------------------------------------------------
# Graph construction — ingredient Wikidata properties
# ---------------------------------------------------------------------------


def test_ingredient_has_wikidata_qid(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    qids = set()
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for qid in kg.graph.objects(ing, EX.wikidataQid):
            qids.add(str(qid))
    assert "Q192628" in qids


def test_ingredient_has_wikidata_uri(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    uris = set()
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for uri in kg.graph.objects(ing, EX.wikidataUri):
            uris.add(str(uri))
    assert "http://www.wikidata.org/entity/Q192628" in uris


def test_ingredient_has_food_category(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    categories = set()
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for cat in kg.graph.objects(ing, EX.foodCategory):
            categories.add(str(cat))
    assert "poultry" in categories


def test_ingredient_has_origin_country(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    countries = set()
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for c in kg.graph.objects(ing, EX.originCountry):
            countries.add(str(c))
    assert "United States" in countries


def test_ingredient_has_dietary_flags(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    flags = set()
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for f in kg.graph.objects(ing, EX.dietaryFlag):
            flags.add(str(f))
    assert "vegan" in flags
    assert "vegetarian" in flags


def test_ingredient_without_entity_has_no_wikidata_triples():
    recipe = Recipe(slug="plain", title="Plain", cuisine="italian", ingredients=["500g Pasta"])
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"500g Pasta": "pasta"}, {}, {})
    recipe_node = EX["recipe_plain"]
    for ing in g.graph.objects(recipe_node, EX.hasIngredient):
        qids = list(g.graph.objects(ing, EX.wikidataQid))
        assert qids == []


# ---------------------------------------------------------------------------
# Graph construction — nutrition node
# ---------------------------------------------------------------------------


def test_ingredient_links_to_nutrition_node(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        has_nutrition = list(kg.graph.objects(ing, EX.hasNutrition))
        assert len(has_nutrition) == 1


def test_nutrition_node_has_protein(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    proteins = []
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for nutr in kg.graph.objects(ing, EX.hasNutrition):
            for p in kg.graph.objects(nutr, EX.proteinPer100g):
                proteins.append(float(p))
    assert any(p == pytest.approx(17.4) for p in proteins)


def test_nutrition_node_has_fat(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        norm = list(kg.graph.objects(ing, EX.normalisedName))
        if norm and str(norm[0]) == "chicken thigh":
            for nutr in kg.graph.objects(ing, EX.hasNutrition):
                fats = list(kg.graph.objects(nutr, EX.fatPer100g))
                assert float(fats[0]) == pytest.approx(9.6)


def test_nutrition_node_has_carbs(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        norm = list(kg.graph.objects(ing, EX.normalisedName))
        if norm and str(norm[0]) == "chicken thigh":
            for nutr in kg.graph.objects(ing, EX.hasNutrition):
                carbs = list(kg.graph.objects(nutr, EX.carbsPer100g))
                assert float(carbs[0]) == pytest.approx(0.0)


def test_nutrition_node_has_kcal(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        norm = list(kg.graph.objects(ing, EX.normalisedName))
        if norm and str(norm[0]) == "chicken thigh":
            for nutr in kg.graph.objects(ing, EX.hasNutrition):
                kcals = list(kg.graph.objects(nutr, EX.kcalPer100g))
                assert float(kcals[0]) == pytest.approx(177.0)


def test_nutrition_node_has_optional_fields(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    fibre_found = False
    sodium_found = False
    cholesterol_found = False
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        for nutr in kg.graph.objects(ing, EX.hasNutrition):
            if list(kg.graph.objects(nutr, EX.fibrePer100g)):
                fibre_found = True
            if list(kg.graph.objects(nutr, EX.sodiumMgPer100g)):
                sodium_found = True
            if list(kg.graph.objects(nutr, EX.cholesterolMgPer100g)):
                cholesterol_found = True
    assert fibre_found
    assert sodium_found
    assert cholesterol_found


def test_ingredient_without_nutrition_has_no_nutrition_node():
    recipe = Recipe(slug="plain", title="Plain", cuisine="italian", ingredients=["500g Pasta"])
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"500g Pasta": "pasta"}, {}, {})
    recipe_node = EX["recipe_plain"]
    for ing in g.graph.objects(recipe_node, EX.hasIngredient):
        nutrs = list(g.graph.objects(ing, EX.hasNutrition))
        assert nutrs == []


# ---------------------------------------------------------------------------
# get_all_recipes
# ---------------------------------------------------------------------------


def test_get_all_recipes_returns_list(kg):
    result = kg.get_all_recipes()
    assert isinstance(result, list)


def test_get_all_recipes_returns_recipe_summary_instances(kg):
    result = kg.get_all_recipes()
    assert all(isinstance(r, RecipeSummary) for r in result)


def test_get_all_recipes_returns_one_recipe(kg):
    assert len(kg.get_all_recipes()) == 1


def test_get_all_recipes_returns_two_recipes(kg_two_recipes):
    assert len(kg_two_recipes.get_all_recipes()) == 2


def test_get_all_recipes_summary_has_correct_slug(kg):
    summaries = kg.get_all_recipes()
    assert summaries[0].slug == "tahini-chicken"


def test_get_all_recipes_summary_has_correct_title(kg):
    summaries = kg.get_all_recipes()
    assert summaries[0].title == "Tahini Chicken"


def test_get_all_recipes_summary_has_correct_cuisine(kg):
    summaries = kg.get_all_recipes()
    assert summaries[0].cuisine == "middle-eastern"


def test_get_all_recipes_summary_has_correct_total_time(kg):
    summaries = kg.get_all_recipes()
    assert summaries[0].total_time_minutes == 45


def test_get_all_recipes_summary_has_tags(kg):
    summaries = kg.get_all_recipes()
    assert set(summaries[0].tags) == {"Quick", "Healthy"}


def test_get_all_recipes_empty_graph():
    g = RecipeKnowledgeGraph()
    assert g.get_all_recipes() == []


# ---------------------------------------------------------------------------
# get_recipe_by_slug
# ---------------------------------------------------------------------------


def test_get_recipe_by_slug_returns_recipe_detail(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert isinstance(result, RecipeDetail)


def test_get_recipe_by_slug_returns_none_for_unknown(kg):
    assert kg.get_recipe_by_slug("does-not-exist") is None


def test_get_recipe_by_slug_has_correct_slug(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.slug == "tahini-chicken"


def test_get_recipe_by_slug_has_correct_title(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.title == "Tahini Chicken"


def test_get_recipe_by_slug_has_correct_cuisine(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.cuisine == "middle-eastern"


def test_get_recipe_by_slug_has_correct_servings(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.servings == 2


def test_get_recipe_by_slug_has_correct_total_time(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.total_time_minutes == 45


def test_get_recipe_by_slug_has_two_ingredients(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert len(result.ingredients) == 2


def test_get_recipe_by_slug_ingredient_has_raw(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    raws = {i.raw for i in result.ingredients}
    assert "400g Chicken thighs" in raws
    assert "2 tbsp Tahini" in raws


def test_get_recipe_by_slug_ingredient_has_normalised(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    normalised = {i.normalised for i in result.ingredients}
    assert "chicken thigh" in normalised
    assert "tahini" in normalised


def test_get_recipe_by_slug_ingredient_has_wikidata_qid(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    qids = {i.wikidata_qid for i in result.ingredients}
    assert "Q192628" in qids
    assert "Q806723" in qids


def test_get_recipe_by_slug_ingredient_has_food_category(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    cats = {i.food_category for i in result.ingredients}
    assert "poultry" in cats


def test_get_recipe_by_slug_ingredient_has_origin_country(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    countries = {i.origin_country for i in result.ingredients}
    assert "United States" in countries


def test_get_recipe_by_slug_ingredient_has_nutrition(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    chicken = next(i for i in result.ingredients if i.normalised == "chicken thigh")
    assert chicken.nutrition is not None
    assert chicken.nutrition.protein_per_100g == pytest.approx(17.4)
    assert chicken.nutrition.fat_per_100g == pytest.approx(9.6)
    assert chicken.nutrition.kcal_per_100g == pytest.approx(177.0)


def test_get_recipe_by_slug_ingredient_without_nutrition_is_none():
    recipe = Recipe(slug="plain", title="Plain", cuisine="italian", ingredients=["500g Pasta"])
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"500g Pasta": "pasta"}, {}, {})
    result = g.get_recipe_by_slug("plain")
    assert result.ingredients[0].nutrition is None


def test_get_recipe_by_slug_has_nutrition_per_serving(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.nutrition_per_serving is not None
    assert result.nutrition_per_serving.protein_g is not None
    assert result.nutrition_per_serving.kcal is not None


def test_get_recipe_by_slug_nutrition_per_serving_is_none_without_data():
    recipe = Recipe(slug="plain", title="Plain", cuisine="italian", servings=2,
                    ingredients=["500g Pasta"])
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"500g Pasta": "pasta"}, {}, {})
    result = g.get_recipe_by_slug("plain")
    assert result.nutrition_per_serving is None


# ---------------------------------------------------------------------------
# filter_recipes
# ---------------------------------------------------------------------------


def test_filter_by_cuisine_returns_match(kg_two_recipes):
    result = kg_two_recipes.filter_recipes(cuisine="middle-eastern")
    assert result.count == 1
    assert result.results[0].slug == "tahini-chicken"


def test_filter_by_cuisine_no_match_returns_empty(kg_two_recipes):
    result = kg_two_recipes.filter_recipes(cuisine="japanese")
    assert result.count == 0
    assert result.results == []


def test_filter_by_max_time_returns_match(kg_two_recipes):
    result = kg_two_recipes.filter_recipes(max_time=60)
    slugs = {r.slug for r in result.results}
    assert "tahini-chicken" in slugs
    assert "pasta-bolognese" not in slugs


def test_filter_by_max_time_includes_equal(kg_two_recipes):
    result = kg_two_recipes.filter_recipes(max_time=45)
    slugs = {r.slug for r in result.results}
    assert "tahini-chicken" in slugs


def test_filter_by_dietary_returns_recipes_with_flag(kg_two_recipes):
    result = kg_two_recipes.filter_recipes(dietary="vegan")
    slugs = {r.slug for r in result.results}
    assert "tahini-chicken" in slugs


def test_filter_by_dietary_no_match(kg_two_recipes):
    result = kg_two_recipes.filter_recipes(dietary="halal")
    assert result.count == 0


def test_filter_no_params_returns_all(kg_two_recipes):
    result = kg_two_recipes.filter_recipes()
    assert result.count == 2


def test_filter_returns_filter_response(kg):
    result = kg.filter_recipes(cuisine="middle-eastern")
    assert isinstance(result, FilterResponse)


def test_filter_response_has_filters_applied(kg):
    result = kg.filter_recipes(cuisine="middle-eastern", max_time=60)
    assert result.filters_applied.get("cuisine") == "middle-eastern"
    assert result.filters_applied.get("max_time") == 60


def test_filter_response_omits_none_filters(kg):
    result = kg.filter_recipes(cuisine="middle-eastern")
    assert "min_protein" not in result.filters_applied
    assert "max_kcal" not in result.filters_applied


def test_filter_results_are_recipe_summaries(kg):
    result = kg.filter_recipes()
    assert all(isinstance(r, RecipeSummary) for r in result.results)


def test_filter_by_min_protein_returns_match(kg):
    # tahini-chicken has 2 ingredients with combined protein 17.4+17.0=34.4, /2 servings=17.2
    result = kg.filter_recipes(min_protein=10.0)
    assert result.count == 1


def test_filter_by_min_protein_excludes_low_protein():
    recipe = Recipe(slug="light", title="Light Salad", cuisine="italian",
                    servings=1, ingredients=["Lettuce"])
    nutrition_lettuce = NutritionPer100g(
        protein_per_100g=1.4,
        fat_per_100g=0.2,
        carbs_per_100g=2.9,
        kcal_per_100g=15.0,
    )
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"Lettuce": "lettuce"}, {}, {"lettuce": nutrition_lettuce})
    result = g.filter_recipes(min_protein=50.0)
    assert result.count == 0


def test_filter_by_max_kcal_returns_match(kg):
    result = kg.filter_recipes(max_kcal=10000.0)
    assert result.count == 1


def test_filter_by_max_kcal_excludes_high_kcal():
    recipe = Recipe(slug="heavy", title="Heavy Dish", cuisine="italian",
                    servings=1, ingredients=["Butter"])
    nutrition_butter = NutritionPer100g(
        protein_per_100g=0.9,
        fat_per_100g=81.0,
        carbs_per_100g=0.1,
        kcal_per_100g=717.0,
    )
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"Butter": "butter"}, {}, {"butter": nutrition_butter})
    result = g.filter_recipes(max_kcal=100.0)
    assert result.count == 0


# ---------------------------------------------------------------------------
# save_graph / load_graph
# ---------------------------------------------------------------------------


def test_save_graph_creates_file(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    assert path.exists()
    assert path.stat().st_size > 0


def test_save_graph_creates_valid_turtle(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    g = Graph()
    g.parse(str(path), format="turtle")
    assert len(g) > 0


def test_load_graph_returns_recipe_knowledge_graph(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    loaded = load_graph(path)
    assert isinstance(loaded, RecipeKnowledgeGraph)


def test_load_graph_preserves_recipe_count(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    loaded = load_graph(path)
    assert len(loaded.get_all_recipes()) == 1


def test_load_graph_preserves_recipe_slug(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    loaded = load_graph(path)
    slugs = {r.slug for r in loaded.get_all_recipes()}
    assert "tahini-chicken" in slugs


def test_load_graph_preserves_recipe_detail(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    loaded = load_graph(path)
    detail = loaded.get_recipe_by_slug("tahini-chicken")
    assert detail is not None
    assert detail.title == "Tahini Chicken"
    assert len(detail.ingredients) == 2


def test_load_graph_preserves_nutrition(kg, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg, path)
    loaded = load_graph(path)
    detail = loaded.get_recipe_by_slug("tahini-chicken")
    chicken = next(i for i in detail.ingredients if i.normalised == "chicken thigh")
    assert chicken.nutrition.protein_per_100g == pytest.approx(17.4)


def test_load_graph_preserves_filter_capability(kg_two_recipes, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg_two_recipes, path)
    loaded = load_graph(path)
    result = loaded.filter_recipes(cuisine="middle-eastern")
    assert result.count == 1
    assert result.results[0].slug == "tahini-chicken"


# ---------------------------------------------------------------------------
# quantity_g — storage and weighted nutrition
# ---------------------------------------------------------------------------


@pytest.fixture
def quantity_map():
    # 400g chicken, 2 tbsp (30g) tahini
    return {"400g Chicken thighs": 400.0, "2 tbsp Tahini": 30.0}


@pytest.fixture
def kg_with_quantities(recipe_tahini, normalised_map, entity_map, nutrition_map, quantity_map):
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe_tahini, normalised_map, entity_map, nutrition_map, quantity_map)
    return g


def test_ingredient_has_quantity_g_when_provided(kg_with_quantities):
    recipe_node = EX["recipe_tahini-chicken"]
    qtys = set()
    for ing in kg_with_quantities.graph.objects(recipe_node, EX.hasIngredient):
        for qty in kg_with_quantities.graph.objects(ing, EX.quantityG):
            qtys.add(float(qty))
    assert 400.0 in qtys
    assert 30.0 in qtys


def test_ingredient_has_no_quantity_g_without_map(kg):
    recipe_node = EX["recipe_tahini-chicken"]
    for ing in kg.graph.objects(recipe_node, EX.hasIngredient):
        assert list(kg.graph.objects(ing, EX.quantityG)) == []


def test_approx_protein_per_serving_uses_quantity_weight(kg_with_quantities):
    # chicken: 400g * (17.4/100) = 69.6; tahini: 30g * (17.0/100) = 5.1; total/2 = 37.35
    recipe_node = EX["recipe_tahini-chicken"]
    vals = list(kg_with_quantities.graph.objects(recipe_node, EX.approxProteinPerServing))
    assert float(vals[0]) == pytest.approx(37.35)


def test_approx_kcal_per_serving_uses_quantity_weight(kg_with_quantities):
    # chicken: 400g * (177.0/100) = 708.0; tahini: 30g * (595.0/100) = 178.5; total/2 = 443.25
    recipe_node = EX["recipe_tahini-chicken"]
    vals = list(kg_with_quantities.graph.objects(recipe_node, EX.approxKcalPerServing))
    assert float(vals[0]) == pytest.approx(443.25)


def test_approx_protein_fallback_factor_one_without_quantities(kg):
    # factor=1.0 for both: (17.4 + 17.0) / 2 = 17.2
    recipe_node = EX["recipe_tahini-chicken"]
    vals = list(kg.graph.objects(recipe_node, EX.approxProteinPerServing))
    assert float(vals[0]) == pytest.approx(17.2)


def test_get_recipe_by_slug_ingredient_has_quantity_g(kg_with_quantities):
    result = kg_with_quantities.get_recipe_by_slug("tahini-chicken")
    chicken = next(i for i in result.ingredients if i.normalised == "chicken thigh")
    assert chicken.quantity_g == pytest.approx(400.0)
    tahini = next(i for i in result.ingredients if i.normalised == "tahini")
    assert tahini.quantity_g == pytest.approx(30.0)


def test_get_recipe_by_slug_ingredient_quantity_g_none_without_map(kg):
    result = kg.get_recipe_by_slug("tahini-chicken")
    for ing in result.ingredients:
        assert ing.quantity_g is None


def test_get_recipe_by_slug_nutrition_per_serving_uses_quantity_weight(kg_with_quantities):
    # protein: (400 * 17.4/100 + 30 * 17.0/100) / 2 = (69.6 + 5.1) / 2 = 37.35
    result = kg_with_quantities.get_recipe_by_slug("tahini-chicken")
    assert result.nutrition_per_serving.protein_g == pytest.approx(37.35)


def test_get_recipe_by_slug_nutrition_per_serving_fallback_without_quantities(kg):
    # factor=1.0 for both: (17.4 + 17.0) / 2 = 17.2
    result = kg.get_recipe_by_slug("tahini-chicken")
    assert result.nutrition_per_serving.protein_g == pytest.approx(17.2)


def test_load_graph_preserves_quantity_g(kg_with_quantities, tmp_path):
    path = tmp_path / "graph.ttl"
    save_graph(kg_with_quantities, path)
    loaded = load_graph(path)
    detail = loaded.get_recipe_by_slug("tahini-chicken")
    chicken = next(i for i in detail.ingredients if i.normalised == "chicken thigh")
    assert chicken.quantity_g == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# get_all_recipes — missing-triple safety (change 5)
# ---------------------------------------------------------------------------


def test_get_all_recipes_skips_recipe_node_missing_slug(kg):
    from rdflib import Literal
    from backend.graph import EX
    # Inject a recipe node that is missing the slug triple
    broken = EX["recipe_broken"]
    kg.graph.add((broken, EX["type"], EX.Recipe))  # uses rdf:type indirectly via subjects
    # Actually add rdf:type so the iterator sees it but omit slug/title/cuisine
    from rdflib import RDF
    kg.graph.add((broken, RDF.type, EX.Recipe))
    # No slug, title, or cuisine → should be silently skipped
    summaries = kg.get_all_recipes()
    slugs = {s.slug for s in summaries}
    assert "broken" not in slugs
    assert "tahini-chicken" in slugs


# ---------------------------------------------------------------------------
# get_ingredient_wikidata — stored label (change 6)
# ---------------------------------------------------------------------------


def test_get_ingredient_wikidata_returns_stored_label(kg):
    result = kg.get_ingredient_wikidata("tahini")
    assert result is not None
    # The stored label comes from entity_tahini.label ("tahini"), not the normalised name
    assert result.label == "tahini"


def test_get_ingredient_wikidata_label_differs_from_normalised_name():
    entity = WikidataEntity(
        qid="Q192628",
        uri="http://www.wikidata.org/entity/Q192628",
        label="chicken thigh (poultry)",  # differs from normalised name
        food_category="poultry",
    )
    recipe = Recipe(
        slug="test-label",
        title="Label Test",
        cuisine="italian",
        ingredients=["raw chicken"],
    )
    g = RecipeKnowledgeGraph()
    g.add_recipe(recipe, {"raw chicken": "chicken"}, {"chicken": entity}, {})
    result = g.get_ingredient_wikidata("chicken")
    assert result is not None
    assert result.label == "chicken thigh (poultry)"
