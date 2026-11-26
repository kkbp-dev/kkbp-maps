"""Meshes from the bundle's raw buffers (ADR 0011): already in Blender's space and winding, so nothing is
converted. One Blender mesh per bundle mesh in each file, shared by every object that draws it.

Vertices aren't merged, so UV seams stay as the game has them; the bundle's normals become custom
normals; each submesh is a material index, with one slot per submesh that objects fill (link OBJECT)."""

from __future__ import annotations

import bpy
import numpy as np

from .materials import PROP_HASH, UV0, UV1

UV_NAMES = {"uv0": UV0, "uv1": UV1}
# The other channels (Map Bundle 0.10) become point attributes of their own name: the vertex colour, and
# SpeedTree's data (for its wind). Four floats are kept as a FLOAT_COLOR, the _zw halves as FLOAT2.
EXTRA = {"color0": ("FLOAT_COLOR", 4), "uv0_zw": ("FLOAT2", 2), "uv1_zw": ("FLOAT2", 2),
         "uv2": ("FLOAT_COLOR", 4), "uv3": ("FLOAT_COLOR", 4)}


class Meshes:
    def __init__(self, bundle):
        self.bundle = bundle
        self.made: dict[str, bpy.types.Mesh] = {}
        self.dropped_triangles = 0

    def get(self, mesh_id: str) -> bpy.types.Mesh:
        me = self.made.get(mesh_id)
        if me is None:
            me = self.made[mesh_id] = self._build(mesh_id)
        return me

    def _build(self, mesh_id: str) -> bpy.types.Mesh:
        record = self.bundle.meshes[mesh_id]
        buf = self.bundle.mesh_buffers(mesh_id)
        n = buf.vertices
        positions = np.frombuffer(buf.attributes["position"], dtype=np.float32)
        normals = np.frombuffer(buf.attributes["normal"], dtype=np.float32).reshape(n, 3)
        corners, material_index = [], []
        for i, sub in enumerate(buf.submeshes):
            tri = np.frombuffer(sub, dtype=np.uint32).astype(np.int32).reshape(-1, 3)
            # A triangle with a repeated corner draws nothing and isn't a face Blender can hold.
            keep = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
            self.dropped_triangles += int((~keep).sum())
            corners.append(tri[keep])
            material_index.append(np.full(int(keep.sum()), i, dtype=np.int32))
        tris = np.concatenate(corners) if corners else np.zeros((0, 3), np.int32)
        loops = tris.ravel()

        me = bpy.data.meshes.new(record["name"] or mesh_id)
        me.vertices.add(n)
        me.vertices.foreach_set("co", positions)
        me.loops.add(len(loops))
        me.loops.foreach_set("vertex_index", loops)
        me.polygons.add(len(tris))
        me.polygons.foreach_set("loop_start", np.arange(0, len(loops), 3, dtype=np.int32))
        me.polygons.foreach_set("material_index", np.concatenate(material_index) if material_index else
                                np.zeros(0, np.int32))
        me.update(calc_edges=True)
        for attr, name in UV_NAMES.items():
            if attr in buf.attributes:
                uv = np.frombuffer(buf.attributes[attr], dtype=np.float32).reshape(n, 2)
                layer = me.uv_layers.new(name=name)
                layer.uv.foreach_set("vector", uv[loops].ravel())
        if me.uv_layers:
            me.uv_layers.active = me.uv_layers[UV0] if UV0 in me.uv_layers else me.uv_layers[0]
        for attr, (kind, width) in EXTRA.items():
            if attr in buf.attributes:
                values = np.frombuffer(buf.attributes[attr], dtype=np.float32).reshape(n, width)
                a = me.attributes.new(attr, kind, "POINT")
                a.data.foreach_set("color" if kind == "FLOAT_COLOR" else "vector", values.ravel())
        me.shade_smooth()
        me.normals_split_custom_set_from_vertices(normals)
        for _ in buf.submeshes:
            me.materials.append(None)
        me[PROP_HASH] = mesh_id
        return me
