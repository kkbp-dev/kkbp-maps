"""Unity's space to Blender's: the only module that converts axes (ADR 0011).

Unity is left-handed with +Y up; Blender right-handed with +Z up. One matrix does it, KKBP's X mirror
followed by glTF's Y-up to Z-up (kk-spike, section 1):

    C = | -1  0  0 |    Blender point = C · Unity point, and the same for directions
        |  0  0 -1 |    Blender matrix = C · Unity matrix · Cᵀ
        |  0  1  0 |    det C = -1, so each triangle (a, b, c) becomes (a, c, b)

Quaternions are Blender's [w, x, y, z]. Everything that is a position, a direction, a rotation, a
scale, a light, an SH probe, a cubemap or a directional lightmap goes through here.
"""

from __future__ import annotations

import math

import numpy as np

C = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])


# --- points, directions, transforms -------------------------------------------------------

def vector(v) -> list[float]:
    """A Unity position or direction, as (x, y, z) or {'x', 'y', 'z'}, in Blender's axes."""
    x, y, z = _xyz(v)
    return [-x, -z, y]


def vectors(a: np.ndarray) -> np.ndarray:
    """Many Unity positions or directions (n × 3) in Blender's axes."""
    a = np.asarray(a)
    return np.stack([-a[:, 0], -a[:, 2], a[:, 1]], axis=1)


def unity_vectors(a: np.ndarray) -> np.ndarray:
    """Blender directions (n × 3) back in Unity's axes: Cᵀ, for looking things up in Unity data."""
    a = np.asarray(a)
    return np.stack([-a[:, 0], a[:, 2], -a[:, 1]], axis=1)


def quaternion(q) -> list[float]:
    """A Unity rotation, as (x, y, z, w) or {'x', 'y', 'z', 'w'}, as Blender's [w, x, y, z].

    C · R · Cᵀ turns the rotation axis by -C (an axis is a pseudovector and det C = -1) and keeps the
    angle: (x, y, z) becomes (x, z, -y).
    """
    if isinstance(q, dict):
        x, y, z, w = q["x"], q["y"], q["z"], q["w"]
    else:
        x, y, z, w = q
    return [w, x, z, -y]


def scale(s) -> list[float]:
    """A Unity local scale in Blender's axes: C · diag(s) · Cᵀ = diag(sx, sz, sy)."""
    x, y, z = _xyz(s)
    return [x, z, y]


def matrix(m: np.ndarray) -> np.ndarray:
    """A Unity 3 × 3 or 4 × 4 matrix in Blender's axes."""
    m = np.asarray(m, dtype=float)
    if m.shape == (3, 3):
        return C @ m @ C.T
    out = np.eye(4)
    out[:3, :3] = C @ m[:3, :3] @ C.T
    out[:3, 3] = C @ m[:3, 3]
    return out


def triangles(indices: np.ndarray) -> np.ndarray:
    """A flat triangle index list with each triangle's last two corners swapped (det C = -1)."""
    t = np.asarray(indices).reshape(-1, 3)
    return t[:, [0, 2, 1]].reshape(-1)


def euler_quaternion(e) -> tuple[float, float, float, float]:
    """Unity's Transform.eulerAngles in degrees as a Unity quaternion (x, y, z, w): Z, then X, then Y."""
    x, y, z = (math.radians(a) for a in _xyz(e))
    qx = (math.sin(x / 2), 0.0, 0.0, math.cos(x / 2))
    qy = (0.0, math.sin(y / 2), 0.0, math.cos(y / 2))
    qz = (0.0, 0.0, math.sin(z / 2), math.cos(z / 2))
    return _qmul(_qmul(qy, qx), qz)


def unity_rotation_matrix(q) -> np.ndarray:
    """A Unity quaternion (x, y, z, w) or dict as a 3 × 3 matrix in Unity's axes."""
    if isinstance(q, dict):
        q = (q["x"], q["y"], q["z"], q["w"])
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


# --- lights --------------------------------------------------------------------------------

# Rx(-90°): turns Blender's local -Z onto the Blender image of Unity's local +Z, which C maps to -Y.
_LIGHT_TURN = (math.sqrt(0.5), -math.sqrt(0.5), 0.0, 0.0)


def light_rotation(q) -> list[float]:
    """A Unity light's world rotation as a Blender light's [w, x, y, z].

    A Unity light shines along its local +Z, a Blender light along its local -Z. The light's own X and
    Y (an area light's width and height) stay its X and Y, up to sign.
    """
    w, x, y, z = quaternion(q)
    tw, tx, ty, tz = _LIGHT_TURN
    rx, ry, rz, rw = _qmul((x, y, z, w), (tx, ty, tz, tw))
    return [rw, rx, ry, rz]


def light_direction(q) -> list[float]:
    """The Blender world direction a Unity light with world rotation `q` shines along."""
    return list(C @ unity_rotation_matrix(q) @ np.array([0.0, 0.0, 1.0]))


# --- the SH probe ----------------------------------------------------------------------------

def sh9(coefficients) -> list[float]:
    """An L2 SH probe of 27 floats (9 per colour channel, Unity's SphericalHarmonicsL2 order) with its
    basis functions taken in Blender's axes.

    Unity's stored coefficients already hold the normalisation, so the probe's value is
    sh0 + sh1·y + sh2·z + sh3·x + sh4·xy + sh5·yz + sh6·(3z² - 1) + sh7·xz + sh8·(x² - y²) (UnityCG's
    SHEval). With Unity's (x, y, z) = (-x', z', -y'), each band maps linearly onto Blender's (x', y', z');
    in band 2, 3y'² - 1 and x'² - z'² are combinations of 3z'² - 1 and x'² - y'².
    """
    out = []
    for c in range(3):
        u = [float(v) for v in coefficients[9 * c:9 * c + 9]]
        out += [u[0], -u[2], u[1], -u[3], u[7], -u[5], -0.5 * u[6] - 0.5 * u[8], -u[4], -1.5 * u[6] + 0.5 * u[8]]
    return out


def sh_eval(coefficients, direction) -> list[float]:
    """The value of a 27-float probe in a direction, in the probe's own axes (for tests and checks)."""
    x, y, z = direction
    basis = [1.0, y, z, x, x * y, y * z, 3 * z * z - 1, x * z, x * x - y * y]
    return [sum(b * coefficients[9 * c + i] for i, b in enumerate(basis)) for c in range(3)]


# --- cubemaps and directional lightmaps --------------------------------------------------------

def equirect_directions(width: int, height: int, rows: range | None = None) -> np.ndarray:
    """The Blender world direction of each texel centre of an equirectangular image (height × width ×
    3), rows top first, as Blender's Environment Texture maps it: u = 0.5 - atan2(y, x) / 2π, and
    v = 0.5 + elevation / π with v = 1 at the top row. Measured in Blender 5.2.2 by rendering a UV
    image through a world: +X at u 0.5, +Y at u 0.25, -Y at u 0.75."""
    u = (np.arange(width) + 0.5) / width
    v = 1.0 - (np.asarray(rows if rows is not None else range(height)) + 0.5) / height
    azimuth = (0.5 - u) * 2 * math.pi
    elevation = (v - 0.5) * math.pi
    az, el = np.meshgrid(azimuth, elevation)
    return np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=2)


# Unity's cube faces in order +X, -X, +Y, -Y, +Z, -Z, each as (major axis, sign, the Unity axis and
# sign along the face's columns, and along its rows from the top): Direct3D's convention, which Unity's
# left-handed space shares.
CUBE_FACES = (
    (0, 1, (2, -1), (1, -1)),
    (0, -1, (2, 1), (1, -1)),
    (1, 1, (0, 1), (2, 1)),
    (1, -1, (0, 1), (2, -1)),
    (2, 1, (0, 1), (1, -1)),
    (2, -1, (0, -1), (1, -1)),
)


def cube_lookup(directions: np.ndarray):
    """For Unity directions (n × 3): each one's face index and its (column, row) in 0…1 on that face,
    rows counted from the top."""
    d = np.asarray(directions, dtype=float)
    major = np.argmax(np.abs(d), axis=1)
    sign = np.take_along_axis(d, major[:, None], axis=1)[:, 0] >= 0
    face = major * 2 + (~sign).astype(int)
    col = np.empty(len(d))
    row = np.empty(len(d))
    for f, (axis, s, (ca, cs), (ra, rs)) in enumerate(CUBE_FACES):
        m = face == f
        ma = np.abs(d[m, axis])
        col[m] = (cs * d[m, ca] / ma + 1) / 2
        row[m] = (rs * d[m, ra] / ma + 1) / 2
    return face, col, row


EQUIRECT_ROWS_PER_PASS = 128


def cubemap_to_equirect(faces: list[np.ndarray], width: int, rotation_deg: float = 0.0) -> np.ndarray:
    """A Unity cubemap's six faces (each H × W × C, rows top first, in face order) as an equirectangular
    image in Blender's world axes, width × width/2, bilinear. `rotation_deg` turns the sky about
    Unity's +Y as Unity's skybox shaders do with _Rotation; the Extractor writes skies at 0."""
    height = width // 2
    channels = faces[0].shape[2]
    out = np.empty((height, width, channels), dtype=np.float32)
    turn = _rot_y(-rotation_deg).T if rotation_deg else None
    for y0 in range(0, height, EQUIRECT_ROWS_PER_PASS):  # in bands, to keep memory low
        y1 = min(height, y0 + EQUIRECT_ROWS_PER_PASS)
        u = unity_vectors(equirect_directions(width, height, range(y0, y1)).reshape(-1, 3))
        if turn is not None:
            u = u @ turn
        face, col, row = cube_lookup(u)
        band = np.empty((len(u), channels), dtype=np.float32)
        for f in range(6):
            m = face == f
            band[m] = _bilinear(faces[f], col[m], row[m])
        out[y0:y1] = band.reshape(y1 - y0, width, channels)
    return out


def six_sided_to_cube(front, back, left, right, up, down) -> list[np.ndarray]:
    """Unity's 6 Sided skybox textures (Front +Z, Back -Z, Left +X, Right -X, Up +Y, Down -Y, rows top
    first) as cube faces in CUBE_FACES order and orientation."""
    return [left, right, up, down, front, back]


def direction_lightmap(rgba: np.ndarray) -> np.ndarray:
    """A Unity `_comp_dir` lightmap (uint8, H × W × 4) re-encoded in Blender's world axes.

    RGB holds 0.5 + 0.5 · d for a Unity world direction d. C only permutes and negates axes, and
    negating about 0.5 on 8-bit values is 255 - v, so this is exact: R' = 255 - R, G' = 255 - B, B' = G.
    A, the directionality weight, is kept."""
    out = rgba.copy()
    out[:, :, 0] = 255 - rgba[:, :, 0]
    out[:, :, 1] = 255 - rgba[:, :, 2]
    out[:, :, 2] = rgba[:, :, 1]
    return out


def yaw_degrees(q) -> float | None:
    """The angle in degrees about Blender's +Z of a Unity rotation that turns only about Unity's +Y,
    or None if it also tilts. Right-handed about Blender's +Z."""
    m = matrix(unity_rotation_matrix(q))
    if abs(m[2, 2] - 1) > 1e-4:
        return None
    return math.degrees(math.atan2(m[1, 0], m[0, 0]))


def skybox_rotation(degrees: float) -> float:
    """Unity's skybox _Rotation (degrees about Unity's +Y) as degrees about Blender's +Z."""
    return yaw_degrees(_quat_y(degrees))


# --- helpers -----------------------------------------------------------------------------------

def _xyz(v):
    if isinstance(v, dict):
        return v["x"], v["y"], v["z"]
    return tuple(v)


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _quat_y(degrees: float):
    a = math.radians(degrees) / 2
    return (0.0, math.sin(a), 0.0, math.cos(a))


def _rot_y(degrees: float) -> np.ndarray:
    return unity_rotation_matrix(_quat_y(degrees))


def _bilinear(img: np.ndarray, col: np.ndarray, row: np.ndarray) -> np.ndarray:
    """Samples an image (H × W × C) at (column, row) in 0…1 with texel centres at (i + 0.5) / size,
    clamped at the edges."""
    h, w = img.shape[:2]
    x = np.clip(col * w - 0.5, 0, w - 1)
    y = np.clip(row * h - 0.5, 0, h - 1)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    f = np.asarray(img, dtype=np.float32)
    top =f[y0, x0] * (1 - fx) + f[y0, x1] * fx
    bottom = f[y1, x0] * (1 - fx) + f[y1, x1] * fx
    return top * (1 - fy) + bottom * fy
