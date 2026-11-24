"""The look check (ADR 0006): renders the Capture Views from the built Golden Maps, compares each with its
Reference Capture, and writes a side-by-side report.

    python3 tools/look.py                    # render on min, compare, report
    python3 tools/look.py --blender latest
    python3 tools/look.py --no-render        # compare the renders already there

Needs numpy and Pillow (KKBP's dev venv): ../kkbp/importer/.venv/bin/python -I tools/look.py
It builds the Golden Maps' Map files through the Camera Profile the captures were taken with
(tests/look/KK.json, "camera"; Studio's for now), renders the Capture Views (tests/look/views/KK.json)
and compares them with the captures tools/capture.py took (captures/KK/), within the tolerances in
tests/look/KK.json. Renders and the report go to tests/.work/look/ (game content, ADR 0007). Each Map
file renders in its own `blender -b` under the memory watchdog. Exits 1 if any view is out of tolerance.
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
from build_golden import BUILDS, GOLDEN, blender, blender_path, copy_golden  # noqa: E402
from memory_watch import Limits  # noqa: E402

WORK = REPO / "tests" / ".work" / "look"


def tolerance(look: dict) -> lc.Tolerance:
    return lc.Tolerance(**look.get("tolerance", {}))


def build_and_render(name: str, game: str, look: dict, limits: Limits) -> bool:
    """Each Golden Map's file, built through the captures' Camera Profile, then its views rendered."""
    bundles = copy_golden(REPO / "golden" / game, GOLDEN[game])
    if bundles is None:
        return False
    root = WORK / name
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
               "--bundles", *map(str, bundles), "--step", f"map:{key}", "--no-previews", "--camera", look["camera"]]
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
            str(root / "renders")], limits, log)
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


def compare_all(blender: str, game: str, look: dict) -> list[dict]:
    views = json.loads((REPO / "tests" / "look" / "views" / f"{game}.json").read_text())["views"]
    t = tolerance(look)
    rows = []
    for v in views:
        rel = Path(v["map"]) / v["variant"] / f"{v['name']}.png"
        cap, ren = REPO / "captures" / game / rel, WORK / blender / "renders" / rel
        row = {"view": str(rel.with_suffix("")), "capture": cap, "render": ren}
        if not cap.exists() or not ren.exists():
            row["missing"] = "capture" if not cap.exists() else "render"
        else:
            row["result"] = lc.compare(_img(ren), _img(cap), t)
        rows.append(row)
    return rows


def report(rows: list[dict], blender: str, game: str) -> Path:
    parts = [f"<!doctype html><meta charset=utf-8><title>Look check {game} {blender}</title><style>"
             "body{font:14px system-ui;margin:16px;background:#1b1b1b;color:#ddd}img{width:32%;margin-right:1%}"
             "h2{font-size:15px;margin:24px 0 4px}.fail{color:#f77}.pass{color:#7d7}td,th{padding:2px 10px;text-align:right}"
             "</style>", f"<h1>Look check: {game} on {blender}</h1><p>Left: Reference Capture. Middle: Blender. "
             "Right: ΔE2000 (blue 0, red ≥ twice the p95 tolerance).</p><table><tr><th>view<th>mean ΔE<th>p95 ΔE"
             "<th>worst tile<th>"]
    for r in rows:
        if "missing" in r:
            parts.append(f"<tr><td>{html.escape(r['view'])}<td colspan=4 class=fail>no {r['missing']}")
        else:
            s = r["result"].summary()
            cls = "pass" if s["passed"] else "fail"
            parts.append(f"<tr><td><a href='#{html.escape(r['view'])}'>{html.escape(r['view'])}</a><td>{s['mean_de']}"
                         f"<td>{s['p95_de']}<td>{s['worst_tile']:+.1%}<td class={cls}>{'pass' if s['passed'] else 'fail'}")
    parts.append("</table>")
    for r in rows:
        if "missing" in r:
            continue
        res = r["result"]
        parts.append(f"<h2 id='{html.escape(r['view'])}'>{html.escape(r['view'])}: {res.summary()}</h2>"
                     f"<img src='{_data_uri(_img(r['capture']))}'><img src='{_data_uri(_img(r['render']))}'>"
                     f"<img src='{_data_uri(_heat(res))}'>")
    path = WORK / blender / "report.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", default="KK")
    ap.add_argument("--blender", default="min", choices=sorted(BUILDS))
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--max-rss-gb", type=float, default=8.0)
    args = ap.parse_args(argv)
    look = json.loads((REPO / "tests" / "look" / f"{args.game}.json").read_text())
    if not args.no_render and not build_and_render(args.blender, args.game, look,
                                                   Limits(max_rss_gb=args.max_rss_gb, min_available_gb=1.5,
                                                          min_swap_free_gb=6.0)):
        return 1
    rows = compare_all(args.blender, args.game, look)
    path = report(rows, args.blender, args.game)
    failed = [r for r in rows if "missing" in r or not r["result"].passed]
    for r in rows:
        print(f"  {r['view']}: {r.get('missing') and 'no ' + r['missing'] or r['result'].summary()}")
    print(f"look: {len(rows) - len(failed)} of {len(rows)} views within tolerance; report {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
