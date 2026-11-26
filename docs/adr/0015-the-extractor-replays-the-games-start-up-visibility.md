# The Extractor replays what the game shows when a Map loads

A Scene Bundle's serialized active flags aren't what the player sees. KK's game code turns objects on and off as a Map loads: every `VisibleChange` component's `Start` shows its show list and hides its hide list, and `SunLightInfo.Set` shows the chosen Time of Day's `visibleList` and hides the other infos' lists. In ground, the evening Sky Dome is serialized inactive while the day and night domes are both active, so the files alone would show two skies and no evening.

So the Extractor replays those steps, in the game's order, once per Time of Day: the serialized flags, then each `VisibleChange.Start` whose object is active, then `SunLightInfo.Set` going through the infos in their order, as the decompiled code does. An object active at no Time of Day is a Helper and is left out with everything under it. One active at some is kept, and the Map Variants of the others list it in `hidden`.

## Considered Options

- **The serialized flags only (rejected)**: no game code to follow, but the sky and every toggled object come out wrong.
- **Treating every listed object as shown in its own Time of Day (rejected)**: simpler, but `Set` is order-dependent. An object in two infos' lists ends up hidden whenever the earlier of them isn't chosen, and the bundle has to show that too.
- **Replaying the steps (chosen)**.

## Consequences

- The replayed scripts are named by their class names in `scene.py`, as the only marker the game gives (CLAUDE.md, "Find things by meaning").
- `MapVisibleList` isn't replayed: the game calls it from gameplay, not when a Map loads, so its lists stay as serialized.
- A Map whose `SunLightInfo` lacks one of the Game's Times of Day stops the extraction, since `Set` would then leave the scene as the previous Time of Day left it. No KK Map does. *Amended by ADR 0032: a missing Time of Day shows the first info, as KKS's story game does, and which scripts are replayed is Game data.*
