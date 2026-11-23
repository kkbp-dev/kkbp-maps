"""What the Builder needs to know about each Game that no Map Bundle holds. Never imports bpy.

- **Camera Profiles** (ADR 0010): the game camera's tonemapper, exposure and sun shaft strength, which
  the capture plugin is to read once per Game (Phase 5). Until then they are the assumed defaults: no
  tonemapper, exposure 1, no sun shafts, and marked as assumed so the Build Report says so.
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
    assumed: bool = True


@dataclass(frozen=True)
class GameLight:
    lights_use_linear_intensity: bool


CAMERA_PROFILES: dict[str, dict[str, CameraProfile]] = {
    "KK": {"game": CameraProfile(), "studio": CameraProfile()},
}

LIGHTS: dict[str, GameLight] = {
    "KK": GameLight(lights_use_linear_intensity=False),  # Koikatu_Data/globalgamemanagers, GraphicsSettings
}


def camera_profile(game: str, camera: str) -> CameraProfile:
    return CAMERA_PROFILES[game][camera]


def light_convention(game: str) -> GameLight:
    return LIGHTS[game]
