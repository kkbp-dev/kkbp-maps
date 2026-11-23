# A Map Library is one file per Map, plus one for the Props and one for the Structures, with data copied between them

ADR 0002 shares meshes and Base Materials so that editing a Prop's look changes every Map it is in. That holds inside one `.blend` file. A Map Library for all of KK in one file would be large, rebuilt whole when one Map changes, and lost whole if a build fails halfway. So a Map Library is a folder:

```
KK Maps/blender_assets.cats.txt
KK Maps/Maps/<Map>.blend       one Map's Map Variants and Worlds, with everything they use
KK Maps/Props.blend            every Prop once
KK Maps/Structures.blend       every Structure once
KK Maps/textures/              every image once, linked by relative path, never packed
```

Each file holds its own copy of the meshes and Base Materials it uses. Nothing is linked from one file to another: an asset dragged out of the library appends local data, with no library file behind it.

## Considered Options

- **One file per Game (rejected)**: sharing holds everywhere, but the file is rebuilt and saved whole, and a build can't resume a Map at a time.
- **Shared data in one file, linked from the Map files (rejected)**: one copy of each mesh, but appending a Map Variant would leave the user's file linked to the library's, with data they can't edit.
- **One file per Map, data copied (chosen)**.

## Consequences

- Amends ADR 0002: meshes and Base Materials are shared within each file, between a Map's Map Variants and between the Props of `Props.blend`, not across files. Editing a Prop in `Props.blend` doesn't change the Map Variants.
- Meshes are on disk once per file that uses them; images, much the larger part, only once per Map Library.
- A build resumes a Map at a time: a Map's file is kept while its Map Bundle and the Builder are unchanged. `Props.blend` and `Structures.blend` are rebuilt from every Map Bundle at the end.
- Each Game's folder is registered as an asset library of its own, since Blender reads the catalog file at a library's root.
