# Each Time of Day is its own Map asset

A Map is published as one asset per Map Variant ("Classroom, Evening"), not as one asset with a switch. Dragging a Map Variant in gives the finished look, with no machinery to run afterwards, and a Time of Day changes much more than a light: KK hides and shows objects, KKS changes the sky, SVS swaps the whole Lightmap Set. The geometry is stored once and shared by every Map Variant of a Map.

## Considered Options

- **One asset per Map with a Time of Day dropdown or driver (rejected)**: a tidier asset browser, but it would swap lightmaps and visibility at run time, which is fragile in Blender.
- **The default Time of Day only (rejected)**: it drops the other lighting states the games have.
