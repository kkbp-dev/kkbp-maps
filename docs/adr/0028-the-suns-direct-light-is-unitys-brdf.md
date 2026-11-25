# The sun's direct light is Unity's BRDF, not the Principled BSDF's

The Variant Materials took their direct light from the Principled BSDF through Shader to RGB (ADR 0008, 0020). The look check measured that on ground's sunlit pathway: the game's sun adds 0.47 to the floor (with its shadows switched off), Blender's 0.62. Unity's Standard shader lights with `BRDF1_Unity_PBS` (Disney diffuse, and GGX with Smith's joint visibility, Fresnel by l·h and specColor = lerp(0.04, albedo, metallic)); computed by hand for those pixels it gives 0.469. The Principled BSDF's metallic lobe gives a rough, 28 % metallic floor, seen at a grazing angle towards a low sun, about twice Unity's specular.

So in EEVEE a Variant Material's direct light is the irradiance EEVEE gives a white Diffuse BSDF at the surface's normal (its lights and shadows, N·L included), times Unity's BRDF over N·L for the Map Variant's sun direction, plus the emission. Cycles keeps the Principled BSDF (D4).

## Considered Options

- **The Principled BSDF with single-scatter GGX (rejected)**: one setting, but it removed under a third of the excess.
- **Unity's BRDF in the light group (chosen)**: it reproduces the game where the game's own numbers are known.

## Consequences

- The BRDF's view-dependent terms use the Map Variant's sun direction, stored in its light group. Turning the sun in Blender moves its shadows and its N·L, but not its specular or Disney terms; a light a user adds is shaded as if it came from the sun's direction.
- A Prop's or Structure's own material, lit by whatever scene it is in, keeps the Principled BSDF.
- In the look check 1F and ground improve (ground's pathway views by about 0.4 to 0.5 mean ΔE before the Grade, and evening eye-0 passes); park's sunlit road, already too bright, gets 4 to 8 % brighter. What remains on sunlit ground is the sun's own shadows: in the game, with shadow bias and normal bias 0, they take about a quarter of the sun's light from ground's floor where nothing shades it (kk-spike.md).
- The `direct` look switch builds the Principled BSDF's direct light instead, to measure the difference.
