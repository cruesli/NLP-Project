import time
from typing import List, Optional

import requests

from backend.models import WikidataEntity

_API_URL = "https://www.wikidata.org/w/api.php"
_SPARQL_URL = "https://query.wikidata.org/sparql"
_USER_AGENT = "recipe-kg/1.0 (geirdunma@gmail.com)"
_ENTITY_BASE = "http://www.wikidata.org/entity/"

# Food (Q2095) used as root of the food subclass hierarchy
_FOOD_QID = "Q2095"

_DIETARY_MAP = {
    "Q2945560": "vegan",
    "Q386724": "vegetarian",
    "Q3088585": "halal",
    "Q178558": "kosher",
}


def _get(session: requests.Session, url: str, params: dict, max_retries: int = 3) -> dict:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    delay = 1.0
    for attempt in range(max_retries):
        resp = session.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code in (429, 503):
            if attempt == max_retries - 1:
                raise requests.HTTPError(
                    f"HTTP {resp.status_code} after {max_retries} retries", response=resp
                )
            wait = float(resp.headers.get("Retry-After", delay))
            time.sleep(wait)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp.json()


def search_candidates(ingredient: str, session: requests.Session) -> List[dict]:
    data = _get(session, _API_URL, {
        "action": "wbsearchentities",
        "search": ingredient,
        "language": "en",
        "type": "item",
        "format": "json",
        "limit": 5,
    })
    return data.get("search", [])


def is_food_entity(qid: str, session: requests.Session) -> bool:
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
ASK {{
  {{ wd:{qid} wdt:P279* wd:{_FOOD_QID} . }}
  UNION
  {{ wd:{qid} wdt:P31/wdt:P279* wd:{_FOOD_QID} . }}
}}
"""
    data = _get(session, _SPARQL_URL, {"query": query, "format": "json"})
    return bool(data.get("boolean", False))


def fetch_properties(qid: str, label: str, session: requests.Session) -> WikidataEntity:
    dietary_values = "\n".join(
        f'      (wd:{q} "{flag}")' for q, flag in _DIETARY_MAP.items()
    )
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?foodCategory ?foodCategoryLabel ?originCountry ?originCountryLabel ?dietaryFlag
WHERE {{
  OPTIONAL {{ wd:{qid} wdt:P31 ?foodCategory . }}
  OPTIONAL {{ wd:{qid} wdt:P495 ?originCountry . }}
  OPTIONAL {{
    wd:{qid} wdt:P31 ?dietaryClass .
    VALUES (?dietaryClass ?dietaryFlag) {{
{dietary_values}
    }}
  }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
"""
    data = _get(session, _SPARQL_URL, {"query": query, "format": "json"})
    bindings = data.get("results", {}).get("bindings", [])

    food_category: Optional[str] = None
    origin_country: Optional[str] = None
    dietary_flags: List[str] = []

    for row in bindings:
        if food_category is None and "foodCategoryLabel" in row:
            food_category = row["foodCategoryLabel"]["value"]
        if origin_country is None and "originCountryLabel" in row:
            origin_country = row["originCountryLabel"]["value"]
        if "dietaryFlag" in row:
            flag = row["dietaryFlag"]["value"]
            if flag not in dietary_flags:
                dietary_flags.append(flag)

    return WikidataEntity(
        qid=qid,
        uri=f"{_ENTITY_BASE}{qid}",
        label=label,
        food_category=food_category,
        origin_country=origin_country,
        dietary_flags=dietary_flags,
    )


def link_ingredient(ingredient: str, session: requests.Session) -> Optional[WikidataEntity]:
    candidates = search_candidates(ingredient, session)
    for candidate in candidates:
        qid = candidate["id"]
        if is_food_entity(qid, session):
            return fetch_properties(qid, candidate.get("label", ingredient), session)
    return None
