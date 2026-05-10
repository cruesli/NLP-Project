import requests, json

r = requests.get(
    "https://wikifcd.wikibase.cloud/query/sparql",
    params={
        "query": """
SELECT ?propLabel ?value WHERE {
  <https://wikifcd.wikibase.cloud/entity/Q563105> ?p ?value .
  ?prop wikibase:directClaim ?p .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
  FILTER(isLiteral(?value))
} LIMIT 50
""",
        "format": "json"
    },
    headers={"User-Agent": "recipe-kg/1.0 (your@email.com)"}
)
data = r.json()
for b in data["results"]["bindings"]:
    print(f"{b['propLabel']['value']:40} {b['value']['value']}")