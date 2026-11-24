# Indirect light is computed in Variant Materials, and the World draws only the sky

KK lights a surface in three parts (kk-spike, sections 3 to 6): the realtime sun, an indirect diffuse term that is either the surface's lightmap or the Map's ambient (a flat colour or an L2 spherical-harmonics probe), and an indirect specular term from a reflection probe or the Map's reflection cubemap. A lightmapped surface takes no ambient at all. EEVEE can't say this through its World: the World is one radiance that lights every surface both diffusely and specularly, so it can't hold a flat ambient and a different reflection cubemap at once, and it can't spare the lightmapped surfaces.

So each Variant Material computes the indirect terms itself, as Unity's Standard shader does. The direct light is the Base Material's BSDF lit by the Lighting Rig's sun, taken through Shader to RGB, which ADR 0008 needs for the Grade anyway. To it the material adds the albedo times the lightmap (with its directional term) or the ambient, times occlusion, and the reflection cubemap sampled along the reflected view, box-projected where the probe says so. In EEVEE the World shows the Sky to camera rays and is black to every other ray, so it adds no light of its own; in Cycles it is the Sky for every ray, and Cycles finds its own indirect light (D4).

## Considered Options

- **The ambient as the World's light, the lightmap added as emission (rejected)**: no lighting maths in the materials, but every lightmapped surface would get the ambient twice and the reflection would be the ambient's.
- **The reflection cubemap as the World's light (rejected)**: right reflections, but the diffuse light would be the cubemap's, not the Map's ambient, and lightmapped surfaces would still get it.
- **Indirect light in the material (chosen)**.

## Consequences

- A Map Variant keeps its light wherever it is dragged: the sun is in its collection and the ambient, lightmaps and reflections are in its materials. A World a user adds lights it further, as any other light does.
- The reflection is sampled at the mip Unity picks for the surface's roughness, from a chain of halved maps the Builder writes beside the Map Library's textures (settled by the look check, kk-spike.md).
- Each Variant Material reads its object's lightmap tile, scale-offset and UV set from object properties, so one material serves every Placement of a Base Material in a Map Variant, lightmapped or not.
