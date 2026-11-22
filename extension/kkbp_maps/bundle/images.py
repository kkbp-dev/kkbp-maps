"""Reads the headers of a bundle's PNG and EXR files, without decoding their pixels."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXR_MAGIC = 20000630
PNG_CHANNELS = {0: 1, 4: 2, 2: 3, 6: 4}  # colour type -> channels: grey, grey and alpha, RGB, RGBA
EXR_HALF = 1
EXR_ZIP = (2, 3)  # ZIPS (one scanline per block) and ZIP (16)


@dataclass(frozen=True)
class Header:
    width: int
    height: int
    problems: tuple[str, ...]  # what in the header breaks the contract's rules for its format


def png_header(path: Path) -> Header:
    with path.open("rb") as f:
        head = f.read(33)
    if len(head) < 33 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise ValueError("isn't a PNG file")
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", head[16:29])
    problems = []
    if depth != 8:
        problems.append(f"has {depth} bits per channel, not 8")
    if color not in PNG_CHANNELS:
        problems.append(f"has PNG colour type {color}, not grey, grey and alpha, RGB or RGBA")
    if interlace:
        problems.append("is interlaced")
    return Header(width, height, tuple(problems))


def exr_header(path: Path) -> Header:
    with path.open("rb") as f:
        data = f.read(1 << 16)
    if len(data) < 8 or struct.unpack("<i", data[:4])[0] != EXR_MAGIC:
        raise ValueError("isn't an OpenEXR file")
    if data[5] & 0x1E:  # tiled, long names, deep or multi-part
        raise ValueError("isn't a single-part scanline OpenEXR file")
    pos = 8
    attributes = {}
    while True:
        name, pos = _cstring(data, pos)
        if not name:
            break
        kind, pos = _cstring(data, pos)
        if pos + 4 > len(data):
            raise ValueError("has a truncated header")
        size = struct.unpack("<i", data[pos:pos + 4])[0]
        pos += 4
        attributes[name] = (kind, data[pos:pos + size])
        pos += size
    for needed in ("channels", "compression", "dataWindow"):
        if needed not in attributes:
            raise ValueError(f"has no {needed} attribute")
    x0, y0, x1, y1 = struct.unpack("<iiii", attributes["dataWindow"][1][:16])
    problems = []
    compression = attributes["compression"][1][0]
    if compression not in EXR_ZIP:
        problems.append(f"uses OpenEXR compression {compression}, not ZIP")
    for name, pixel_type in _channels(attributes["channels"][1]):
        if pixel_type != EXR_HALF:
            problems.append(f"has channel {name} of pixel type {pixel_type}, not half float")
    return Header(x1 - x0 + 1, y1 - y0 + 1, tuple(problems))


def _cstring(data: bytes, pos: int) -> tuple[str, int]:
    end = data.find(b"\0", pos)
    if end < 0:
        raise ValueError("has a truncated header")
    return data[pos:end].decode("ascii", "replace"), end + 1


def _channels(chlist: bytes):
    pos = 0
    while pos < len(chlist) and chlist[pos] != 0:
        name, pos = _cstring(chlist, pos)
        pixel_type = struct.unpack("<i", chlist[pos:pos + 4])[0]
        pos += 16  # pixel type, pLinear and 3 reserved bytes, x and y sampling
        yield name, pixel_type
