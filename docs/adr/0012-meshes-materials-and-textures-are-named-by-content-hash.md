# Meshes, materials and textures are named by Content Hash

KKBP numbers its texture files in write order and gives meshes and materials Ids built from their names. The Map Bundle names each mesh, material and texture by a Content Hash instead, and uses that hash as both its id and its file name (`meshes/<hash>.bin`, `textures/<hash>.png`).

The same mesh, material or texture turns up in many Maps of a Game under a different Unity path id each time, since KK's Scene Bundles are self-contained ([kk-spike.md](../design/kk-spike.md), section 2). A Prop is kept once per Map Library by a hash of its meshes, materials and relative transforms (D3), and a Base Material is shared by every Map that uses it. With Content Hashes as ids, that identity is in the bundle itself: the Builder sees that two Maps use the same desk by comparing strings, with nothing to re-derive.

The hashes are part of the contract, so that any Extractor version gives the same ones: SHA-256, cut to its first 32 hex digits (128 bits), over a canonical form that [the contract's rule text](../../extension/kkbp_maps/bundle/README.md) defines for each kind. A texture's hash is taken from its full-size pixels before the optional size limit (D21) scales it, so its identity doesn't depend on that option.

## Considered Options

- **Numbered files and name-based Ids, as KKBP (rejected)**: familiar, but every Builder step that shares data across Maps would need a second identity.
- **Unity path ids (rejected)**: they differ between Scene Bundles for the same content.
- **Content Hashes (chosen)**.

## Consequences

- File names carry no meaning to a person, as in KKBP, but they do carry identity.
- Changing what a hash covers changes every Prop's identity, so it is a major Schema Version change.
- Prop and Structure hashes use exact float32 values, with no rounding. If the Golden Maps show near-duplicates, rounding is added then.
- Each Map Bundle is still self-contained, so a texture used by many Maps is on disk once per bundle. The Builder writes it once.
