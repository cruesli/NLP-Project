import json
import os
from pathlib import Path
from typing import Optional

import openai
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.graph import RecipeKnowledgeGraph, load_graph
from backend.models import (
    FilterResponse,
    IngredientNutritionResponse,
    QueryRequest,
    QueryResponse,
    RecipeDetail,
    RecipeSummary,
    WikidataResponse,
)
from backend.normaliser import make_client

load_dotenv(Path.home() / ".env")

_GRAPH_PATH = Path(__file__).parent.parent / "graph.ttl"

_kg: Optional[RecipeKnowledgeGraph] = None


def get_kg() -> RecipeKnowledgeGraph:
    global _kg
    if _kg is None:
        if _GRAPH_PATH.exists():
            _kg = load_graph(_GRAPH_PATH)
        else:
            _kg = RecipeKnowledgeGraph()
    return _kg


def get_openai_client() -> openai.OpenAI:
    return make_client()


_QUERY_SYSTEM_PROMPT = (
    "You are a recipe filter assistant. Extract structured filter criteria from a "
    "natural language question about recipes.\n\n"
    "Return a JSON object with zero or more of these fields:\n"
    '- "min_protein": minimum protein per serving in grams (number)\n'
    '- "max_kcal": maximum calories per serving (number)\n'
    '- "max_time": maximum total cook time in minutes (integer)\n'
    '- "cuisine": cuisine type string (e.g. "middle-eastern", "italian")\n'
    '- "dietary": dietary restriction (e.g. "vegan", "vegetarian", "halal")\n\n'
    "Include only the fields explicitly mentioned or strongly implied. "
    "Return ONLY valid JSON, no other text."
)


def interpret_query(question: str, client: openai.OpenAI) -> dict:
    model = os.getenv("CAMPUSAI_MODEL", "gemma-3-27b-it")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _QUERY_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    )
    text = response.choices[0].message.content.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {}


app = FastAPI(title="Recipe Knowledge Graph API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/recipes", response_model=list[RecipeSummary])
def list_recipes(kg: RecipeKnowledgeGraph = Depends(get_kg)):
    return kg.get_all_recipes()


# /filter must be registered before /{slug} so FastAPI does not treat "filter" as a slug
@app.get("/api/v1/recipes/filter", response_model=FilterResponse)
def filter_recipes(
    min_protein: Optional[float] = None,
    max_kcal: Optional[float] = None,
    max_time: Optional[int] = None,
    cuisine: Optional[str] = None,
    dietary: Optional[str] = None,
    kg: RecipeKnowledgeGraph = Depends(get_kg),
):
    return kg.filter_recipes(
        min_protein=min_protein,
        max_kcal=max_kcal,
        max_time=max_time,
        cuisine=cuisine,
        dietary=dietary,
    )


@app.get("/api/v1/recipes/{slug}", response_model=RecipeDetail)
def get_recipe(slug: str, kg: RecipeKnowledgeGraph = Depends(get_kg)):
    detail = kg.get_recipe_by_slug(slug)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Recipe '{slug}' not found")
    return detail


@app.get("/api/v1/ingredients/{ingredient}/nutrition", response_model=IngredientNutritionResponse)
def get_ingredient_nutrition(ingredient: str, kg: RecipeKnowledgeGraph = Depends(get_kg)):
    result = kg.get_ingredient_nutrition(ingredient)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Ingredient '{ingredient}' not found")
    return result


@app.get("/api/v1/ingredients/{ingredient}/wikidata", response_model=WikidataResponse)
def get_ingredient_wikidata(ingredient: str, kg: RecipeKnowledgeGraph = Depends(get_kg)):
    result = kg.get_ingredient_wikidata(ingredient)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Ingredient '{ingredient}' not found")
    return result


@app.post("/api/v1/query", response_model=QueryResponse)
def nl_query(
    body: QueryRequest,
    kg: RecipeKnowledgeGraph = Depends(get_kg),
    llm: openai.OpenAI = Depends(get_openai_client),
):
    raw_filters = interpret_query(body.question, llm)
    known_keys = {"min_protein", "max_kcal", "max_time", "cuisine", "dietary"}
    filters = {k: v for k, v in raw_filters.items() if k in known_keys}
    result = kg.filter_recipes(**filters)
    return QueryResponse(
        question=body.question,
        interpreted_filters=result.filters_applied,
        results=result.results,
    )
