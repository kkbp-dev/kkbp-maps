# Unity's built-in resources are read from the player's folder

A Scene Bundle can point outside every bundle, into the two files the game's player ships under `<Name>_Data/Resources/`: `unity default resources`, with Unity's built-in meshes (Cube, Sphere, Plane), and `unity_builtin_extra`, with its built-in shaders. The Extractor didn't read them. That was harmless for meshes, whose rule was "a built-in mesh is a Helper unless a Sky Dome uses it", tested as "the mesh isn't loaded". It wasn't for warehouse: its Shadow Caster `o_koi_map80_00_s` is drawn with a copy of Unity's `Default-Diffuse` material, whose shader, `Legacy Shaders/Diffuse`, is object 7 of `unity_builtin_extra`, and the extraction stopped. It is the only such material in KK's 43 Maps.

So the Extractor's Store loads the player's built-in resource files beside the Scene Bundle, named per Game in `extractor/games.py`. An object in them resolves and reads like any other, but is never listed as one of the Map's own, so no walk starts from one. They are files of the install, read like the bundles (ADR 0001), and join each Manifest's sources.

## Considered Options

- **A made-up opaque material for a Shadow Caster whose shader is missing (rejected)**: data the game doesn't hold.
- **Skipping such a renderer with a new skip reason (rejected)**: a contract change, and warehouse would lose the Shadow Caster that keeps the sun out.
- **Reading the player's built-in resources (chosen)**.

## Consequences

- Whether a mesh is built-in is now asked by file (`Store.is_builtin`), not by whether it loaded, so Sky Domes and Helpers are found as before. The 19 built-in Planes KK draws (mirrors, volumetric beams, a mosaic, heat haze) stay Helpers; each uses a shader the Builder leaves out anyway.
- `Legacy Shaders/Diffuse` has a Shader Tier: approximated, as Standard.
- No contract change, but every Map Bundle's sources grow by two files, so each is extracted again once.
