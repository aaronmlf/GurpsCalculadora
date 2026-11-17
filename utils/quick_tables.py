"""Pure Basic Set Revised quick lookups (yards and yards/second).

Illumination is for seeing the target, not detecting the light source itself.
The caller picks a representative ambient level and at most one point source;
the model does not infer lighting, shadow, line of sight or traits from a map.
"""

from dataclasses import dataclass
import math
from typing import Literal

from utils.dice_roller import ceil_range_distance, get_range_band, get_range_modifier


@dataclass(frozen=True, slots=True)
class IlluminationPreset:
    key: str
    kind: Literal['ambient', 'point']
    modifier: int
    cloud_sensitive: bool = False
    high_latitude_sensitive: bool = False


# Basic Set Revised p. 574. Keys are stable translation identifiers, not prose.
ILLUMINATION_PRESETS = (
    IlluminationPreset('total_darkness', 'ambient', -10),
    IlluminationPreset('overcast_moonless', 'ambient', -9),
    IlluminationPreset('clouded_starlight', 'ambient', -8),
    IlluminationPreset('starlight', 'ambient', -7),
    IlluminationPreset('quarter_moon', 'ambient', -6, True, True),
    IlluminationPreset('half_moon', 'ambient', -5, True, True),
    IlluminationPreset('full_moon', 'ambient', -4, True, True),
    IlluminationPreset('deep_twilight', 'ambient', -3, True),
    IlluminationPreset('twilight', 'ambient', -2, True),
    IlluminationPreset('side_street_lights', 'ambient', -2),
    IlluminationPreset('sunrise_sunset', 'ambient', -1),
    IlluminationPreset('main_street_lights', 'ambient', -1),
    IlluminationPreset('daylight', 'ambient', 0),
    IlluminationPreset('interior_light', 'ambient', 0),
    IlluminationPreset('indicator_led', 'point', -5),
    IlluminationPreset('candle', 'point', -3),
    IlluminationPreset('nightlight', 'point', -3),
    IlluminationPreset('gaslight', 'point', -2),
    IlluminationPreset('phone_screen', 'point', -2),
    IlluminationPreset('torch', 'point', -1),
    IlluminationPreset('flashlight', 'point', -1),
    IlluminationPreset('reading_light', 'point', 0),
    IlluminationPreset('quality_flashlight', 'point', 0),
)
_PRESETS = {preset.key: preset for preset in ILLUMINATION_PRESETS}


@dataclass(frozen=True, slots=True)
class IlluminationResult:
    modifier: int
    ambient_modifier: int
    cloud_modifier: int
    polar_modifier: int
    point_modifier: int | None
    point_distance_modifier: int
    chosen_modifier: int
    flicker_modifier: int
    adaptation_modifier: int
    adaptation_required_minutes: int
    point_used: bool
    total_darkness: bool
    page: int = 574


@dataclass(frozen=True, slots=True)
class SpeedRangeResult:
    modifier: int
    distance_yards: float
    speed_yps: float
    speed_adjustment: float
    effective_yards: float
    lookup_yards: int
    band_limit_yards: int
    mode: Literal['attack', 'sense']
    consider_speed: bool
    page: int


def _nonnegative_number(value: float) -> float:
    if type(value) not in (int, float):
        raise ValueError('quick_tables_invalid_number')
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError('quick_tables_invalid_number') from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError('quick_tables_invalid_number')
    return number


def _preset(key: str, kind: Literal['ambient', 'point']) -> IlluminationPreset:
    preset = _PRESETS.get(key) if isinstance(key, str) else None
    if preset is None or preset.kind != kind:
        raise ValueError('quick_tables_invalid_option')
    return preset


def calculate_illumination(ambient_key: str, point_key: str | None = None, point_distance_yards: float = 1.0,
                           *, heavy_cloud: bool = False, polar_moonlight: bool = False,
                           flicker: int = 0, sudden_dimming_steps: int = 0,
                           adaptation_elapsed_minutes: float = 0.0) -> IlluminationResult:
    """Evaluate revised p. 574 for the light falling on a target.

    Point-source distance is source to target, not observer to target. Clouds
    apply only to the clear-sky presets and polar dimming only to moonlight.
    Flicker is the chosen penalty magnitude for the useful illumination
    (including moving shadows). Dimming steps are the sudden drop experienced
    by a human observer, not inferred from the new light level. This lookup
    neither grants Vision-only plain-sight bonuses nor simulates vision traits.
    """
    ambient = _preset(ambient_key, 'ambient')
    point = _preset(point_key, 'point') if point_key is not None else None
    if (type(heavy_cloud) is not bool or type(polar_moonlight) is not bool
            or type(flicker) is not int or not 0 <= flicker <= 3
            or type(sudden_dimming_steps) is not int or not 0 <= sudden_dimming_steps <= 10):
        raise ValueError('quick_tables_invalid_option')
    distance = _nonnegative_number(point_distance_yards)
    elapsed = _nonnegative_number(adaptation_elapsed_minutes)

    cloud_modifier = -1 if heavy_cloud and ambient.cloud_sensitive else 0
    polar_modifier = -1 if polar_moonlight and ambient.high_latitude_sensitive else 0
    local_ambient = ambient.modifier + cloud_modifier + polar_modifier

    point_distance_modifier = 0
    point_modifier = None
    if point is not None:
        lookup = ceil_range_distance(distance)
        if lookup > 1:
            point_distance_modifier = -1 + get_range_modifier(lookup) // 2
        point_modifier = point.modifier + point_distance_modifier

    point_used = point_modifier is not None and point_modifier > local_ambient
    chosen = point_modifier if point_used else local_ambient
    adaptation_required_minutes = 2 * sudden_dimming_steps
    adaptation_modifier = -2 if elapsed < adaptation_required_minutes else 0
    return IlluminationResult(
        modifier=max(-10, chosen - flicker + adaptation_modifier),
        ambient_modifier=ambient.modifier, cloud_modifier=cloud_modifier, polar_modifier=polar_modifier,
        point_modifier=point_modifier, point_distance_modifier=point_distance_modifier, chosen_modifier=chosen,
        flicker_modifier=-flicker, adaptation_modifier=adaptation_modifier,
        adaptation_required_minutes=adaptation_required_minutes, point_used=point_used,
        total_darkness=chosen == -10,
    )


def calculate_speed_range(distance_yards: float, speed_yps: float = 0.0, *,
                          mode: Literal['attack', 'sense'] = 'attack',
                          consider_speed: bool = False) -> SpeedRangeResult:
    """Look up range plus speed for attacks, or range minus speed for senses.

    Selecting speed is explicit: ordinary foot combat often ignores it (p.
    550). Sense/sensor rolls can benefit from target motion (p. 551), with
    effective range clamped at zero. Size Modifier is not part of this lookup.
    """
    if mode not in ('attack', 'sense') or type(consider_speed) is not bool:
        raise ValueError('quick_tables_invalid_option')
    distance = _nonnegative_number(distance_yards)
    speed = _nonnegative_number(speed_yps)
    adjustment = (speed if mode == 'attack' else -speed) if consider_speed else 0.0
    effective = _nonnegative_number(max(0.0, distance + adjustment))
    lookup = ceil_range_distance(effective)
    modifier, band_limit = get_range_band(lookup)
    return SpeedRangeResult(
        modifier=modifier, distance_yards=distance, speed_yps=speed, speed_adjustment=adjustment,
        effective_yards=effective, lookup_yards=lookup, band_limit_yards=band_limit,
        mode=mode, consider_speed=consider_speed, page=550 if mode == 'attack' else 551,
    )
