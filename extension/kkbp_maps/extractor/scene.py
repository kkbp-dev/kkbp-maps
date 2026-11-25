"""A Scene Bundle's scene graph as the game shows it: which objects are active at each Time of Day,
which renderers are Helpers, and the nodes that are left.

Visibility follows what the game does when a Map loads: the serialized active flags, then every
VisibleChange's Start (its show list on, its hide list off), then SunLightInfo.Set for the Time of Day
(the chosen info's visibleList on, the others' off, in the infos' order). An object active at no Time
of Day is left out with everything under it; one active at some is kept and hidden in the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..bundle.hashing import shortest32
from . import space
from .games import Game
from .unity import Ref, Store

NO_LIGHTMAP = 65534          # a lightmap index at or above this means none
SHADOW_MODES = {0: "off", 1: "on", 2: "two_sided", 3: "shadows_only"}   # m_CastShadows
RENDERERS = ("MeshRenderer", "SkinnedMeshRenderer", "ParticleSystemRenderer", "SpriteRenderer",
             "LineRenderer", "TrailRenderer", "BillboardRenderer")


class Unsupported(NotImplementedError):
    """A Map holds something the Extractor doesn't handle yet; it stops rather than write it wrong."""


@dataclass
class Obj:
    """A GameObject with its Transform."""
    go: Ref
    tf: Ref
    name: str
    self_active: bool
    parent: "Obj | None" = None
    children: list["Obj"] = field(default_factory=list)
    components: dict[str, list[Ref]] = field(default_factory=dict)

    def component(self, type_name: str) -> Ref | None:
        refs = self.components.get(type_name)
        return refs[0] if refs else None


@dataclass
class Renderer:
    ref: Ref
    mesh: Ref
    materials: list[Ref | None]
    shadows: str                # SHADOW_MODES
    receive_shadows: bool
    lightmap_index: int
    lightmap_scale_offset: tuple[float, float, float, float]
    realtime_gi: bool


@dataclass
class Graph:
    store: Store
    game: Game
    objects: dict[Ref, Obj]           # by GameObject
    by_transform: dict[Ref, Obj]
    roots: list[Obj]
    behaviours: dict[str, list[Ref]]  # MonoBehaviours by script class name
    active: dict[str, dict[Ref, bool]] = field(default_factory=dict)  # per Time of Day: self-active

    def world_active(self, obj: Obj, tod: str) -> bool:
        flags = self.active[tod]
        while obj is not None:
            if not flags.get(obj.go, obj.self_active):
                return False
            obj = obj.parent
        return True

    def world_rotation(self, obj: Obj):
        """The Unity world rotation (x, y, z, w) of an object."""
        q = (0.0, 0.0, 0.0, 1.0)
        chain = []
        while obj is not None:
            chain.append(obj)
            obj = obj.parent
        for o in reversed(chain):
            r = self.store.tree(o.tf)["m_LocalRotation"]
            q = space._qmul(q, (r["x"], r["y"], r["z"], r["w"]))
        return q

    def world_matrix(self, obj: Obj) -> np.ndarray:
        """The Unity world matrix (4 × 4) of an object."""
        m = np.eye(4)
        chain = []
        while obj is not None:
            chain.append(obj)
            obj = obj.parent
        for o in reversed(chain):
            t = self.store.tree(o.tf)
            local = np.eye(4)
            p, s = t["m_LocalPosition"], t["m_LocalScale"]
            local[:3, :3] = space.unity_rotation_matrix(t["m_LocalRotation"]) @ np.diag([s["x"], s["y"], s["z"]])
            local[:3, 3] = (p["x"], p["y"], p["z"])
            m = m @ local
        return m

    def obj_of(self, component: Ref) -> Obj | None:
        t = self.store.tree(component)
        go = self.store.resolve(component, t.get("m_GameObject"))
        return self.objects.get(go)


def read_graph(store: Store, game: Game) -> Graph:
    objects: dict[Ref, Obj] = {}
    by_transform: dict[Ref, Obj] = {}
    for tf in store.refs("Transform") + store.refs("RectTransform"):
        t = store.tree(tf)
        go = store.resolve(tf, t["m_GameObject"])
        g = store.tree(go)
        obj = Obj(go=go, tf=tf, name=g.get("m_Name", ""), self_active=bool(g.get("m_IsActive", True)))
        for c in g.get("m_Component", []):
            ref = store.resolve(go, c["component"])
            if ref is not None and store.is_loaded(ref):
                obj.components.setdefault(store.type_of(ref), []).append(ref)
        objects[go] = obj
        by_transform[tf] = obj
    roots = []
    for tf, obj in sorted(by_transform.items(), key=lambda kv: kv[0][1]):
        t = store.tree(tf)
        father = store.resolve(tf, t.get("m_Father"))
        if father is None:
            roots.append(obj)
            continue
        obj.parent = by_transform[father]
    for tf, obj in by_transform.items():
        t = store.tree(tf)
        obj.children = [by_transform[c] for c in (store.resolve(tf, p) for p in t.get("m_Children", []))
                        if c in by_transform]
    behaviours: dict[str, list[Ref]] = {}
    for mb in store.refs("MonoBehaviour"):
        name = store.script(mb)
        if name:
            behaviours.setdefault(name, []).append(mb)
    graph = Graph(store, game, objects, by_transform, roots, behaviours)
    _simulate_visibility(graph)
    return graph


# --- visibility -----------------------------------------------------------------------------

def sun_infos(graph: Graph) -> tuple[Ref | None, list[dict]]:
    """The SunLightInfo component and its infos, or (None, []) for a Map without one."""
    refs = graph.behaviours.get("SunLightInfo", [])
    if len(refs) > 1:
        raise Unsupported(f"{len(refs)} SunLightInfo components")
    if not refs:
        return None, []
    return refs[0], graph.store.tree(refs[0]).get("_infos", [])


def _simulate_visibility(graph: Graph):
    store = graph.store
    start: dict[Ref, bool] = {}
    for mb in graph.behaviours.get("VisibleChange", []):
        t = store.tree(mb)
        owner = graph.obj_of(mb)
        if not t.get("m_Enabled", 1) or owner is None or not _active_with(graph, owner, start):
            continue  # Start never runs
        for p in t.get("_visibleList", []):
            go = store.resolve(mb, p)
            if go in graph.objects:
                start[go] = True
        for p in t.get("_unVisibleList", []):
            go = store.resolve(mb, p)
            if go in graph.objects:
                start[go] = False
    ref, infos = sun_infos(graph)
    for tod in graph.game.times_of_day:
        flags = dict(start)
        chosen = next((i for i in infos if graph.game.sun_types.get(i.get("type")) == tod), None)
        if infos and chosen is None:
            raise Unsupported(f"SunLightInfo has no info for {tod}")
        for info in infos:
            for p in info.get("visibleList", []):
                go = store.resolve(ref, p)
                if go in graph.objects:
                    flags[go] = info is chosen
        graph.active[tod] = flags


def _active_with(graph: Graph, obj: Obj, flags: dict[Ref, bool]) -> bool:
    while obj is not None:
        if not flags.get(obj.go, obj.self_active):
            return False
        obj = obj.parent
    return True


# --- renderers and Helpers ----------------------------------------------------------------------

@dataclass
class Census:
    """What the walk met that the bundle can't carry, by skip reason."""
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, reason: str, n: int = 1):
        self.counts[reason] = self.counts.get(reason, 0) + n


def mesh_renderer(graph: Graph, obj: Obj) -> Renderer | None:
    """The object's MeshRenderer as the game draws it, or None for none or a Helper: a disabled
    renderer, or one without a mesh or without any material (1F's navigation meshes). A shadows-only
    caster is kept: it shapes the Map's light (ADR 0024)."""
    store = graph.store
    ref = obj.component("MeshRenderer")
    mf = obj.component("MeshFilter")
    if ref is None or mf is None:
        return None
    r = store.tree(ref)
    if not r.get("m_Enabled", True):
        return None
    mesh = store.resolve(mf, store.tree(mf).get("m_Mesh"))
    if mesh is None:
        return None
    if r.get("m_StaticBatchInfo", {}).get("subMeshCount", 0):
        raise Unsupported(f"{obj.name} is statically batched")
    materials = [store.resolve(ref, m) for m in r.get("m_Materials", [])]
    materials = [m if m is not None and store.is_loaded(m) else None for m in materials]
    if not any(materials):
        return None
    st = r.get("m_LightmapTilingOffset", {"x": 1.0, "y": 1.0, "z": 0.0, "w": 0.0})
    return Renderer(
        ref=ref, mesh=mesh, materials=materials,
        shadows=SHADOW_MODES.get(r.get("m_CastShadows", 1), "on"), receive_shadows=bool(r.get("m_ReceiveShadows", 1)),
        lightmap_index=r.get("m_LightmapIndex", 0xFFFF),
        lightmap_scale_offset=(st["x"], st["y"], st["z"], st["w"]),
        realtime_gi=r.get("m_LightmapIndexDynamic", 0xFFFF) < NO_LIGHTMAP)


def shader_name(store: Store, material: Ref | None) -> str | None:
    if material is None or not store.is_loaded(material):
        return None
    shader = store.resolve(material, store.tree(material).get("m_Shader"))
    if shader is None or not store.is_loaded(shader):
        return None
    return store.tree(shader).get("m_ParsedForm", {}).get("m_Name") or store.tree(shader).get("m_Name")


def is_sky_dome(graph: Graph, r: Renderer) -> bool:
    """A Sky Dome: a built-in mesh (from Unity's own resources, not the bundle) drawn with a skybox shader."""
    if graph.store.is_loaded(r.mesh):
        return False
    names = [shader_name(graph.store, m) for m in r.materials if m is not None]
    return bool(names) and all(n and n.startswith(graph.game.sky_shader_prefix) for n in names)


# --- the walk -----------------------------------------------------------------------------------

@dataclass
class Node:
    obj: Obj
    parent: int | None
    renderer: Renderer | None = None
    sky: bool = False
    dome: bool = False


@dataclass
class Walk:
    nodes: list[Node]
    census: Census
    hidden: dict[str, list[int]]       # per Time of Day: node ids hidden with everything under them
    domes: list[int]                   # node ids of Sky Domes


def walk(graph: Graph, mesh_readable) -> Walk:
    """The nodes to keep, in walk order (each parent before its children), with Helpers left out.

    `mesh_readable(ref)` says whether a mesh has vertex data the bundle can carry."""
    census = Census()
    tods = graph.game.times_of_day
    skipped_types = dict(graph.game.skipped_renderers)
    kept: list[Node] = []

    def visit(obj: Obj, parent_index: int | None, in_sky: bool) -> bool:
        shown = [t for t in tods if graph.world_active(obj, t)]
        if not shown:
            return False
        renderer = None
        dome = False
        for type_name in RENDERERS:
            if type_name == "MeshRenderer" or type_name not in obj.components:
                continue
            enabled = graph.store.tree(obj.components[type_name][0]).get("m_Enabled", True)
            if type_name in graph.game.helper_renderers or not enabled:
                continue
            if type_name in skipped_types:
                census.add(skipped_types[type_name])
                continue
            raise Unsupported(f"{obj.name} has a {type_name}")
        r = mesh_renderer(graph, obj)
        if r is not None:
            if is_sky_dome(graph, r):
                dome = True
            elif not graph.store.is_loaded(r.mesh):
                pass  # any other built-in mesh is a Helper
            elif not mesh_readable(r.mesh):
                census.add("unreadable_mesh")
            else:
                renderer = r
        sky = in_sky or dome
        index = len(kept)
        node = Node(obj, parent_index, renderer, sky, dome)
        kept.append(node)
        keep = renderer is not None or dome
        for child in obj.children:
            keep |= visit(child, index, sky)
        if not keep:
            del kept[index:]  # an empty subtree: nothing in it is drawn
            return False
        if renderer is not None and renderer.realtime_gi:
            census.add("realtime_gi")
        return True

    for root in graph.roots:
        visit(root, None, False)
    # An Animator or Animation moves what is under it in the game; the bundle keeps the serialized pose.
    animating = sum(1 for n in kept if "Animator" in n.obj.components or "Animation" in n.obj.components)
    if animating:
        census.add("animated", animating)

    hidden: dict[str, list[int]] = {}
    for tod in tods:
        flags = graph.active[tod]
        hidden[tod] = sorted(i for i, n in enumerate(kept) if not flags.get(n.obj.go, n.obj.self_active))
    domes = [i for i, n in enumerate(kept) if n.dome]
    return Walk(kept, census, hidden, domes)


def node_records(walk_: Walk, graph: Graph, mesh_id, draws_of) -> list[dict]:
    """scene.json's nodes. `mesh_id(ref)` gives a mesh's Content Hash; `draws_of(node)` its draws."""
    out = []
    for i, n in enumerate(walk_.nodes):
        t = graph.store.tree(n.obj.tf)
        rec = {
            "id": i, "name": n.obj.name, "parent": n.parent,
            "translation": floats(space.vector(t["m_LocalPosition"])),
            "rotation": floats(space.quaternion(t["m_LocalRotation"])),
            "scale": floats(space.scale(t["m_LocalScale"])),
        }
        if n.renderer is not None:
            r = n.renderer
            rec["renderer"] = {"mesh": mesh_id(r.mesh), "draws": draws_of(n), "shadows": r.shadows,
                               "receive_shadows": r.receive_shadows, "realtime_gi": r.realtime_gi}
        if n.sky:
            rec["sky"] = True
        out.append(rec)
    return out


def floats(values) -> list[float]:
    return [shortest32(float(v) + 0.0) for v in values]
