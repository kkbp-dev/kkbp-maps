# The wheels ship inside the extension, one zip per platform

Supersedes ADR 0005. The Extractor needs UnityPy and the packages UnityPy loads when it is imported: its native texture decoders, LZ4, Brotli, Pillow, and its audio packages too, which it imports even though no Map has audio. ADR 0005 had the first run download them with Blender's pip. That made the first run depend on the network, a proxy or a TLS-inspecting firewall, and on PyPI still serving the pinned versions, and it needed an installer, its consent dialog and an offline route of its own.

So the wheels ship inside the extension, listed in `blender_manifest.toml`, and Blender installs them when the extension is installed, into the profile's extension site-packages (never into Blender's own Python). `blender --command extension build --split-platforms` makes one zip per supported platform (Linux x64, Windows x64, macOS arm64), each holding only its own wheels; Blender refuses a zip for another platform.

- **The wheels are made at packaging time, never committed.** `tools/package.py` downloads the pinned wheels for every platform, each checked against the hash lock (`extension/kkbp_maps/deps/requirements.lock`), into the ignored `extension/kkbp_maps/wheels/`. A pinned version is raised only on purpose, and a wheel tag is never written into the code: the lock lists every wheel of a pinned version, and Blender's builder sorts them by platform.
- **`tpk_ar` has no wheel on PyPI**, only its source. It is pure Python, so the packaging tool builds its wheel from the hash-checked source.
- **The audio packages are left out.** `fmod_toolkit`'s wheel carries Firelight's FMOD library, whose licence doesn't let us pass it on, and `pyfmodex` only wraps it. UnityPy's export module imports `fmod_toolkit` but only calls it for AudioClips, which no Map is read for, so `extractor/unity.py` puts an empty module in its place before importing UnityPy. A Map Bundle extracted that way is the same as one extracted with FMOD installed (park, checked byte for byte).
- **numpy is Blender's own.** Every Blender build ships numpy; a numpy wheel in the shared site-packages would replace it for Blender and every other extension. The extension checks that Blender's numpy is recent enough.
- **UnityPy is never imported in Blender's own process.** Only the Extractor's subprocess imports it; Blender's process finds where the wheels went without loading them and passes that folder on.

## Considered Options

- **Download at first run (ADR 0005; superseded)**: one package, but the first run needs the network and an installer of its own.
- **One zip with every platform's wheels (rejected)**: one package, three times the size, and Blender would still install only the matching wheels.
- **A zip per platform with the wheels inside (chosen)**.

## Consequences

- Every release is three zips to build and check (the release checklist, ADR 0006).
- Packaging needs the network once per release, on the developer's machine.
- The wheels are shared with other extensions in the same profile. Where two extensions list the same package Blender installs one copy; KKBP's Pillow is the same version today.
- The manifest asks for no network permission, and the extension can be listed on extensions.blender.org.
