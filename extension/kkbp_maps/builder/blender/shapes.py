"""Shapes for asset previews, on pixel arrays: numpy only, no bpy, so the host tests run them.

A World's preview is its Map Variant's thumbnail cut to a circle with a thin light ring, so the two
assets look alike but can't be mistaken for each other in the Asset Browser.
"""

from __future__ import annotations

import numpy as np

RING_ALPHA = 0.67


def round_preview(pixels, width: int, height: int) -> tuple[int, np.ndarray]:
    """`pixels` (flat RGBA floats, rows bottom first, as Blender gives them) cut to the centred square
    of the shorter side, masked to a circle with smooth edges, and ringed. Returns (side, flat pixels),
    premultiplied: the Asset Browser draws previews with premultiplied alpha, so a pixel's colour shows
    whatever its alpha unless it is multiplied by it."""
    img = np.asarray(pixels, dtype=np.float32).reshape(height, width, 4)
    side = min(width, height)
    x0, y0 = (width - side) // 2, (height - side) // 2
    img = img[y0:y0 + side, x0:x0 + side].copy()

    inset = max(1.0, side / 128)                   # a hair inside the tile's edge
    radius = side / 2 - inset
    ring = max(1.5, side * 0.012)                  # the ring's width in pixels
    centre = (side - 1) / 2
    yy, xx = np.mgrid[0:side, 0:side].astype(np.float32)
    distance = np.hypot(xx - centre, yy - centre)

    inside = np.clip(radius - distance + 0.5, 0.0, 1.0)
    band = np.clip(ring / 2 - np.abs(distance - (radius - ring / 2)) + 0.5, 0.0, 1.0) * RING_ALPHA

    img[..., 3] *= inside
    over = band[..., None]
    img[..., :3] = img[..., :3] * (1 - over) + over          # white ring over the picture
    img[..., 3] = img[..., 3] + band * (1 - img[..., 3])
    img[..., :3] *= img[..., 3:4]
    return side, img.reshape(-1)
