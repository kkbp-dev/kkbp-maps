# Working on kkbp-maps

Instructions for an AI agent (or anyone) changing this repository. Read this first, then the docs it points to.

kkbp-maps reads the maps of a user's own KK, KKS or SVS install and builds Blender asset libraries from them. It is one Blender extension in two stages: the **Extractor** writes **Map Bundles**, and the **Builder** turns them into a **Map Library**. It is a sister project of KKBP, whose repository sits beside this one at `../kkbp` on the development machine.

Status: Phases 1 and 2 of [docs/design/roadmap.md](docs/design/roadmap.md) are done: the KK spike ([docs/design/kk-spike.md](docs/design/kk-spike.md)) and the Map Bundle contract ([docs/design/map-bundle.md](docs/design/map-bundle.md)), with its checker and tests. There is no Extractor or Builder code yet.

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
- **Layers:** `extractor/` and `bundle/` never import `bpy`. Blender version checks (`bpy.app.version`) live only in `compat/`.
- **Three platforms:** Windows, macOS arm64 and Linux x64. Use `pathlib`, never hard-coded separators, drive letters or Wine paths; no shell-only tooling (D23). A wheel must match the running Python and platform; never hard-code a tag.
- **Game differences** are data about each Game, not checks of the Game's id scattered through the code.
- **Find things by meaning**, such as Texture Roles and Prop hashes, not by object or node names, except where a name is the only marker the game gives (the `p_`, `mo_`, `o_` prefixes, the helper names in [games.md](docs/design/games.md)); those are listed in one place.
- **The contract** is `extension/kkbp_maps/bundle/`: change it only with the user's OK. Until the first release the Schema Version is `0.x` and every change raises its minor (ADR 0014); from `1.0`, additive changes raise the minor and anything else the major. A change touches the schema in `schema/`, the rule text in its `README.md`, the checker (`rules.py`, or `hashing.py` for a Content Hash, which is never additive), `tests/bundle_builder.py` and a test for the new rule.
- **One space:** every value in a Map Bundle is in Blender's space, converted from Unity in one module of the Extractor (ADR 0011). Nothing else converts axes.

## Commands

| What | Command |
|---|---|
| The host tests (about 12 s) | `../kkbp/importer/.venv/bin/python -I -m pytest tests` |
| Check Map Bundles, deep (any Python 3.11 or later) | `python3 tools/check_bundle.py <bundle>...` |

The tests need `pytest` and `jsonschema`, which KKBP's dev venv has; `bundle/` itself needs only the standard library.

## Running the games safely

Only for Reference Captures and investigation, never for users (ADR 0006). Follow "Running the games safely" in `../kkbp/CLAUDE.md`: check a game isn't running before launching it, stop it by its exact process name, and launch through `games/play.sh`.

## The machine

- The games are in `../games/` (KK `Koikatsu`, KKS `Koikatsu Sunshine`, SVS `Summer Vacation Scramble`), HF Patched with BepInEx.
- Blender: 5.2.2 LTS in `~/.local/opt/blender-5.2.2/` (`min`) and the snap (`latest`). A process the Claude desktop app starts can't launch the snap; use `/snap/blender/current/blender`.
- UnityPy 1.25.4 is in KKBP's dev venv, `../kkbp/importer/.venv`.
