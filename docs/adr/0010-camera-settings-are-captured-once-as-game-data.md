# The game camera's settings are captured once and kept as Game data

The Extractor reads only the game's files (ADR 0001). But part of a Map Variant's look comes from the game camera, which no Scene Bundle holds. These are AmplifyColor's tonemapper, exposure and dithering, and the strength of the sun shafts ([kk-spike.md](../design/kk-spike.md)). They are the same for every Map of a Game.

So the developer capture plugin (Phase 5) reads them from the running game once per Game, and they are kept in the repository as a few numbers of Game data, beside the other per-Game facts. They are settings, not game content, so ADR 0007 holds. Until they are captured, the Builder assumes no tonemapper, exposure 1 and no sun shafts.

## Considered Options

- **Finding the camera in the game's own data files (rejected)**: it keeps the files-only rule pure. But KK's player data has no type trees, so it would mean generating them from the game's assemblies, and the camera may not be in a file at all.
- **Defaults only (rejected)**: no capture needed, but if the game uses a tonemapper, every Map Variant would be off in the same way.
- **Captured once, kept as Game data (chosen)**.

## Consequences

- A game update that changes the camera means capturing again. The look check (ADR 0006) would show it.
- Users still never run the game; only developers do, as for Reference Captures.
