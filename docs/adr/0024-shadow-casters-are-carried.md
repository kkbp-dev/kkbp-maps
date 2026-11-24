# Shadow Casters are carried, and renderers keep Unity's shadow mode

`games.md` listed shadow-only casters (`m_CastShadows 3`) among the Helpers to leave out, and the Map Bundle kept only whether a renderer casts shadows. The look check (Phase 5) showed both were wrong. In 1F the sun reached the floor and ceiling of the building in Blender where the Reference Captures show only the lightmaps: the hidden shells `mo_koi_map02_kage*` and `o_koi_map02_kage`, which the game never draws, are what keep the sun out. And Unity's shadow pass culls as the material draws, so a one-sided surface casts shadows from its front only, while Blender let every face cast.

So a shadow-only renderer is carried as a Shadow Caster, and a renderer records Unity's mode: `off`, `on`, `two_sided` or `shadows_only` (Schema Version 0.3). A Shadow Caster outside any Placement starts no Candidate: it belongs to the Map Variant alone, as a sky node does. One inside a Placement is part of that asset, so a Prop carries its own hidden caster, and it marks the Placement's shape. In Blender a Shadow Caster is an object hidden from the camera and every other ray but shadows, and a one-sided material casts shadows from its front faces only.

## Considered Options

- **Shadow Casters in the Map Variant only, never in assets (rejected)**: simpler, but a Prop that carries a hidden caster in the game would cast the wrong shadow once dragged into a scene.
- **Shadow Casters as Structures (rejected)**: an asset nobody can see is no use in an asset browser.
- **Carried, the Map Variant's own outside Placements (chosen)**.

## Consequences

- The Schema Version is 0.3, and every Golden Map is extracted again. Content Hashes of shapes change only where a Shadow Caster lies inside a Placement.
- Blender sets shadow culling per material, not per object: a `two_sided` renderer whose material draws one side casts from its front only.
- Whether a renderer receives shadows is carried but not yet used by the Builder.
