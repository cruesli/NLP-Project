from backend.graph import RecipeKnowledgeGraph, save_graph, load_graph
from backend.models import Recipe, NutritionPer100g, WikidataEntity
from pathlib import Path

# Build a small graph
kg = RecipeKnowledgeGraph()
recipe = Recipe(slug="test-recipe", title="Test", cuisine="italian",
                ingredients=["chicken"], servings=2, total_time_minutes=30)
kg.add_recipe(recipe,
    normalised_map={"chicken": "chicken"},
    entity_map={"chicken": WikidataEntity(qid="Q123", uri="http://wikidata.org/entity/Q123", label="chicken", food_category="poultry")},
    nutrition_map={"chicken": NutritionPer100g(protein_per_100g=25.0, fat_per_100g=9.0, carbs_per_100g=0.0, kcal_per_100g=180.0)})

# Query
print(kg.get_all_recipes())
print(kg.get_recipe_by_slug("test-recipe"))
print(kg.filter_recipes(min_protein=5.0))

# Save/load roundtrip
save_graph(kg, Path("test.ttl"))
kg2 = load_graph(Path("test.ttl"))
print(kg2.get_all_recipes())