import requests
from backend.nutrition import fetch_nutrition

session = requests.Session()

# Known ingredient
result = fetch_nutrition("chicken thigh", session)
print(result)

# Vegan ingredient
result = fetch_nutrition("chickpeas", session)
print(result)

# Unknown
result = fetch_nutrition("xyzzy123abc", session)
print(result)  # should be None