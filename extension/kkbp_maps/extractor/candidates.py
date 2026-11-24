"""The Prop and Structure Candidates, picked by the game's name prefixes (ADR 0004).

One walk from the roots: sky nodes are passed over; a room container (a node without a renderer whose
name marks it as a whole room, ADR 0019) is walked into like a group; a `p_` node starts a Prop, and
nothing inside it is a root of its own; a `mo_` or `o_` node starts a Structure, inside which only `p_`
starts a new root; any other node with a renderer starts an `unprefixed` Structure; a group without a
renderer is walked into. A subtree outside any Placement whose renderers only cast shadows starts
nothing: it is the Map Variant's own (ADR 0024). The prefixes and container names are Game data
(games.Game).

Placements with the same shape are one Candidate, which takes the rule of the first of them in walk
order. An unprefixed Placement with a Prop's shape is another Placement of that Prop (ADR 0023): KK
places plain copies of a `p_` Prop without the prefix. A `mo_` or `o_` Structure with a Prop's shape
can't be told apart from it, and stops the extraction.
"""

from __future__ import annotations

import re

from ..bundle import hashing


def candidates(nodes: list[dict], prefixes: tuple[tuple[str, str], ...], containers: tuple[str, ...] = ()) -> list[dict]:
    """assets.json's Candidates for scene.json's `nodes`, each with its Placements in walk order."""
    container = [re.compile(c) for c in containers]
    children: list[list[int]] = [[] for _ in nodes]
    for n in nodes:
        if n["parent"] is not None:
            children[n["parent"]].append(n["id"])
    roots: dict[int, str] = {}

    def rule_of(node) -> str | None:
        if "renderer" not in node and any(c.search(node["name"]) for c in container):
            return None  # a room container: walked into
        for prefix, rule in prefixes:
            if node["name"].startswith(prefix):
                return rule
        return None

    def casts_only(i: int) -> bool:
        """Whether every renderer in the subtree only casts shadows (and there is one)."""
        modes = []
        stack = [i]
        while stack:
            n = nodes[stack.pop()]
            if "renderer" in n:
                modes.append(n["renderer"]["shadows"])
            stack.extend(children[n["id"]])
        return bool(modes) and all(m == "shadows_only" for m in modes)

    def visit(i: int, inside: str | None):
        node = nodes[i]
        if node.get("sky"):
            return
        if inside is None and casts_only(i):
            return  # hidden shadow casters outside any Placement: the Map Variant's own (ADR 0024)
        rule = rule_of(node)
        if inside == "prop":
            pass
        elif rule == "p_prefix":
            roots[i] = rule
            inside = "prop"
        elif inside is None and rule is not None:
            roots[i] = rule
            inside = "structure"
        elif inside is None and rule is None and "renderer" in node:
            roots[i] = "unprefixed"
            inside = "structure"
        for c in children[i]:
            visit(c, inside)

    for n in nodes:
        if n["parent"] is None:
            visit(n["id"], None)
    shapes = hashing.candidate_shapes(nodes, set(roots))
    prop_shapes = {shapes[r] for r, rule in roots.items() if rule == "p_prefix"}
    for root, rule in roots.items():
        if rule == "unprefixed" and shapes[root] in prop_shapes and not _holds_roots(root, roots, children):
            roots[root] = "p_prefix"  # a copy of the Prop, without its prefix (ADR 0023)
    by_hash: dict[str, dict] = {}
    for root in sorted(roots):
        rule = roots[root]
        c = by_hash.setdefault(shapes[root], {"hash": shapes[root], "kind": "prop" if rule == "p_prefix" else "structure",
                                              "rule": rule, "placements": []})
        if (c["rule"] == "p_prefix") != (rule == "p_prefix"):
            raise ValueError(f"node {root} ({nodes[root]['name']}) has the shape of a {c['kind']} but rule {rule}")
        c["placements"].append(root)
    return list(by_hash.values())


def _holds_roots(node: int, roots: dict, children: list[list[int]]) -> bool:
    """Whether another Placement root lies under `node`: a Prop can't hold one."""
    stack = list(children[node])
    while stack:
        i = stack.pop()
        if i in roots:
            return True
        stack.extend(children[i])
    return False
