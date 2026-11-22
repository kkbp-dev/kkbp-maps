# Materials keep only the properties their shader declares

A Unity material keeps every value it was ever given, including those of shaders it used before. KK's materials do: a `Standard` material can carry `_EmissionColorUI` or a Shader Forge shader's floats. A material's Content Hash covers its values (ADR 0012), so two materials that draw the same would get different hashes, and different Base Materials, because of values no shader reads.

So the Extractor keeps only the properties the material's shader declares. The Shader object's parsed form lists them, with their types, even in KK's Unity 5.6, whose run time can't. The types also tell colours from vectors, which Unity 5.6 serializes the same way.

## Considered Options

- **Every serialized property (rejected)**: nothing to resolve, but leftovers split identical materials and show the Builder values that mean nothing.
- **The shader's declared properties (chosen)**.

## Consequences

- A material whose shader isn't in the bundle stops the extraction, since there is nothing to filter by. None in KK's Maps does.
- The render queue, blend mode and double-sidedness are read the same way: a queue of −1 becomes the shader's own `Queue` tag, and blending and culling come from the shader's first forward pass, through the material's values where a property sets them. `SetRenderQueue`, which changes a renderer's queues when the Map loads, is applied too, and gives that renderer's materials records of their own.
