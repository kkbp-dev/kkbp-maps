"""Pixels in and out: the bundle's PNG and EXR files, colour decoding and resizing.

The EXR writer makes the same bytes as tests/bundle_builder.exr_bytes, whose files Blender 5.2.2 reads
(a test checks they agree), with numpy doing the work. PNGs are written by Pillow: 8-bit, not
interlaced, grey, grey and alpha, RGB or RGBA.
"""

from __future__ import annotations

import io
import struct
import zlib

import numpy as np

EXR_ROWS_PER_BLOCK = 16  # ZIP compression
EXR_CHANNELS = ("R", "G", "B", "A")


def png_bytes(pixels: np.ndarray) -> bytes:
    """An 8-bit PNG of an H × W × C uint8 array, rows top first."""
    from PIL import Image

    a = _hwc(pixels)
    if a.dtype != np.uint8:
        raise TypeError("a PNG holds uint8 pixels")
    mode = {1: "L", 2: "LA", 3: "RGB", 4: "RGBA"}[a.shape[2]]
    img = Image.fromarray(a[:, :, 0] if mode == "L" else a, mode)
    out = io.BytesIO()
    img.save(out, format="PNG", compress_level=6)
    return out.getvalue()


def exr_bytes(pixels: np.ndarray) -> bytes:
    """A half-float, ZIP-compressed, scanline OpenEXR of an H × W × C float array (C = 3 or 4: R, G,
    B and A), rows top first."""
    a = _hwc(pixels)
    height, width, channels = a.shape
    if channels not in (3, 4):
        raise ValueError("an EXR here holds RGB or RGBA")
    names = EXR_CHANNELS[:channels]
    order = sorted(range(channels), key=lambda c: names[c])  # EXR stores channels by name

    def attribute(name: str, kind: str, data: bytes) -> bytes:
        return name.encode() + b"\0" + kind.encode() + b"\0" + struct.pack("<i", len(data)) + data

    chlist = b"".join(names[c].encode() + b"\0" + struct.pack("<iB3xii", 1, 0, 1, 1) for c in order) + b"\0"
    box = struct.pack("<iiii", 0, 0, width - 1, height - 1)
    header = (struct.pack("<ii", 20000630, 2)
              + attribute("channels", "chlist", chlist)
              + attribute("compression", "compression", bytes([3]))
              + attribute("dataWindow", "box2i", box)
              + attribute("displayWindow", "box2i", box)
              + attribute("lineOrder", "lineOrder", bytes([0]))
              + attribute("pixelAspectRatio", "float", struct.pack("<f", 1.0))
              + attribute("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0))
              + attribute("screenWindowWidth", "float", struct.pack("<f", 1.0))
              + b"\0")
    planar = np.ascontiguousarray(half(a)[:, :, order].transpose(0, 2, 1))  # per row, each channel's run
    blocks = []
    for y0 in range(0, height, EXR_ROWS_PER_BLOCK):
        raw = planar[y0:y0 + EXR_ROWS_PER_BLOCK].astype("<f2").tobytes()
        blocks.append((y0, _exr_zip(raw)))
    offset = len(header) + 8 * len(blocks)
    table, body = bytearray(), bytearray()
    for y0, data in blocks:
        table += struct.pack("<Q", offset + len(body))
        body += struct.pack("<ii", y0, len(data)) + data
    return header + bytes(table) + bytes(body)


def _exr_zip(raw: bytes) -> bytes:
    """OpenEXR's ZIP compression: even bytes then odd bytes, delta-encoded, deflated."""
    b = np.frombuffer(raw, dtype=np.uint8)
    split = np.concatenate([b[0::2], b[1::2]])
    delta = split.copy()
    delta[1:] = (split[1:].astype(np.int16) - split[:-1] + 128) & 0xFF
    packed = zlib.compress(delta.tobytes())
    return packed if len(packed) < len(raw) else raw


def half(a: np.ndarray) -> np.ndarray:
    """Floats as float16, clamped to its finite range."""
    return np.clip(np.nan_to_num(np.asarray(a, dtype=np.float32)), -65504.0, 65504.0).astype(np.float16)


def hash_bytes(pixels: np.ndarray) -> bytes:
    """The pixels as the Content Hash takes them: as the file holds them, interleaved, rows top first;
    a byte per channel for PNG, little-endian float16 for EXR."""
    a = _hwc(pixels)
    return a.tobytes() if a.dtype == np.uint8 else half(a).astype("<f2").tobytes()


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def rgbm_decode(rgba: np.ndarray, scale: float, exponent: float) -> np.ndarray:
    """A Unity RGBM lightmap (uint8 H × W × 4, RGB sampled as sRGB) as linear float RGB:
    scale · a^exponent · srgb_to_linear(rgb) (kk-spike, section 3)."""
    f = rgba.astype(np.float32) / 255.0
    return (scale * f[:, :, 3:4] ** exponent * srgb_to_linear(f[:, :, :3])).astype(np.float32)


def unpack_normal(rgba: np.ndarray, x_from_alpha: bool) -> np.ndarray:
    """A Unity normal map (uint8 H × W × 4) as a standard tangent-space map (uint8 RGB), the way the
    game's Unity reads it: X from A (Unity 5.6's UnpackNormalDXT5nm) or from R · A (later Unity), Y
    from G, Z rebuilt (KKBP's NormalMaps.Unpack)."""
    f = rgba.astype(np.float64) / 255.0
    x = (f[:, :, 3] if x_from_alpha else f[:, :, 0] * f[:, :, 3]) * 2 - 1
    y = f[:, :, 1] * 2 - 1
    z = np.sqrt(np.maximum(0.0, 1 - x * x - y * y))
    return to_byte(np.stack([x, y, z], axis=2) * 0.5 + 0.5)


def to_byte(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.asarray(x) * 255.0), 0, 255).astype(np.uint8)


def to_rgb(a: np.ndarray) -> np.ndarray:
    """Grey or grey-and-alpha pixels as RGB, other pixels' first three channels."""
    a = _hwc(a)
    if a.shape[2] in (1, 2):
        return np.repeat(a[:, :, :1], 3, axis=2)
    return a[:, :, :3]


def resize(pixels: np.ndarray, max_size: int, *, renormalize: bool = False) -> np.ndarray:
    """An image scaled down so its longest side is at most `max_size`, keeping its aspect ratio, with
    Pillow's Lanczos filter on the stored values; normal maps are renormalised afterwards."""
    from PIL import Image

    a = _hwc(pixels)
    h, w = a.shape[:2]
    if max(h, w) <= max_size:
        return a
    f = max_size / max(h, w)
    size = (max(1, round(w * f)), max(1, round(h * f)))
    channels = []
    for c in range(a.shape[2]):
        img = Image.fromarray(a[:, :, c].astype(np.float32), "F")
        channels.append(np.asarray(img.resize(size, Image.Resampling.LANCZOS)))
    out = np.stack(channels, axis=2)
    if renormalize:
        n = out[:, :, :3] / 255.0 * 2 - 1
        n /= np.maximum(np.linalg.norm(n, axis=2, keepdims=True), 1e-6)
        out[:, :, :3] = (n * 0.5 + 0.5) * 255.0
    if a.dtype == np.uint8:
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return out.astype(np.float32)


def _hwc(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    if a.ndim == 2:
        a = a[:, :, None]
    return np.ascontiguousarray(a)
