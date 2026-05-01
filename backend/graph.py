import re
from pathlib import Path
from typing import Dict, List, Optional

from rdflib import XSD, Graph, Literal, Namespace, RDF, URIRef

from backend.models import (
    EnrichedIngredient,
    FilterResponse,
    IngredientNutritionResponse,
    NutritionPer100g,
    NutritionPerServing,
    Recipe,
    RecipeDetail,
    RecipeSummary,
    WikidataEntity,
    WikidataResponse,
)

EX = Namespace("http://example.org/recipe-kg/")


class RecipeKnowledgeGraph:
    def __init__(self) -> None:
        self.graph = Graph()
        self.graph.bind("ex", EX)

    def add_recipe(
        self,
        recipe: Recipe,
        normalised_map: Dict[str, str],
        entity_map: Dict[str, WikidataEntity],
        nutrition_map: Dict[str, NutritionPer100g],
        quantity_map: Optional[Dict[str, Optional[float]]] = None,
    ) -> None:
        r = EX[f"recipe_{recipe.slug}"]
        self.graph.add((r, RDF.type, EX.Recipe))
        self.graph.add((r, EX.slug, Literal(recipe.slug)))
        self.graph.add((r, EX.title, Literal(recipe.title)))
        self.graph.add((r, EX.cuisine, Literal(recipe.cuisine)))
        if recipe.food_type:
            self.graph.add((r, EX.foodType, Literal(recipe.food_type)))
        if recipe.servings is not None:
            self.graph.add((r, EX.servings, Literal(recipe.servings, datatype=XSD.integer)))
        if recipe.total_time_minutes is not None:
            self.graph.add((r, EX.totalTimeMinutes, Literal(recipe.total_time_minutes, datatype=XSD.integer)))
        for tag in recipe.tags:
            self.graph.add((r, EX.tag, Literal(tag)))

        # ingredients
        ing_nutritions = []  # list of (NutritionPer100g, Optional[float]) tuples
        for idx, raw in enumerate(recipe.ingredients):
            ing_node = EX[f"ing_{recipe.slug}_{idx}"]
            self.graph.add((r, EX.hasIngredient, ing_node))
            self.graph.add((ing_node, RDF.type, EX.Ingredient))
            self.graph.add((ing_node, EX.rawString, Literal(raw)))

            normalised = normalised_map.get(raw)
            if normalised:
                self.graph.add((ing_node, EX.normalisedName, Literal(normalised)))

            quantity_g = quantity_map.get(raw) if quantity_map else None
            if quantity_g is not None:
                self.graph.add((ing_node, EX.quantityG, Literal(quantity_g, datatype=XSD.decimal)))

            entity = entity_map.get(normalised) if normalised else None
            if entity:
                self.graph.add((ing_node, EX.wikidataQid, Literal(entity.qid)))
                self.graph.add((ing_node, EX.wikidataUri, Literal(entity.uri)))
                if entity.food_category:
                    self.graph.add((ing_node, EX.foodCategory, Literal(entity.food_category)))
                if entity.origin_country:
                    self.graph.add((ing_node, EX.originCountry, Literal(entity.origin_country)))
                for flag in entity.dietary_flags:
                    self.graph.add((ing_node, EX.dietaryFlag, Literal(flag)))

            nutrition = nutrition_map.get(normalised) if normalised else None
            if nutrition:
                ing_nutritions.append((nutrition, quantity_g))
                nutr_node = EX[f"nutr_{recipe.slug}_{idx}"]
                self.graph.add((ing_node, EX.hasNutrition, nutr_node))
                self.graph.add((nutr_node, RDF.type, EX.Nutrition))
                self._add_nutrition_triples(nutr_node, nutrition)

        # approx per-serving nutrition stored on the recipe node for filtering
        if ing_nutritions and recipe.servings:
            s = recipe.servings
            total_protein = 0.0
            total_kcal = 0.0
            for n, qty in ing_nutritions:
                factor = (qty / 100) if qty is not None else 1.0
                total_protein += factor * n.protein_per_100g
                total_kcal += factor * n.kcal_per_100g
            self.graph.add((r, EX.approxProteinPerServing, Literal(total_protein / s, datatype=XSD.decimal)))
            self.graph.add((r, EX.approxKcalPerServing, Literal(total_kcal / s, datatype=XSD.decimal)))

    def _add_nutrition_triples(self, node: URIRef, n: NutritionPer100g) -> None:
        self.graph.add((node, EX.proteinPer100g, Literal(n.protein_per_100g, datatype=XSD.decimal)))
        self.graph.add((node, EX.fatPer100g, Literal(n.fat_per_100g, datatype=XSD.decimal)))
        self.graph.add((node, EX.carbsPer100g, Literal(n.carbs_per_100g, datatype=XSD.decimal)))
        self.graph.add((node, EX.kcalPer100g, Literal(n.kcal_per_100g, datatype=XSD.decimal)))
        if n.fibre_per_100g is not None:
            self.graph.add((node, EX.fibrePer100g, Literal(n.fibre_per_100g, datatype=XSD.decimal)))
        if n.sugar_per_100g is not None:
            self.graph.add((node, EX.sugarPer100g, Literal(n.sugar_per_100g, datatype=XSD.decimal)))
        if n.saturated_fat_per_100g is not None:
            self.graph.add((node, EX.saturatedFatPer100g, Literal(n.saturated_fat_per_100g, datatype=XSD.decimal)))
        if n.sodium_mg_per_100g is not None:
            self.graph.add((node, EX.sodiumMgPer100g, Literal(n.sodium_mg_per_100g, datatype=XSD.decimal)))
        if n.cholesterol_mg_per_100g is not None:
            self.graph.add((node, EX.cholesterolMgPer100g, Literal(n.cholesterol_mg_per_100g, datatype=XSD.decimal)))

    def get_all_recipes(self) -> List[RecipeSummary]:
        results = []
        for recipe_node in self.graph.subjects(RDF.type, EX.Recipe):
            slug = str(next(self.graph.objects(recipe_node, EX.slug)))
            title = str(next(self.graph.objects(recipe_node, EX.title)))
            cuisine = str(next(self.graph.objects(recipe_node, EX.cuisine)))
            tags = [str(t) for t in self.graph.objects(recipe_node, EX.tag)]
            time_vals = list(self.graph.objects(recipe_node, EX.totalTimeMinutes))
            total_time = int(time_vals[0]) if time_vals else None
            results.append(RecipeSummary(
                slug=slug, title=title, cuisine=cuisine,
                tags=tags, total_time_minutes=total_time,
            ))
        return results

    def get_recipe_by_slug(self, slug: str) -> Optional[RecipeDetail]:
        recipe_node = EX[f"recipe_{slug}"]
        if (recipe_node, RDF.type, EX.Recipe) not in self.graph:
            return None

        title = str(next(self.graph.objects(recipe_node, EX.title)))
        cuisine = str(next(self.graph.objects(recipe_node, EX.cuisine)))
        servings_vals = list(self.graph.objects(recipe_node, EX.servings))
        servings = int(servings_vals[0]) if servings_vals else None
        time_vals = list(self.graph.objects(recipe_node, EX.totalTimeMinutes))
        total_time = int(time_vals[0]) if time_vals else None

        ingredients = []
        for ing_node in self.graph.objects(recipe_node, EX.hasIngredient):
            raw = str(next(self.graph.objects(ing_node, EX.rawString)))
            norm_vals = list(self.graph.objects(ing_node, EX.normalisedName))
            normalised = str(norm_vals[0]) if norm_vals else None
            qid_vals = list(self.graph.objects(ing_node, EX.wikidataQid))
            wikidata_qid = str(qid_vals[0]) if qid_vals else None
            cat_vals = list(self.graph.objects(ing_node, EX.foodCategory))
            food_category = str(cat_vals[0]) if cat_vals else None
            country_vals = list(self.graph.objects(ing_node, EX.originCountry))
            origin_country = str(country_vals[0]) if country_vals else None

            nutrition = None
            nutr_nodes = list(self.graph.objects(ing_node, EX.hasNutrition))
            if nutr_nodes:
                nutrition = self._read_nutrition(nutr_nodes[0])

            qty_vals = list(self.graph.objects(ing_node, EX.quantityG))
            quantity_g = float(qty_vals[0]) if qty_vals else None

            ingredients.append(EnrichedIngredient(
                raw=raw,
                normalised=normalised,
                wikidata_qid=wikidata_qid,
                food_category=food_category,
                origin_country=origin_country,
                nutrition=nutrition,
                quantity_g=quantity_g,
            ))

        nutrition_per_serving = None
        if servings and any(i.nutrition for i in ingredients):
            total_protein = total_fat = total_carbs = total_kcal = 0.0
            for i in ingredients:
                if not i.nutrition:
                    continue
                factor = (i.quantity_g / 100) if i.quantity_g is not None else 1.0
                total_protein += factor * i.nutrition.protein_per_100g
                total_fat += factor * i.nutrition.fat_per_100g
                total_carbs += factor * i.nutrition.carbs_per_100g
                total_kcal += factor * i.nutrition.kcal_per_100g
            nutrition_per_serving = NutritionPerServing(
                protein_g=total_protein / servings,
                fat_g=total_fat / servings,
                carbs_g=total_carbs / servings,
                kcal=total_kcal / servings,
            )

        return RecipeDetail(
            slug=slug,
            title=title,
            cuisine=cuisine,
            servings=servings,
            total_time_minutes=total_time,
            ingredients=ingredients,
            nutrition_per_serving=nutrition_per_serving,
        )

    def _read_nutrition(self, nutr_node: URIRef) -> NutritionPer100g:
        def _f(prop):
            vals = list(self.graph.objects(nutr_node, prop))
            return float(vals[0]) if vals else None

        return NutritionPer100g(
            protein_per_100g=_f(EX.proteinPer100g) or 0.0,
            fat_per_100g=_f(EX.fatPer100g) or 0.0,
            carbs_per_100g=_f(EX.carbsPer100g) or 0.0,
            kcal_per_100g=_f(EX.kcalPer100g) or 0.0,
            fibre_per_100g=_f(EX.fibrePer100g),
            sugar_per_100g=_f(EX.sugarPer100g),
            saturated_fat_per_100g=_f(EX.saturatedFatPer100g),
            sodium_mg_per_100g=_f(EX.sodiumMgPer100g),
            cholesterol_mg_per_100g=_f(EX.cholesterolMgPer100g),
        )

    def filter_recipes(
        self,
        min_protein: Optional[float] = None,
        max_kcal: Optional[float] = None,
        max_time: Optional[int] = None,
        cuisine: Optional[str] = None,
        dietary: Optional[str] = None,
    ) -> FilterResponse:
        filters_applied = {}
        if min_protein is not None:
            filters_applied["min_protein"] = min_protein
        if max_kcal is not None:
            filters_applied["max_kcal"] = max_kcal
        if max_time is not None:
            filters_applied["max_time"] = max_time
        if cuisine is not None:
            filters_applied["cuisine"] = cuisine
        if dietary is not None:
            filters_applied["dietary"] = dietary

        results = []
        for recipe_node in self.graph.subjects(RDF.type, EX.Recipe):
            if not self._matches_filter(recipe_node, min_protein, max_kcal, max_time, cuisine, dietary):
                continue
            slug = str(next(self.graph.objects(recipe_node, EX.slug)))
            title = str(next(self.graph.objects(recipe_node, EX.title)))
            cuisine_val = str(next(self.graph.objects(recipe_node, EX.cuisine)))
            tags = [str(t) for t in self.graph.objects(recipe_node, EX.tag)]
            time_vals = list(self.graph.objects(recipe_node, EX.totalTimeMinutes))
            total_time = int(time_vals[0]) if time_vals else None
            results.append(RecipeSummary(
                slug=slug, title=title, cuisine=cuisine_val,
                tags=tags, total_time_minutes=total_time,
            ))

        return FilterResponse(
            filters_applied=filters_applied,
            count=len(results),
            results=results,
        )

    def _matches_filter(
        self,
        recipe_node: URIRef,
        min_protein: Optional[float],
        max_kcal: Optional[float],
        max_time: Optional[int],
        cuisine: Optional[str],
        dietary: Optional[str],
    ) -> bool:
        if cuisine is not None:
            vals = list(self.graph.objects(recipe_node, EX.cuisine))
            if not vals or str(vals[0]) != cuisine:
                return False

        if max_time is not None:
            vals = list(self.graph.objects(recipe_node, EX.totalTimeMinutes))
            if not vals or int(vals[0]) > max_time:
                return False

        if min_protein is not None:
            vals = list(self.graph.objects(recipe_node, EX.approxProteinPerServing))
            protein = float(vals[0]) if vals else 0.0
            if protein < min_protein:
                return False

        if max_kcal is not None:
            vals = list(self.graph.objects(recipe_node, EX.approxKcalPerServing))
            kcal = float(vals[0]) if vals else 0.0
            if kcal > max_kcal:
                return False

        if dietary is not None:
            all_flags = set()
            for ing_node in self.graph.objects(recipe_node, EX.hasIngredient):
                for flag in self.graph.objects(ing_node, EX.dietaryFlag):
                    all_flags.add(str(flag))
            if dietary not in all_flags:
                return False

        return True


    def get_ingredient_nutrition(self, ingredient: str) -> Optional[IngredientNutritionResponse]:
        for ing_node in self.graph.subjects(EX.normalisedName, Literal(ingredient)):
            nutr_nodes = list(self.graph.objects(ing_node, EX.hasNutrition))
            if not nutr_nodes:
                continue
            nutrition = self._read_nutrition(nutr_nodes[0])
            qid_vals = list(self.graph.objects(ing_node, EX.wikidataQid))
            wikidata_qid = str(qid_vals[0]) if qid_vals else None
            return IngredientNutritionResponse(
                ingredient=ingredient,
                wikidata_qid=wikidata_qid,
                nutrition=nutrition,
            )
        return None

    def get_ingredient_wikidata(self, ingredient: str) -> Optional[WikidataResponse]:
        for ing_node in self.graph.subjects(EX.normalisedName, Literal(ingredient)):
            qid_vals = list(self.graph.objects(ing_node, EX.wikidataQid))
            if not qid_vals:
                continue
            qid = str(qid_vals[0])
            uri_vals = list(self.graph.objects(ing_node, EX.wikidataUri))
            uri = str(uri_vals[0]) if uri_vals else None
            cat_vals = list(self.graph.objects(ing_node, EX.foodCategory))
            food_category = str(cat_vals[0]) if cat_vals else None
            country_vals = list(self.graph.objects(ing_node, EX.originCountry))
            origin_country = str(country_vals[0]) if country_vals else None
            flags = [str(f) for f in self.graph.objects(ing_node, EX.dietaryFlag)]
            return WikidataResponse(
                ingredient=ingredient,
                wikidata_qid=qid,
                wikidata_uri=uri,
                label=ingredient,
                food_category=food_category,
                origin_country=origin_country,
                dietary_flags=flags,
            )
        return None


def save_graph(kg: RecipeKnowledgeGraph, path: Path) -> None:
    kg.graph.serialize(destination=str(path), format="turtle")


def load_graph(path: Path) -> RecipeKnowledgeGraph:
    kg = RecipeKnowledgeGraph()
    kg.graph.parse(str(path), format="turtle")
    return kg
