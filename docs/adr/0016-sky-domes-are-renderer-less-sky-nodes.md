# Sky Domes are kept as sky nodes without a renderer

KK's Sky Domes are Unity's built-in Sphere, scaled to hundreds of metres, drawn with a `Skybox/Cubemap` material (kk-spike, section 5). D7 turns the dome's cubemap into the Map Variant's World background and keeps its clouds and stars as geometry. The sphere itself is neither: its mesh lives in Unity's own resources, not in the Scene Bundle, and drawing it would hide the World.

So a renderer that draws a built-in mesh with a skybox shader is a Sky Dome. Its node stays in `scene.json` as a sky node with no renderer, so its clouds and stars keep their parent and transforms. Its material becomes the Map Variant's Sky (the cubemap as an equirectangular EXR, with tint, exposure and rotation), and its node is the Sky's `geometry`. Every other built-in mesh is a Helper (the `Cube (N)` colliders). No built-in mesh ever enters `meshes.json`, so the Extractor never reads Unity's default resources.

## Considered Options

- **Reading the built-in Sphere from `unity default resources` and keeping the dome as a mesh (rejected)**: complete, but the Builder would have to hide it again, and the resources file belongs to the game's player, not the Map.
- **Dropping the dome node and re-parenting its clouds (rejected)**: fewer nodes, but the clouds' transforms would have to absorb the dome's scale of about 500.
- **A renderer-less sky node (chosen)**.

## Consequences

- The sky's rotation combines the dome's world rotation with the material's `_Rotation`. A dome that tilts stops the extraction; none in KK does.
- A dome's radius (448 to 613 m) isn't carried: the World background is at infinity. The look check measured what this costs where a dome is centred far from the camera, and it was kept (kk-spike.md, "Known discrepancies").
