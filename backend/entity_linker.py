import re
import time
from typing import List, Optional

import requests

from backend.models import WikidataEntity

_API_URL = "https://www.wikidata.org/w/api.php"
_SPARQL_URL = "https://query.wikidata.org/sparql"
_USER_AGENT = "recipe-kg/1.0 (geirdunma@gmail.com)"
_ENTITY_BASE = "http://www.wikidata.org/entity/"

_FOOD_QID = "Q2095"  # root of food subclass hierarchy

_DIETARY_MAP = {
    "Q2945560": "vegan",
    "Q386724":  "vegetarian",
    "Q3088585": "halal",
    "Q178558":  "kosher",
}

# Modifiers to strip when broadening a compound ingredient search term
_MODIFIERS = re.compile(
    r"\b(minced|ground|diced|chopped|sliced|dried|fresh|frozen|raw|cooked|"
    r"roasted|smoked|canned|tinned|pickled|whole|boneless|skinless|rind|"
    r"neutral|extra.virgin|semi-skimmed|full.fat|low.fat|organic)\b",
    re.IGNORECASE,
)


# --- HTTP helper -----------------------------------------------------------

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
        if resp.status_code in (429, 502, 503, 504):
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
    return {}


# --- Wikidata search -------------------------------------------------------

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


# --- Food classification (fixed-depth, no P279*) --------------------------

def filter_food_entities(qids: List[str], session: requests.Session) -> set:
    """Return subset of QIDs that are food entities.

    Uses a fixed 4-level subclass chain instead of P279* to avoid the
    frequent 502/504 gateway errors caused by the unbounded transitive query.
    4 levels covers deep hierarchies like:
      red wine -> wine -> alcoholic beverage -> beverage -> food/drink
    """
    if not qids:
        return set()
    values = " ".join(f"wd:{q}" for q in qids)
    food = f"wd:{_FOOD_QID}"
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?entity WHERE {{
  VALUES ?entity {{ {values} }}
  {{
    # depth 1
    {{ ?entity wdt:P279 {food} }}
    UNION
    {{ ?entity wdt:P31  {food} }}
    UNION
    # depth 2
    {{ ?entity wdt:P279/wdt:P279 {food} }}
    UNION
    {{ ?entity wdt:P31/wdt:P279  {food} }}
    UNION
    # depth 3
    {{ ?entity wdt:P279/wdt:P279/wdt:P279 {food} }}
    UNION
    {{ ?entity wdt:P31/wdt:P279/wdt:P279  {food} }}
    UNION
    # depth 4
    {{ ?entity wdt:P279/wdt:P279/wdt:P279/wdt:P279 {food} }}
    UNION
    {{ ?entity wdt:P31/wdt:P279/wdt:P279/wdt:P279  {food} }}
  }}
}}
"""
    try:
        data = _get(session, _SPARQL_URL, {"query": query, "format": "json"})
    except requests.HTTPError:
        return set()
    bindings = data.get("results", {}).get("bindings", [])
    return {row["entity"]["value"].split("/")[-1] for row in bindings}


# --- Description heuristic fallback ---------------------------------------

def _description_looks_like_food(candidates: List[dict]) -> Optional[dict]:
    """Return the first candidate whose Wikidata description mentions food."""
    food_words = {
        "food", "fruit", "vegetable", "meat", "fish", "spice", "herb",
        "grain", "cereal", "legume", "dairy", "cheese", "oil", "sauce",
        "beverage", "drink", "condiment", "nut", "wine", "alcohol",
        "alcoholic", "spirit", "seasoning", "stock", "broth", "paste",
        "seed", "fat", "flour", "sugar", "syrup", "vinegar", "ingredient",
    }
    for c in candidates:
        desc = c.get("description", "").lower()
        if any(w in desc for w in food_words):
            return c
    return None


# --- Properties fetch -----------------------------------------------------

def fetch_properties(qid: str, label: str, session: requests.Session) -> WikidataEntity:
    dietary_values = "\n".join(
        f'      (wd:{q} "{flag}")' for q, flag in _DIETARY_MAP.items()
    )
    query = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?foodCategory ?foodCategoryLabel ?subclassCategory ?subclassCategoryLabel
                ?originCountry ?originCountryLabel ?dietaryFlag
WHERE {{
  OPTIONAL {{ wd:{qid} wdt:P31  ?foodCategory . }}
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


# --- Core linking logic ---------------------------------------------------

def _try_link(query: str, session: requests.Session) -> Optional[WikidataEntity]:
    """Search, filter to food entities, return the best match or None."""
    candidates = sorted(
        search_candidates(query, session),
        key=lambda c: c.get("sitelinks", 0),
        reverse=True,
    )
    if not candidates:
        return None

    # SPARQL food filter
    food_qids = filter_food_entities([c["id"] for c in candidates], session)
    for c in candidates:
        if c["id"] in food_qids:
            return fetch_properties(c["id"], c.get("label", query), session)

    # description heuristic when SPARQL returns nothing
    match = _description_looks_like_food(candidates)
    if match:
        return fetch_properties(match["id"], match.get("label", query), session)

    return None


def _broaden(ingredient: str) -> Optional[str]:
    """Strip recognised modifiers to produce a broader search term."""
    broader = _MODIFIERS.sub("", ingredient).strip()
    broader = re.sub(r"\s+", " ", broader)
    return broader if broader and broader != ingredient else None


def _singularise(term: str) -> Optional[str]:
    """Return singular of last word if it ends in 's', else None.

    Handles: "garlic cloves" -> "garlic clove", "chickpeas" -> "chickpea",
             "tomatoes" -> "tomato".
    Skips words <= 3 chars or already singular-looking.
    """
    words = term.split()
    last = words[-1]
    if len(last) <= 3 or not last.endswith("s") or last.endswith("ss"):
        return None
    # "oes"/"ies" endings need special handling; keep it simple: strip "es"
    if last.endswith("es") and len(last) > 4:
        singular = last[:-2]
    else:
        singular = last[:-1]
    words[-1] = singular
    result = " ".join(words)
    return result if result != term else None


def link_ingredient(ingredient: str, session: requests.Session) -> Optional[WikidataEntity]:
    """Link an ingredient string to a Wikidata entity.

    Fallback chain:
      1. Direct search
      2. Singular form  (e.g. "garlic cloves" -> "garlic clove")
      3. Search with " food" appended  (handles ambiguous terms like "turkey")
      4. Broadened term (modifiers stripped, e.g. "minced beef" -> "beef")
      5. Broadened term + " food"
    """
    # 1. direct
    result = _try_link(ingredient, session)
    if result:
        return result

    # 2. singular
    singular = _singularise(ingredient)
    if singular:
        result = _try_link(singular, session)
        if result:
            return result

    # 3. append "food"
    result = _try_link(f"{ingredient} food", session)
    if result:
        return result

    # 4. strip modifiers
    broader = _broaden(ingredient)
    if broader:
        result = _try_link(broader, session)
        if result:
            return result

        # 5. broader + "food"
        result = _try_link(f"{broader} food", session)
        if result:
            return result

    return None