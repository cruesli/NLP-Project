import os
from typing import List

import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = (
    "You are an ingredient normaliser. Given a list of raw ingredient strings (one per line), "
    "return the canonical food name for each on its own line in the same order. "
    "Reply with only the lowercase food names — no quantities, units, numbering, or extra words. "
    "Examples: '400g Chicken thighs' → 'chicken thigh', '2 tbsp olive oil' → 'olive oil', "
    "'1 large onion' → 'onion'."
)


def make_client() -> openai.OpenAI:
    api_key = os.getenv("CAMPUSAI_API_KEY")
    if not api_key:
        raise ValueError("CAMPUSAI_API_KEY not set. Add it to your .env file.")
    base_url = os.getenv("CAMPUSAI_BASE_URL", "https://chat.campusai.compute.dtu.dk/api/v1")
    return openai.OpenAI(api_key=api_key, base_url=base_url)


def normalise_all(ingredients: List[str], client: openai.OpenAI) -> List[str]:
    if not ingredients:
        return []
    model = os.getenv("CAMPUSAI_MODEL", "gemma-3-27b-it")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(ingredients)},
        ],
    )
    lines = response.choices[0].message.content.strip().splitlines()
    return [line.strip() for line in lines]


def normalise_ingredient(raw: str, client: openai.OpenAI) -> str:
    return normalise_all([raw], client)[0]
