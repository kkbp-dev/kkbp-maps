# kkbp-maps

Turn the maps of your own KK, KKS or SVS install into Blender asset libraries:

- every prop (desks, chairs, trees) and every shell piece (walls, floors, terrain) as a tagged asset, kept once however many maps use it;
- every map at every time of day as a finished asset, lit with the game's own lightmaps, lights, sky and colour grade, for EEVEE.

It runs in Blender on Windows, macOS (Apple Silicon) and Linux. It reads the game's files directly, so the game never has to start, and it ships no game content: your library is built from your own install. It is a sister project of [KKBP](https://github.com/kkbp-dev/kkbp), and its maps are made to fit KKBP Characters.

**Status:** v0.1 builds KK's Maps, and is tested on Linux only so far: the Windows and macOS zips are built the same way but haven't been tried yet. KKS and SVS come next (see the [roadmap](docs/design/roadmap.md)). Install the zip for your platform in Blender 5.2 or later, then use the KKBP Maps tab in the 3D Viewport's sidebar: pick your game folder and an output folder, choose Maps and build. The output folder gets the Map Library (`KK Maps`) and the Map Bundles it was built from, about 2 GB for every KK Map.

- [Design](docs/design/README.md)
- [Glossary](CONTEXT.md)
- [Decisions](docs/adr/)

Licensed under the MIT License; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
