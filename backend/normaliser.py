import os
from typing import List

import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = (
    "You are an ingredient normaliser. Extract the canonical food name from an ingredient string. "
    "Reply with only the lowercase food name — no quantities, units, or extra words. "
    "Examples: '400g Chicken thighs' → 'chicken thigh', '2 tbsp olive oil' → 'olive oil', "
    "'1 large onion' → 'onion'."
)


def make_client() -> openai.OpenAI:
    api_key = os.getenv("CAMPUSAI_API_KEY")
    if not api_key:
        raise ValueError("CAMPUSAI_API_KEY not set. Add it to your .env file.")
    base_url = os.getenv("CAMPUSAI_BASE_URL", "https://campusai.compute.dtu.dk/v1")
    return openai.OpenAI(api_key=api_key, base_url=base_url)


def normalise_ingredient(raw: str, client: openai.OpenAI) -> str:
    model = os.getenv("CAMPUSAI_MODEL", "gemma-3-27b-it")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": raw},
        ],
    )
    return response.choices[0].message.content.strip()


def normalise_all(ingredients: List[str], client: openai.OpenAI) -> List[str]:
    return [normalise_ingredient(raw, client) for raw in ingredients]
