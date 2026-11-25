# The story camera's height fog is drawn in the materials and the World

KK's story game shows a Map through its `ActionCamera` (`camera/action.unity3d`; free roam's camera is a copy of it), and that camera carries Unity's `GlobalFog` image effect with distance fog off and height fog on: top 1 m, density 2. `ActionMap.UpdateCameraFog` switches it on wherever the Map Variant's own fog is on, so the story game draws both: the Map's linear fog in each surface's shader (ADR 0021), then the height fog over the frame, in the same colour and through the same start and end. Studio's camera has none. The height fog runs as `[ImageEffectOpaque]`, after the opaque queue and before transparent surfaces, and it leaves only far-plane pixels alone, so it fogs a Sky Dome, which is a mesh, but not Unity's skybox.

The look check through the story game's captures found it was most of ground's error: below the horizon the game shows the dome as exactly the fog colour, and Blender showed the sky.

So the height fog is part of the Camera Profile (`HeightFog` in `builder/games.py`, Game data like the rest of it), and the Builder draws it where the game does:

- in the Variant Materials, in the Light group, after the linear fog and before the Grade, on materials up to Unity's opaque queue (2500): Unity's `ComputeHalfSpace` with the camera's position, the surface's and the fog's top;
- in the World, over a Sky Dome only: with the dome at infinity (ADR 0016), every direction below the horizon goes the whole way through the fog, so it is the fog colour.

## Considered Options

- **A Blender volume (rejected)**: Blender's volumes thin out exponentially, Unity's height fog is the linear fog over a distance that grows with depth below the top, and a volume would be graded once rather than per surface (as ADR 0021 found for the linear fog).
- **A compositor pass over the render (rejected)**: matches the game's order exactly, but a Map Library is assets placed in the user's scenes, where a compositor setup doesn't travel.
- **In the materials and the World (chosen)**: the same place and order as ADR 0021's linear fog.

## Consequences

- Only the `game` Camera Profile has height fog, so a library built for Studio is as before.
- It depends on the camera's height: a material computes the camera's position from the surface's position, the view direction and the view distance, so it follows the camera in the user's scene as the game's does.
- A camera below the fog's top would see a little fog above the horizon on the Sky; the World doesn't draw it (none of the Capture Views stands below 1 m).
- Transparent surfaces, and a user's own objects, get no height fog, as in the game for the first.
- The story camera's sun shafts aren't drawn: they start only from far-plane pixels, which a Map with a Sky Dome has none of, and they added nothing (at most 1/255) to any of ground's views (kk-spike.md, "Known discrepancies").
