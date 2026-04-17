
# Recipe Knowledge Graph — NLP Final Project

## Description

A web service that enriches a personal recipe collection with structured knowledge
and nutritional data, enabling natural language queries over the recipes.

Recipes are stored as Markdown files with structured frontmatter (title, cuisine,
ingredients, tags, cook time, etc.) on a static Astro website. This project builds
a backend NLP pipeline that:

1. **Parses and normalises** ingredient strings from each recipe using an LLM
   (e.g. `"400g Chicken thighs"` → `"chicken thigh"`)
2. **Links** normalised ingredients to Wikidata entities via SPARQL, enriching
   them with semantic properties (food category, origin country, dietary flags)
3. **Fetches nutritional data** per ingredient from the USDA FoodData Central API
   (protein, fat, carbohydrates, calories, fibre)
4. **Builds a knowledge graph** (RDF triples) connecting recipes, ingredients,
   nutrition nodes and Wikidata concepts
5. **Exposes a FastAPI web service** that allows structured and natural language
   queries over the graph, Dockerised for reproducibility

The existing Astro website acts as the human-facing frontend, consuming the API.

---

## Tools

| Tool / Library | Purpose |
| --- | --- |
| **FastAPI** | Web service and REST API |
| **Docker** | Containerisation |
| **spaCy** | Ingredient string parsing / NER |
| **LLM (CampusAI)** | Ingredient normalisation, NL query interpretation |
| **SPARQLWrapper** | Querying Wikidata for ingredient entity linking |
| **USDA FoodData Central API** | Nutritional data per ingredient |
| **RDFLib** | Building and querying the knowledge graph (in-memory or file-backed) |
| **Pydantic** | API request/response validation |
| **pytest** | Unit tests |

---

## Data

### Recipe data (primary)

- Source: Personal recipe collection on the Astro website
- Format: Markdown files with YAML frontmatter
- Fields: `title`, `cuisine`, `foodType`, `tags`, `servings`,
  `totalTimeMinutes`, `ingredients` (list or grouped string), recipe steps (body)
- Example recipe: *Tahini Chicken with Butternut Hummus and Bulgur Salad*

### Wikidata (semantic enrichment)

- Accessed via SPARQL at `https://query.wikidata.org/sparql`
- Properties of interest:
  - `P31` (instance of) — food type classification
  - `P279` (subclass of) — taxonomic category (e.g. poultry → meat)
  - `P495` (country of origin)
  - `P1566` (dietary restriction flags, e.g. vegan, halal, kosher)

### USDA FoodData Central API (nutrition)

- Free public API, no authentication required for basic use
- Endpoint: `https://api.nal.usda.gov/fdc/v1/foods/search`
- Returns: protein (g), fat (g), carbohydrates (g), energy (kcal),
  fibre (g) per 100g of ingredient

---

## Architecture

```text
Recipe Markdown files
        │
        ▼
  Ingredient Parser          ← LLM strips quantities/units → normalised food name
        │
        ▼
  Entity Linker              ← SPARQL query to Wikidata → QID + semantic properties
        │
        ▼
  Nutrition Fetcher          ← USDA API lookup per normalised ingredient name
        │
        ▼
  Knowledge Graph (RDFLib)   ← RDF triples stored in-memory or as .ttl file
        │
        ▼
  FastAPI Web Service        ← structured + NL query endpoints
        │
        ▼
  Astro Website Frontend     ← consumes API, shows nutrition badges, filters
```

### Knowledge graph structure (example triples)

```turtle
ex:recipe_tahini_chicken  rdf:type              ex:Recipe
ex:recipe_tahini_chicken  ex:hasIngredient      ex:ingredient_chicken_thigh
ex:recipe_tahini_chicken  ex:cuisine            "middle-eastern"
ex:recipe_tahini_chicken  ex:totalTimeMinutes   45

ex:ingredient_chicken_thigh  ex:wikidataEntity  wd:Q192628
ex:ingredient_chicken_thigh  ex:originCountry   wd:Q30        ← United States
ex:ingredient_chicken_thigh  ex:foodCategory    "poultry"

ex:ingredient_chicken_thigh  ex:hasNutrition    ex:nutrition_chicken_thigh
ex:nutrition_chicken_thigh   ex:proteinPer100g  "17.4"^^xsd:decimal
ex:nutrition_chicken_thigh   ex:fatPer100g      "9.6"^^xsd:decimal
ex:nutrition_chicken_thigh   ex:kcalPer100g     "177"^^xsd:decimal
```

---

## API

Base path: `/api/v1`

Interactive docs available at `/docs` (Swagger) and `/redoc`.

---

### `GET /api/v1/recipes`

Returns all recipes with basic metadata.

#### Example response

```json
[
  {
    "slug": "tahini-chicken-with-butternut-hummus-and-bulgur-salad",
    "title": "Tahini Chicken with Butternut Hummus and Bulgur Salad",
    "cuisine": "middle-eastern",
    "totalTimeMinutes": 45,
    "tags": ["Quick", "Healthy"]
  }
]
```

---

### `GET /api/v1/recipes/{slug}`

Returns full recipe data including enriched ingredient knowledge graph nodes
and aggregated nutrition per serving.

#### Example request (get single recipe)

```http
GET /api/v1/recipes/tahini-chicken-with-butternut-hummus-and-bulgur-salad
```

#### Example response (single recipe)

```json
{
  "slug": "tahini-chicken-with-butternut-hummus-and-bulgur-salad",
  "title": "Tahini Chicken with Butternut Hummus and Bulgur Salad",
  "cuisine": "middle-eastern",
  "servings": 2,
  "totalTimeMinutes": 45,
  "ingredients": [
    {
      "raw": "400g Chicken",
      "normalised": "chicken thigh",
      "wikidataQid": "Q192628",
      "foodCategory": "poultry",
      "originCountry": "United States",
      "nutrition": {
        "proteinPer100g": 17.4,
        "fatPer100g": 9.6,
        "carbsPer100g": 0.0,
        "kcalPer100g": 177
      }
    },
    {
      "raw": "1 Butternut squash",
      "normalised": "butternut squash",
      "wikidataQid": "Q1138398",
      "foodCategory": "vegetable",
      "originCountry": "Guatemala",
      "nutrition": {
        "proteinPer100g": 1.0,
        "fatPer100g": 0.1,
        "carbsPer100g": 11.7,
        "kcalPer100g": 45
      }
    }
  ],
  "nutritionPerServing": {
    "proteinG": 42.1,
    "fatG": 18.3,
    "carbsG": 55.4,
    "kcal": 610
  }
}
```

---

### `POST /api/v1/query`

Natural language query over the recipe knowledge graph. An LLM interprets
the intent and translates it to a structured graph query.

#### Example request (query)

```json
{
  "question": "Show me a high-protein recipe that takes less than 30 minutes"
}
```

#### Example response (query)

```json
{
  "question": "Show me a high-protein recipe that takes less than 30 minutes",
  "interpreted_filters": {
    "min_protein_per_serving_g": 30,
    "max_total_time_minutes": 30
  },
  "results": [
    {
      "slug": "lebanese-chicken-hummus-and-grilled-vegetables",
      "title": "Lebanese Chicken, Hummus and Grilled Vegetables",
      "totalTimeMinutes": 20,
      "nutritionPerServing": {
        "proteinG": 38.5,
        "kcal": 520
      }
    }
  ]
}
```

---

### `GET /api/v1/ingredients/{ingredient}/nutrition`

Returns nutritional data for a single normalised ingredient name.

#### Example request (nutrition)

```http
GET /api/v1/ingredients/chickpeas/nutrition
```

#### Example response (nutrition)

```json
{
  "ingredient": "chickpeas",
  "wikidataQid": "Q23768",
  "nutrition": {
    "proteinPer100g": 8.9,
    "fatPer100g": 2.6,
    "carbsPer100g": 27.4,
    "kcalPer100g": 164,
    "fibrePer100g": 7.6
  }
}
```

---

### `GET /api/v1/recipes/filter`

Filter recipes by nutritional thresholds and/or semantic properties.

#### Filter query parameters

| Parameter | Type | Description |
| --- | --- | --- |
| `min_protein` | float | Minimum protein per serving (g) |
| `max_kcal` | float | Maximum calories per serving (kcal) |
| `max_time` | int | Maximum total cook time (minutes) |
| `cuisine` | string | Cuisine slug (e.g. `middle-eastern`) |
| `dietary` | string | Dietary flag (e.g. `vegan`, `vegetarian`) |

#### Filter request

```http
GET /api/v1/recipes/filter?min_protein=30&max_time=30&cuisine=middle-eastern
```

#### Filter response

```json
{
  "filters_applied": {
    "min_protein": 30,
    "max_time": 30,
    "cuisine": "middle-eastern"
  },
  "count": 1,
  "results": [
    {
      "slug": "lebanese-chicken-hummus-and-grilled-vegetables",
      "title": "Lebanese Chicken, Hummus and Grilled Vegetables",
      "nutritionPerServing": { "proteinG": 38.5, "kcal": 520 },
      "totalTimeMinutes": 20
    }
  ]
}
```

---

### `GET /api/v1/ingredients/{ingredient}/wikidata`

Returns the Wikidata entity and semantic properties for a given ingredient.

#### Wikidata request

```http
GET /api/v1/ingredients/tahini/wikidata
```

#### Wikidata response

```json
{
  "ingredient": "tahini",
  "wikidataQid": "Q806723",
  "wikidataUri": "http://www.wikidata.org/entity/Q806723",
  "label": "tahini",
  "foodCategory": "condiment",
  "originCountry": "Middle East",
  "dietaryFlags": ["vegan", "vegetarian"]
}
```

---

## Web Application

The existing Astro website acts as the frontend. The API augments it with:

- **Nutrition badges** on each recipe page (protein, kcal, carbs per serving)
- **Smart filter bar** on the recipe index page (high-protein, low-carb, vegan, etc.)
- **Natural language search box** that calls `POST /api/v1/query`
- **Ingredient info panel** on recipe pages showing origin country and food category

---

## Running the service

```bash
# Build and run
docker build -t recipe-kg .
docker run -p 8000:8000 recipe-kg

# API docs
open http://localhost:8000/docs
```

---

## Tests

Unit tests are written with `pytest` and cover:

- Ingredient string parsing and normalisation
- USDA API response parsing and nutrition extraction
- Wikidata SPARQL query construction and result parsing
- RDF triple insertion and graph query correctness
- API endpoint response schemas (via `TestClient`)

```bash
pytest tests/
```

---

## References

- USDA FoodData Central API: <https://fdc.nal.usda.gov/api-guide.html>
- Wikidata Query Service: <https://query.wikidata.org>
- RDFLib documentation: <https://rdflib.readthedocs.io>
- FastAPI documentation: <https://fastapi.tiangolo.com>
- spaCy documentation: <https://spacy.io>
