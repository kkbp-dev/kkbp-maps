# A skybox reflection that was never baked reflects the ambient light

ADR 0036 assumed that a KKS Map reflects "the skybox reflection baked when the Map was built". The Golden Maps hold none: hoteloutside's and aquariuminside's `RenderSettings` reflect the skybox (`m_DefaultReflectionMode` 0) with `m_GeneratedSkyboxReflection` empty, and SkyStudio's `updateGlobalIllumination` is off, so nothing renders one at run time ([kks-spike.md](../design/kks-spike.md), section 4). The Builder drew such a Map with no reflection at all, and its metallic and smooth surfaces came out dark.

What the game draws instead isn't in any file, so the look check chose it from the Reference Captures. On hoteloutside's 20 views, mean ΔE before the Grade:

| Reflection | hoteloutside |
|---|---|
| Nothing | 10.5 |
| The SkyStudio sky, unblurred | 8.9 |
| Unity's grey (sRGB 0.5) | 8.3 |
| The Map's ambient light along the reflected direction | 7.2 |

The sky made white surfaces saturated blue; grey gave the right hues but 15 to 25% too dark. The ambient light matches both: the captured white table (0.60, 0.70, 0.78) is hoteloutside's trilight sky colour (0.55, 0.64, 0.75) almost exactly. aquariuminside, whose skybox is a cubemap with an empty slot, goes from 9.4 to 8.4 with the same rule.

So where a Map Variant reflects its skybox and holds no cubemap of it, the Variant Materials reflect the Map Variant's ambient light, evaluated along the reflected direction with the probe that lights the diffuse term (`_ambient`), times the reflection intensity. A custom reflection left empty still reflects nothing.

## Considered Options

- **Nothing (rejected)**: what the Builder did; the worst of the four.
- **The sky (rejected)**: the most plausible on paper, and wrong in the captures.
- **Unity's grey (rejected)**: right hues, too dark.
- **Bake the sky into a cubemap in the Extractor (set aside)**: would reproduce the sky's reflection with Unity's roughness blur, but the sky lost to the ambient light, blurred or not, on the white surfaces that decide it.
- **The ambient light (chosen)**.

## Consequences

- Amends ADR 0036's consequence: a room with a realtime probe reflects the ambient light, not a baked sky.
- No KK Golden Map is affected: park's skybox reflection is baked, and 1F's and ground's are custom.
- The reflection is the ambient probe, which is already blurred, so it is the same at every roughness; a smooth surface shows no sky in it.
- It rests on the captures, not on Unity's code. A Map whose look check disagrees reopens it.
