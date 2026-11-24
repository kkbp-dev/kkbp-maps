# Unprefixed copies of a Prop are its Placements, and unbaked reflection probes are left out

Extracting all 43 KK Maps stopped on four. Two things the Golden Maps never showed:

- **Copies without the prefix.** In 2f, libraryroom and lockerroom the game places plain copies of a `p_` Prop under `MapObjectGroup` with no prefix: 2f's `isu00` beside `p_o_koi_isu00`, libraryroom's six `isu0200` beside `p_o_koi_isu0200_00`, lockerroom's `c00` beside the `p_o_koi_tana12Ac_00` shelves. Each has exactly the Prop's shape. The walk makes them `unprefixed` Structures, and ADR 0019 stops on a shape that is both a Prop and a Structure.
- **A probe that was never baked.** akikyoushitu's `Reflection Probe2-99` is in baked mode with no baked cubemap. Unity draws nothing from such a probe: the renderers in its box take the Map's own reflection.

So an unprefixed Placement whose shape is a `p_` Prop's is another Placement of that Prop, unless another Placement lies under it (a Prop can't hold one). The Candidate keeps the `p_prefix` rule, so its kind still follows its rule and the contract doesn't change. A `mo_` or `o_` Structure with a Prop's shape still stops the extraction: a prefix is the game's own word for what a piece is, and the two disagree. A reflection probe in baked mode with no baked cubemap is left out; a realtime probe, or a custom one without its cubemap, still stops it.

## Considered Options

- **Keep stopping (rejected)**: four Maps couldn't be extracted, for copies that are plainly the Prop.
- **Shape always wins, whatever the prefix (rejected)**: a `mo_` piece and a `p_` piece with the same shape would silently become one, against the game's own naming.
- **Unprefixed defers to a Prop's shape (chosen)**.
- **Counting the left-out probe in `skipped` (rejected)**: it needs a new skip reason, a contract change, for a probe the game itself doesn't use.

## Consequences

- Amends ADR 0019's consequence that a Prop and a Structure of the same shape stop the extraction: it still holds for prefixed Structures.
- With both, every one of KK's 43 Maps extracts.
