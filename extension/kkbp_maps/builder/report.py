"""The Build Report: what a build made, approximated and left out, and which names the Name Tables
didn't know. Written as build-report.json and build-report.md in the Map Library. Never imports bpy."""

from __future__ import annotations

from . import NAME, VERSION, shaders
from .games import camera_profile
from .plan import LibraryPlan

REPORT_VERSION = 1


def build_report(plan: LibraryPlan, results: dict | None = None) -> dict:
    """The report of a build of `plan`. `results` are what the Blender side reports per Map key
    ({"kept": bool, "previews": {...}}) and for the asset files."""
    results = results or {}
    unknown: dict[str, list[str]] = {}
    for a in plan.assets.values():
        for w in a.unknown_words:
            unknown.setdefault(w, []).append(a.name)
    maps = []
    for m in plan.maps:
        tiers = []
        for (shader, t), draws in sorted(m.shader_use.items(), key=lambda kv: (kv[0][0], kv[0][1].level)):
            if t.level == shaders.REBUILT:
                continue
            tiers.append({"shader": shader, "level": t.level, "reason": t.reason,
                          "materials": len(m.shader_materials[(shader, t)]), "draws": draws})
        props = sum(1 for a in plan.assets.values() if a.kind == "prop" and a.source[0] == m.key)
        structures = sum(1 for a in plan.assets.values() if a.kind == "structure" and a.source[0] == m.key)
        profile = camera_profile(plan.game, m.bundle.map["camera"])
        assumptions = []
        if profile.assumed:
            assumptions.append(f"Camera Profile '{m.bundle.map['camera']}' not captured yet: no tonemapper, "
                               "exposure 1, no sun shafts (ADR 0010)")
        maps.append({
            "key": m.key,
            "name": m.name,
            "named": m.named,
            "file": m.file,
            "kept": results.get(m.key, {}).get("kept", False),
            "variants": [v.name for v in m.variants],
            "new_props": props,
            "new_structures": structures,
            "placements": len(m.roots),
            "shader_tiers": tiers,
            "material_notes": [{"note": n, "materials": c} for n, c in sorted(m.notes.items())],
            "extractor_skipped": m.bundle.map["skipped"],
            "left_out_assets": [a.game_name for a in plan.left_out_assets.values() if a.source[0] == m.key],
            "overrides": sorted({a.game_name for a in plan.assets.values() if a.overridden and a.source[0] == m.key}),
            "assumptions": assumptions,
        })
    return {
        "report_version": REPORT_VERSION,
        "builder": {"name": NAME, "version": VERSION},
        "game": plan.game,
        "maps": maps,
        "props": len(plan.props()),
        "structures": len(plan.structures()),
        "map_variants": sum(len(m.variants) for m in plan.maps),
        "unknown_words": {w: sorted(names) for w, names in sorted(unknown.items())},
        "unnamed_maps": [m.key for m in plan.maps if not m.named],
        "files": results.get("files", {}),
    }


def markdown(report: dict) -> str:
    lines = [f"# Build Report: {report['game']} Maps", "",
             f"{len(report['maps'])} Maps, {report['map_variants']} Map Variants, {report['props']} Props and "
             f"{report['structures']} Structures. Built by {report['builder']['name']} {report['builder']['version']}.",
             ""]
    for m in report["maps"]:
        lines += [f"## {m['name']}", "", f"`{m['key']}` → `{m['file']}`{' (kept: unchanged)' if m['kept'] else ''}", ""]
        lines.append(f"- Map Variants: {'; '.join(m['variants'])}")
        lines.append(f"- New Props: {m['new_props']}; new Structures: {m['new_structures']}; Placements: {m['placements']}")
        for t in m["shader_tiers"]:
            what = "left out" if t["level"] == shaders.SKIPPED else "approximated"
            lines.append(f"- `{t['shader']}` {what} ({t['reason']}): {t['materials']} materials, {t['draws']} draws")
        for n in m["material_notes"]:
            lines.append(f"- {n['note']}: {n['materials']} materials")
        for s in m["extractor_skipped"]:
            lines.append(f"- Not in the Map Bundle ({s['reason']}): {s['count']}")
        if m["left_out_assets"]:
            lines.append(f"- Candidates with nothing of their own drawn, not made assets: {', '.join(m['left_out_assets'])}")
        if m["overrides"]:
            lines.append(f"- Made Props by the Name Tables' overrides: {', '.join(m['overrides'])}")
        for a in m["assumptions"]:
            lines.append(f"- Assumed: {a}")
        if not m["named"]:
            lines.append("- The Name Tables don't know this Map: it keeps the game's list name")
        lines.append("")
    if report["unknown_words"]:
        lines += ["## Words the Name Tables don't know", ""]
        lines += [f"- `{w}`: {', '.join(names)}" for w, names in report["unknown_words"].items()]
        lines.append("")
    return "\n".join(lines)
