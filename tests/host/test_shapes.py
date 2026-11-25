"""The round preview a World gets (builder/blender/shapes.py, numpy only)."""

import numpy as np

from kkbp_maps.builder.blender.shapes import round_preview


def picture(w, h):
    px = np.zeros((h, w, 4), np.float32)
    px[..., 0], px[..., 3] = 0.25, 1.0
    return px.reshape(-1)


def test_a_wide_thumbnail_becomes_a_square_of_its_height():
    side, out = round_preview(picture(300, 200), 300, 200)
    assert side == 200 and out.shape == (200 * 200 * 4,)


def test_the_corners_are_clear_and_the_middle_is_the_picture():
    side, out = round_preview(picture(256, 256), 256, 256)
    img = out.reshape(side, side, 4)
    for y, x in ((0, 0), (0, side - 1), (side - 1, 0), (side - 1, side - 1)):
        assert img[y, x, 3] == 0.0
    assert np.allclose(img[side // 2, side // 2], [0.25, 0, 0, 1])


def test_the_edge_is_ringed_and_smooth():
    side, out = round_preview(picture(256, 256), 256, 256)
    row = out.reshape(side, side, 4)[side // 2]
    assert row[:, 0].max() > 0.7                      # a light ring at the edge
    alphas = row[:12, 3]
    assert 0 < alphas[alphas > 0].min() < 1           # soft, not a hard step


def test_the_crop_is_centred():
    px = np.zeros((100, 300, 4), np.float32)
    px[:, 100:200] = [0, 1, 0, 1]                     # only the middle third is green
    side, out = round_preview(px.reshape(-1), 300, 100)
    img = out.reshape(side, side, 4)
    assert side == 100 and img[50, 50, 1] == 1.0 and img[50, 50, 3] == 1.0
