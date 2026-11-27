# A missing Time of Day shows the Map's first info, and load-time scripts are Game data

Amends ADR 0015. The Extractor replays what the game does when a Map loads, once per Time of Day, and it stopped on a Map whose `SunLightInfo` lacked one of the Game's Times of Day, since KK's `Set` would then have left the scene as the previous Time of Day left it. No KK Map does. Six of KKS's 31 do: five have only Morning, seacretbeach Morning and Night ([kks-spike.md](../design/kks-spike.md), section 1).

KKS's own code says what happens. The story game calls `Set(type)` and, when the Map has no info of that type, `Set(null)`, which picks the first info. Studio offers only the Times of Day a Map has. So the Extractor follows the story game: a missing Time of Day gets the first info, the Map keeps every Time of Day of its Game, and ADR 0009 makes the identical ones one Map Variant. fittingroom becomes one Map Variant covering all four Times of Day.

The spike also found that KKS's `VisibleChange` doesn't run when a Map loads: it has no `Start`, and the H and esthetic scenes call it at their points. So which scripts the Extractor replays at load is Game data in `extractor/games.py`: KK replays `VisibleChange`, KKS doesn't. KKS's `MapSkyInfo.Change` switches its lists after `Set`, with the requested Time of Day's number even where `Set` fell back. KKS's `MapVisibleState` (seacretbeach only) is replayed at state 0, which the story game sets on every weekday but Tuesday and Friday.

## Considered Options

- **Keep stopping (rejected)**: six Maps couldn't be extracted, for a case the game handles.
- **Give such a Map only the Times of Day it has (rejected)**: what Studio shows, but a Map listed for the story game would have no asset for the Times of Day it is shown at, and its tags would say less than the game does.
- **The story game's fallback (chosen)**.

## Consequences

- A KK Map without an info for a Time of Day would now be extracted the same way, with KKS's rule; KK has none, so KK's bundles don't change.
- KKS's `Set` hides every info's list before it shows the chosen one's, where KK's goes through the infos in turn, and they differ for an object in two lists: hoteloutside's `dentyu_OFF` is in three, and KK's order would hide it at Morning, where KKS shows it. So how `Set` treats the lists is Game data too (`sun_lists`).
- seacretbeach's Tuesday and Friday look isn't extracted.
