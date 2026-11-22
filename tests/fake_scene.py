"""A synthetic Scene Bundle for the Extractor's host tests: a Store built from Python values.

    s = FakeScene()
    root = s.object("Map")
    desk = s.object("p_desk", parent=root, position=(1, 0, 0))
    s.mesh_renderer(desk, s.mesh("desk"), [s.material("wood")])
    store = s.store()

Objects, components and assets live in one file, "scene"; a reference with another file id points at
Unity's built-in resources, which the bundle doesn't hold. Standard library and numpy only.
"""

from __future__ import annotations

import numpy as np

from kkbp_maps.extractor.unity import DXT5, RGB24, RGBA32, MeshData, Store, TextureData

FILE = "scene"


def ptr(pid):
    return {"m_FileID": 0, "m_PathID": pid or 0}


def builtin(pid):
    return {"m_FileID": 2, "m_PathID": pid}


NULL = {"m_FileID": 0, "m_PathID": 0}

STANDARD_PROPS = [("_Color", 0), ("_MainTex", 4), ("_BumpMap", 4), ("_Glossiness", 3), ("_Mode", 2),
                  ("_SrcBlend", 2), ("_DstBlend", 2), ("_Cull", 2)]
SKYBOX_PROPS = [("_Tint", 0), ("_Exposure", 3), ("_Rotation", 3), ("_Tex", 4)]


class FakeScene:
    def __init__(self):
        self.objects: dict[int, tuple[str, dict]] = {}
        self.meshes: dict[int, MeshData] = {}
        self.textures: dict[int, tuple[TextureData, list[np.ndarray]]] = {}
        self.next_id = 1
        self.shaders: dict[str, int] = {}

    def add(self, type_name: str, tree: dict) -> int:
        pid = self.next_id
        self.next_id += 1
        self.objects[pid] = (type_name, tree)
        return pid

    # --- the graph ----------------------------------------------------------------------

    def object(self, name, parent=None, *, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0, 1.0),
               scale=(1.0, 1.0, 1.0), active=True) -> int:
        """A GameObject with its Transform; returns the GameObject's id."""
        go = self.add("GameObject", {"m_Name": name, "m_IsActive": active, "m_Component": []})
        tf = self.add("Transform", {
            "m_GameObject": ptr(go), "m_LocalPosition": dict(zip("xyz", position)),
            "m_LocalRotation": dict(zip("xyzw", rotation)), "m_LocalScale": dict(zip("xyz", scale)),
            "m_Children": [], "m_Father": ptr(self.transform(parent)) if parent else NULL})
        self.objects[go][1]["m_Component"].append({"component": ptr(tf)})
        if parent:
            self.objects[self.transform(parent)][1]["m_Children"].append(ptr(tf))
        return go

    def transform(self, go: int) -> int:
        return next(c["component"]["m_PathID"] for c in self.objects[go][1]["m_Component"]
                    if self.objects[c["component"]["m_PathID"]][0] == "Transform")

    def component(self, go: int, type_name: str, tree: dict) -> int:
        cid = self.add(type_name, {"m_GameObject": ptr(go), **tree})
        self.objects[go][1]["m_Component"].append({"component": ptr(cid)})
        return cid

    def behaviour(self, go: int, script: str, tree: dict) -> int:
        sid = self.add("MonoScript", {"m_ClassName": script})
        return self.component(go, "MonoBehaviour", {"m_Enabled": 1, "m_Script": ptr(sid), **tree})

    def mesh_renderer(self, go, mesh_ref, materials, *, enabled=True, cast=1, lightmap=0xFFFF,
                      scale_offset=(1.0, 1.0, 0.0, 0.0), dynamic=0xFFFF):
        """`mesh_ref` is a mesh id, or builtin(pid) for a Unity built-in mesh."""
        self.component(go, "MeshFilter", {"m_Mesh": mesh_ref if isinstance(mesh_ref, dict) else ptr(mesh_ref)})
        return self.component(go, "MeshRenderer", {
            "m_Enabled": enabled, "m_CastShadows": cast, "m_ReceiveShadows": 1,
            "m_LightmapIndex": lightmap, "m_LightmapIndexDynamic": dynamic,
            "m_LightmapTilingOffset": dict(zip("xyzw", scale_offset)),
            "m_Materials": [ptr(m) for m in materials], "m_StaticBatchInfo": {"firstSubMesh": 0, "subMeshCount": 0}})

    # --- assets ----------------------------------------------------------------------------

    def shader(self, name, props, *, queue=None, cull=2, blend=(1, 0)):
        if name in self.shaders:
            return self.shaders[name]
        tags = [("RenderType", "Opaque")] + ([("QUEUE", queue)] if queue else [])
        state = {"rtBlend0": {"srcBlend": {"val": float(blend[0]), "name": "_SrcBlend"},
                              "destBlend": {"val": float(blend[1]), "name": "_DstBlend"}},
                 "culling": {"val": float(cull), "name": "<noninit>"}, "m_Tags": {"tags": [("LIGHTMODE", "FORWARDBASE")]}}
        pid = self.add("Shader", {"m_Name": "", "m_ParsedForm": {
            "m_Name": name, "m_PropInfo": {"m_Props": [{"m_Name": n, "m_Type": t} for n, t in props]},
            "m_SubShaders": [{"m_Tags": {"tags": tags}, "m_Passes": [{"m_State": state}]}]}})
        self.shaders[name] = pid
        return pid

    def material(self, name, *, shader="Standard", props=STANDARD_PROPS, textures=None, colors=None,
                 floats=None, queue=-1, keywords="", shader_queue=None, cull=2, blend=(1, 0)):
        sh = self.shader(shader, props, queue=shader_queue, cull=cull, blend=blend)
        texenvs = [[k, {"m_Texture": ptr(v), "m_Scale": {"x": 1.0, "y": 1.0}, "m_Offset": {"x": 0.0, "y": 0.0}}]
                   for k, v in (textures or {}).items()]
        cols = {"_Color": (1.0, 1.0, 1.0, 1.0), "_Stale": (0.5, 0.5, 0.5, 1.0), **(colors or {})}
        fl = {"_Glossiness": 0.5, "_Mode": 0.0, "_SrcBlend": 1.0, "_DstBlend": 0.0, "_OldShaderValue": 3.0, **(floats or {})}
        return self.add("Material", {
            "m_Name": name, "m_Shader": ptr(sh), "m_ShaderKeywords": keywords, "m_CustomRenderQueue": queue,
            "m_SavedProperties": {"m_TexEnvs": texenvs,
                                  "m_Floats": [[k, v] for k, v in fl.items()],
                                  "m_Colors": [[k, dict(zip("rgba", v))] for k, v in cols.items()]}})

    def mesh(self, name, *, uv1=True, submeshes=1, offset=(0.0, 0.0, 0.0)) -> int:
        quad = np.array([[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]], np.float32) + np.array(offset, np.float32)
        normals = np.tile(np.array([[0, 1, 0]], np.float32), (4, 1))
        uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)
        subs = [np.array([0, 1, 2, 0, 2, 3])] * submeshes
        pid = self.add("Mesh", {"m_Name": name})
        self.meshes[pid] = MeshData(name, quad, normals, uv, uv.copy() if uv1 else None, subs)
        return pid

    def texture(self, name, pixels, *, fmt=RGBA32, color_space=1, lightmap_format=0, cube=False) -> int:
        faces = pixels if cube else [pixels]
        h, w = faces[0].shape[:2]
        pid = self.add("Cubemap" if cube else "Texture2D", {"m_Name": name})
        self.textures[pid] = (TextureData(name, w, h, fmt, color_space, lightmap_format, 1, (0, 0),
                                          6 if cube else 1), [np.asarray(f) for f in faces])
        return pid

    def store(self) -> Store:
        return FakeStore(self)


class FakeStore(Store):
    def __init__(self, scene: FakeScene):
        self.scene = scene

    def refs(self, type_name):
        return [(FILE, pid) for pid, (t, _) in self.scene.objects.items() if t == type_name]

    def type_of(self, ref):
        o = self.scene.objects.get(ref[1]) if ref[0] == FILE else None
        return o[0] if o else None

    def is_loaded(self, ref):
        return ref[0] == FILE and ref[1] in self.scene.objects

    def tree(self, ref):
        return self.scene.objects[ref[1]][1]

    def resolve(self, owner, pptr):
        if not pptr or not pptr.get("m_PathID"):
            return None
        return (FILE, pptr["m_PathID"]) if pptr["m_FileID"] == 0 else ("unity default resources", pptr["m_PathID"])

    def script(self, ref):
        s = self.resolve(ref, self.tree(ref).get("m_Script"))
        return self.tree(s)["m_ClassName"] if s else None

    def mesh(self, ref):
        return self.scene.meshes[ref[1]]

    def texture(self, ref):
        return self.scene.textures[ref[1]][0]

    def pixels(self, ref, face=0):
        return self.scene.textures[ref[1]][1][face]


def solid(h, w, values, dtype=np.uint8):
    return np.tile(np.asarray(values, dtype=dtype), (h, w, 1))


__all__ = ["FakeScene", "FakeStore", "ptr", "builtin", "NULL", "solid", "DXT5", "RGB24", "RGBA32"]
