import re
from pathlib import Path
from typing import List

import frontmatter

from backend.models import Recipe


def _clean_ingredients(raw) -> List[str]:
    if isinstance(raw, list):
        lines = raw
    else:
        lines = str(raw).splitlines()

    result = []
    for line in lines:
        line = line.strip()
        line = re.sub(r"^-+\s*", "", line)
        line = line.strip()
        if not line or line.endswith(":"):
            continue
        result.append(line)
    return result


def parse_recipe(path: Path) -> Recipe:
    post = frontmatter.load(str(path))
    fm = post.metadata

    return Recipe(
        slug=path.stem,
        title=fm["title"],
        cuisine=fm["cuisine"],
        food_type=fm.get("foodType"),
        tags=[t for t in fm.get("tags", []) if t],
        servings=fm.get("servings"),
        total_time_minutes=fm.get("totalTimeMinutes"),
        image=fm.get("image"),
        ingredients=_clean_ingredients(fm.get("ingredients", [])),
        body=post.content,
    )


def load_all_recipes(recipes_dir: Path) -> List[Recipe]:
    return [parse_recipe(p) for p in sorted(recipes_dir.glob("*.md"))]
