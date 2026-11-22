"""Checks Map Bundles against the contract, with the deep check: schemas, rules and mesh hashes.

Usage: python tools/check_bundle.py <bundle folder>...

Exits with 1 if any bundle has a problem. Needs only the standard library.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extension" / "kkbp_maps"))

from bundle import check  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    failed = False
    for arg in argv:
        problems = check(arg, deep=True)
        print(f"{arg}: {'ok' if not problems else f'{len(problems)} problems'}")
        for p in problems:
            print(f"  {p}")
        failed |= bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
