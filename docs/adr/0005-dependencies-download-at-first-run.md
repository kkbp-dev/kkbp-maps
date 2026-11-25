# Python dependencies download at first run

*Superseded by ADR 0029: the wheels ship inside the extension, one zip per platform.*

The extension ships as one zip for every platform. UnityPy and its native wheels (texture decoders, LZ4, Brotli, Pillow) are pinned, and the first run downloads them with Blender's own pip for the running Python and platform, as KKBP's Pillow installer does (`importer/kkbp/pillow.py` in KKBP). An offline wheel the user supplies is checked against the platform's tags before it is used.

## Considered Options

- **Per-platform zips with the wheels bundled (`--split-platforms`) (rejected)**: it works offline, but every release is three packages to build and check.
- **Download at first run (chosen)**: one package; the first run needs the network.

## Consequences

- A pinned version is raised only on purpose, and a wheel tag is never written into the code.
- The error a user sees when the download fails has to say what to do, including how to install a wheel by hand.
