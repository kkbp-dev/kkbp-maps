# Room containers are walked into, not made one Candidate

ADR 0004 and D3 make a `p_` node with everything under it a Prop, and a `mo_` or `o_` node a Structure. In KK the prefix isn't always the piece's own. In 33 of the 43 Maps a whole room or shell sits under one node whose name has the prefix and `koi_map` in it: park's whole Map is under `p_koi_map71_park`, 1F's shell under `o_koi_map02_00`, and libraryroom's `p_koi_map21_00` holds 231 `p_` Props. Read literally, park became a single Prop of 73 renderers, and 1F's shell one Structure of 124.

So a node without a renderer of its own whose name matches `^(p_|o_|mo_)(o_)?koi_(stu_)?map` (`p_koi_map…`, `p_o_koi_map…`, `o_koi_map…`, `p_koi_stu_map…`) is a Room Container. The Candidate walk goes into it as it does into an `n_` group, so the pieces under it become Candidates by their own prefixes. The pattern is Game data (`containers` in `games.py`), beside the prefixes.

| Golden Map | Literal rule | Containers walked into |
|---|---|---|
| 1F | 1 Structure, 12 Props | 45 Structures, 12 Props; largest Placement 31 renderers |
| park | 1 Prop holding the Map | 29 Structures with 54 Placements |
| ground | 1 Structure, 8 Props | 26 Structures, 8 Props; largest Placement 19 renderers |

## Considered Options

- **The literal prefix rule (rejected)**: no name pattern beyond the prefixes, but whole rooms become single assets and the pieces inside them can't be reused.
- **Walking into every node without a renderer (rejected)**: no pattern at all, but real multi-part Props such as 1F's flower beds (`p_o_koi_kadan01`, 31 renderers under a group) would fall apart.
- **A name pattern for room containers (chosen)**.

## Consequences

- A node matching the pattern that has a renderer of its own, such as pool's `p_koi_map37_water00`, is an ordinary piece under its prefix.
- park's benches, lamps and trees are named `o_` by the game, so they come out as Structures; the Name Tables' overrides make them Props in the Builder (ADR 0004).
- Placements with the same shape are one Candidate with the first Placement's rule; a Prop and a Structure of the same shape stop the extraction.
