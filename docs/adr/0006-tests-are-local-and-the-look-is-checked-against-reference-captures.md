# Tests run locally, and the look is checked against Reference Captures

There is no CI: game files can't go into the repository or onto a CI runner, so the tests that matter need each developer's own install, as in KKBP (ADR 0031 there). Host tests use synthetic data built in code; the Golden Maps are made locally; the Builder's scene summaries are committed snapshots. Windows and macOS arm64 are checked by hand with a release checklist before each release.

"Close to the in-game lighting" is measured, not judged by eye. A developer-only BepInEx plugin, never shipped, uses KKBP's file-triggered request pattern (ADR 0012 there) to set a fixed camera per Map Variant in the running game and write the frame to a file: a Reference Capture. Blender renders the same camera from the built Map Variant, and a test compares the two images within a tolerance and writes a side-by-side report.

## Considered Options

- **A CI matrix on synthetic fixtures (rejected)**: it catches platform regressions sooner, but most of what can go wrong needs real game data.
- **Side-by-side screenshots judged by eye (rejected)**: no fixed measure to tune or test against.
- **Comparing extracted values only (rejected)**: the values can be right while the Blender rebuild still looks wrong.

## Consequences

- Reference Captures are game content and stay local, like the Golden Maps (ADR 0007).
- The capture plugin is the only code that runs inside a game, and only on developers' machines (ADR 0001).
