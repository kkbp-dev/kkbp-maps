# Working on kkbp-maps

Instructions for an AI agent (or anyone) changing this repository. Read this first, then the docs it points to.

kkbp-maps reads the maps of a user's own KK, KKS or SVS install and builds Blender asset libraries from them. It is one Blender extension in two stages: the **Extractor** writes **Map Bundles**, and the **Builder** turns them into a **Map Library**. It is a sister project of KKBP, whose repository sits beside this one at `../kkbp` on the development machine.

Status: Phases 1 and 2 of [docs/design/roadmap.md](docs/design/roadmap.md) are done: the KK spike ([docs/design/kk-spike.md](docs/design/kk-spike.md)) and the Map Bundle contract ([docs/design/map-bundle.md](docs/design/map-bundle.md)), with its checker and tests. Phase 3, the KK Extractor (`extension/kkbp_maps/extractor/`), writes Golden Maps that pass the deep check. Phase 4, the KK Builder (`extension/kkbp_maps/builder/`), builds them into a Map Library on both Blender builds, checked against committed snapshots. Phase 5, the look check, passes or has accepted every view through both Camera Profiles. Phase 6, the product shell, is the extension as users get it: its manifest and entry point (`extension/kkbp_maps/__init__.py`), the pinned wheels shipped inside a zip per platform (`deps/`, ADR 0029), the Build driver that runs each step in a watched process outside Blender (`jobs/`), and the N-panel (`ui/`). Its release checklist is [docs/release/v0.1.md](docs/release/v0.1.md); Windows and macOS are checked by hand there.

## Read before changing anything

- [CONTEXT.md](CONTEXT.md): the glossary. Use its terms, not the ones it lists under "Avoid".
- [docs/design/README.md](docs/design/README.md): the shape of the tool and every numbered decision (D1 onwards).
- [docs/design/games.md](docs/design/games.md): what each Game's map data looks like.
- [docs/design/map-bundle.md](docs/design/map-bundle.md) and [extension/kkbp_maps/bundle/README.md](extension/kkbp_maps/bundle/README.md): the Map Bundle contract and its rules.
- [docs/adr/](docs/adr/): decisions that look wrong without context. Check them before "fixing" something that seems odd.

## How to work

- Before writing code, list every undecided point with a proposal and wait for the user's OK.
- Record a surprising decision as a new ADR (next number in `docs/adr/`), list it in `docs/design/README.md`, and add new terms to `CONTEXT.md` (a glossary only, never implementation detail).
- Work in small commits. Stage files by path; never `git add -A`. End every commit message with the `Co-Authored-By:` trailer of the model that wrote it.
- The git author is a placeholder from the global `~/.gitconfig`; leave it alone.
- Nothing gets installed into Blender's own Python or the user's Blender profile without their OK, and each OK covers that one install.
- Long runs (extracting or building many Maps, the full test suite) run in the background.

## Rules the code follows

- **No game content in the repository** (ADR 0007): no bundles, Map Bundles, textures, meshes, built libraries, Golden Maps or Reference Captures. Snapshots hold counts, names, hashes and tags only.
- **Files only** (ADR 0001): the Extractor never starts or talks to a game. Only the developer capture plugin runs inside a game.
- **Layers:** `extractor/` and `bundle/` never import `bpy`, and neither does the Builder's plan (everything in `builder/` outside `builder/blender/`), which decides what a build makes and is host-tested. `jobs/` and `deps/` import only the standard library: the driver runs on Blender's Python outside Blender, and UnityPy is never imported in Blender's own process. The package's `__init__.py` imports bpy only in `register()`. Blender version checks (`bpy.app.version`) live only in `compat/`. In the Extractor only `unity.py` imports UnityPy; the rest works on its Store of plain data, which the host tests fake (`tests/fake_scene.py`).
- **Three platforms:** Windows, macOS arm64 and Linux x64. Use `pathlib`, never hard-coded separators, drive letters or Wine paths; no shell-only tooling (D23). A wheel must match the running Python and platform; no wheel tag in the extension's code (the lock tool picks one file per platform). numpy and attrs are Blender's own (`deps.FROM_BLENDER`), never shipped.
- **Game differences** are data about each Game, not checks of the Game's id scattered through the code.
- **Find things by meaning**, such as Texture Roles and Prop hashes, not by object or node names, except where a name is the only marker the game gives (the `p_`, `mo_`, `o_` prefixes, the room containers of ADR 0019, the helper names in [games.md](docs/design/games.md)); those are listed in one place, `extractor/games.py`.
- **The contract** is `extension/kkbp_maps/bundle/`: change it only with the user's OK. Until the first release the Schema Version is `0.x` and every change raises its minor (ADR 0014); from `1.0`, additive changes raise the minor and anything else the major. A change touches the schema in `schema/`, the rule text in its `README.md`, the checker (`rules.py`, or `hashing.py` for a Content Hash, which is never additive), `tests/bundle_builder.py` and a test for the new rule.
- **One space:** every value in a Map Bundle is in Blender's space, converted from Unity in one module of the Extractor (ADR 0011). Nothing else converts axes.

## Commands

| What | Command |
|---|---|
| The tests (about 15 s): host tests, and game-backed ones that skip without the install or the Golden Maps | `../kkbp/importer/.venv/bin/python -I -m pytest tests` |
| Make the Golden Maps (stale ones only; `--force` for all), check them and compare the snapshot, in the background | `../kkbp/importer/.venv/bin/python -I tools/golden.py` |
| Record the extraction snapshot after an intended change (review the diff) | `../kkbp/importer/.venv/bin/python -I tools/golden.py --update-snapshot` |
| Check Map Bundles, deep (any Python 3.11 or later) | `python3 tools/check_bundle.py <bundle>...` |
| Build copies of the Golden Maps on `min` then `latest`, summarize the files and compare the build snapshot, in the background (about 30 s of building per Blender build, plus a summary per file) | `python3 tools/build_golden.py` |
| Record the build snapshot after an intended change (review the diff) | `python3 tools/build_golden.py --update-snapshot` |
| The look check: build the Golden Maps, render the Capture Views, compare with the Reference Captures (both passes) and the look snapshot, in the background; `--camera game` for the story game's | `../kkbp/importer/.venv/bin/python -I tools/look.py [--blender latest] [--camera game]` |
| Record the look snapshot after an intended change (review the diff), per Blender build and Camera Profile | `../kkbp/importer/.venv/bin/python -I tools/look.py --no-render --update-snapshot [--blender latest] [--camera game]` |
| Lock the pinned dependencies after raising a pin in `deps/__init__.py` (reads PyPI; review the diff) | `python3 tools/lock_deps.py` |
| Make the zips, one per platform, into `dist/` (downloads the locked wheels once into `dist/wheels/`) | `python3 tools/package.py` |
| Check this platform's zip as a user gets it: a throwaway profile, the Golden Maps built through the extension, both snapshots, in the background | `python3 tools/product_check.py` |
| Run a Build from a request file, as the N-panel does | `<python> -I extension/kkbp_maps/jobs/driver.py --request "<out>/Map Bundles/KK/build-request.json"` |
| Build a Map Library from Map Bundles | `<blender> -b --factory-startup --python tools/blender_build.py -- --library "<out>/KK Maps" --bundles <bundle>...` |

The tests need `pytest` and `jsonschema`, and the Extractor UnityPy, numpy and Pillow, all in KKBP's dev venv; `bundle/` itself needs only the standard library. `golden.py` extracts each Map in a process it watches, and stops it before memory runs short. A Golden Map takes 15 to 40 s and under 1 GB. `build_golden.py` runs each build step in its own `blender -b` process under the same watchdog (`extension/kkbp_maps/jobs/memory.py`, which reads each platform's own counters), one Blender build at a time, with its own profile and `extension/` on the path, so nothing is installed into Blender. Its work folder, `tests/.work/`, is under home because the snap can't see `/tmp`.

## Running the games safely

Only for Reference Captures and investigation, never for users (ADR 0006). Follow "Running the games safely" in `../kkbp/CLAUDE.md`: check a game isn't running before launching it, stop it by its exact process name, and launch through `games/play.sh`.

## The machine

- The games are in `../games/` (KK `Koikatsu`, KKS `Koikatsu Sunshine`, SVS `Summer Vacation Scramble`), HF Patched with BepInEx.
- Blender: 5.2.2 LTS in `~/.local/opt/blender-5.2.2/` (`min`) and the snap (`latest`). A process the Claude desktop app starts can't launch the snap; use `/snap/blender/current/blender`.
- UnityPy 1.25.4 is in KKBP's dev venv, `../kkbp/importer/.venv`.
