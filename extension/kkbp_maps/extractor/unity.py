"""The only module that talks to UnityPy: it opens a Scene Bundle and hands out plain data.

Everything else in the Extractor works on a Store: objects named by `Ref` (file name, path id), their
typetrees as dicts, and decoded meshes and pixels as numpy arrays. Tests give the logic a synthetic
Store instead, so they need neither UnityPy nor a game.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

Ref = tuple[str, int]
# The files Unity's built-in objects live in, by the name a reference ends in (ADR 0031).
BUILTIN_NAMES = {"unity default resources", "unity_builtin_extra"}


@dataclass
class MeshData:
    """A Unity mesh in Unity's space: float32 arrays (n × 3 or n × 2, None where absent) and the
    triangle indices of each submesh as int arrays, already offset to the vertex buffer."""
    name: str
    positions: np.ndarray | None
    normals: np.ndarray | None
    uv0: np.ndarray | None
    uv1: np.ndarray | None
    submeshes: list[np.ndarray]
    readable: bool = True


@dataclass
class TextureData:
    """A Texture2D's settings, and its pixels decoded on demand."""
    name: str
    width: int
    height: int
    format: int
    color_space: int          # m_ColorSpace: 1 sRGB, 0 linear
    lightmap_format: int      # m_LightmapFormat: 2 RGBM, 0 none
    filter: int
    wrap: tuple[int, int]
    faces: int = 1            # 6 for a cubemap


# Unity's texture formats by number, as far as the Extractor needs them.
ALPHA8, ARGB4444, RGB24, RGBA32, ARGB32, RGB565, R16, DXT1, DXT5, RGBA4444, BGRA32 = 1, 2, 3, 4, 5, 7, 9, 10, 12, 13, 14
RHALF, RGHALF, RGBAHALF, RFLOAT, RGFLOAT, RGBAFLOAT = 15, 16, 17, 18, 19, 20
BC6H, BC7, BC4, BC5, R8 = 24, 25, 26, 27, 63
HDR_FORMATS = {RHALF, RGHALF, RGBAHALF, RFLOAT, RGFLOAT, RGBAFLOAT, BC6H}
NO_ALPHA_FORMATS = {RGB24, RGB565, DXT1, BC6H, BC4, BC5, R16, R8, RHALF, RGHALF, RFLOAT, RGFLOAT}
GREY_FORMATS = {ALPHA8, R16, R8, BC4, RHALF, RFLOAT}


class Store:
    """What the Extractor reads from a Scene Bundle. UnityStore reads a real one."""

    def refs(self, type_name: str) -> list[Ref]: ...
    def type_of(self, ref: Ref) -> str | None: ...
    def tree(self, ref: Ref) -> dict: ...
    def resolve(self, owner: Ref, pptr: dict) -> Ref | None: ...
    def is_loaded(self, ref: Ref) -> bool: ...
    def script(self, ref: Ref) -> str | None: ...
    def is_builtin(self, ref: Ref) -> bool: ...
    def mesh(self, ref: Ref) -> MeshData: ...
    def texture(self, ref: Ref) -> TextureData: ...
    def pixels(self, ref: Ref, face: int = 0) -> np.ndarray: ...


def unitypy():
    """UnityPy, imported. Its export module imports fmod_toolkit, which only AudioClips use and which
    the extension doesn't ship (ADR 0029): where it isn't installed, an empty module stands in."""
    import importlib.util
    import sys

    try:
        present = "fmod_toolkit" in sys.modules or importlib.util.find_spec("fmod_toolkit") is not None
    except (ImportError, ValueError):
        present = False
    if not present:
        import types

        stub = types.ModuleType("fmod_toolkit", "Stands in for fmod_toolkit, which kkbp-maps doesn't ship (ADR 0029).")

        def missing(name):
            raise AttributeError(f"fmod_toolkit.{name}: audio isn't read, and FMOD isn't shipped (ADR 0029)")

        stub.__getattr__ = missing
        sys.modules["fmod_toolkit"] = stub
    import UnityPy

    return UnityPy


class UnityStore(Store):
    def __init__(self, path: Path, builtin: tuple[Path, ...] = (), cabs: dict[str, Path] | None = None):
        """A Scene Bundle and the bundles its files name. `builtin` are the player's own resource files
        (Game.builtin_resources, ADR 0031): their objects resolve and read like the bundle's, but
        refs() never lists them, so nothing starts a walk from one. `cabs` maps the serialized files of
        the Game's shared bundles to their bundles (bundles.cab_index): every one the Scene Bundle's
        files name, and those they name in turn, is loaded too, and listed in `dependencies`. Bundles
        are read a block at a time (bundles.py), so a shared bundle costs what a Map reads of it."""
        UnityPy = unitypy()  # here, so the rest of the Extractor imports without it

        self.path = Path(path)
        self.env = UnityPy.Environment()
        self._blocks = []
        self._mine = set(self._load_bundle(self.path))
        self.dependencies: list[Path] = []
        cabs = cabs or {}
        while True:
            present = {sf.name.lower() for sf in _serialized_files(self.env)}
            wanted = sorted({cabs[e] for sf in _serialized_files(self.env) for e in _external_names(sf)
                             if e not in present and e in cabs} - set(self.dependencies) - {self.path})
            if not wanted:
                break
            for bundle in wanted:
                self.dependencies.append(bundle)
                self._load_bundle(bundle)
        self._objects: dict[Ref, object] = {}
        self._files: dict[str, object] = {}
        for sf in _serialized_files(self.env):
            self._files[sf.name.lower()] = sf
            for pid, obj in sf.objects.items():
                self._objects[(sf.name, pid)] = obj
        self._by_type: dict[str, list[Ref]] = {}
        for ref, obj in self._objects.items():
            if ref[0] in self._mine:   # only the Scene Bundle's own objects start a walk
                self._by_type.setdefault(obj.type.name, []).append(ref)
        self._builtin_names = {Path(p).name.lower() for p in builtin}
        self._builtin_envs = []
        for p in builtin:
            env = UnityPy.load(str(p))
            self._builtin_envs.append(env)
            for sf in _serialized_files(env):
                name = Path(p).name   # the name an external reference ends in
                self._files[name.lower()] = sf
                for pid, obj in sf.objects.items():
                    self._objects[(name, pid)] = obj
        self._trees: dict[Ref, dict] = {}

    def _load_bundle(self, path: Path) -> list[str]:
        """Parses each file of a bundle into the environment as UnityPy's BundleFile would, but over a
        lazy stream; returns the serialized files' names."""
        from UnityPy.files import SerializedFile
        from UnityPy.helpers import ImportHelper
        from UnityPy.streams import EndianBinaryReader

        from .bundles import Blocks

        blocks = Blocks(path)
        self._blocks.append(blocks)
        names = []
        for name, offset, size in blocks.nodes:
            f = ImportHelper.parse_file(EndianBinaryReader(blocks.stream(offset, size)), self.env, name)
            self.env.register_cab(name, f)
            self.env.files[name] = f
            if isinstance(f, SerializedFile):
                names.append(f.name)
        return names

    def close(self):
        self._trees.clear()
        self._objects.clear()
        self.env = None
        self._builtin_envs = []
        for b in self._blocks:
            b.close()
        self._blocks = []

    def refs(self, type_name):
        return list(self._by_type.get(type_name, ()))

    def type_of(self, ref):
        obj = self._objects.get(ref)
        return obj.type.name if obj is not None else None

    def is_loaded(self, ref):
        return ref in self._objects

    def tree(self, ref):
        t = self._trees.get(ref)
        if t is None:
            t = self._trees[ref] = self._objects[ref].read_typetree()
        return t

    def forget(self, ref):
        """Drops a cached typetree (textures and meshes hold large byte strings)."""
        self._trees.pop(ref, None)

    def resolve(self, owner, pptr):
        if not pptr or not pptr.get("m_PathID"):
            return None
        fid, pid = pptr["m_FileID"], pptr["m_PathID"]
        if fid == 0:
            return (owner[0], pid)
        sf = self._objects[owner].assets_file
        external = sf.externals[fid - 1].path.replace("\\", "/").rsplit("/", 1)[-1]
        target = self._files.get(external.lower())
        if target is not None and external.lower() in self._builtin_names:
            return (external, pid)
        return (target.name if target is not None else external, pid)

    def is_builtin(self, ref):
        """Whether `ref` is in Unity's own resources rather than the game's bundles, loaded or not."""
        return ref is not None and ref[0].lower() in BUILTIN_NAMES

    def script(self, ref):
        t = self.tree(ref)
        s = self.resolve(ref, t.get("m_Script"))
        if s is None or not self.is_loaded(s):
            return None
        return self.tree(s).get("m_ClassName")

    def mesh(self, ref):
        from UnityPy.helpers.MeshHelper import MeshHandler

        obj = self._objects[ref].read()
        name = obj.m_Name
        if not getattr(obj, "m_IsReadable", True) or not obj.m_VertexData.m_VertexCount:
            return MeshData(name, None, None, None, None, [], readable=False)
        h = MeshHandler(obj)
        h.process()

        def arr(values, width):
            if not values:
                return None
            a = np.asarray(values, dtype=np.float32)
            if a.ndim == 1:
                a = a.reshape(-1, width)
            return np.ascontiguousarray(a[:, :width])  # normals can come as 4 floats, the 4th 0

        submeshes = [np.asarray(tris, dtype=np.int64).reshape(-1) for tris in h.get_triangles()]
        return MeshData(name, arr(h.m_Vertices, 3), arr(h.m_Normals, 3), arr(h.m_UV0, 2), arr(h.m_UV1, 2), submeshes)

    def texture(self, ref):
        t = self.tree(ref)
        settings = t.get("m_TextureSettings", {})
        wrap_u = settings.get("m_WrapU", settings.get("m_WrapMode", 0))
        wrap_v = settings.get("m_WrapV", settings.get("m_WrapMode", 0))
        return TextureData(
            name=t.get("m_Name", ""), width=t["m_Width"], height=t["m_Height"], format=t["m_TextureFormat"],
            color_space=t.get("m_ColorSpace", 1), lightmap_format=t.get("m_LightmapFormat", 0),
            filter=settings.get("m_FilterMode", 1), wrap=(wrap_u, wrap_v),
            faces=6 if self.type_of(ref) == "Cubemap" else 1)

    def pixels(self, ref, face=0):
        """The full-size image (mip 0) of a texture or one cubemap face, rows top first: uint8 H × W × C
        for LDR formats and float32 for HDR ones, with C = 1, 3 or 4 by the format."""
        from UnityPy.export import Texture2DConverter

        info = self.texture(ref)
        obj = self._objects[ref].read()
        data = obj.get_image_data()
        per_face = len(data) // info.faces
        data = data[face * per_face:(face + 1) * per_face]
        sf = self._objects[ref].assets_file
        self.forget(ref)
        # A Texture2D is stored bottom row first; a cubemap's faces are stored top row first (measured
        # on KK's sky and reflection cubemaps: flipped, their faces don't meet at the edges).
        flip = info.faces == 1
        if info.format == BC6H:
            from .bc6h import decode_bc6h
            px = decode_bc6h(data, info.width, info.height)
            return np.ascontiguousarray(px[::-1] if flip else px)
        if info.format in (RHALF, RGHALF, RGBAHALF, RFLOAT, RGFLOAT, RGBAFLOAT):
            return _float_pixels(data, info, flip)
        img = Texture2DConverter.parse_image_data(data, info.width, info.height, info.format, sf.version,
                                                  sf.target_platform, None, flip=flip)
        a = np.asarray(img.convert("RGBA"))
        if info.format in GREY_FORMATS:
            return np.ascontiguousarray(a[:, :, 3:4] if info.format == ALPHA8 else a[:, :, 0:1])
        if info.format in NO_ALPHA_FORMATS:
            return np.ascontiguousarray(a[:, :, :3])
        return np.ascontiguousarray(a)


def _float_pixels(data: bytes, info: TextureData, flip: bool) -> np.ndarray:
    channels = {RHALF: 1, RGHALF: 2, RGBAHALF: 4, RFLOAT: 1, RGFLOAT: 2, RGBAFLOAT: 4}[info.format]
    dtype = np.float16 if info.format in (RHALF, RGHALF, RGBAHALF) else np.float32
    n = info.width * info.height * channels
    a = np.frombuffer(data, dtype=dtype, count=n).astype(np.float32).reshape(info.height, info.width, channels)
    if channels == 2:
        a = np.concatenate([a, np.zeros_like(a[:, :, :1])], axis=2)
    return np.ascontiguousarray(a[::-1] if flip else a)


def _external_names(sf) -> list[str]:
    """The lower-cased file names a serialized file's external references point into."""
    return [e.path.replace("\\", "/").rsplit("/", 1)[-1].lower() for e in sf.externals]


def _serialized_files(env) -> Iterator:
    """Every SerializedFile in an Environment, however deeply its bundles nest them."""
    from UnityPy.files import SerializedFile

    stack = list(env.files.values())
    while stack:
        f = stack.pop()
        if isinstance(f, SerializedFile):
            yield f
        elif hasattr(f, "files"):
            stack.extend(f.files.values())


def list_records(path: Path) -> list[tuple[str, dict]]:
    """(name, typetree) of every MonoBehaviour in a small list bundle."""
    UnityPy = unitypy()

    env = UnityPy.load(str(path))
    out = []
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            t = obj.read_typetree()
            out.append((t.get("m_Name", ""), t))
    return out


def sprite_textures(path: Path, names: set[str]) -> dict[str, tuple[np.ndarray, int]]:
    """The pixels (RGB, rows top first) and m_ColorSpace of the named sprites of a thumbnail bundle,
    each cut to its rectangle in its texture."""
    UnityPy = unitypy()

    env = UnityPy.load(str(path))
    out = {}
    for obj in env.objects:
        if obj.type.name != "Sprite":
            continue
        sprite = obj.read()
        if sprite.m_Name not in names:
            continue
        tex = sprite.m_RD.texture.read()
        img = np.asarray(tex.image.convert("RGB"))
        r = sprite.m_RD.textureRect
        h = img.shape[0]
        x0, y0 = int(round(r.x)), int(round(r.y))
        x1, y1 = x0 + int(round(r.width)), y0 + int(round(r.height))
        out[sprite.m_Name] = (np.ascontiguousarray(img[h - y1:h - y0, x0:x1]), getattr(tex, "m_ColorSpace", 1))
    return out
