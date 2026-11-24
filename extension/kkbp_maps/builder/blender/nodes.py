"""A small helper for writing node graphs as code, after KKBP's library-from-code (its nodes.py).

    g = Graph(tree)
    tex = g.node("ShaderNodeTexImage", image=img, interpolation="Linear", Vector=uv)
    mul = g.math("MULTIPLY", (tex, "Alpha"), 2.0)
    g.link(mul, (out, "Strength"))

- A socket is a node (its first output), a (node, name-or-identifier) pair, or a bpy socket.
- Keyword arguments of `node` are node properties when the node has one of that name, and inputs
  otherwise: a value sets the input's default, a socket links it. Properties that decide which sockets
  a node has (`data_type`, `operation`, ...) are set first.
- Inputs and outputs are looked up by identifier first, then by name: ordinary nodes repeat names
  (`ShaderNodeMix`'s `A_Color`, `A_Float`), group nodes have only names.
"""

from __future__ import annotations

import bpy

FIRST = ("node_tree", "data_type", "domain", "operation", "blend_type", "mode", "space", "target",
         "attribute_type", "interpolation", "projection", "extension")


def _find(sockets, key):
    if isinstance(key, int):
        return sockets[key]
    for s in sockets:
        if s.identifier == key:
            return s
    for s in sockets:
        if s.name == key and s.enabled:
            return s
    for s in sockets:
        if s.name == key:
            return s
    raise KeyError(f"no socket {key!r}; there are {[s.identifier for s in sockets]}")


class Graph:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self._x = 0

    def output_of(self, source):
        if isinstance(source, bpy.types.NodeSocket):
            return source
        if isinstance(source, tuple):
            node, key = source
            return _find(node.outputs, key)
        return next(s for s in source.outputs if s.enabled)

    def input_of(self, node, key):
        return _find(node.inputs, key)

    def link(self, source, target):
        """`target` is (node, input) or a bpy input socket."""
        if isinstance(target, tuple):
            target = self.input_of(*target)
        self.tree.links.new(self.output_of(source), target)

    def set(self, node, key, value):
        """An input: a socket links it, anything else is its default value."""
        socket = self.input_of(node, key)
        if isinstance(value, (bpy.types.Node, bpy.types.NodeSocket, tuple)) and not _is_vector(value):
            self.link(value, socket)
        else:
            if socket.type == "RGBA" and isinstance(value, (list, tuple)) and len(value) == 3:
                value = (*value, 1.0)
            socket.default_value = value

    def node(self, idname, name=None, label=None, **kwargs):
        n = self.nodes.new(idname)
        if name:
            n.name = name
        if label:
            n.label = label
        n.location = (self._x, 0)
        self._x += 20
        props = {k: v for k, v in kwargs.items() if k in n.bl_rna.properties and k not in ("location",)}
        props.update({k: kwargs[k] for k in FIRST if k in kwargs and k in n.bl_rna.properties})
        for k in sorted(props, key=lambda k: FIRST.index(k) if k in FIRST else len(FIRST)):
            setattr(n, k, props[k])
        for k, v in kwargs.items():
            if k not in props and v is not None:
                self.set(n, k, v)
        return n

    # --- shorthands ------------------------------------------------------------------------

    def math(self, operation, a, b=None, c=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=operation, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            if v is not None:
                self.set(n, i, v)
        return n

    def vmath(self, operation, a, b=None, c=None, scale=None):
        n = self.node("ShaderNodeVectorMath", operation=operation)
        for key, v in (("Vector", a), ("Vector_001", b), ("Vector_002", c), ("Scale", scale)):
            if v is not None:
                self.set(n, key, v)
        out = "Value" if operation in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"
        return (n, out)

    def mix(self, factor, a, b, data_type="RGBA", blend_type="MIX", clamp_factor=True):
        n = self.node("ShaderNodeMix", data_type=data_type, blend_type=blend_type, clamp_factor=clamp_factor)
        suffix = {"RGBA": "Color", "FLOAT": "Float", "VECTOR": "Vector"}[data_type]
        self.set(n, "Factor_Float", factor)
        self.set(n, f"A_{suffix}", a)
        self.set(n, f"B_{suffix}", b)
        return (n, f"Result_{suffix}")

    def group(self, tree, **inputs):
        n = self.node("ShaderNodeGroup", node_tree=tree)
        for k, v in inputs.items():
            if v is not None:
                self.set(n, k, v)
        return n

    def value(self, v):
        n = self.node("ShaderNodeValue")
        n.outputs[0].default_value = v
        return n

    def rgb(self, color):
        n = self.node("ShaderNodeRGB")
        n.outputs[0].default_value = (*color[:3], 1.0)
        return n

    def vector(self, v):
        return self.node("ShaderNodeCombineXYZ", X=float(v[0]), Y=float(v[1]), Z=float(v[2]))

    def combine(self, r, g, b):
        return self.node("ShaderNodeCombineColor", Red=r, Green=g, Blue=b)


def _is_vector(value):
    return isinstance(value, tuple) and all(isinstance(x, (int, float)) for x in value)


def new_group(name: str, inputs=(), outputs=()) -> bpy.types.ShaderNodeTree:
    """A shader node group with its interface: (name, socket type, default) triples."""
    tree = bpy.data.node_groups.new(name, "ShaderNodeTree")
    for socket_name, socket_type, *default in inputs:
        s = tree.interface.new_socket(socket_name, in_out="INPUT", socket_type=socket_type)
        if default:
            s.default_value = default[0]
    for socket_name, socket_type in outputs:
        tree.interface.new_socket(socket_name, in_out="OUTPUT", socket_type=socket_type)
    return tree


def io(tree):
    """A group's input and output nodes, and its Graph."""
    g = Graph(tree)
    return g, g.node("NodeGroupInput"), g.node("NodeGroupOutput")
