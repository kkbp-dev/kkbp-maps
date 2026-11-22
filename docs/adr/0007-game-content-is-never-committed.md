# Game content is never committed

Nothing taken from a game enters the repository or a release: no Scene Bundles, Map Bundles, built Map Libraries, textures, meshes, Golden Maps or Reference Captures. Each user builds their own Map Library from their own install, and each developer makes their own Golden Maps and Reference Captures. What is committed is code, the contract, the Name Tables, and test snapshots that hold only counts, names, hashes and tags.

## Consequences

- A developer without a Game has that Game's game-backed tests skipped, with a notice.
- The Name Tables hold names and categories, not game data, so they stay in the repository and can be improved by anyone.
