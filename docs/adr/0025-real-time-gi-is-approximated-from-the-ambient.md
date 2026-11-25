# Real-time GI is approximated from the ambient light

Some renderers take Enlighten's real-time GI in the game (`m_LightmapIndexDynamic`): Unity solves the sun's bounce at run time and adds it to the baked lightmap. No file holds that light, so ADR 0001's files-only rule can't carry it. In park all 8 lightmapped renderers take it: the two roads, the lawn and the five street lamps, the Map's largest surfaces. The look check (Phase 5) found the shaded road 3× darker in Blender than in the Reference Capture, while the baked lightmap there is black.

So the Map Bundle records which renderers take real-time GI (Schema Version 0.4), and the Builder adds a share of the Map's ambient light (its Flat colour or SH probe at the surface's normal) on top of their lightmap. The share is Game data beside the light convention, fitted to the Reference Captures.

## Considered Options

- **Reading the real-time lightmaps in the running game (rejected)**: exact, but they are Map content, not a per-Game setting, so every user would need to run the game (ADR 0001, 0010).
- **The ambient instead of the lightmap (rejected)**: the look check found it better in some park views and worse in others.
- **The lightmap plus a share of the ambient (chosen)**: one number per Game, fitted to the captures.

## Consequences

- The share is fitted on park, the only Golden Map with real-time GI; a Map whose bounce differs from its ambient drifts. The look check shows it as more Maps get captures.
- The Build Report keeps counting real-time GI renderers among what isn't carried exactly.
