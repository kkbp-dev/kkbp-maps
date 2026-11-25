# A renderer can refuse reflection probes

A renderer's reflection in Unity comes from a reflection probe whose box holds it, unless its `m_ReflectionProbeUsage` is Off: it then takes the scene's default reflection, the skybox's or a custom cubemap. The Builder used to give every renderer inside a probe's box that probe. On ground, the school building's renderer is Off, and ground's default reflection is a custom cubemap with an empty slot, so its window glass reflects nothing in the game. In Blender the glass reflected the probe's sky and yellow sand: 64 % too bright in the worst tile of the look check, and yellow where the game shows grey.

So the Map Bundle records each renderer's reflection probe usage as Unity's mode (Schema Version 0.5): `off`, `blend_probes`, `blend_probes_and_skybox` or `simple`, as `shadows` records Unity's shadow casting mode. The Builder gives an `off` renderer its Map Variant's own reflection and every other renderer the probe as before.

## Considered Options

- **A boolean (rejected)**: enough for KK, which uses only Off and Blend Probes, but KKS and SVS may blend with the skybox, which a boolean can't say.
- **Unity's mode (chosen)**: the Builder treats the three blending modes alike for now; blending at a probe's edge is left out.

## Consequences

- ground has three renderers that are Off (the school building, the sports ground's surface and its goal; a fourth, the gym's, has no mesh) and 1F one; park has no probe. With them on the Map's reflection, 8 of ground's 15 Capture Views pass the look check instead of 5.
- The usage isn't part of any Content Hash: it changes a renderer's light, not its shape, as `realtime_gi` doesn't.
