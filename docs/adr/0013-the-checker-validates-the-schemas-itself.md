# The checker validates the JSON Schemas itself

The Map Bundle's JSON Schemas are the contract. Both the Extractor and the Builder check bundles against them, inside Blender's Python. Blender's Python has no `jsonschema`, and current `jsonschema` needs `rpds-py`, a native wheel for each platform. KKBP solves this with two copies: its importer checks the types by hand, and only its tests run `jsonschema` on the schemas.

kkbp-maps has `bundle/` validate the schemas itself, with a small standard-library validator for only the keywords the schemas use. The schemas stay the only statement of the shapes. A test checks that this validator and `jsonschema` (a developer dependency, in KKBP's dev venv) agree on every synthetic bundle, valid and broken, and another fails if a schema uses a keyword the validator doesn't know.

## Considered Options

- **Hand-written type checks beside the schemas, as KKBP (rejected)**: no dependency, but two copies that must change together.
- **`jsonschema` as a first-run dependency (rejected)**: the real thing, but one more native wheel to pin for three platforms, for a job a hundred lines do.
- **A validator for the subset the schemas use (chosen)**.

## Consequences

- A schema can only use the keywords the validator knows. Adding one means adding it to the validator and to the agreement test.
- The validator's messages are its own; only whether a file is valid has to agree with `jsonschema`.
