"""The bundle's textures: each use of a game texture decoded the way the game samples it, named by its
Content Hash and written once.

A texture's hash comes from its full-size pixels; the optional size limit (D21) scales only what is
written (ADR 0012). The limit applies to material textures and to sky and reflection cubemaps, never
to lightmaps (their charts would bleed into each other), Grade LUTs or thumbnails.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..bundle import hashing
from . import images, space
from .games import Game
from .unity import HDR_FORMATS, Ref, Store

WRAP = {0: "repeat", 1: "clamp", 2: "mirror", 3: "mirror_once"}
FILTER = {0: "point", 1: "bilinear", 2: "trilinear"}
CUBE_EQUIRECT_SCALE = 4  # an equirectangular image is 4 faces wide and 2 high
MAX_EQUIRECT_WIDTH = 4096  # 4 × KK's 1024² sky faces; larger faces gain nothing a world background shows


class Textures:
    """The textures of one bundle, written into its textures/ folder as they are added."""

    def __init__(self, folder: Path, max_size: int | None):
        self.folder = Path(folder)
        self.max_size = max_size
        self.records: dict[str, dict] = {}
        self._by_use: dict[tuple, str] = {}

    def add(self, pixels: np.ndarray, *, name: str, color_space: str, wrap=("repeat", "repeat"),
            filter: str = "bilinear", limit: bool = False, normal: bool = False) -> str:
        """Writes a texture unless the bundle has it, and returns its id. uint8 pixels become a PNG,
        float pixels a linear EXR."""
        a = np.asarray(pixels)
        if a.ndim == 2:
            a = a[:, :, None]
        exr = a.dtype != np.uint8
        if exr:
            a = images.half(images.to_rgb(a) if a.shape[2] < 3 else a).astype(np.float32)
            color_space = "linear"
        h, w, c = a.shape
        tid = hashing.texture_hash(w, h, c, images.hash_bytes(a))
        if tid in self.records:
            return tid
        out = images.resize(a, self.max_size, renormalize=normal) if limit and self.max_size else a
        fmt = "exr" if exr else "png"
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / f"{tid}.{fmt}").write_bytes(images.exr_bytes(out) if exr else images.png_bytes(out))
        self.records[tid] = {"id": tid, "name": name, "format": fmt, "width": int(out.shape[1]),
                             "height": int(out.shape[0]), "color_space": color_space, "wrap": list(wrap),
                             "filter": filter}
        return tid

    def once(self, key: tuple, make) -> str:
        """The id of a use of a game texture, made by `make()` the first time the bundle meets it."""
        tid = self._by_use.get(key)
        if tid is None:
            tid = self._by_use[key] = make()
        return tid

    # --- uses of game textures ----------------------------------------------------------------

    def material(self, store: Store, ref: Ref, game: Game, *, normal: bool) -> str:
        """A material's texture: a normal map unpacked as the game's Unity does, anything else as
        stored, sRGB or linear as the texture says."""
        def make():
            info = store.texture(ref)
            px = store.pixels(ref)
            settings = dict(name=info.name, wrap=(WRAP.get(info.wrap[0], "repeat"), WRAP.get(info.wrap[1], "repeat")),
                            filter=FILTER.get(info.filter, "bilinear"), limit=True)
            if info.format in HDR_FORMATS:
                return self.add(px, color_space="linear", **settings)
            if normal:
                return self.add(images.unpack_normal(_rgba(px), game.normal_x_from_alpha), color_space="linear",
                                normal=True, **settings)
            return self.add(px, color_space="srgb" if info.color_space == 1 else "linear", **settings)
        return self.once(("material", ref, normal), make)

    def lightmap_color(self, store: Store, ref: Ref, game: Game) -> str:
        """A `_comp_light` lightmap decoded from RGBM to linear light, as an EXR."""
        def make():
            info = store.texture(ref)
            px = store.pixels(ref)
            if info.lightmap_format != 2 or info.format in HDR_FORMATS:
                raise NotImplementedError(f"lightmap {info.name} isn't RGBM (format {info.format}, "
                                          f"lightmap format {info.lightmap_format})")
            return self.add(images.rgbm_decode(_rgba(px), *game.rgbm), name=info.name, color_space="linear",
                            wrap=("clamp", "clamp"), filter=FILTER.get(info.filter, "bilinear"))
        return self.once(("lightmap", ref), make)

    def lightmap_direction(self, store: Store, ref: Ref) -> str:
        """A `_comp_dir` lightmap with its directions in Blender's world axes, as a linear PNG."""
        def make():
            info = store.texture(ref)
            return self.add(space.direction_lightmap(_rgba(store.pixels(ref))), name=info.name,
                            color_space="linear", wrap=("clamp", "clamp"), filter=FILTER.get(info.filter, "bilinear"))
        return self.once(("direction", ref), make)

    def cubemap(self, store: Store, ref: Ref) -> str:
        """A Unity cubemap as an equirectangular linear EXR in Blender's world axes."""
        def make():
            info = store.texture(ref)
            faces = [_linear_float(store.pixels(ref, f), info.color_space, info.format) for f in range(6)]
            return self.add(space.cubemap_to_equirect(faces, min(MAX_EQUIRECT_WIDTH, CUBE_EQUIRECT_SCALE * info.width)), name=info.name,
                            color_space="linear", limit=True)
        return self.once(("cubemap", ref), make)

    def six_sided(self, store: Store, refs: dict[str, Ref], name: str) -> str:
        """A 6 Sided skybox's textures as one equirectangular linear EXR."""
        def make():
            faces = {}
            for slot, ref in refs.items():
                info = store.texture(ref)
                faces[slot] = _linear_float(store.pixels(ref), info.color_space, info.format)
            cube = space.six_sided_to_cube(faces["_FrontTex"], faces["_BackTex"], faces["_LeftTex"],
                                           faces["_RightTex"], faces["_UpTex"], faces["_DownTex"])
            width = min(MAX_EQUIRECT_WIDTH, CUBE_EQUIRECT_SCALE * max(f.shape[1] for f in cube))
            return self.add(space.cubemap_to_equirect(cube, width), name=name, color_space="linear", limit=True)
        return self.once(("six_sided", tuple(sorted(refs.items()))), make)

    def lut(self, store: Store, ref: Ref) -> str:
        """A Grade's LUT as stored, a linear RGB PNG."""
        def make():
            info = store.texture(ref)
            px = store.pixels(ref)
            if px.dtype != np.uint8:
                raise NotImplementedError(f"LUT {info.name} is an HDR texture")
            return self.add(images.to_rgb(px), name=info.name, color_space="linear", wrap=("clamp", "clamp"),
                            filter=FILTER.get(info.filter, "bilinear"))
        return self.once(("lut", ref), make)

    def thumbnail(self, pixels: np.ndarray, name: str, color_space: int) -> str:
        return self.add(images.to_rgb(pixels), name=name, color_space="srgb" if color_space == 1 else "linear",
                        wrap=("clamp", "clamp"))


def _rgba(px: np.ndarray) -> np.ndarray:
    """uint8 pixels as RGBA: grey becomes RGB, a missing alpha is 255."""
    if px.shape[2] == 4:
        return px
    rgb = images.to_rgb(px)
    return np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), 255, np.uint8)], axis=2)


def _linear_float(px: np.ndarray, color_space: int, fmt: int) -> np.ndarray:
    """A cube face as linear float RGB: 8-bit sRGB faces are decoded, HDR ones kept."""
    if px.dtype != np.uint8:
        return images.to_rgb(px).astype(np.float32)
    rgb = images.to_rgb(px).astype(np.float32) / 255.0
    return images.srgb_to_linear(rgb) if color_space == 1 else rgb
