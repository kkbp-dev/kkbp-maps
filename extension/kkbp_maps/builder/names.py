"""The Name Tables (D14): English names, catalogs' areas and categories, and the overrides that correct
the Extractor's Candidates. The tables are names/<Game>.toml; this module only reads them. Never imports
bpy.

A game name becomes English word by word: its " (N)" or " N" copy suffix and the prefixes in
[naming] strip are cut, the rest is split at underscores and between letters and digits, each word of
letters is looked up in [words], and numbers stay as they are: "mo_koi_map02_wall06_kaidan03" is
"Wall 06 Stairs 03". A word the tables don't know keeps its romaji, title-cased, and is reported.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

TABLES = Path(__file__).resolve().parent.parent / "names"
COPY_SUFFIX = re.compile(r"(\s*\(\d+\)|\s+\d+)$")
PART = re.compile(r"[A-Za-z]+|\d+")


@dataclass(frozen=True)
class Name:
    english: str
    words: tuple[str, ...]      # the game name's words of letters, lower case, in order
    unknown: tuple[str, ...]    # those the tables don't know


@dataclass(frozen=True)
class Override:
    kind: str | None
    category: str | None
    name: str | None


class NameTables:
    def __init__(self, data: dict, source: str = "<tables>"):
        self.source = source
        self.times_of_day: dict[str, str] = data.get("times_of_day", {})
        naming = data.get("naming", {})
        self.strip = [re.compile(p) for p in naming.get("strip", [])]
        self.default_category: str = naming.get("default_category", "Other")
        self.maps: dict[str, dict] = data.get("maps", {})
        self.words: dict[str, str] = {k.lower(): v for k, v in data.get("words", {}).items()}
        self.categories = [(c["category"], {w.lower() for w in c["words"]}) for c in data.get("categories", [])]
        self.overrides = []
        for o in data.get("overrides", []):
            if "match" not in o and "hash" not in o:
                raise ValueError(f"{source}: an override needs a match or a hash: {o}")
            if o.get("kind") not in (None, "prop", "structure"):
                raise ValueError(f"{source}: override kind {o['kind']!r} isn't prop or structure")
            self.overrides.append((re.compile(o["match"]) if "match" in o else None, o.get("hash"),
                                   Override(o.get("kind"), o.get("category"), o.get("name"))))

    @classmethod
    def load(cls, game: str, folder: Path = TABLES) -> "NameTables":
        path = Path(folder) / f"{game}.toml"
        with open(path, "rb") as f:
            return cls(tomllib.load(f), str(path))

    # --- Maps ------------------------------------------------------------------------------------

    def map_name(self, key: str) -> str | None:
        return self.maps.get(key, {}).get("name")

    def map_area(self, key: str) -> str | None:
        return self.maps.get(key, {}).get("area")

    def time_of_day(self, tod: str) -> str:
        return self.times_of_day.get(tod, tod.title())

    # --- game names ------------------------------------------------------------------------------

    def name(self, game_name: str) -> Name:
        text = COPY_SUFFIX.sub("", game_name.strip())
        cut = True
        while cut:
            cut = False
            for p in self.strip:
                shorter = p.sub("", text, count=1)
                if shorter != text and shorter:
                    text, cut = shorter, True
        out, words, unknown = [], [], []
        for part in PART.findall(text):
            if part.isdigit():
                out.append(part)
                continue
            word = part.lower()
            words.append(word)
            if word in self.words:
                out.append(self.words[word])
            else:
                unknown.append(word)
                out.append(word.title())
        if not out:
            return Name(game_name, (), ())
        return Name(" ".join(out), tuple(words), tuple(unknown))

    def category(self, name: Name) -> str:
        for category, words in self.categories:
            if words.intersection(name.words):
                return category
        return self.default_category

    def override(self, game_name: str, content_hash: str) -> Override | None:
        for pattern, h, o in self.overrides:
            if (h is not None and h == content_hash) or (pattern is not None and pattern.search(game_name)):
                return o
        return None
