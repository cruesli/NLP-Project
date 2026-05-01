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

_GRAPH_PATH = Path(__file__).parent / "graph.ttl"

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


_BASE_SYSTEM_PROMPT = (
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

_EXAMPLES: list[tuple[str, dict]] = [
    ("give me a high protein recipe", {"min_protein": 50}),
    ("something with lots of protein", {"min_protein": 50}),
    ("protein rich meal", {"min_protein": 50}),
    ("quick dinner under 30 minutes", {"max_time": 30}),
    ("fast meal I can make tonight", {"max_time": 30}),
    ("low calorie option", {"max_kcal": 500}),
    ("light meal for lunch", {"max_kcal": 400}),
    ("something vegan", {"dietary": "vegan"}),
    ("vegetarian recipe please", {"dietary": "vegetarian"}),
    ("italian food tonight", {"cuisine": "italian"}),
    ("middle eastern cuisine", {"cuisine": "middle-eastern"}),
    ("quick italian pasta dinner", {"max_time": 30, "cuisine": "italian"}),
    ("high protein vegan recipe", {"min_protein": 25, "dietary": "vegan"}),
    ("light quick meal under 30 minutes", {"max_kcal": 500, "max_time": 30}),
    ("vegetarian low calorie dish", {"dietary": "vegetarian", "max_kcal": 500}),
]

_STOPWORDS = frozenset({
    "a", "an", "the", "for", "me", "i", "can", "make", "want", "give",
    "show", "something", "some", "with", "and", "or", "that", "is", "are",
    "please", "tonight", "today", "under", "over",
})


def _keyword_overlap(q1: str, q2: str) -> int:
    words1 = {w for w in q1.lower().split() if w not in _STOPWORDS}
    words2 = {w for w in q2.lower().split() if w not in _STOPWORDS}
    return len(words1 & words2)


def _select_examples(
    question: str, examples: list[tuple[str, dict]], k: int = 3
) -> list[tuple[str, dict]]:
    scored = sorted(examples, key=lambda ex: _keyword_overlap(question, ex[0]), reverse=True)
    return scored[:k]


def _build_prompt(question: str) -> str:
    examples = _select_examples(question, _EXAMPLES)
    shots = "\n".join(f'"{q}" -> {json.dumps(f)}' for q, f in examples)
    return _BASE_SYSTEM_PROMPT + f"\n\nExamples:\n{shots}"


def interpret_query(question: str, client: openai.OpenAI) -> dict:
    model = os.getenv("CAMPUSAI_MODEL", "gemma-3-27b-it")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _build_prompt(question)},
            {"role": "user", "content": question},
        ],
    )
    text = response.choices[0].message.content.strip()
    print(f"LLM raw response: {repr(text)}")  # debug
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
