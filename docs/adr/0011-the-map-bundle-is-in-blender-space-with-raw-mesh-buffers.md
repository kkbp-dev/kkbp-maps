# The Map Bundle is in Blender's space, with meshes as raw buffers

KKBP's Export Bundle is in glTF's space: its exporters negate X, and Blender's glTF importer then turns Y-up into Z-up and flips V back. Its meshes are `.glb` files. The Map Bundle does neither. Every position, rotation, scale, direction, light, spherical-harmonics probe, cubemap and directional lightmap in it is already in Blender's space (right-handed, +Z up, metres), converted from Unity by the one matrix `C` of [kk-spike.md](../design/kk-spike.md) (section 1) in one module of the Extractor. Each mesh is a raw little-endian file of float32 vertex attributes and uint32 triangle indices, with its winding already swapped.

A map isn't a Character. It has hundreds of meshes shared across objects and Maps, lighting values that are directions (the sun, the probe's SH, the `_comp_dir` lightmaps, the sky's rotation), and Builder code that sets mesh data through `foreach_set` anyway, to keep a mesh shared by every Placement. With glTF, the conversion would be split between the Extractor and Blender's importer, and every direction that isn't geometry would need converting separately to match. With one space, the Builder converts nothing, and a value in a bundle means the same in Blender.

## Considered Options

- **glTF space and `.glb` meshes, as KKBP (rejected)**: one format across the sister projects, but two places convert, the glTF importer decides how objects and meshes are made, and the lighting data would still need its own conversion.
- **Unity's space, converted by the Builder (rejected)**: the Extractor stays a plain reader, but every Builder step would have to know the conversion.
- **Blender's space, raw buffers (chosen)**.

## Consequences

- The result matches KKBP Characters (D6): `C` is KKBP's X mirror followed by glTF's Y-up to Z-up.
- Tangents aren't in the bundle. Blender can't take custom tangents and computes its own (MikkTSpace) from the mirrored geometry and the unchanged UVs, so normal maps need no change beyond unpacking.
- The bundle uses Blender's quaternion order `[w, x, y, z]`, not KKBP's `[x, y, z, w]`.
- Directional lightmaps are re-encoded in Blender's world axes. `C` only permutes and negates axes, so this is exact on 8-bit values.
