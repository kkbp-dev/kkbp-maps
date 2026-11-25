"""The look check (ADR 0006): renders the Capture Views from the built Golden Maps, compares each with its
Reference Capture, and writes a side-by-side report.

    python3 tools/look.py                    # render on min, compare, report
    python3 tools/look.py --blender latest
    python3 tools/look.py --no-render        # compare the renders already there
    python3 tools/look.py --update-snapshot  # record this Blender build's numbers in the look snapshot

Needs numpy and Pillow (KKBP's dev venv): ../kkbp/importer/.venv/bin/python -I tools/look.py
It builds the Golden Maps' Map files through the Camera Profile the captures were taken with
(tests/look/KK.json, "camera"; Studio's for now), renders the Capture Views (tests/look/views/KK.json)
and compares them with the captures tools/capture.py took (captures/KK/), within the tolerances in
tests/look/KK.json: one before the Grade and one after it, and a view must pass both. Renders and the
report go to tests/.work/look/ (game content, ADR 0007). Each Map file renders in its own `blender -b`
under the memory watchdog.

The numbers are then compared with the look snapshot, tests/snapshots/look/<Game>.json (numbers only), per
Blender build: a view worse than its recorded numbers by more than the look file's "regression" margins is
a regression even if it passes. A view the look file lists under "accepted" (with the reason the user
accepted it) is reported as accepted rather than failed, and is still checked against the snapshot.
Exits 1 if any view is out of tolerance and not accepted, or regressed.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import look_compare as lc  # noqa: E402
from build_golden import BUILDS, GOLDEN, WORK as BUILD_WORK, blender, blender_path, copy_golden  # noqa: E402
from memory_watch import Limits  # noqa: E402

WORK = REPO / "tests" / ".work" / "look"
BUILD_BUNDLES = BUILD_WORK / "bundles"
SNAPSHOTS = REPO / "tests" / "snapshots" / "look"


def build_and_render(name: str, game: str, look: dict, limits: Limits, switches: list[str], root: Path,
                     keep: bool = False) -> bool:
    """Each Golden Map's file, built through the captures' Camera Profile, then its views rendered.
    With `keep`, from the bundle copies as they are (an experiment may have edited them)."""
    if keep:
        bundles = [BUILD_BUNDLES / Path(*k.split("/")) for k in GOLDEN[game]]
    else:
        bundles = copy_golden(REPO / "golden" / game, GOLDEN[game])
    if bundles is None:
        return False
    library = root / f"{game} Maps"
    if library.exists():
        shutil.rmtree(library)
    profile = root / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    log = root / "look.log"
    log.write_text("")
    exe = blender_path(name)
    for key in GOLDEN[game]:
        cmd = ["--python", str(REPO / "tools" / "blender_build.py"), "--", "--library", str(library),
               "--bundles", *map(str, bundles), "--step", f"map:{key}", "--no-previews", "--camera", look["camera"],
               *[a for sw in switches for a in ("--look", sw)]]
        code, peak, reason = blender(exe, profile, cmd, limits, log)
        print(f"look: built {key} on {name}: {'ok' if code == 0 else f'failed ({reason or code})'}, "
              f"peak {peak / 2**30:.2f} GB", flush=True)
        if code != 0:
            print(f"  see {log}")
            return False
    for blend in sorted((library / "Maps").glob("*.blend")):
        code, peak, reason = blender(exe, profile, [
            str(blend), "--python", str(REPO / "tests" / "blender" / "render_views.py"), "--",
            str(REPO / "tests" / "look" / "views" / f"{game}.json"), str(REPO / "tests" / "look" / f"{game}.json"),
            str(root / "renders"), str(REPO / "captures" / game)], limits, log)
        print(f"look: rendered {blend.stem} on {name}: {'ok' if code == 0 else f'failed ({reason or code})'}, "
              f"peak {peak / 2**30:.2f} GB", flush=True)
        if code != 0:
            print(f"  see {log}")
            return False
    return True


def _img(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def _data_uri(a: np.ndarray, scale: int = 2) -> str:
    im = Image.fromarray(a)
    im = im.resize((im.width // scale, im.height // scale), Image.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _heat(r: lc.Result) -> np.ndarray:
    x = np.clip(r.heat / (2 * r.tolerance.p95_de), 0, 1)
    return (np.stack([x, np.clip(1.5 - 3 * np.abs(x - 0.5), 0, 1), 1 - x], -1) * 255).astype(np.uint8)


def compare_all(root: Path, game: str, look: dict, pregrade: bool = False) -> list[dict]:
    """Each Capture View's render against its capture; with `pregrade`, both before the Grade."""
    views = json.loads((REPO / "tests" / "look" / "views" / f"{game}.json").read_text())["views"]
    t = lc.tolerances(look)["pregrade" if pregrade else "graded"]
    rows = []
    renders = root / "renders"
    for v in views:
        rel = Path(v["map"]) / v["variant"] / v["name"]
        if pregrade:
            cap, ren = renders / f"{rel}.capture-pregrade.png", renders / f"{rel}.pregrade.png"
        else:
            cap, ren = REPO / "captures" / game / f"{rel}.png", renders / f"{rel}.png"
        row = {"view": str(rel), "capture": cap, "render": ren}
        if not cap.exists() or not ren.exists():
            row["missing"] = "capture" if not cap.exists() else "render"
        else:
            row["result"] = lc.compare(_img(ren), _img(cap), t)
        rows.append(row)
    return rows


def report(rows: list[dict], root: Path, game: str, name: str = "report", accepted: dict | None = None) -> Path:
    accepted = accepted or {}
    parts = [f"<!doctype html><meta charset=utf-8><title>Look check {game} {root.name}</title><style>"
             "body{font:14px system-ui;margin:16px;background:#1b1b1b;color:#ddd}img{width:32%;margin-right:1%}"
             "h2{font-size:15px;margin:24px 0 4px}.fail{color:#f77}.pass{color:#7d7}.accepted{color:#db7}td,th{padding:2px 10px;text-align:right}"
             "</style>", f"<h1>Look check: {game}, {html.escape(root.name)}</h1><p>Left: Reference Capture. Middle: Blender. "
             "Right: ΔE2000 (blue 0, red ≥ twice the p95 tolerance).</p><table><tr><th>view<th>mean ΔE<th>p95 ΔE"
             "<th>worst tile<th>"]
    for r in rows:
        if "missing" in r:
            parts.append(f"<tr><td>{html.escape(r['view'])}<td colspan=4 class=fail>no {r['missing']}")
        else:
            s = r["result"].summary()
            cls = "pass" if s["passed"] else "accepted" if r["view"] in accepted else "fail"
            parts.append(f"<tr><td><a href='#{html.escape(r['view'])}'>{html.escape(r['view'])}</a><td>{s['mean_de']}"
                         f"<td>{s['p95_de']}<td>{s['worst_tile']:+.1%}<td class={cls} title='{html.escape(accepted.get(r["view"], ""))}'>{cls}")
    parts.append("</table>")
    for r in rows:
        if "missing" in r:
            continue
        res = r["result"]
        parts.append(f"<h2 id='{html.escape(r['view'])}'>{html.escape(r['view'])}: {res.summary()}</h2>"
                     f"<img src='{_data_uri(_img(r['capture']))}'><img src='{_data_uri(_img(r['render']))}'>"
                     f"<img src='{_data_uri(_heat(res))}'>")
    path = root / f"{name}.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", default="KK")
    ap.add_argument("--blender", default="min", choices=sorted(BUILDS))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--keep-bundles", action="store_true", help="build from the bundle copies as they are")
    ap.add_argument("--tag", default="", help="a name for an experiment's folder, such as one on edited bundle copies")
    ap.add_argument("--look", action="append", default=[], metavar="NAME=VALUE",
                    help="a look switch for the build (extension/kkbp_maps/builder/look.py)")
    ap.add_argument("--update-snapshot", action="store_true",
                    help="record this Blender build's numbers in the look snapshot (review the diff)")
    ap.add_argument("--max-rss-gb", type=float, default=8.0)
    args = ap.parse_args(argv)
    if args.update_snapshot and (args.look or args.tag or args.keep_bundles):
        ap.error("--update-snapshot records the default build only, without --look, --tag or --keep-bundles")
    look = json.loads((REPO / "tests" / "look" / f"{args.game}.json").read_text())
    root = WORK / (args.blender + "".join(f"+{sw}" for sw in sorted(args.look)) + (f"+{args.tag}" if args.tag else ""))
    if not args.no_render and not build_and_render(args.blender, args.game, look,
                                                   Limits(max_rss_gb=args.max_rss_gb, min_available_gb=1.5,
                                                          min_swap_free_gb=6.0), args.look, root,
                                                   args.keep_bundles):
        return 1
    rows = {}
    for kind in lc.PASSES:
        rows[kind] = compare_all(root, args.game, look, pregrade=kind == "pregrade")
        path = report(rows[kind], root, args.game, "report-pregrade" if kind == "pregrade" else "report",
                      look.get("accepted", {}))
        within = sum(1 for r in rows[kind] if "result" in r and r["result"].passed)
        print(f"look: {kind}, {within} of {len(rows[kind])} views within tolerance; report {path}")
    views = [r["view"] for r in rows["graded"]]
    print(f"  {'view':34} {'before the Grade':>26}   {'after the Grade':>26}")
    for i, view in enumerate(views):
        cells = []
        for kind in lc.PASSES:
            r = rows[kind][i]
            if "missing" in r:
                cells.append(f"{'no ' + r['missing']:>26}")
            else:
                m = r["result"].summary()
                state = "pass" if m["passed"] else "accepted" if view in look.get("accepted", {}) else "FAIL"
                cells.append(f"{m['mean_de']:5.2f} {m['p95_de']:5.1f} {m['worst_tile']:5.0%} {state:>8}")
        print(f"  {view:34} {cells[0]}   {cells[1]}")
    summary = {kind: {r["view"]: {k: v for k, v in r["result"].summary().items() if k != "passed"}
                      for r in rows[kind] if "result" in r} for kind in lc.PASSES}
    (root / "summary.json").write_text(json.dumps(summary, indent=1))
    out = [v for i, v in enumerate(views)
           if any("missing" in rows[k][i] or not rows[k][i]["result"].passed for k in lc.PASSES)]
    accepted = look.get("accepted", {})
    failed = [v for v in out if v not in accepted]
    for v in sorted(set(accepted) - set(out)):
        print(f"  {v} is accepted but {'passes' if v in views else 'is no Capture View'}: take it out of \"accepted\"")
    print(f"look: {len(views) - len(out)} of {len(views)} views pass both, {len(out) - len(failed)} accepted, "
          f"{len(failed)} failing")
    return check_snapshot(args.game, args.blender, summary, look, args.update_snapshot) or (1 if failed else 0)


def check_snapshot(game: str, build: str, summary: dict, look: dict, update: bool) -> int:
    """Compares this build's numbers with the look snapshot, or records them."""
    path = SNAPSHOTS / f"{game}.json"
    snapshot = json.loads(path.read_text()) if path.exists() else {}
    if update:
        snapshot[build] = summary
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
        print(f"look: recorded {build}'s numbers in {path.relative_to(REPO)}")
        return 0
    if build not in snapshot:
        print(f"look: no snapshot for {build} yet; record one with --update-snapshot")
        return 0
    margin = look.get("regression", {})
    worse = [f"{kind}, {line}" for kind in lc.PASSES
             for line in lc.regressions(snapshot[build].get(kind, {}), summary.get(kind, {}), margin)]
    for line in worse:
        print(f"  regressed: {line}")
    print(f"look: {len(worse)} regressions from the snapshot" if worse else "look: no regressions from the snapshot")
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
