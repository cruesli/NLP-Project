from pathlib import Path

import pytest

from backend.models import Recipe
from backend.parser import load_all_recipes, parse_recipe

RECIPES_DIR = Path(__file__).parents[2] / "src" / "content" / "recipes"

# --- helpers ---

def write_recipe(tmp_path: Path, name: str, frontmatter: str, body: str = "") -> Path:
    content = f"---\n{frontmatter}---\n{body}"
    path = tmp_path / f"{name}.md"
    path.write_text(content)
    return path


# --- unit tests with synthetic fixtures ---

def test_slug_from_filename(tmp_path):
    path = write_recipe(
        tmp_path,
        "my-test-recipe",
        "title: Test\ncuisine: italian\n",
    )
    recipe = parse_recipe(path)
    assert recipe.slug == "my-test-recipe"


def test_parse_simple_ingredients(tmp_path):
    path = write_recipe(
        tmp_path,
        "simple",
        "title: Simple\ncuisine: italian\ningredients: |-\n  - 400g Pasta\n  - 2 Eggs\n",
    )
    recipe = parse_recipe(path)
    assert recipe.ingredients == ["400g Pasta", "2 Eggs"]


def test_parse_grouped_ingredients(tmp_path):
    frontmatter = (
        "title: Grouped\n"
        "cuisine: middle-eastern\n"
        "ingredients: |-\n"
        "  Marinade:\n"
        "  - 400g Chicken\n"
        "  - Tahini\n"
        "\n"
        "  Salad:\n"
        "  - Bulgur\n"
        "  - Parsley\n"
    )
    path = write_recipe(tmp_path, "grouped", frontmatter)
    recipe = parse_recipe(path)
    assert "Marinade:" not in recipe.ingredients
    assert "Salad:" not in recipe.ingredients
    assert "400g Chicken" in recipe.ingredients
    assert "Tahini" in recipe.ingredients
    assert "Bulgur" in recipe.ingredients
    assert "Parsley" in recipe.ingredients


def test_optional_fields_absent(tmp_path):
    path = write_recipe(tmp_path, "minimal", "title: Min\ncuisine: italian\n")
    recipe = parse_recipe(path)
    assert recipe.servings is None
    assert recipe.total_time_minutes is None
    assert recipe.food_type is None
    assert recipe.image is None
    assert recipe.ingredients == []
    assert recipe.tags == []


def test_tags_filters_empty_strings(tmp_path):
    path = write_recipe(
        tmp_path,
        "tagged",
        'title: Tagged\ncuisine: italian\ntags:\n  - Quick\n  - ""\n  - Healthy\n',
    )
    recipe = parse_recipe(path)
    assert recipe.tags == ["Quick", "Healthy"]
    assert "" not in recipe.tags


def test_body_captured(tmp_path):
    path = write_recipe(
        tmp_path,
        "with-body",
        "title: Body\ncuisine: italian\n",
        body="1. Boil water\n2. Add pasta\n",
    )
    recipe = parse_recipe(path)
    assert "Boil water" in recipe.body
    assert "Add pasta" in recipe.body


def test_optional_fields_present(tmp_path):
    path = write_recipe(
        tmp_path,
        "full",
        (
            "title: Full\n"
            "cuisine: mexican\n"
            "foodType: Taco\n"
            "servings: 4\n"
            "totalTimeMinutes: 60\n"
            "image: /images/test.jpg\n"
        ),
    )
    recipe = parse_recipe(path)
    assert recipe.food_type == "Taco"
    assert recipe.servings == 4
    assert recipe.total_time_minutes == 60
    assert recipe.image == "/images/test.jpg"


# --- integration tests against real recipe files ---

def test_real_carnitas():
    recipe = parse_recipe(RECIPES_DIR / "carnitas.md")
    assert recipe.slug == "carnitas"
    assert recipe.cuisine == "mexican"
    assert recipe.servings == 15
    assert recipe.total_time_minutes == 300
    assert any("Pork shoulder" in i for i in recipe.ingredients)


def test_real_tahini_excludes_group_headers():
    recipe = parse_recipe(
        RECIPES_DIR / "tahini-chicken-with-butternut-hummus-and-bulgur-salad.md"
    )
    assert any("400g Chicken" in i for i in recipe.ingredients)
    assert not any(i.endswith(":") for i in recipe.ingredients)


def test_load_all_recipes():
    recipes = load_all_recipes(RECIPES_DIR)
    assert len(recipes) >= 5
    slugs = {r.slug for r in recipes}
    assert "carnitas" in slugs
    assert "pasta-bolognese" in slugs


def test_load_all_recipes_returns_recipe_objects():
    recipes = load_all_recipes(RECIPES_DIR)
    assert all(isinstance(r, Recipe) for r in recipes)
