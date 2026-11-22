# Shell pieces are published as Structure assets beside the Props

The built scenes keep no prefab information, so what a Prop is has to be read from the scene itself. A Prop is a `p_` GameObject with everything under it, kept once per Map Library by a hash of its meshes, materials and their relative transforms. The games' naming makes this reliable: props are `p_…`, shell geometry is `mo_…` or `o_…`, groups are `n_…`, and repeated objects share one Mesh. Shell geometry (walls, floors, terrain) isn't left out: it is published as Structure assets in their own catalogs, so a user can build a new set from a Map's pieces. Curated overrides in the Name Tables cover objects the prefixes get wrong.

## Considered Options

- **Every unique mesh is an asset (rejected)**: complete, but a multi-part prop splits apart and the library fills with fragments.
- **Shell geometry only inside Map Variants (rejected)**: a cleaner prop library, but the shell pieces could not be reused.
