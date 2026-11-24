# kkbp-maps

Reads the maps of a user's own game install and builds Blender asset libraries from them: the distinct props and shell pieces as assets, and every map at every time of day as a finished, lit asset.

## Language

### Games and maps

**Game**:
One supported Illusion title, identified by a fixed id: `KK`, `KKS` or `SVS`; the same ids as KKBP.
_Avoid_: title, game name, prefix

**Map**:
One location a Game lets the player or Studio use, such as a classroom or a beach, built from one Scene Bundle and the bundles it depends on.
_Avoid_: stage, level, scene, background

**Scene Bundle**:
The game's own AssetBundle that holds one Map as a streamed Unity scene.
_Avoid_: map file, unity3d

**Time of Day**:
One of the lighting states a Game gives a Map, such as day, evening or night; each Game has its own fixed set.
_Avoid_: time slot, period, lighting preset

**Map Variant**:
A Map at one Time of Day, or at several Times of Day that light it the same. The unit a Map asset is made of.
_Avoid_: map version, map preset

**Sky Dome**:
The sky a Game shows around a Map at one Time of Day, as geometry: KK's cubemap-textured sphere with its clouds or stars.
_Avoid_: skybox, sky sphere, background

**Helper**:
An object in a Scene Bundle that the player never sees and that doesn't change what they see, such as a collision box or a navigation mesh. The Extractor leaves it out. A Shadow Caster isn't one.
_Avoid_: dummy, hidden object, collider

**Room Container**:
An object in a Scene Bundle that holds a whole room or shell under a name that looks like a Prop's or a Structure's. It is neither: the pieces under it are.
_Avoid_: map root, wrapper, group

**Studio Map**:
A Map listed in a Game's Studio rather than its story or free mode. It is a Map of its own only when its geometry differs from the story Map's.
_Avoid_: studio scene, studio stage

### The Map Bundle

**Map Bundle**:
The folder the Extractor writes for one Map, and the only thing the Builder reads.
_Avoid_: export, cache, intermediate

**Manifest**:
The file that identifies a Map Bundle: its Game, Map, Schema Version, Extractor version and contents. A Map Bundle without one is unfinished.
_Avoid_: header, config

**Schema Version**:
The `major.minor` version of the Map Bundle contract; the only version that decides whether a Builder accepts a bundle.
_Avoid_: format version

**Raw Property**:
The game shader's own name for a material property or texture slot.
_Avoid_: shader prop name

**Texture Role**:
The meaning of a texture slot on a material, such as main, normal or occlusion, drawn from a small closed set. A texture outside that set is known only by its Raw Property.
_Avoid_: texture type, suffix

**Content Hash**:
The hash a Map Bundle gives a mesh, material, texture, Prop or Structure from its content alone, so the same thing has the same hash in every Map.
_Avoid_: path id, checksum, fingerprint

**Candidate**:
A part of a Map that the Extractor proposes as a Prop or a Structure, with its Content Hash and the rule that picked it. The Builder makes the final call.
_Avoid_: asset, prefab

**Shadow Caster**:
A renderer the game never draws but that casts shadows, such as the hidden shell that keeps the sun out of a room. Outside any Placement it belongs to the Map Variant alone.
_Avoid_: kage, shadow proxy

**Camera Profile**:
The settings of one game camera that no map file holds, such as its tonemapper, exposure and sun shaft strength, kept in the repository as Game data. A Map names the one that shows it.
_Avoid_: camera preset, post settings

### What a Map Library holds

**Map Library**:
The asset library built for one Game, holding its Props, Structures and Map Variants.
_Avoid_: asset pack, library folder

**Prop**:
A movable object a Map is furnished with, such as a desk, a chair or a tree, kept once per Map Library however many Maps it appears in.
_Avoid_: object, item, model, furniture

**Structure**:
A piece of a Map's shell, such as a wall, a floor or terrain, published as an asset of its own beside the Props.
_Avoid_: shell, environment mesh, building

**Placement**:
One occurrence of a Prop or Structure in a Map, with its position.
_Avoid_: instance, copy, spawn

**Base Material**:
One game material rebuilt once in Blender, and shared by every Placement and asset that uses it.
_Avoid_: master material, source material

**Variant Material**:
The material a Map Variant puts on a Placement: its Base Material with that Map Variant's Lightmap Set and Grade.
_Avoid_: lit material, instance material

**Lightmap Set**:
The light a Game baked for one Map Variant: its lightmaps and which part of them each Placement uses.
_Avoid_: lightmaps, bake

**Lighting Rig**:
The Blender lights and World that a Map Variant recreates from the Game's lights, sky, ambient light and fog.
_Avoid_: light setup, light preset

**Grade**:
The colour grade a Game applies at one Time of Day, applied inside materials.
_Avoid_: LUT, colour correction, post

**Name Tables**:
The curated English names, word translations and category rules that give assets their names, catalogs and tags.
_Avoid_: translations, dictionary

### The tool

**Extractor**:
The stage that reads a Game install and writes Map Bundles. It never needs Blender or a running game.
_Avoid_: ripper, exporter, reader

**Builder**:
The stage that turns Map Bundles into a Map Library in Blender.
_Avoid_: importer, generator

**Shader Tier**:
How the Builder rebuilds a game shader: exactly, approximated, or not at all, in which case its renderers are left out. The Build Report lists the last two.
_Avoid_: shader support level, fallback

**Build Report**:
What a build tells its user afterwards: what was built and skipped, and which names the Name Tables didn't know.
_Avoid_: log

### Testing

**Golden Map**:
The Map Bundle of one fixed Map, made on each developer's own machine from their own install and never committed, that the tests check and build.
_Avoid_: sample map, test map, fixture

**Reference Capture**:
A frame the running game renders of a Map Variant from a Capture View, made only by developers, that a Blender render of the same Map Variant is compared with.
_Avoid_: screenshot, ground truth

**Capture View**:
A fixed camera for one Map Variant, its position, target and field of view in Blender's space, kept in the repository as data, from which a Reference Capture is taken and the Blender render made.
_Avoid_: camera preset, shot
