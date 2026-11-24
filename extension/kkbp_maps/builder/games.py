"""What the Builder needs to know about each Game that no Map Bundle holds. Never imports bpy.

- **Camera Profiles** (ADR 0010): the settings of each game camera that no map file holds, read by the
  capture plugin (tools/capture.py, camera-<profile>.json). `map_fog` and `map_sun_shafts` say whether
  the camera shows the Map's own fog and sun shafts: Studio replaces both with the scene's settings, off
  by default. `grade_lut` names the LUT the camera grades with instead of the Map's: Studio keeps its
  scene filter (Lut_Amount unless the user picks another) whatever the Time of Day. A profile not captured yet is marked assumed, and the Build Report says so.
- **The light convention** of the Game's Unity: with `lights_use_linear_intensity` false (KK's
  GraphicsSettings), a light's colour reaches the shader as linear(colour · intensity).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraProfile:
    tonemapper: str = "none"      # AmplifyColor's: "none", "photographic" or "aces"
    exposure: float = 1.0
    sun_shafts: float = 0.0
    map_fog: bool = True          # the Map's fog is drawn (SunLightInfo's)
    map_sun_shafts: bool = True   # the Map's sun shafts are drawn
    grade_lut: str | None = None  # a LUT, by name, that grades every Map instead of the Map's own
    assumed: bool = True


@dataclass(frozen=True)
class GameLight:
    lights_use_linear_intensity: bool


CAMERA_PROFILES: dict[str, dict[str, CameraProfile]] = {
    "KK": {
        "game": CameraProfile(),
        # CharaStudio 5.6.2f1, captured 2026-11-24: AmplifyColor Tonemapper Disabled, Exposure 1,
        # ApplyDithering false; GlobalFog and SunShafts follow the Studio scene, both off by default;
        # the Grade is the scene's filter, Lut_Amount by default, at every Time of Day (look check: the
        # captures' frames before AmplifyColor through Lut_Amount match the frames after it to ΔE 0.7).
        "studio": CameraProfile(tonemapper="none", exposure=1.0, sun_shafts=0.0, map_fog=False,
                                map_sun_shafts=False, grade_lut="Lut_Amount", assumed=False),
    },
}

LIGHTS: dict[str, GameLight] = {
    "KK": GameLight(lights_use_linear_intensity=False),  # Koikatu_Data/globalgamemanagers, GraphicsSettings
}


def camera_profile(game: str, camera: str) -> CameraProfile:
    return CAMERA_PROFILES[game][camera]


def light_convention(game: str) -> GameLight:
    return LIGHTS[game]
