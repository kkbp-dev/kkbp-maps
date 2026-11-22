# The Grade is applied inside materials, through Variant Materials around shared Base Materials

Each Time of Day has its own colour grade in the games (KK's and KKS's AmplifyColor LUTs, KKS's PostProcessing, SVS's URP Volume). kkbp-maps applies it inside materials, as KKBP's templates do, and not in the compositor: a scene's look then travels with its objects, and needs no compositor setup when a Map Variant is dragged in. The view transform is Standard, not AgX.

A Placement in a Map Variant therefore can't use the same material as its standalone Prop: it needs that Map Variant's Grade and its own part of the Lightmap Set. So each game material becomes one shared Base Material, a node group, and each Map Variant gives its Placements thin Variant Materials that wrap the Base Material and add the lightmap and the Grade. Meshes and Base Materials stay shared, so editing a Prop's look changes every Map it is in. A standalone Prop shows the Day Grade, and another can be picked.

## Considered Options

- **A compositor Grade per Map Variant, set by an operator (rejected)**: materials would stay identical across Map Variants, but the look would depend on scene settings outside the asset.
- **Independent copies per Map Variant (rejected)**: simpler, but disk use multiplies with the Times of Day and edits don't spread.
- **Variant Materials around shared Base Materials (chosen)**.

## Consequences

- Placements are real objects sharing mesh data, not collection instances, because each carries its own Variant Materials.
- A Map Variant's lightmaps are one UDIM image; each Placement picks its tile and scale-offset through object properties the Variant Material reads.
- KKBP Characters carry the maker's day light and Grade in their baked textures, so they look like daytime in an evening or night Map Variant until a KKBP Hook re-grades them from the light and Grade each Map Variant records.
