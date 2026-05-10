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
    time.sleep(1)
    delay = 1.0
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, headers=headers, timeout=90)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code in (429, 502, 503):
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
        "limit": 10,
    })
    return data.get("search", [])


def is_food_entity(qid: str, session: requests.Session) -> bool:
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
ASK {{
  {{ wd:{qid} wdt:P279 wd:{_FOOD_QID} . }}
  UNION {{ wd:{qid} wdt:P31 wd:{_FOOD_QID} . }}
  UNION {{ wd:{qid} wdt:P279/wdt:P279 wd:{_FOOD_QID} . }}
  UNION {{ wd:{qid} wdt:P31/wdt:P279 wd:{_FOOD_QID} . }}
  UNION {{ wd:{qid} wdt:P31/wdt:P279/wdt:P279 wd:{_FOOD_QID} . }}
}}
"""
    data = _get(session, _SPARQL_URL, {"query": query, "format": "json"})
    return bool(data.get("boolean", False))


def filter_food_entities(qids: List[str], session: requests.Session) -> set:
    """Return the subset of QIDs that are food entities via a single batch SPARQL query."""
    if not qids:
        return set()
    values = " ".join(f"wd:{q}" for q in qids)
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT ?entity WHERE {{
  VALUES ?entity {{ {values} }}
  {{
    ?entity wdt:P279* wd:{_FOOD_QID} .
  }}
  UNION
  {{
    ?entity wdt:P31/wdt:P279* wd:{_FOOD_QID} .
  }}
}}
"""
    data = _get(session, _SPARQL_URL, {"query": query, "format": "json"})
    bindings = data.get("results", {}).get("bindings", [])
    return {row["entity"]["value"].split("/")[-1] for row in bindings}


def fetch_properties(qid: str, label: str, session: requests.Session) -> WikidataEntity:
    dietary_values = "\n".join(
        f'      (wd:{q} "{flag}")' for q, flag in _DIETARY_MAP.items()
    )
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?foodCategory ?foodCategoryLabel ?subclassCategory ?subclassCategoryLabel ?originCountry ?originCountryLabel ?dietaryFlag
WHERE {{
  OPTIONAL {{ wd:{qid} wdt:P31 ?foodCategory . }}
  OPTIONAL {{ wd:{qid} wdt:P279 ?subclassCategory . }}
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
    subclass_category: Optional[str] = None
    origin_country: Optional[str] = None
    dietary_flags: List[str] = []

    for row in bindings:
        if food_category is None and "foodCategoryLabel" in row:
            food_category = row["foodCategoryLabel"]["value"]
        if subclass_category is None and "subclassCategoryLabel" in row:
            subclass_category = row["subclassCategoryLabel"]["value"]
        if origin_country is None and "originCountryLabel" in row:
            origin_country = row["originCountryLabel"]["value"]
        if "dietaryFlag" in row:
            flag = row["dietaryFlag"]["value"]
            if flag not in dietary_flags:
                dietary_flags.append(flag)

    if food_category is None:
        food_category = subclass_category

    return WikidataEntity(
        qid=qid,
        uri=f"{_ENTITY_BASE}{qid}",
        label=label,
        food_category=food_category,
        origin_country=origin_country,
        dietary_flags=dietary_flags,
    )


def link_ingredient(ingredient: str, session: requests.Session) -> Optional[WikidataEntity]:
    # first attempt — one batch query checks all candidates at once
    candidates = sorted(
        search_candidates(ingredient, session),
        key=lambda c: c.get("sitelinks", 0),
        reverse=True,
    )
    if candidates:
        food_qids = filter_food_entities([c["id"] for c in candidates], session)
        for candidate in candidates:
            if candidate["id"] in food_qids:
                return fetch_properties(candidate["id"], candidate.get("label", ingredient), session)
    # fallback: retry with "food" appended
    candidates_fb = sorted(
        search_candidates(f"{ingredient} food", session),
        key=lambda c: c.get("sitelinks", 0),
        reverse=True,
    )
    if candidates_fb:
        food_qids_fb = filter_food_entities([c["id"] for c in candidates_fb], session)
        for candidate in candidates_fb:
            if candidate["id"] in food_qids_fb:
                return fetch_properties(candidate["id"], candidate.get("label", ingredient), session)
    return None
