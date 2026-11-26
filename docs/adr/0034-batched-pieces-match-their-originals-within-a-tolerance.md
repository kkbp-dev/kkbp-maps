# Statically batched pieces match their originals within a tolerance

ADR 0012 identifies a mesh by the hash of its file, and D3 a Prop by exact hashes of its meshes, materials and transforms: no rounding, until "the Golden Maps show near-duplicates". KKS's static batching makes them. Unity merged 79 renderers in 10 Maps into one world-space `Combined Mesh (root: scene)` per Map, and the original meshes aren't in those Maps. The Extractor splits a renderer's submesh range out and moves it back into the renderer's space, but in float32 the result isn't the original: aquariuminside's 12 copies of `p_ks_r01_partion00_00` come out as 10 different meshes, up to 1.2e-5 m apart ([kks-spike.md](../design/kks-spike.md), section 7). Unbatched copies of the same pieces are drawn in other Maps (hotellobby, hoteloutside, hukuya), where each batched piece matches one with identical UV0, identical indices, and positions within 6e-6 m.

So a split mesh is marked `batched` in `meshes.json` (Schema Version 0.12), and two meshes **match** when they have the same vertex count, attributes, UV0 and indices exactly, and every position and normal within 1e-4 (metres for positions) of the other's, one of them being batched. Within a Map the Extractor gives every batched copy that matches an earlier mesh (batched or not) that mesh, so each piece has one mesh and its Placements one Candidate. Across Maps the Builder does the same before it keeps a Prop once (D3): a Candidate whose shape differs from another's only by meshes that match is the same Candidate, kept with the unbatched mesh where there is one.

## Considered Options

- **Exact hashes (rejected)**: no tolerance anywhere, but each batched copy becomes a Prop of its own, and the Map Library holds near-identical pens and partitions side by side.
- **Rounding the split positions (rejected)**: rounding to 1e-4 still left aquariuminside's 10 shapes apart, since copies straddle the rounding boundaries.
- **A Game-wide pool of unbatched meshes in the Extractor (rejected)**: the Extractor would read other Maps to write one, and a Map Bundle would no longer depend on its own sources only.
- **Batched meshes match within a tolerance (chosen)**: exact on what batching copies unchanged (UV0, indices), tolerant only on what it transformed.

## Consequences

- Only meshes marked `batched` are matched with a tolerance; every other mesh keeps ADR 0012's exact identity, and KK has no batched meshes.
- A Candidate's `hash` is still its exact shape; the Builder merges matching Candidates, so a Prop's identity in the Map Library can rest on a match.
- The matched position is the first mesh's, so a Placement may draw up to 1e-4 m from where the game drew it.
