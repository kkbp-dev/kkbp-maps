# Roadmap

The order of work. Decisions (D1 onwards) are in [README.md](README.md).

| Phase | What | Done when |
|---|---|---|
| 0 Bootstrap | This repository: glossary, ADRs, design, agent instructions | Committed |
| 1 KK spike | A throwaway script on KK's 1F, park and ground: scene graph walk, Unity-to-Blender axes in one place, meshes with UV1, the lightmap encoding and colour space, `LightmapPrefab`, `SunLightInfo` and its LUTs, RenderSettings ambient and fog | A design note answers each "to confirm" in [games.md](games.md); the script is not kept |
| 2 Map Bundle contract | Schemas: Manifest, nodes and transforms, shared meshes, materials by Raw Property with Texture Roles, textures, Lightmap Sets, lights, environment, Grades per Time of Day, Placements, Prop and Structure candidates with hashes, Map metadata | Schemas, rule text and a checker, with tests on synthetic bundles |
| 3 KK Extractor | Game detection, Map lists, dependency resolution, helper filters, Prop hashing, texture decoding, lightmaps, lights, environment, a resumable cache | Golden Maps pass the contract check |
| 4 KK Builder | Library layout, meshes, Base Materials, Variant Materials, Grades, Lighting Rigs, Worlds from Sky Domes, lightmap UDIMs of mixed tile sizes, assets with catalogs, tags and previews, Map Variants, Structures, Name Tables, the Build Report. KK's one `Shader Forge/main_item` use (lovehotel) is approximated; its Game Shader Model comes with the Golden Map that needs it | The Golden Maps build, with committed snapshots |
| 5 Look check | The dev-only capture plugin for KK, the game camera's Grade and sun shaft settings (ADR 0010), the camera presets, the image comparison and its report | Every Golden Map's Map Variants are within tolerance |
| 6 Product shell | Wheels inside a zip per platform (ADR 0029), N-panel, background build, library registration, packaging, release checklist | **v0.1, KK only**, checked on Linux, Windows and macOS arm64. *v0.1.0 released, checked on Linux only; Windows and macOS are unchecked ([release/v0.1.md](../release/v0.1.md))* |
| 7 KKS | Shared dependencies, splitting the batched meshes, SpeedTree with wind, Koikano shaders, SkyStudio skies, realtime Lighting Rigs, four Times of Day, PostProcessing Grades, Studio Maps | KKS Golden Maps pass the snapshots and the look check |
| 8 SVS | MemoryPack lists, external Lightmap Sets matched by name, URP Lit and SpeedTree8, URP lights, trilight ambient, Volume Grades, H furniture | SVS Golden Maps pass the snapshots and the look check |
| 9 Mods | KK and KKS Sideloader map zipmods read in place, with their Studio lists | A sample of modded Maps builds |
| 10 KKBP Hook | In KKBP: a Hook that re-grades a Character from a Map Variant's recorded light and Grade | Released by KKBP |

## What carries over from KKBP

Paths are in the KKBP repository.

- `importer/tools/game_shaders/` (`dump.py`, `dxdis.py`, `models.py`): shader disassembly and Game Shader Models.
- `importer/kkbp/pillow.py`: checking a wheel's tags against the running Blender with `packaging`.
- `docs/design/library-from-code.md` and `importer/tools/library/`: node groups written as code, built by a script and checked by fingerprint.
- `importer/tests/harness/`: scene summaries compared with committed snapshots, on a `min` and a `latest` Blender.
- `exporters/kk/src/AutoExport.cs` and `scripts/auto-export.sh`: the request and result files the capture plugin will use.
- `exporters/kk/src/Materials.cs` and the normal unpacking in `exporters/kk/src/Kks.cs`: textures hold the values the shader samples, not sRGB-decoded colours.
- `contract/`: the style of the schemas, closed sets, Manifest and Schema Version rules.
