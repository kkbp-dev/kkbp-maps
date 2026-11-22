"""The Prop and Structure Candidates, picked by the game's name prefixes (ADR 0004).

One walk from the roots: sky nodes are passed over; a `p_` node starts a Prop, and nothing inside it is
a root of its own; a `mo_` or `o_` node starts a Structure, inside which only `p_` starts a new root;
any other node with a renderer starts an `unprefixed` Structure; a group without a renderer is walked
into. The prefixes are Game data (games.Game.prefixes).
"""

from __future__ import annotations

from ..bundle import hashing


def candidates(nodes: list[dict], prefixes: tuple[tuple[str, str], ...]) -> list[dict]:
    """assets.json's Candidates for scene.json's `nodes`, each with its Placements in walk order."""
    children: list[list[int]] = [[] for _ in nodes]
    for n in nodes:
        if n["parent"] is not None:
            children[n["parent"]].append(n["id"])
    roots: dict[int, str] = {}

    def rule_of(node) -> str | None:
        for prefix, rule in prefixes:
            if node["name"].startswith(prefix):
                return rule
        return None

    def visit(i: int, inside: str | None):
        node = nodes[i]
        if node.get("sky"):
            return
        rule = rule_of(node)
        if inside == "prop":
            pass
        elif rule == "p_prefix":
            roots[i] = rule
            inside = "prop"
        elif inside is None and rule is not None:
            roots[i] = rule
            inside = "structure"
        elif inside is None and "renderer" in node:
            roots[i] = "unprefixed"
            inside = "structure"
        for c in children[i]:
            visit(c, inside)

    for n in nodes:
        if n["parent"] is None:
            visit(n["id"], None)
    shapes = hashing.candidate_shapes(nodes, set(roots))
    by_hash: dict[str, dict] = {}
    for root in sorted(roots):
        rule = roots[root]
        c = by_hash.setdefault(shapes[root], {"hash": shapes[root], "kind": "prop" if rule == "p_prefix" else "structure",
                                              "rule": rule, "placements": []})
        if (c["rule"] == "p_prefix") != (rule == "p_prefix"):
            raise ValueError(f"node {root} has the shape of a {c['kind']} but rule {rule}")
        c["placements"].append(root)
    return list(by_hash.values())
