"""What the Builder needs to know about each Game that no Map Bundle holds. Never imports bpy.

- **Camera Profiles** (ADR 0010): the settings of each game camera that no map file holds, read by the
  capture plugin (tools/capture.py, camera-<profile>.json). `map_fog` and `map_sun_shafts` say whether
  the camera shows the Map's own fog and sun shafts: Studio replaces both with the scene's settings, off
  by default. `grade_lut` names the LUT the camera grades with instead of the Map's: Studio keeps its
  scene filter (Lut_Amount unless the user picks another) whatever the Time of Day. `height_fog` is the
  camera's own height fog (ADR 0028), drawn where the Map's fog is. A profile not captured yet is marked
  assumed, and the Build Report says so.
- **The light convention** of the Game's Unity: with `lights_use_linear_intensity` false (KK's
  GraphicsSettings), a light's colour reaches the shader as linear(colour · intensity).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HeightFog:
    """Unity's GlobalFog with height fog only (ADR 0028): fog thickening below `top` metres above the
    origin (Unity's Y, Blender's Z, the same number), in the Map Variant's fog colour and through its linear
    fog's start and end, over every surface up to the opaque queue and over a Sky Dome."""
    top: float
    density: float


@dataclass(frozen=True)
class CameraProfile:
    tonemapper: str = "none"      # AmplifyColor's: "none", "photographic" or "aces"
    exposure: float = 1.0
    sun_shafts: float = 0.0
    map_fog: bool = True          # the Map's fog is drawn (SunLightInfo's)
    map_sun_shafts: bool = True   # the Map's sun shafts are drawn
    grade_lut: str | None = None  # a LUT, by name, that grades every Map instead of the Map's own
    height_fog: HeightFog | None = None
    height_fog_from_map: bool = False   # the height fog is on only where a Map Variant switches it on (KKS)
    assumed: bool = True


@dataclass(frozen=True)
class GameLight:
    lights_use_linear_intensity: bool
    # Real-time GI that no file holds (ADR 0025): a renderer that takes it gets this share of the Map's
    # ambient light on top of its lightmap, fitted to the Reference Captures by the look check.
    realtime_gi_ambient: float = 0.0
    # Point and spot lights: Unity's built-in falloff is 1 / (1 + 25 (d/range)^2), Blender's 1/d^2. A
    # Blender light agrees with Unity's at this share of its range, and is cut off at its range.
    point_reference: float = 0.2
    # Unity's spot cookie fades towards the cone's edge; the Blender spot's blend.
    spot_blend: float = 0.5


CAMERA_PROFILES: dict[str, dict[str, CameraProfile]] = {
    "KK": {
        # The story game's ActionCamera (camera/action.unity3d; free roam's camera is a copy of it), captured
        # 2026-11-25: AmplifyColor Tonemapper Disabled, Exposure 1, ApplyDithering false, the Map's own LUT
        # per Time of Day; GlobalFog height fog only (height 1, heightDensity 2), on where the Map's fog is
        # (ActionMap.UpdateCameraFog); SunShafts intensity 2.2, added after the Grade, which draw nothing on
        # Maps with a Sky Dome (kk-spike.md, "Known discrepancies").
        "game": CameraProfile(tonemapper="none", exposure=1.0, sun_shafts=2.2, map_fog=True, map_sun_shafts=True,
                              grade_lut=None, height_fog=HeightFog(top=1.0, density=2.0), assumed=False),
        # CharaStudio 5.6.2f1, captured 2026-11-24: AmplifyColor Tonemapper Disabled, Exposure 1,
        # ApplyDithering false; GlobalFog and SunShafts follow the Studio scene, both off by default;
        # the Grade is the scene's filter, Lut_Amount by default, at every Time of Day (look check: the
        # captures' frames before AmplifyColor through Lut_Amount match the frames after it to ΔE 0.7).
        "studio": CameraProfile(tonemapper="none", exposure=1.0, sun_shafts=0.0, map_fog=False,
                                map_sun_shafts=False, grade_lut="Lut_Amount", assumed=False),
    },    # Not captured yet (the KKS capture plugin, Phase 7): KK's, as a start. The story camera's CameraEffector
    # has GlobalFog, AmplifyColor and SunShafts like KK's (kks-spike.md, section 2); its height fog is
    # on only where a Map Variant switches it on (Map Bundle 0.9), with KK's density until captured.
    "KKS": {
        "game": CameraProfile(tonemapper="none", exposure=1.0, sun_shafts=0.0, map_fog=True, map_sun_shafts=True,
                              grade_lut=None, height_fog=HeightFog(top=0.0, density=2.0),
                              height_fog_from_map=True, assumed=True),
        "studio": CameraProfile(tonemapper="none", exposure=1.0, sun_shafts=0.0, map_fog=False,
                                map_sun_shafts=False, grade_lut="Lut_Amount", assumed=True),
    },
}

LIGHTS: dict[str, GameLight] = {
    # lights_use_linear_intensity: Koikatu_Data/globalgamemanagers, GraphicsSettings. realtime_gi_ambient:
    # fitted on park's captures (kk-spike.md, "Settled by the look check"; 0.25 to 0.75 were tried).
    "KK": GameLight(lights_use_linear_intensity=False, realtime_gi_ambient=0.5),
    # KoikatsuSunshine_Data/globalgamemanagers, GraphicsSettings (kks-spike.md, section 5); the point
    # light reference and spot blend are first guesses, for the look check to fit.
    "KKS": GameLight(lights_use_linear_intensity=False),
}


def camera_profile(game: str, camera: str) -> CameraProfile:
    return CAMERA_PROFILES[game][camera]


def light_convention(game: str) -> GameLight:
    return LIGHTS[game]
