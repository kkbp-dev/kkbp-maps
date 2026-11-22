# Maps are read from the game's files, not captured in the running game

KKBP captures Characters inside the running game with BepInEx plugins. kkbp-maps doesn't: the Extractor reads the Scene Bundles and the bundles they depend on straight from the install folder with UnityPy, and the game never starts. The games are Windows-only, and the tool must run on Windows, macOS arm64 and Linux x64; reading files is the only route that works the same on all three without Wine or CrossOver. It is also possible: all three Games' map bundles are standard, unencrypted UnityFS, and they carry their type trees, SVS's IL2CPP build included, so UnityPy reads every component, MonoBehaviours too.

## Considered Options

- **A BepInEx capture plugin per Game, as KKBP has (rejected)**: it sees the map as the game shows it, but Mac users would need CrossOver and the HF Patch, and each Game would need its own adapter.
- **Both routes writing the same Map Bundle (rejected)**: twice the work to build and keep matching.
- **Files only (chosen)**.

## Consequences

- The Extractor works out what the game would do at runtime: which objects each Time of Day shows (`SunLightInfo.visibleList` in KK and KKS), which lightmaps each renderer uses (in KK, the renderer's own fields, replaced by its `LightmapPrefab` entry where it has one; SVS's external `LightmapSettings` matched by object name) and which bundles a scene depends on.
- The game still runs on developers' machines, but only for Reference Captures (ADR 0006) and the camera settings no file holds (ADR 0010), never for users.
