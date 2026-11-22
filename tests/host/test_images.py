"""The Extractor's image files, colour decoding and BC6H, on synthetic pixels."""

import struct

import numpy as np
import pytest

from bundle import hashing
from bundle import images as headers
from bundle_builder import exr_bytes as reference_exr
from kkbp_maps.extractor import bc6h, images
from kkbp_maps.extractor.textures import Textures

rng = np.random.default_rng(3)


@pytest.mark.parametrize("shape", [(5, 7, 3), (33, 4, 4), (16, 16, 3)])
def test_the_exr_writer_makes_the_test_builders_bytes(shape):
    """bundle_builder's EXRs open in Blender 5.2.2; the Extractor's are byte for byte the same."""
    values = rng.uniform(-2, 30, size=shape).astype(np.float32)
    as_half = values.astype(np.float16).astype(np.float32)
    h, w, c = shape
    assert images.exr_bytes(values) == reference_exr(w, h, c, [float(v) for v in as_half.reshape(-1)])


def test_an_exr_header_passes_the_contract(tmp_path):
    path = tmp_path / "x.exr"
    path.write_bytes(images.exr_bytes(np.ones((3, 9, 3), np.float32)))
    header = headers.exr_header(path)
    assert (header.width, header.height, header.problems) == (9, 3, ())


@pytest.mark.parametrize("channels", [1, 2, 3, 4])
def test_png_files_pass_the_contract_and_hold_the_pixels(tmp_path, channels):
    from PIL import Image

    px = rng.integers(0, 256, size=(6, 5, channels), dtype=np.uint8)
    path = tmp_path / "x.png"
    path.write_bytes(images.png_bytes(px))
    header = headers.png_header(path)
    assert (header.width, header.height, header.problems) == (5, 6, ())
    back = np.asarray(Image.open(path))
    assert np.array_equal(back.reshape(px.shape), px)


def test_hash_bytes_are_the_files_values():
    px = rng.integers(0, 256, size=(2, 3, 3), dtype=np.uint8)
    assert images.hash_bytes(px) == px.tobytes()
    f = np.array([[[1.0, 0.5, 70000.0]]], np.float32)
    assert images.hash_bytes(f) == struct.pack("<3e", 1.0, 0.5, 65504.0)


def test_rgbm_decode():
    """value = 34.493242 · a^2.2 · srgb_to_linear(rgb) (kk-spike, section 3)."""
    px = np.array([[[255, 128, 0, 255], [255, 255, 255, 51]]], np.uint8)
    out = images.rgbm_decode(px, 34.493242, 2.2)
    assert np.allclose(out[0, 0], [34.493242, 34.493242 * 0.2158605, 0.0], rtol=1e-4)
    assert np.allclose(out[0, 1], 34.493242 * 0.2 ** 2.2, rtol=1e-4)


def test_kk_normal_maps_take_x_from_alpha():
    flat = np.array([[[128, 128, 128, 128]]], np.uint8)  # KK's DXT5nm: Y in R, G and B
    assert np.array_equal(images.unpack_normal(flat, True)[0, 0], [128, 128, 255])
    tilted = np.array([[[0, 128, 0, 255]]], np.uint8)
    assert images.unpack_normal(tilted, True)[0, 0, 0] == 255
    assert images.unpack_normal(tilted, False)[0, 0, 0] == 0  # R · A, as later Unity reads it


def test_resize_keeps_the_aspect_and_renormalises_normals():
    px = np.full((64, 32, 3), [128, 128, 255], np.uint8)
    out = images.resize(px, 16, renormalize=True)
    assert out.shape == (16, 8, 3)
    assert np.array_equal(out[4, 4], [128, 128, 255])


def test_textures_are_named_by_their_full_size_pixels(tmp_path):
    px = rng.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    full = Textures(tmp_path / "a", None)
    small = Textures(tmp_path / "b", 16)
    a = full.add(px, name="t", color_space="srgb", limit=True)
    b = small.add(px, name="t", color_space="srgb", limit=True)
    assert a == b == hashing.texture_hash(64, 64, 3, px.tobytes())
    assert (full.records[a]["width"], small.records[b]["width"]) == (64, 16)
    assert headers.png_header(tmp_path / "b" / f"{b}.png").width == 16
    assert small.add(px, name="again", color_space="srgb") == b and len(small.records) == 1


def test_float_textures_are_linear_exrs(tmp_path):
    t = Textures(tmp_path, None)
    tid = t.add(np.ones((2, 2, 3), np.float32) * 3, name="hdr", color_space="srgb")
    assert t.records[tid]["format"] == "exr" and t.records[tid]["color_space"] == "linear"


# --- BC6H ------------------------------------------------------------------------------------

def bc6h_mode11_block(e0, e1, indices):
    """A one-region, untransformed BC6H block (mode 11, 0b00011): 10-bit endpoints, 4-bit indices."""
    bits, pos = 0, 0

    def put(value, n):
        nonlocal bits, pos
        bits |= (value & ((1 << n) - 1)) << pos
        pos += n
    put(0b00011, 5)
    for c in range(3):
        put(e0[c], 10)
    for c in range(3):
        put(e1[c], 10)
    for i, index in enumerate(indices):
        put(index, 3 if i == 0 else 4)
    assert pos == 128
    return bits.to_bytes(16, "little")


def test_bc6h_interpolates_between_its_endpoints():
    block = bc6h_mode11_block((0, 0, 0), (1023, 1023, 1023), [0] + [15] * 15)
    out = bc6h.decode_bc6h(block, 4, 4)
    assert out.shape == (4, 4, 3)
    assert np.allclose(out[0, 0], 0.0)
    assert np.allclose(out[0, 1], 65504.0)  # the top endpoint is the largest finite half


def test_bc6h_keeps_values_above_one():
    # The endpoint 0x3C00 in half bits is 1.0; quantized to 10 bits and back it lands near it.
    q = (0x3C00 * 64 // 31) >> 6
    block = bc6h_mode11_block((q, q, q), (1023, 1023, 1023), [0] * 16)
    out = bc6h.decode_bc6h(block, 4, 4)
    assert np.allclose(out, 1.0, rtol=0.05)


def test_reserved_bc6h_modes_are_black():
    assert not bc6h.decode_bc6h(bytes([0b10011]) + bytes(15), 4, 4).any()
