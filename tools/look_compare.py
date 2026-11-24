"""The look check's measure: how far a Blender render is from its Reference Capture (ADR 0006).

Both images are sRGB-encoded 8-bit frames of the same Capture View. Three numbers, each with a tolerance
from tests/look/<Game>.json:

- **mean ΔE**: the mean CIEDE2000 difference over all pixels (D65 white, the sRGB primaries);
- **p95 ΔE**: its 95th percentile, so a few edge pixels don't fail a view but a wrong region does;
- **worst tile**: the image is cut into a grid of tiles and each tile's mean linear luminance compared;
  the result is the largest relative difference, |render − capture| / max(capture, floor). This catches
  a region that is too bright or dark overall, which ΔE spreads thin.

numpy only, so it is host-tested on synthetic images.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_WHITE = _M.sum(axis=1)


def lab(rgb8: np.ndarray) -> np.ndarray:
    """CIELAB of an (h, w, 3) sRGB image in 0…255 or 0…1 floats."""
    rgb = np.asarray(rgb8, dtype=np.float64)
    if rgb.max(initial=0) > 1.0:
        rgb = rgb / 255.0
    xyz = srgb_to_linear(rgb) @ _M.T / _WHITE
    e = 216 / 24389
    k = 24389 / 27
    f = np.where(xyz > e, np.cbrt(xyz), (k * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def delta_e2000(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 between two Lab arrays of the same shape (Sharma, Wu and Dalal 2005)."""
    L1, a1, b1 = np.moveaxis(lab1, -1, 0)
    L2, a2, b2 = np.moveaxis(lab2, -1, 0)
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dL = L2 - L1
    dC = C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0, dh)
    dH = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh) / 2)
    Lm = (L1 + L2) / 2
    Cmp = (C1p + C2p) / 2
    hs = h1p + h2p
    hm = np.where(C1p * C2p == 0, hs,
                  np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hm - 30)) + 0.24 * np.cos(np.radians(2 * hm))
         + 0.32 * np.cos(np.radians(3 * hm + 6)) - 0.20 * np.cos(np.radians(4 * hm - 63)))
    dtheta = 30 * np.exp(-(((hm - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cmp ** 7 / (Cmp ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lm - 50) ** 2 / np.sqrt(20 + (Lm - 50) ** 2)
    Sc = 1 + 0.045 * Cmp
    Sh = 1 + 0.015 * Cmp * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dL / Sl) ** 2 + (dC / Sc) ** 2 + (dH / Sh) ** 2 + Rt * (dC / Sc) * (dH / Sh))


@dataclass(frozen=True)
class Tolerance:
    mean_de: float = 3.0
    p95_de: float = 10.0
    tile: float = 0.10
    grid: int = 8
    floor: float = 0.02   # linear luminance below which a tile's difference is measured against this


@dataclass(frozen=True)
class Result:
    mean_de: float
    p95_de: float
    worst_tile: float
    tiles: np.ndarray        # (grid, grid) relative differences, signed: render brighter is positive
    heat: np.ndarray         # (h, w) ΔE per pixel
    tolerance: Tolerance

    @property
    def passed(self) -> bool:
        t = self.tolerance
        return self.mean_de <= t.mean_de and self.p95_de <= t.p95_de and self.worst_tile <= t.tile

    def summary(self) -> dict:
        return {"mean_de": round(self.mean_de, 3), "p95_de": round(self.p95_de, 3),
                "worst_tile": round(self.worst_tile, 4), "passed": self.passed}


def luminance(rgb8: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb8, dtype=np.float64)
    if rgb.max(initial=0) > 1.0:
        rgb = rgb / 255.0
    return srgb_to_linear(rgb) @ _M[1]


def tiles(render: np.ndarray, capture: np.ndarray, t: Tolerance) -> np.ndarray:
    yr, yc = luminance(render), luminance(capture)
    h, w = yc.shape
    out = np.zeros((t.grid, t.grid))
    for i in range(t.grid):
        for j in range(t.grid):
            sl = (slice(i * h // t.grid, (i + 1) * h // t.grid), slice(j * w // t.grid, (j + 1) * w // t.grid))
            c, r = yc[sl].mean(), yr[sl].mean()
            out[i, j] = (r - c) / max(c, t.floor)
    return out


def compare(render: np.ndarray, capture: np.ndarray, t: Tolerance = Tolerance()) -> Result:
    render = np.asarray(render)[..., :3]
    capture = np.asarray(capture)[..., :3]
    if render.shape != capture.shape:
        raise ValueError(f"sizes differ: render {render.shape}, capture {capture.shape}")
    heat = delta_e2000(lab(capture), lab(render))
    tl = tiles(render, capture, t)
    return Result(float(heat.mean()), float(np.percentile(heat, 95)), float(np.abs(tl).max()), tl, heat, t)
