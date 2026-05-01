from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.ingest import (
    build_normalised_map,
    build_quantity_map,
    collect_unique_ingredients,
    run_ingest,
)
from backend.models import NutritionPer100g, Recipe, WikidataEntity


def _recipe(slug: str, ingredients: list) -> Recipe:
    return Recipe(slug=slug, title=slug.title(), cuisine="test", ingredients=ingredients)


def _write_recipe(path: Path, slug: str, ingredients: list) -> None:
    ing_yaml = "\n".join(f"  - {i}" for i in ingredients)
    (path / f"{slug}.md").write_text(
        f"---\ntitle: {slug}\ncuisine: test\ningredients:\n{ing_yaml}\n---\n"
    )


def _nd(name: str, qty=None):
    """Shorthand for a normaliser dict entry."""
    return {"name": name, "quantity_g": qty}


@pytest.fixture()
def recipes_dir(tmp_path):
    d = tmp_path / "recipes"
    d.mkdir()
    return d


# ── collect_unique_ingredients ──────────────────────────────────────────────

def test_collect_unique_returns_empty_for_no_recipes():
    assert collect_unique_ingredients([]) == []


def test_collect_unique_returns_empty_for_empty_ingredients():
    assert collect_unique_ingredients([_recipe("r", [])]) == []


def test_collect_unique_deduplicates_across_recipes():
    r1 = _recipe("r1", ["Pasta", "Eggs"])
    r2 = _recipe("r2", ["Pasta", "Cheese"])
    assert collect_unique_ingredients([r1, r2]) == ["Pasta", "Eggs", "Cheese"]


def test_collect_unique_preserves_insertion_order():
    r = _recipe("r", ["Eggs", "Flour", "Butter"])
    assert collect_unique_ingredients([r]) == ["Eggs", "Flour", "Butter"]


# ── build_normalised_map ─────────────────────────────────────────────────────

def test_build_normalised_map_basic():
    assert build_normalised_map(
        ["400g Pasta", "2 Eggs"],
        [_nd("pasta", 400.0), _nd("egg")],
    ) == {"400g Pasta": "pasta", "2 Eggs": "egg"}


def test_build_normalised_map_empty():
    assert build_normalised_map([], []) == {}


def test_build_normalised_map_length_mismatch_raises():
    with pytest.raises(ValueError):
        build_normalised_map(["a", "b"], [_nd("x")])


# ── build_quantity_map ───────────────────────────────────────────────────────

def test_build_quantity_map_basic():
    assert build_quantity_map(
        ["400g Pasta", "2 Eggs"],
        [_nd("pasta", 400.0), _nd("egg")],
    ) == {"400g Pasta": 400.0, "2 Eggs": None}


def test_build_quantity_map_empty():
    assert build_quantity_map([], []) == {}


def test_build_quantity_map_length_mismatch_raises():
    with pytest.raises(ValueError):
        build_quantity_map(["a", "b"], [_nd("x")])


def test_build_quantity_map_all_none():
    result = build_quantity_map(["salt to taste"], [_nd("salt")])
    assert result == {"salt to taste": None}


# ── run_ingest ────────────────────────────────────────────────────────────────

def test_run_ingest_creates_ttl_file(recipes_dir, tmp_path):
    _write_recipe(recipes_dir, "soup", ["Chicken", "Water"])
    out = tmp_path / "graph.ttl"
    with patch("backend.ingest.normalise_all", return_value=[_nd("chicken"), _nd("water")]), \
         patch("backend.ingest.link_ingredient", return_value=None), \
         patch("backend.ingest.fetch_nutrition", return_value=None):
        run_ingest(recipes_dir, out, llm_client=MagicMock())
    assert out.exists()


def test_run_ingest_deduplicates_before_normalise(recipes_dir, tmp_path):
    _write_recipe(recipes_dir, "r1", ["Pasta", "Eggs"])
    _write_recipe(recipes_dir, "r2", ["Pasta", "Cheese"])
    out = tmp_path / "graph.ttl"
    mock_normalise = MagicMock(return_value=[_nd("pasta", 400.0), _nd("egg"), _nd("cheese")])
    with patch("backend.ingest.normalise_all", mock_normalise), \
         patch("backend.ingest.link_ingredient", return_value=None), \
         patch("backend.ingest.fetch_nutrition", return_value=None):
        run_ingest(recipes_dir, out, llm_client=MagicMock())
    total_sent = sum(len(c.args[0]) for c in mock_normalise.call_args_list)
    assert total_sent == 3  # Pasta deduplicated, not 4


def test_run_ingest_calls_link_and_nutrition_per_unique_normalised(recipes_dir, tmp_path):
    _write_recipe(recipes_dir, "r1", ["Pasta", "Eggs"])
    _write_recipe(recipes_dir, "r2", ["Pasta", "Cheese"])
    out = tmp_path / "graph.ttl"
    mock_link = MagicMock(return_value=None)
    mock_nutr = MagicMock(return_value=None)
    with patch("backend.ingest.normalise_all", return_value=[_nd("pasta", 400.0), _nd("egg"), _nd("cheese")]), \
         patch("backend.ingest.link_ingredient", mock_link), \
         patch("backend.ingest.fetch_nutrition", mock_nutr):
        run_ingest(recipes_dir, out, llm_client=MagicMock())
    assert mock_link.call_count == 3
    assert mock_nutr.call_count == 3


def test_run_ingest_enrichment_written_to_graph(recipes_dir, tmp_path):
    _write_recipe(recipes_dir, "soup", ["Chicken"])
    out = tmp_path / "graph.ttl"
    entity = WikidataEntity(
        qid="Q192628",
        uri="http://www.wikidata.org/entity/Q192628",
        label="chicken",
        food_category="poultry",
    )
    nutr = NutritionPer100g(
        protein_per_100g=20.0, fat_per_100g=5.0,
        carbs_per_100g=0.0, kcal_per_100g=120.0,
    )
    with patch("backend.ingest.normalise_all", return_value=[_nd("chicken")]), \
         patch("backend.ingest.link_ingredient", return_value=entity), \
         patch("backend.ingest.fetch_nutrition", return_value=nutr):
        run_ingest(recipes_dir, out, llm_client=MagicMock())
    content = out.read_text()
    assert "Q192628" in content
    assert "20" in content


def test_run_ingest_batches_normalisation(recipes_dir, tmp_path):
    for i in range(5):
        _write_recipe(recipes_dir, f"r{i}", [f"Ingredient{i}"])
    out = tmp_path / "graph.ttl"
    mock_normalise = MagicMock(
        side_effect=lambda batch, _client: [_nd(f"ingredient{i}") for i in range(len(batch))]
    )
    with patch("backend.ingest.normalise_all", mock_normalise), \
         patch("backend.ingest.link_ingredient", return_value=None), \
         patch("backend.ingest.fetch_nutrition", return_value=None), \
         patch("backend.ingest._BATCH_SIZE", 2):
        run_ingest(recipes_dir, out, llm_client=MagicMock())
    # 5 ingredients with batch size 2 → 3 batches
    assert mock_normalise.call_count == 3


def test_run_ingest_quantity_written_to_graph(recipes_dir, tmp_path):
    _write_recipe(recipes_dir, "soup", ["400g Chicken"])
    out = tmp_path / "graph.ttl"
    with patch("backend.ingest.normalise_all", return_value=[_nd("chicken", 400.0)]), \
         patch("backend.ingest.link_ingredient", return_value=None), \
         patch("backend.ingest.fetch_nutrition", return_value=None):
        run_ingest(recipes_dir, out, llm_client=MagicMock())
    content = out.read_text()
    assert "quantityG" in content
