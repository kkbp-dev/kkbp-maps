# Realtime reflection probes are left out and counted

ADR 0023 left out a reflection probe in baked mode that was never baked, since Unity draws nothing from it, and kept stopping on a realtime probe or a custom one without its cubemap. KK has neither. KKS has 15 realtime probes in 11 Maps (hoteloutside, aquariuminside, harbor, forest, bathroom and others): 13 rendered once when the Map loads and 2 every frame. No file holds what they capture; the game renders it. fittingroom has a custom probe whose slot is empty.

So a realtime probe is left out of the Map Variants and counted in `map.json`'s `skipped` as `realtime_probe` (Schema Version 0.13), and the renderers in its box take their Map Variant's own reflection, as a renderer outside every probe does. A custom probe without its cubemap is left out like an unbaked one: Unity draws nothing from either.

## Considered Options

- **Keep stopping (rejected)**: 11 KKS Maps, two of the three Golden Maps among them, couldn't be extracted.
- **The Builder renders each probe from the built Map Variant (set aside)**: closer to the game, which renders the probe from the loaded Map, but a Build step of its own per probe and Time of Day. The look check says whether it is worth it.
- **Left out and counted (chosen)**.

## Consequences

- Amends ADR 0023's "a realtime probe, or a custom one without its cubemap, still stops it".
- In KKS the Map's own reflection is the skybox reflection baked when the Map was built, so a room with a realtime probe reflects the sky instead of itself. The look check measures it, and the Build Report counts the probes.
