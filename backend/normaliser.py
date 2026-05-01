import json
import os
import re
from typing import Any, Dict, List, Optional

import openai
from dotenv import load_dotenv

load_dotenv()

_SYSTEM_PROMPT = (
    "You are an ingredient normaliser. Given a list of raw ingredient strings (one per line), "
    "return a JSON array where each element has \"name\" (canonical lowercase food name, no quantities "
    "or units) and \"quantity_g\" (the quantity converted to grams as a float, or null if unquantifiable). "
    "Unit conversions: 1 tbsp = 15 g, 1 tsp = 5 g, 1 cup = 240 g, 1 oz = 28.35 g, 1 lb = 453.6 g, "
    "1 kg = 1000 g. For whole countable items estimate a reasonable weight (e.g. '1 butternut squash' "
    "→ 700 g, '2 garlic cloves' → 10 g, '1 onion' → 150 g, '1 egg' → 50 g). "
    "Use null for 'to taste', 'pinch', or any amount that cannot be quantified. "
    "Preserve the input order. Reply with only the JSON array, no markdown fencing or extra text. "
    "Example input: '400g Chicken thighs\\n2 tbsp olive oil\\nsalt to taste' "
    "Example output: [{\"name\": \"chicken thigh\", \"quantity_g\": 400.0}, "
    "{\"name\": \"olive oil\", \"quantity_g\": 30.0}, "
    "{\"name\": \"salt\", \"quantity_g\": null}]"
)


def _parse_response(content: str) -> List[Dict[str, Any]]:
    content = re.sub(r"```(?:json)?\s*", "", content).strip()
    return json.loads(content)


def make_client() -> openai.OpenAI:
    api_key = os.getenv("CAMPUSAI_API_KEY")
    if not api_key:
        raise ValueError("CAMPUSAI_API_KEY not set. Add it to your .env file.")
    base_url = os.getenv("CAMPUSAI_BASE_URL", "https://chat.campusai.compute.dtu.dk/api/v1")
    return openai.OpenAI(api_key=api_key, base_url=base_url)


def normalise_all(ingredients: List[str], client: openai.OpenAI) -> List[Dict[str, Any]]:
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
    items = _parse_response(response.choices[0].message.content.strip())
    return [{"name": item["name"].strip(), "quantity_g": item.get("quantity_g")} for item in items]


def normalise_ingredient(raw: str, client: openai.OpenAI) -> str:
    return normalise_all([raw], client)[0]["name"]
