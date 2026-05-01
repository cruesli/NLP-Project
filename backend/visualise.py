"""Visualise the recipe knowledge graph from graph.ttl.

One subplot per recipe: recipe (red) → ingredients (blue) → nutrition (green).
Run with:  python -m backend.visualise
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import networkx as nx
from rdflib import Graph, Namespace, RDF

ROOT = Path(__file__).parent.parent
TTL_PATH = ROOT / "graph.ttl"
OUT_PATH = ROOT / "graph.png"

EX = Namespace("http://example.org/recipe-kg/")

COLORS = {"Recipe": "#E07070", "Ingredient": "#70A0D0", "Nutrition": "#70C070"}
SIZES  = {"Recipe": 2200,      "Ingredient": 900,        "Nutrition": 700}


def _shorten(s: str, n: int = 14) -> str:
    return (s[:n] + "…") if len(s) > n else s


def _label(g: Graph, node, ntype: str) -> str:
    if ntype == "Recipe":
        v = next(g.objects(node, EX.title), None)
        return str(v) if v else str(node).split("/")[-1]
    if ntype == "Ingredient":
        v = next(g.objects(node, EX.normalisedName), None)
        if v:
            return _shorten(str(v))
        v = next(g.objects(node, EX.rawString), None)
        return _shorten(str(v)) if v else str(node).split("/")[-1]
    if ntype == "Nutrition":
        kcal = next(g.objects(node, EX.kcalPer100g), None)
        prot = next(g.objects(node, EX.proteinPer100g), None)
        parts = []
        if kcal:
            parts.append(f"{float(kcal):.0f}kcal")
        if prot:
            parts.append(f"{float(prot):.1f}g")
        return "\n".join(parts) if parts else "nutr"
    return str(node)


def build(g: Graph) -> tuple[nx.DiGraph, dict[str, str], dict[str, str]]:
    G = nx.DiGraph()
    node_types: dict[str, str] = {}
    labels: dict[str, str] = {}

    type_map = {
        str(EX.Recipe):    "Recipe",
        str(EX.Ingredient):"Ingredient",
        str(EX.Nutrition): "Nutrition",
    }
    for s, _, o in g.triples((None, RDF.type, None)):
        ntype = type_map.get(str(o))
        if ntype:
            nid = str(s)
            node_types[nid] = ntype
            labels[nid] = _label(g, s, ntype)
            G.add_node(nid)

    for s, _, o in g:
        sid, oid = str(s), str(o)
        if sid in node_types and oid in node_types:
            G.add_edge(sid, oid)

    return G, node_types, labels


def _subplot_pos(recipe: str, ings: list[str], G: nx.DiGraph,
                 nutritions: set[str]) -> dict[str, tuple[float, float]]:
    n = len(ings)
    pos: dict[str, tuple[float, float]] = {}
    pos[recipe] = (n / 2, 4.0)
    for ii, ing in enumerate(ings):
        pos[ing] = (float(ii), 2.0)
        for nutr in G.successors(ing):
            if nutr in nutritions:
                pos[nutr] = (float(ii), 0.0)
    return pos


def draw(G: nx.DiGraph, node_types: dict[str, str], labels: dict[str, str],
         out_path: Path) -> None:
    recipes     = sorted(n for n, t in node_types.items() if t == "Recipe")
    ingredients = {n for n, t in node_types.items() if t == "Ingredient"}
    nutritions  = {n for n, t in node_types.items() if t == "Nutrition"}

    n = len(recipes)
    n_cols = min(n, 3)
    n_rows = math.ceil(n / n_cols)

    # Width per subplot scales with the widest recipe ingredient count
    ing_counts = [sum(1 for x in G.successors(r) if x in ingredients) for r in recipes]
    max_ings = max(ing_counts, default=1)
    col_w = max(6, max_ings * 0.9)

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(col_w * n_cols, 8 * n_rows),
                             squeeze=False)

    legend = [mpatches.Patch(color=c, label=t) for t, c in COLORS.items()]

    for i, recipe in enumerate(recipes):
        ax = axes[i // n_cols][i % n_cols]

        ings = sorted(G.successors(recipe), key=lambda n: n)
        ings = [x for x in ings if x in ingredients]
        sub_nodes = [recipe] + ings + [
            nutr for ing in ings for nutr in G.successors(ing) if nutr in nutritions
        ]
        Gsub = G.subgraph(sub_nodes)
        pos = _subplot_pos(recipe, ings, G, nutritions)

        for ntype, color in COLORS.items():
            nodes = [nd for nd in Gsub.nodes if node_types[nd] == ntype]
            if nodes:
                nx.draw_networkx_nodes(
                    Gsub, pos, nodelist=nodes, node_color=color,
                    node_size=SIZES[ntype], alpha=0.88, ax=ax,
                )
        nx.draw_networkx_labels(
            Gsub, pos, labels={nd: labels[nd] for nd in Gsub.nodes},
            font_size=7, font_weight="bold", ax=ax,
        )
        nx.draw_networkx_edges(
            Gsub, pos, edge_color="#777", arrows=True, arrowsize=10,
            alpha=0.6, ax=ax, connectionstyle="arc3,rad=0.05",
        )

        ax.set_title(labels[recipe], fontsize=11, fontweight="bold")
        ax.axis("off")

    # Hide unused subplot panels
    for j in range(n, n_rows * n_cols):
        axes[j // n_cols][j % n_cols].set_visible(False)

    fig.legend(handles=legend, loc="lower right", fontsize=10, framealpha=0.9)
    fig.suptitle("Recipe Knowledge Graph", fontsize=15, fontweight="bold", y=1.01)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved → {out_path}")


def main() -> None:
    if not TTL_PATH.exists():
        sys.exit(f"Not found: {TTL_PATH} — run the ingest pipeline first.")

    g = Graph()
    g.parse(str(TTL_PATH), format="turtle")
    print(f"Loaded {len(g)} triples from {TTL_PATH}")

    G, node_types, labels = build(g)
    n_recipes = sum(1 for t in node_types.values() if t == "Recipe")
    print(f"Nodes: {len(G.nodes)}, Edges: {len(G.edges)}, Recipes: {n_recipes}")

    draw(G, node_types, labels, OUT_PATH)


if __name__ == "__main__":
    main()
