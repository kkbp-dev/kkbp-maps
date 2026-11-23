# Fog is applied in the material, before the Grade

ADR 0008 graded the fog only approximately: fog was to be a Blender volume, which lies outside the materials, so its colour would be graded once instead of after lighting. KK's fog is linear (`SunLightInfo` always sets it so), and Unity applies it in each surface's forward shader, before AmplifyColor grades the frame. Since ADR 0020 the Variant Material computes the whole lit colour itself, so it can apply the fog the same way: mix the lit colour towards the fog colour by `(end − distance) / (end − start)`, the distance being the camera's, and grade the result.

## Considered Options

- **A volume with its colour graded once (rejected)**: works for any object a user adds, but Blender's volumes thin out exponentially, not linearly, and the grade would be a guess.
- **Linear fog in the material, before the Grade (chosen)**: what the game does, in the game's order.

## Consequences

- Supersedes ADR 0008's consequence that the fog is graded only approximately.
- Only the Map Variant's own materials are fogged. An object a user adds isn't, and neither is the Sky, as in the game, whose skybox shaders draw no fog.
- An additive material fades towards black instead of the fog colour, as Unity's additive shaders do.
