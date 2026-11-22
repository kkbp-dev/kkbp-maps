"""A BC6H decoder that keeps the HDR values.

UnityPy decodes BC6H through Pillow, which clamps it to 8 bits; KK's reflection probes and skybox
reflections are BC6H, and their values reach above 1. This follows the Direct3D 11 specification of
the format (unsigned and signed, all 14 modes). Pure Python per block: KK's BC6H cubemaps are at most
256² per face, which decodes in a few seconds.
"""

from __future__ import annotations

import numpy as np

# Each mode: (mode bits, number of mode bits, two regions, transformed, endpoint bits, delta bits R G B,
# bit layout). The layout lists, for each block bit after the mode bits, the field it belongs to and
# the field's bit: fields are w (base endpoint), x, y, z (the other endpoints) per channel r, g, b,
# and d (the partition). From the specification's "BC6H compressed endpoint format" table.


def _f(spec: str):
    """The specification's field runs ('rw 9:0, gz 4, ...') as (field, bit) per block bit, in stream
    order. A run a:b is read from bit b to bit a: 9:0 is bits 0 to 9, and a reversed run such as
    rw 10:15 is bits 15 down to 10."""
    out = []
    for run in spec.split(","):
        name, bits = run.split()
        a, _, b = bits.partition(":")
        a = int(a)
        b = int(b) if b else a
        step = 1 if a >= b else -1
        out += [(name, bit) for bit in range(b, a + step, step)]
    return out


MODES = {
    # 2-bit modes
    0b00: (2, True, True, 10, (5, 5, 5), _f(
        "gy 4,by 4,bz 4,rw 9:0,gw 9:0,bw 9:0,rx 4:0,gz 4,gy 3:0,gx 4:0,bz 0,gz 3:0,bx 4:0,bz 1,by 3:0,"
        "ry 4:0,bz 2,rz 4:0,bz 3,d 4:0")),
    0b01: (2, True, True, 7, (6, 6, 6), _f(
        "gy 5,gz 4,gz 5,rw 6:0,bz 0,bz 1,by 4,gw 6:0,by 5,bz 2,gy 4,bw 6:0,bz 3,bz 5,bz 4,rx 5:0,gy 3:0,"
        "gx 5:0,gz 3:0,bx 5:0,by 3:0,ry 5:0,rz 5:0,d 4:0")),
    # 5-bit modes
    0b00010: (5, True, True, 11, (5, 4, 4), _f(
        "rw 9:0,gw 9:0,bw 9:0,rx 4:0,rw 10,gy 3:0,gx 3:0,gw 10,bz 0,gz 3:0,bx 3:0,bw 10,bz 1,by 3:0,"
        "ry 4:0,bz 2,rz 4:0,bz 3,d 4:0")),
    0b00110: (5, True, True, 11, (4, 5, 4), _f(
        "rw 9:0,gw 9:0,bw 9:0,rx 3:0,rw 10,gz 4,gy 3:0,gx 4:0,gw 10,gz 3:0,bx 3:0,bw 10,bz 1,by 3:0,"
        "ry 3:0,bz 0,bz 2,rz 3:0,gy 4,bz 3,d 4:0")),
    0b01010: (5, True, True, 11, (4, 4, 5), _f(
        "rw 9:0,gw 9:0,bw 9:0,rx 3:0,rw 10,by 4,gy 3:0,gx 3:0,gw 10,bz 0,gz 3:0,bx 4:0,bw 10,by 3:0,"
        "ry 3:0,bz 1,bz 2,rz 3:0,bz 4,bz 3,d 4:0")),
    0b01110: (5, True, True, 9, (5, 5, 5), _f(
        "rw 8:0,by 4,gw 8:0,gy 4,bw 8:0,bz 4,rx 4:0,gz 4,gy 3:0,gx 4:0,bz 0,gz 3:0,bx 4:0,bz 1,by 3:0,"
        "ry 4:0,bz 2,rz 4:0,bz 3,d 4:0")),
    0b10010: (5, True, True, 8, (6, 5, 5), _f(
        "rw 7:0,gz 4,by 4,gw 7:0,bz 2,gy 4,bw 7:0,bz 3,bz 4,rx 5:0,gy 3:0,gx 4:0,bz 0,gz 3:0,bx 4:0,"
        "bz 1,by 3:0,ry 5:0,rz 5:0,d 4:0")),
    0b10110: (5, True, True, 8, (5, 6, 5), _f(
        "rw 7:0,bz 0,by 4,gw 7:0,gy 5,gy 4,bw 7:0,gz 5,bz 4,rx 4:0,gz 4,gy 3:0,gx 5:0,gz 3:0,bx 4:0,"
        "bz 1,by 3:0,ry 4:0,bz 2,rz 4:0,bz 3,d 4:0")),
    0b11010: (5, True, True, 8, (5, 5, 6), _f(
        "rw 7:0,bz 1,by 4,gw 7:0,by 5,gy 4,bw 7:0,bz 5,bz 4,rx 4:0,gz 4,gy 3:0,gx 4:0,bz 0,gz 3:0,bx 5:0,"
        "by 3:0,ry 4:0,bz 2,rz 4:0,bz 3,d 4:0")),
    0b11110: (5, True, False, 6, (6, 6, 6), _f(
        "rw 5:0,gz 4,bz 0,bz 1,by 4,gw 5:0,gy 5,by 5,bz 2,gy 4,bw 5:0,gz 5,bz 3,bz 5,bz 4,rx 5:0,gy 3:0,"
        "gx 5:0,gz 3:0,bx 5:0,by 3:0,ry 5:0,rz 5:0,d 4:0")),
    0b00011: (5, False, False, 10, (10, 10, 10), _f("rw 9:0,gw 9:0,bw 9:0,rx 9:0,gx 9:0,bx 9:0")),
    0b00111: (5, False, True, 11, (9, 9, 9), _f("rw 9:0,gw 9:0,bw 9:0,rx 8:0,rw 10,gx 8:0,gw 10,bx 8:0,bw 10")),
    0b01011: (5, False, True, 12, (8, 8, 8), _f(
        "rw 9:0,gw 9:0,bw 9:0,rx 7:0,rw 10:11,gx 7:0,gw 10:11,bx 7:0,bw 10:11")),
    0b01111: (5, False, True, 16, (4, 4, 4), _f(
        "rw 9:0,gw 9:0,bw 9:0,rx 3:0,rw 10:15,gx 3:0,gw 10:15,bx 3:0,bw 10:15")),
}

# The first 32 two-subset partitions of BC7, which BC6H shares: bit i set means pixel i is in subset 1.
PARTITIONS = (
    0xCCCC, 0x8888, 0xEEEE, 0xECC8, 0xC880, 0xFEEC, 0xFEC8, 0xEC80, 0xC800, 0xFFEC, 0xFE80, 0xE800,
    0xFFE8, 0xFF00, 0xFFF0, 0xF000, 0xF710, 0x008E, 0x7100, 0x08CE, 0x008C, 0x7310, 0x3100, 0x8CCE,
    0x088C, 0x3110, 0x6666, 0x366C, 0x17E8, 0x0FF0, 0x718E, 0x399C,
)
ANCHOR2 = (15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15,
           15, 2, 8, 2, 2, 8, 8, 15, 2, 8, 2, 2, 8, 8, 2, 2)
WEIGHTS3 = (0, 9, 18, 27, 37, 46, 55, 64)
WEIGHTS4 = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)


def decode_bc6h(data: bytes, width: int, height: int, signed: bool = False) -> np.ndarray:
    """BC6H data as float32 RGB, height × width × 3, rows in the data's own order."""
    bw, bh = (width + 3) // 4, (height + 3) // 4
    out = np.zeros((bh * 4, bw * 4, 3), dtype=np.float32)
    blocks = np.frombuffer(data, dtype=np.uint8, count=bw * bh * 16).reshape(-1, 16)
    for i, block in enumerate(blocks):
        by, bx = divmod(i, bw)
        out[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4] = _block(int.from_bytes(block.tobytes(), "little"), signed)
    return out[:height, :width]


def _block(bits: int, signed: bool) -> np.ndarray:
    mode = bits & 0b11
    if mode not in (0b00, 0b01):
        mode = bits & 0b11111
    if mode not in MODES:
        return np.zeros((4, 4, 3), dtype=np.float32)  # reserved modes decode to black
    nbits, two, transformed, ep_bits, delta_bits, layout = MODES[mode]
    fields: dict[str, int] = {}
    pos = nbits
    for name, b in layout:
        if (bits >> pos) & 1:
            fields[name] = fields.get(name, 0) | (1 << b)
        pos += 1
    ends = ("w", "x", "y", "z") if two else ("w", "x")
    e = {c: [fields.get(c + k, 0) for k in ends] for c in "rgb"}
    for ci, c in enumerate("rgb"):
        if signed:
            e[c][0] = _sext(e[c][0], ep_bits)
        if transformed:
            for k in range(1, len(ends)):
                e[c][k] = _sext(e[c][k], delta_bits[ci])
                e[c][k] = (e[c][0] + e[c][k]) & ((1 << ep_bits) - 1)
                if signed:
                    e[c][k] = _sext(e[c][k], ep_bits)
        elif signed:
            for k in range(1, len(ends)):
                e[c][k] = _sext(e[c][k], ep_bits)
        e[c] = [_unquantize(v, ep_bits, signed) for v in e[c]]

    partition = fields.get("d", 0) if two else 0
    index_bits = 3 if two else 4
    weights = WEIGHTS3 if two else WEIGHTS4
    anchors = (0, ANCHOR2[partition]) if two else (0,)
    out = np.empty((16, 3), dtype=np.float32)
    for p in range(16):
        subset = (PARTITIONS[partition] >> p) & 1 if two else 0
        n = index_bits - 1 if p in anchors else index_bits
        index = (bits >> pos) & ((1 << n) - 1)
        pos += n
        w = weights[index]
        for ci, c in enumerate("rgb"):
            a, b = e[c][2 * subset], e[c][2 * subset + 1]
            out[p, ci] = _finish(((64 - w) * a + w * b + 32) >> 6, signed)
    return out.reshape(4, 4, 3)


def _sext(v: int, n: int) -> int:
    return v - (1 << n) if v & (1 << (n - 1)) else v


def _unquantize(v: int, bits: int, signed: bool) -> int:
    if not signed:
        if bits >= 15 or v == 0:
            return v
        if v == (1 << bits) - 1:
            return 0xFFFF
        return ((v << 16) + 0x8000) >> bits
    if bits >= 16:
        return v
    negative = v < 0
    v = -v if negative else v
    if v == 0:
        u = 0
    elif v >= (1 << (bits - 1)) - 1:
        u = 0x7FFF
    else:
        u = ((v << 15) + 0x4000) >> (bits - 1)
    return -u if negative else u


def _finish(v: int, signed: bool) -> float:
    if not signed:
        h = (v * 31) >> 6
    else:
        h = (-v * 31) >> 5 if v < 0 else (v * 31) >> 5
        h = (h | 0x8000) if v < 0 else h
    return float(np.frombuffer(int(h).to_bytes(2, "little"), dtype=np.float16)[0])
