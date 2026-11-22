# The Schema Version stays 0.x until the first release

KKBP's rule is that an additive change raises the Schema Version's minor and anything else its major, and that an importer accepts every bundle with its own major. kkbp-maps follows that rule, but not yet. Phases 3 to 5 will change the contract as the Extractor, the Builder and the look check meet real Maps, and many of those changes won't be additive.

So the Schema Version starts at `0.1`, and while its major is 0, a Builder accepts only bundles with exactly its own version. Any change raises the minor. The first release (v0.1, Phase 6) sets it to `1.0`, and from then on KKBP's rule applies.

## Considered Options

- **`1.0` now, with KKBP's rule from the start (rejected)**: honest only if the contract were stable, and it would reach a high major version before anyone uses it.
- **No version until the release (rejected)**: nothing would tell a developer that a cached bundle is stale.
- **`0.x`, exact match (chosen)**.

## Consequences

- A developer's cached Map Bundles go stale with every contract change before the release and have to be extracted again.
