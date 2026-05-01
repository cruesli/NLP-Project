from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from backend.entity_linker import link_ingredient
from backend.graph import RecipeKnowledgeGraph, save_graph
from backend.models import NutritionPer100g, Recipe, WikidataEntity
from backend.normaliser import make_client, normalise_all
from backend.nutrition import fetch_nutrition
from backend.parser import load_all_recipes

_BATCH_SIZE = 50


def collect_unique_ingredients(recipes: List[Recipe]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for recipe in recipes:
        for ing in recipe.ingredients:
            if ing not in seen:
                seen.add(ing)
                result.append(ing)
    return result


def build_normalised_map(raw: List[str], normalised: List[Dict[str, Any]]) -> Dict[str, str]:
    if len(raw) != len(normalised):
        raise ValueError(
            f"Normaliser returned {len(normalised)} results for {len(raw)} inputs"
        )
    return {r: n["name"] for r, n in zip(raw, normalised)}


def build_quantity_map(raw: List[str], normalised: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    if len(raw) != len(normalised):
        raise ValueError(
            f"Normaliser returned {len(normalised)} results for {len(raw)} inputs"
        )
    return {r: n.get("quantity_g") for r, n in zip(raw, normalised)}


def run_ingest(
    recipes_dir: Path,
    output_path: Path,
    *,
    llm_client=None,
    http_session: Optional[requests.Session] = None,
) -> None:
    load_dotenv(Path.home() / ".env")

    # parse
    print("Parsing recipes...")
    recipes = load_all_recipes(recipes_dir)
    print(f"  {len(recipes)} recipes parsed")

    # collect unique raw ingredients
    unique_raw = collect_unique_ingredients(recipes)
    print(f"  {len(unique_raw)} unique raw ingredients")

    # normalise in batches
    print("Normalising ingredients...")
    if llm_client is None:
        llm_client = make_client()
    normalised_list: List[Dict[str, Any]] = []
    for i in range(0, len(unique_raw), _BATCH_SIZE):
        batch = unique_raw[i : i + _BATCH_SIZE]
        batch_result = normalise_all(batch, llm_client)
        # Align length with input in case LLM returns wrong count
        if len(batch_result) > len(batch):
            batch_result = batch_result[: len(batch)]
        elif len(batch_result) < len(batch):
            for j in range(len(batch_result), len(batch)):
                batch_result.append({"name": batch[j].lower(), "quantity_g": None})
        normalised_list.extend(batch_result)
        print(f"  normalised {min(i + _BATCH_SIZE, len(unique_raw))}/{len(unique_raw)}")
    normalised_map = build_normalised_map(unique_raw, normalised_list)
    quantity_map = build_quantity_map(unique_raw, normalised_list)

    # unique normalised names (preserving order)
    unique_normalised: List[str] = list(dict.fromkeys(n["name"] for n in normalised_list))
    print(f"  {len(unique_normalised)} unique normalised names")

    # entity linking
    print("Linking entities to Wikidata...")
    if http_session is None:
        http_session = requests.Session()
    entity_map: Dict[str, Optional[WikidataEntity]] = {}
    for norm in unique_normalised:
        entity = link_ingredient(norm, http_session)
        entity_map[norm] = entity
        status = entity.qid if entity else "not found"
        print(f"  {norm}: {status}")

    # nutrition
    print("Fetching nutrition from USDA...")
    nutrition_map: Dict[str, Optional[NutritionPer100g]] = {}
    for norm in unique_normalised:
        try:
            nutrition = fetch_nutrition(norm, http_session)
        except requests.HTTPError as exc:
            print(f"  {norm}: HTTP error {exc.response.status_code}, skipping")
            nutrition = None
        nutrition_map[norm] = nutrition
        status = f"{nutrition.kcal_per_100g} kcal/100g" if nutrition else "not found"
        print(f"  {norm}: {status}")

    # build graph
    print("Building knowledge graph...")
    kg = RecipeKnowledgeGraph()
    for recipe in recipes:
        kg.add_recipe(recipe, normalised_map, entity_map, nutrition_map, quantity_map)

    # serialise
    print(f"Saving graph to {output_path}...")
    save_graph(kg, output_path)
    print(f"Done. {len(kg.graph)} triples written.")


if __name__ == "__main__":
    run_ingest(
        recipes_dir=Path(__file__).parent.parent / "src" / "content" / "recipes",
        output_path=Path(__file__).parent / "graph.ttl",
    )
