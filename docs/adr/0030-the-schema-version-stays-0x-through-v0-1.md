# The Schema Version stays 0.x through v0.1

Amends ADR 0014, which set the Schema Version to `1.0` at the first release. v0.1 is KK only. KKS (shared dependencies, batched meshes, SpeedTree, realtime Lighting Rigs) and SVS (URP, external Lightmap Sets) will reshape the contract, and most of those changes won't be additive: under KKBP's rule they would raise the major again within two phases.

The contract binds nobody else yet. To a user, Map Bundles are a folder the extension writes and reads itself (the Bundle Folder), and a Map Bundle of another Schema Version is extracted again, a Map at a time, the way a stale one is today. So the Schema Version stays `0.x`, matched exactly, through v0.1, and becomes `1.0` with the first release whose contract is meant to last: the one that covers all three Games.

## Considered Options

- **`1.0` at v0.1, as ADR 0014 said (rejected)**: a promise of stability the next two phases would break.
- **`0.x` until the contract covers every Game (chosen)**.

## Consequences

- Upgrading the extension can make a user's Map Bundles stale; the next build extracts them again.
