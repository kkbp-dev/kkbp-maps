# The Grade is applied to the lit result in EEVEE, with an ungraded output for Cycles

ADR 0002 puts the Grade inside Variant Materials. The KK spike ([kk-spike.md](../design/kk-spike.md)) showed what that Grade is. AmplifyColor grades the finished frame, sky and fog included, after an optional tonemapper. It encodes the frame to sRGB, looks it up in a 32³ LUT and decodes it again. The LUT is far from linear, and even the day one isn't neutral: mid grey 0.5 becomes (0.42, 0.34, 0.39). Grading the albedo or the light colours instead would give another look.

So each Variant Material has two Material Outputs. The EEVEE output takes the Base Material's BSDF through Shader to RGB, encodes it to sRGB, applies the Map Variant's LUT, decodes it and emits the result. The Cycles output is the Base Material's BSDF, ungraded. The World and the Sky Dome's cloud and star materials are graded the same way. Fog is a volume in Blender, so it can't be graded after lighting; its colour is graded once instead.

## Considered Options

- **Shader to RGB with no Cycles output (rejected)**: simpler, but Cycles doesn't support Shader to RGB, which breaks D4's promise that Cycles renders sensibly.
- **Grading albedo, light and sky colours (rejected)**: works in both renderers, but it doesn't match the game.
- **Two outputs (chosen)**.

## Consequences

- In EEVEE a Placement is emissive after grading, so it gets no further lighting from what a user adds to the scene, such as a Character's lights. That is the price of matching the game's frame.
- Cycles renders the Map Variant ungraded. It is sensible but not matched (D4).
- The fog is graded only approximately, so a foggy distance can drift from the Reference Capture. The look check (Phase 5) says how much. *Superseded by ADR 0021: the fog is applied in the material, before the Grade.*
- The tonemapper and exposure that run before the LUT come from the game camera, not the Map (ADR 0010).
