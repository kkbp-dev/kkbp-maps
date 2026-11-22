# Times of Day that light a Map the same are one Map Variant

ADR 0003 publishes one asset per Map Variant, and a Map Variant was a Map at one Time of Day. Some Maps give every Time of Day the same light: KK's park has three identical `SunLightInfo` entries, because it is always night there ([kk-spike.md](../design/kk-spike.md)). One asset per Time of Day would publish three assets that look the same.

So a Map gets one Map Variant per distinct lighting state. Times of Day whose sun, fog, sky, shown objects, Lightmap Set and Grade are all equal share one Map Variant. It is tagged with every Time of Day it covers, and its name leaves the Time of Day out ("Park" rather than "Park, Night").

## Considered Options

- **Three identical assets (rejected)**: uniform, but it clutters the asset browser with duplicates.
- **One Map Variant per distinct lighting state (chosen)**.

## Consequences

- The Extractor compares the Times of Day it reads, and the Map Bundle says which Times of Day each lighting state covers.
- A KKBP Hook (D15) looking for a Map's night light finds it through the tags, not the asset name.
