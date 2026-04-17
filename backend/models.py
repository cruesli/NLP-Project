from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# Internal pipeline model (snake_case, no aliases needed)
class Recipe(BaseModel):
    slug: str
    title: str
    cuisine: str
    food_type: Optional[str] = None
    tags: List[str] = []
    servings: Optional[int] = None
    total_time_minutes: Optional[int] = None
    image: Optional[str] = None
    ingredients: List[str] = []
    body: str = ""


# Nutrition models

class NutritionPer100g(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    protein_per_100g: float = Field(alias="proteinPer100g")
    fat_per_100g: float = Field(alias="fatPer100g")
    carbs_per_100g: float = Field(alias="carbsPer100g")
    kcal_per_100g: float = Field(alias="kcalPer100g")
    fibre_per_100g: Optional[float] = Field(default=None, alias="fibrePer100g")


class NutritionPerServing(_CamelModel):
    protein_g: Optional[float] = None
    fat_g: Optional[float] = None
    carbs_g: Optional[float] = None
    kcal: Optional[float] = None


# Ingredient model (enriched, for API responses)

class EnrichedIngredient(_CamelModel):
    raw: str
    normalised: Optional[str] = None
    wikidata_qid: Optional[str] = None
    food_category: Optional[str] = None
    origin_country: Optional[str] = None
    nutrition: Optional[NutritionPer100g] = None


# Recipe response models

class RecipeSummary(_CamelModel):
    slug: str
    title: str
    cuisine: str
    total_time_minutes: Optional[int] = None
    tags: List[str] = []


class RecipeDetail(_CamelModel):
    slug: str
    title: str
    cuisine: str
    servings: Optional[int] = None
    total_time_minutes: Optional[int] = None
    ingredients: List[EnrichedIngredient] = []
    nutrition_per_serving: Optional[NutritionPerServing] = None


# Ingredient endpoint response models

class IngredientNutritionResponse(_CamelModel):
    ingredient: str
    wikidata_qid: Optional[str] = None
    nutrition: NutritionPer100g


class WikidataResponse(_CamelModel):
    ingredient: str
    wikidata_qid: Optional[str] = None
    wikidata_uri: Optional[str] = None
    label: Optional[str] = None
    food_category: Optional[str] = None
    origin_country: Optional[str] = None
    dietary_flags: List[str] = []


# Filter and query models

class FilterResponse(BaseModel):
    filters_applied: Dict[str, Any]
    count: int
    results: List[RecipeSummary]


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    interpreted_filters: Dict[str, Any]
    results: List[RecipeSummary]
