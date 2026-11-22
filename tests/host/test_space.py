"""The Unity-to-Blender conversion: every kind of value against C, on synthetic values."""

import math

import numpy as np
import pytest

from kkbp_maps.extractor import space
from kkbp_maps.extractor.space import C

rng = np.random.default_rng(7)


def blender_matrix(q):
    """Blender's [w, x, y, z] as a matrix."""
    w, x, y, z = q
    return space.unity_rotation_matrix((x, y, z, w))  # the same formula in any right-handed reading


def random_quaternions(n=20):
    q = rng.normal(size=(n, 4))
    return q / np.linalg.norm(q, axis=1, keepdims=True)


def test_vectors_go_through_c_and_back():
    v = rng.normal(size=(10, 3))
    assert np.allclose(space.vectors(v), v @ C.T)
    assert np.allclose(space.unity_vectors(space.vectors(v)), v)
    assert space.vector({"x": 1.0, "y": 2.0, "z": 3.0}) == [-1.0, -3.0, 2.0]


@pytest.mark.parametrize("q", random_quaternions())
def test_a_rotation_is_conjugated_by_c(q):
    unity = space.unity_rotation_matrix(q)
    assert np.allclose(blender_matrix(space.quaternion(q)), C @ unity @ C.T)


def test_scale_swaps_y_and_z():
    s = (2.0, 3.0, 5.0)
    assert np.allclose(np.diag(space.scale(s)), C @ np.diag(s) @ C.T)


def test_a_whole_transform():
    m = np.eye(4)
    m[:3, :3] = space.unity_rotation_matrix(random_quaternions(1)[0]) @ np.diag([1.0, 2.0, 3.0])
    m[:3, 3] = (4.0, 5.0, 6.0)
    p = np.array([0.3, -0.2, 0.9, 1.0])
    assert np.allclose(space.matrix(m) @ np.append(space.vector(p[:3]), 1.0), np.append(space.vector((m @ p)[:3]), 1))


def test_swapped_winding_keeps_the_face_normal_with_the_geometry():
    a, b, c = rng.normal(size=(3, 3))
    unity_normal = np.cross(b - a, c - a)
    pa, pb, pc = space.vectors(np.array([a, b, c]))[space.triangles(np.array([0, 1, 2]))]
    assert np.allclose(np.cross(pb - pa, pc - pa), C @ unity_normal)


def test_unity_euler_angles_apply_z_then_x_then_y():
    q = space.euler_quaternion((0.0, 90.0, 0.0))
    assert np.allclose(space.unity_rotation_matrix(q) @ [0, 0, 1], [1, 0, 0])  # yaw turns forward to the right
    rz, rx, ry = (space.unity_rotation_matrix(space.euler_quaternion(e)) for e in
                  ((0, 0, 30.0), (40.0, 0, 0), (0, 50.0, 0)))
    assert np.allclose(space.unity_rotation_matrix(space.euler_quaternion((40.0, 50.0, 30.0))), ry @ rx @ rz)


def test_the_1f_day_sun():
    """kk-spike, section 1: Unity direction (0.548, -0.394, 0.738), Blender (-0.548, -0.738, -0.394)."""
    q = space.euler_quaternion((23.2, 36.6, 213.3))
    assert np.allclose(space.unity_rotation_matrix(q) @ [0, 0, 1], [0.548, -0.394, 0.738], atol=2e-3)
    assert np.allclose(space.light_direction(q), [-0.548, -0.738, -0.394], atol=2e-3)


@pytest.mark.parametrize("q", random_quaternions(8))
def test_a_blender_light_shines_along_its_local_minus_z(q):
    r = blender_matrix(space.light_rotation(q))
    assert np.allclose(r @ [0, 0, -1], space.light_direction(q))
    unity = space.unity_rotation_matrix(q)
    for axis in (0, 1):  # an area light's width and height stay along its own X and Y
        assert np.isclose(abs(np.dot(r[:, axis], C @ unity[:, axis])), 1.0)


def test_the_sh_probe_gives_the_same_light_in_both_spaces():
    u = list(rng.normal(size=27))
    b = space.sh9(u)
    for d in rng.normal(size=(12, 3)):
        d /= np.linalg.norm(d)
        assert np.allclose(space.sh_eval(u, d), space.sh_eval(b, C @ d))


def test_equirect_directions_follow_blenders_environment_texture():
    d = space.equirect_directions(8, 4)
    assert np.allclose(d[1, 4], [math.cos(math.pi / 8) * math.cos(-math.pi / 8),
                                 math.cos(math.pi / 8) * math.sin(-math.pi / 8), math.sin(math.pi / 8)])
    assert d[0, 0, 2] > 0.9 and d[3, 0, 2] < -0.9  # the top row looks up


def test_cube_lookup_finds_each_face_at_its_centre():
    axes = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], dtype=float)
    face, col, row = space.cube_lookup(axes)
    assert list(face) == [0, 1, 2, 3, 4, 5]
    assert np.allclose(col, 0.5) and np.allclose(row, 0.5)


def test_cube_faces_meet_at_their_edges():
    """A point on the edge between two faces has the same place on both edges' sides."""
    d = np.array([[1.0, 0.2, 0.9999], [0.9999, 0.2, 1.0]])  # either side of the +X / +Z edge
    face, col, row = space.cube_lookup(d)
    assert list(face) == [0, 4]
    assert np.isclose(col[0], 0.0, atol=1e-3) and np.isclose(col[1], 1.0, atol=1e-3)
    assert np.isclose(row[0], row[1], atol=1e-3)


def test_a_cubemap_becomes_an_equirect_in_blender_axes():
    faces = [np.full((4, 4, 1), float(i)) for i in range(6)]
    eq = space.cubemap_to_equirect(faces, 16)
    assert eq.shape == (8, 16, 1)
    dirs = space.equirect_directions(16, 8)

    def face_at(blender_dir):
        i = np.argmax(dirs.reshape(-1, 3) @ np.asarray(blender_dir, dtype=float))
        return eq.reshape(-1)[i]
    assert face_at([0, 0, 1]) == 2   # Blender up is Unity +Y
    assert face_at([1, 0, 0]) == 1   # Blender +X is Unity -X
    assert face_at([0, 1, 0]) == 5   # Blender +Y is Unity -Z
    assert face_at([0, -1, 0]) == 4  # Blender -Y is Unity +Z


def test_the_skybox_rotation_turns_the_sky():
    faces = [np.full((4, 4, 1), float(i)) for i in range(6)]
    turned = space.cubemap_to_equirect(faces, 16, rotation_deg=90.0)
    plain = space.cubemap_to_equirect(faces, 16)
    # Unity's _Rotation 90 shows what was at Unity +Z (Blender -Y) at Unity +X (Blender -X).
    assert turned[4, 0, 0] == plain[4, 12, 0]
    phi = space.skybox_rotation(90.0)
    assert np.isclose(phi, -90.0)


def test_yaw_of_a_unity_turn_and_of_a_tilt():
    assert np.isclose(space.yaw_degrees((0.0, 0.0, 0.0, 1.0)), 0.0)
    assert np.isclose(space.yaw_degrees(space.euler_quaternion((0, 30.0, 0))), -30.0)
    assert space.yaw_degrees(space.euler_quaternion((10.0, 0, 0))) is None


def test_direction_lightmaps_are_reencoded_exactly():
    rgba = rng.integers(0, 256, size=(4, 4, 4), dtype=np.uint8)
    out = space.direction_lightmap(rgba)
    unity = rgba[:, :, :3].reshape(-1, 3) / 255.0 - 0.5
    blender = out[:, :, :3].reshape(-1, 3) / 255.0 - 0.5
    assert np.allclose(blender, unity @ C.T)
    assert np.array_equal(out[:, :, 3], rgba[:, :, 3])
