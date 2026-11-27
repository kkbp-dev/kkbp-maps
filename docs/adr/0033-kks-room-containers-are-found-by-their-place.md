# KKS's room containers are found by their place under the Map root

Amends ADR 0019, which finds a Room Container by a name pattern: a node without a renderer of its own whose name matches `^(p_|o_|mo_)(o_)?koi_(stu_)?map`. KKS's names don't fit that pattern, and no other pattern separates its containers from its Props: hotellobby's whole room is `p_ks_r01`, and a table in it is `p_ks_r01_table00` ([kks-spike.md](../design/kks-spike.md), section 10). What does separate them is where they are. In 30 of KKS's 31 Maps exactly one node directly under the `Map` root has no renderer of its own and a `p_ks_` or `o_ks_` name, and it holds the room or the whole outdoor area: hoteloutside's `o_ks_m00hotel00_00` (187 renderers), lighthouse's `o_ks_m06_LightHouse00_00` (604). Deeper renderer-less `ks_` nodes are colliders (`…col`) or Props of several parts.

So a Game's containers are data in `extractor/games.py` in two forms: a name pattern that holds at any depth (KK's) or one that holds only for children of the scene's root (KKS's, `^(p_|o_)ks_`). The Candidate walk goes into a container either way, as ADR 0019 says.

## Considered Options

- **A longer name pattern for KKS (rejected)**: `p_ks_r01` and `p_ks_r01_table00` differ only by a suffix that other containers have too (`p_ks_r07_00`, `p_ks_r14_room`).
- **Walking into every renderer-less node (rejected)**: as ADR 0019 found, multi-part Props would fall apart.
- **A pattern that holds under the root only (chosen)**.

## Consequences

- KK's pattern and Candidates don't change.
- A KKS container below the root's children (harbor's `o_ks_m03_shop00_00`, 45 renderers) is a Structure of its own, like any other multi-part piece.
