from typing import List, Optional

from pydantic import BaseModel


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
