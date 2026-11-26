# Bundles are read a block at a time, and shared bundles are found by their CAB names

UnityPy reads a UnityFS bundle by decompressing every block into one buffer, then parsing the files inside it. For KK's self-contained Scene Bundles that cost little. KKS's Scene Bundles point into shared bundles: every story Map but one into `map/materials/00` (815 MB, 1.7 GB decompressed), the Studio Maps into `studio/map/materials/00` (1.7 GB stored as is). Loaded UnityPy's way, a story Map peaked at 3.6 GB, over the Extractor's limit and more than a user's machine can be asked for, to read the few hundred objects it uses ([kks-spike.md](../design/kks-spike.md), section 6).

So the Extractor reads bundles itself: `extractor/bundles.py` parses a bundle's header and directory, and hands UnityPy each file inside it as a seekable stream that decompresses a block only when a read reaches it, keeping the last 64. UnityPy parses those streams with its own code (`ImportHelper.parse_file`), so every object reads exactly as before. On hoteloutside with its shared bundles, the 511 objects the Map uses read back the same bytes, and the peak fell from 3.6 GB to 172 MB.

Which shared bundles a Map needs comes from its own files: each external reference names a serialized file by its CAB name, and the header of each bundle in the Game's dependency folders (`dependency_folders` in `extractor/games.py`) names the CABs inside it. Unity's own manifest, `abdata/abdata`, isn't used: it lists bundles the scenes don't point into, and none of Studio's.

## Considered Options

- **UnityPy's loader with a higher memory limit (rejected)**: no code of our own, but 3.6 GB for a story Map and more for a Studio one.
- **Splitting the shared bundle once per Build into small files (rejected)**: a step and a cache of 1.7 GB per Game, and rewriting game files the Extractor would then read instead of the install's.
- **Reading blocks on demand (chosen)**.

## Consequences

- `bundles.py` uses only the standard library and lz4, which UnityPy already depends on; no new wheel (ADR 0029). LZMA bundles, which none of the Games uses, stop the extraction.
- The shared bundles a Map depends on join its Manifest's sources. Their hashes are kept in the Bundle Folder (`source-hashes.json`, by path, size and modification time), so a 1.7 GB file isn't hashed again for every Map.
- KK's Golden Maps extract to the same bundles, with less memory (1F 0.62 GB instead of 0.95).
