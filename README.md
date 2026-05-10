# Recipe Knowledge Graph

## Description

This project builds a knowledge graph over a personal recipe collection, enriching each recipe with semantic and nutritional data sourced from Wikidata and the USDA FoodData Central API. The knowledge graph connects recipes to ingredients, ingredients to Wikidata entities (food category, origin country, dietary properties), and ingredients to a full nutritional profile (protein, fat, carbohydrates, calories, fibre, sugar, saturated fat, sodium, cholesterol). The graph is built by an NLP pipeline that parses recipe Markdown files, normalises ingredient strings using an LLM, links them to Wikidata entities via SPARQL, and fetches nutritional data from USDA. The enriched graph is exposed via a FastAPI web service that supports both structured filtering and natural language queries. The existing recipe website serves as the frontend, consuming the API to display nutrition information and enable natural language search.

---

## Note on dataset size

The submitted `graph.ttl` was built from 5 recipes. The normalisation and parsing steps were verified with 20 recipes, but the full ingest pipeline could not be completed due but intermittent 502/504 timeout errors
from the Wikidata SPARQL endpoint on the day of submission. The submitted graph therefore reflects the smaller dataset. Improving the robustness of the Wikidata entity linking step is a planned improvement, hopefully before the oral defence.

## Data

### Recipes (primary)

A personal recipe collection stored as Markdown files with YAML frontmatter in a Git repository (`src/content/recipes/`). Each file contains structured metadata (`title`, `cuisine`, `foodType`, `tags`, `servings`, `totalTimeMinutes`, `ingredients`) and step-by-step instructions in the body. Ingredient strings are free-form human-readable text (e.g. `"400g chicken thighs, boneless and skin-on"`), which motivates the normalisation step.

### Wikidata

Accessed via the `wbsearchentities` API and SPARQL endpoint at
`https://query.wikidata.org/sparql`. Used for semantic enrichment of
ingredients: food category (`P31` instance of, `P279` subclass of), country
of origin (`P495`), and dietary flags (vegan, vegetarian, halal, kosher).
Food entity classification uses a SPARQL ASK query checking the subclass
hierarchy up to `Q2095` (food). Coverage is sparse for some ingredients,
many return `food_category=None` due to missing `P31`/`P279` data in
Wikidata. The `P279*` query proved unreliable in practice due to
frequent 502/504 gateway errors from the public SPARQL endpoint, which can be expected from expensive queries on public infrastructure.

### USDA FoodData Central

Free public API at `https://api.nal.usda.gov/fdc/v1/foods/search`. Returns a
full nutrient profile per 100g including protein, fat, carbohydrates, kcal,
fibre, sugar, saturated fat, sodium, cholesterol, and more. Foundation Foods
and SR Legacy data types are preferred over branded foods. A free API key is
required (obtainable at `https://fdc.nal.usda.gov/api-key-signup`).
Limitation: USDA item names follow verbose conventions, meaning the top
search result sometimes returns dried or processed versions of an ingredient
(e.g. dehydrated carrots at 341 kcal/100g instead of fresh at ~41 kcal/100g).

### WikiFCD (investigated, not adopted)

WikiFCD (`https://wikifcd.wikibase.cloud`) is a dedicated food composition
knowledge base built on Wikibase with a SPARQL endpoint and data from 10
national food composition databases. Its SPARQL endpoint was confirmed to be
programmatically accessible. However, its data is largely derived from USDA
FoodData Central and uses the same verbose naming convention, offering no
practical advantage over using USDA directly. It could serve as a future
supplement for international ingredients not well covered by USDA.

---

## Architecture

```
src/content/recipes/*.md
        │
        ▼
  parser.py              ← parse Markdown + YAML frontmatter into Recipe objects
        │
        ▼
  normaliser.py          ← LLM (CampusAI/Gemma) normalises ingredient strings
                           and extracts quantities in grams
        │
        ▼
  entity_linker.py       ← wbsearchentities API + SPARQL → Wikidata QID,
                           food category, origin country, dietary flags
        │
        ▼
  nutrition.py           ← USDA API → full nutrient profile per ingredient
        │
        ▼
  graph.py               ← RDFLib knowledge graph: recipes, ingredients,
                           Wikidata nodes, nutrition nodes
        │
        ▼
  ingest.py              ← runs full pipeline, serialises to graph.ttl
        │
        ▼
  main.py (FastAPI)      ← structured + NL query endpoints over the graph
        │
        ▼
  Astro website          ← consumes API: nutrition badges, filter bar, NL search
```

The graph is built once by running `ingest.py` and serialised to `graph.ttl`.
The FastAPI service loads `graph.ttl` once at startup and never rebuilds it at
runtime. External API calls (Wikidata, USDA) only happen during ingest.
Intermediate results are cached in `.cache/` to avoid redundant API calls on
re-runs.

---

## Pipeline design choices and limitations

**Parsing** — standard YAML frontmatter parsing with handling for grouped
ingredient sections (lines ending in `:`). Ingredient strings are passed as is
to the normaliser.

**Normalisation:** an LLM is used to normalise ingredient strings into clean
food names and extract quantities in grams in a single batched call per recipe.
This handles the full messiness of real recipe text that rule-based approaches
cannot. Several edge cases were addressed through iterative prompt engineering:
off-by-one errors from compound ingredients like "salt and pepper" (fixed by
instructing the model to always return exactly one entry per input line),
foreign-language ingredient names (fixed by instructing the model to identify
the correct English food name), and "or" alternatives like "thyme or rosemary"
(fixed by pre-processing to keep only the first alternative before sending to
the LLM). Quantity extraction is approximate — whole items like "1 butternut
squash" rely on the LLM's estimated weight.

**Entity linking:** a two-step approach: `wbsearchentities` to find
candidates ranked by sitelinks, then a SPARQL ASK query to verify food entity
membership via the subclass hierarchy. A fallback search appending "food" to
the query handles ambiguous terms like "turkey". Of 42 unique normalised
ingredients, ~30 (71%) were successfully linked to Wikidata QIDs. Failures
include overly specific terms ("parmesan rind"), ambiguous terms ("water",
"spices"), and compound ingredients not fully resolved by normalisation
("minced beef"). The `P279*` SPARQL query proved unreliable on the public
Wikidata endpoint. A more robust solution would use a fixed-depth query or a
local Wikidata mirror.

**Nutrition:** full nutrient profile fetched once per ingredient during
ingest. Quantities from the normalisation step are used to weight each
ingredient's contribution to per-serving nutrition. Nutrition per serving is an approximation since not all ingredients have parseable quantities.

**Knowledge graph:** RDFLib in-memory graph using a custom namespace
(`http://example.org/recipe-kg/`). Serialised to `graph.ttl` and loaded at
startup. At current scale (5 recipes, ~1000 triples) query performance is
fast. For larger collections, migration to QLever would be appropriate.

**Natural language queries:** the LLM interprets free-form questions and
extracts structured filter parameters (min protein, max kcal, max time,
cuisine, dietary). Dynamic few-shot example selection injects the 2-3 most
relevant examples based on keyword overlap, improving extraction accuracy for
novel phrasings. This is quite limited because of the filter parameters, and extending these would improve the usability of the search function.

---

## Tools

| Tool | Purpose |
|---|---|
| **FastAPI** | Web service and REST API |
| **RDFLib** | Knowledge graph construction and querying |
| **SPARQLWrapper** | Wikidata SPARQL queries |
| **CampusAI (Gemma)** | Ingredient normalisation and NL query interpretation |
| **USDA FoodData Central API** | Full nutritional data per ingredient |
| **Docker** | Containerisation |
| **pytest** | Unit tests |
| **uv** | Python package management |

---

## Running the service

### Prerequisites

- Docker installed

- A `~/.env` file containing:

```
CAMPUSAI_API_KEY=your-key-here
CAMPUSAI_BASE_URL=https://chat.campusai.compute.dtu.dk/api/v1
CAMPUSAI_MODEL=Gemma 4
USDA_API_KEY=your-key-here
```

A pre-built `graph.ttl` is included in the repository. To rebuild it from
scratch:

```bash
cd backend
python -m backend.ingest
```

### Build and run

```bash
docker build -t recipe-kg .
docker run --rm -p 8000:8000 --env-file ~/.env recipe-kg
```

The API is then available at `http://localhost:8000`.

---

## API

Base path: `/api/v1`

#### `GET /api/v1/recipes`

Returns all recipes as a list of summaries.

#### `GET /api/v1/recipes/filter`

Filter recipes by query parameters: `min_protein` (float, g per serving),
`max_kcal` (float), `max_time` (int, minutes), `cuisine` (string),
`dietary` (string, e.g. `vegan`).

#### `GET /api/v1/recipes/{slug}`

Returns full recipe detail including enriched ingredients and per-serving
nutrition. Returns 404 if not found.

#### `GET /api/v1/ingredients/{ingredient}/nutrition`

Returns the full USDA nutritional profile for a normalised ingredient name.

#### `GET /api/v1/ingredients/{ingredient}/wikidata`

Returns Wikidata entity data for a normalised ingredient name.

#### `POST /api/v1/query`

Natural language query over the recipe knowledge graph. Accepts
`{"question": "..."}` and returns matching recipes with interpreted filters.

#### `GET /health`

Returns `{"status": "ok", "triples": <count>}`.

---

## Tests

```bash
cd backend
pytest tests/
```

Unit tests cover: recipe Markdown parsing, ingredient normalisation (including
edge cases), USDA response parsing, Wikidata SPARQL query construction, RDF
triple insertion and graph querying, and all API endpoint response schemas.

---

## Evaluation

### Entity linking

Of 57 ingredient nodes in the graph (across 5 recipes, including duplicates across recipes), 50 (88%) were successfully linked to a Wikidata QID. Food category (P31/P279) was populated for all 50 linked ingredients. Failures are concentrated in overly specific terms ('parmesan rind'), ambiguous terms ('water', 'spices'), and compound ingredients not fully resolved by normalisation ('minced beef', 'neutral oil')

### Nutrition data quality

USDA lookup works well for common ingredients. Known quality issues from
incorrect result selection: dehydrated carrots (341 kcal/100g vs ~41 for
fresh), dried chickpeas (387 kcal/100g vs ~128 for cooked). These represent
a roughly 3–9x overestimate for affected ingredients. Foundation Foods and SR
Legacy data types are preferred to mitigate this, but do not fully resolve it.
Quantity-weighted per-serving nutrition is an approximation, and ingredients
without parseable quantities (e.g. "salt", "spices") are excluded from the
calculation.

### Natural language query

The NL query endpoint correctly extracts structured filters for common
phrasings. Example results:

| Query | Extracted filters | Works? |
|---|---|---|
| "give me a high protein recipe" | `min_protein: 50` | Yes |
| "quick italian dinner" | `max_time: 30, cuisine: italian` | Yes |
| "something vegan and light" | `dietary: vegan, max_kcal: 400` | Yes |
| "low sodium dish" | `{}` | No,e not covered by few-shot examples |

Performance degrades for phrasings not covered by the few-shot example set.
Extending the example set or using embedding-based retrieval would improve
coverage.

### Wikidata reliability

The `P279*` SPARQL query for food entity classification produced
frequent 502/504 gateway errors from the public Wikidata endpoint during
development. Whether this is a scaling issue or general endpoint instability
is unclear. A fixed-depth query or a local Wikidata mirror (e.g. QLever) would
be more robust.

---

## References

- USDA FoodData Central API: https://fdc.nal.usda.gov/api-guide.html
- Wikidata Query Service: https://query.wikidata.org
- WikiFCD food composition knowledge base: https://wikifcd.wikibase.cloud
- RDFLib: https://rdflib.readthedocs.io
- FastAPI: https://fastapi.tiangolo.com
- CampusAI: https://campusai.compute.dtu.dk
- Knowledge Graphs book
- NLP Book
