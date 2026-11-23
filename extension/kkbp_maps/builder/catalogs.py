"""Asset catalogs (D10): UUIDs that stay the same across rebuilds and differ between Games, and
Blender's catalog definition file. Never imports bpy."""

from __future__ import annotations

import uuid

# Fixed for good: changing it changes every catalog's UUID, and assets in users' files lose their catalog.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://kkbp-maps.invalid/catalogs")
FILE_NAME = "blender_assets.cats.txt"


def catalog_uuid(game: str, path: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{game}/{path}"))


def catalog_file(catalogs: dict[str, str]) -> str:
    """The text of blender_assets.cats.txt for {path: UUID}."""
    lines = [
        "# This is an Asset Catalog Definition file for Blender.",
        "#",
        "# Empty lines and lines starting with `#` will be ignored.",
        "# The first non-ignored line should be the version indicator.",
        '# Other lines are of the format "UUID:catalog/path/for/assets:simple catalog name"',
        "#",
        "# Written by kkbp-maps; a rebuild writes it again.",
        "",
        "VERSION 1",
        "",
    ]
    lines += [f"{u}:{path}:{path.replace('/', '-')}" for path, u in sorted(catalogs.items())]
    return "\n".join(lines) + "\n"
