# Every readable renderer is carried, whatever its shader

KK's Maps draw some meshes with shaders that Blender can't match at first: mirrors (`FX/MirrorReflection_Transparent`), heat haze (`Xffect/heat_distortion`), volume light and spot beams (`Shader Forge/volumeLight`, `spotLight_beam`), particle materials on plain meshes. D13 says particles and volumetric beams are skipped at first. Whether to skip them is the Builder's call, though: it knows which shaders it can rebuild.

So the Extractor carries every enabled MeshRenderer whose mesh it can read, with its material by Raw Property, whatever its shader. `map.json`'s `skipped` lists only what the bundle doesn't hold: particle systems, skinned meshes, renderers lit by realtime GI (their light is solved at run time), animated objects (kept at their serialized pose), and unreadable meshes.

## Considered Options

- **Skipping by a shader list in the Extractor (rejected)**: smaller bundles, but every change to the Builder's shader tiers would mean extracting again.
- **Carrying everything readable (chosen)**.

## Consequences

- The Builder's Build Report says which renderers it left out and why; the Extractor's `skipped` counts don't include them.
- The `volumetric` skip reason isn't used by KK.
- A renderer type the Extractor doesn't know (a line or trail renderer, say) stops the extraction instead of being dropped silently.
