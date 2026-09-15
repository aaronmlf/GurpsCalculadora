"""Falling rules from GURPS Basic Set Revised, pp. 430-431."""

from typing import Any, Dict

from utils.dice_roller import (
    calculate_collision_damage,
    get_falling_velocity,
    get_range_modifier,
    roll_dice,
)
from calculators.injury import calculate_simple_injury


class FallsCalculator:
    """Calculate impact damage, armor penetration, and falling blunt trauma."""

    def calculate_fall(
        self,
        distance_yards: int,
        target_hp: int,
        surface_type: str = "hard",
        acrobatics_success: bool = False,
        swimming_success: bool = False,
        armor_dr: int = 0,
        elastic_dr: int = 5,
        gravity: float = 1.0,
    ) -> Dict[str, Any]:
        if distance_yards < 0 or target_hp < 1 or armor_dr < 0 or elastic_dr < 0:
            raise ValueError("Distance and DR cannot be negative, and HP must be positive.")
        if surface_type not in {"hard", "soft", "elastic", "water"}:
            raise ValueError(f"Unknown surface type: {surface_type}")

        effective_distance = max(0, distance_yards - 5) if acrobatics_success else distance_yards
        velocity = get_falling_velocity(effective_distance, gravity)
        result: Dict[str, Any] = {
            "distance_yards": effective_distance,
            "original_distance": distance_yards,
            "target_hp": target_hp,
            "surface_type": surface_type,
            "acrobatics_used": acrobatics_success,
            "swimming_used": swimming_success,
            "swimming_modifier": get_range_modifier(velocity) if surface_type == "water" else 0,
            "armor_dr": armor_dr,
            "surface_dr": elastic_dr if surface_type == "elastic" else 0,
            "velocity": velocity,
            "effective_hp": target_hp * 2 if surface_type == "hard" else target_hp,
            "damage_dice": "0d",
            "damage_total": 0,
            "penetrating_damage": 0,
            "blunt_trauma": 0,
            "total_injury": 0,
            "valid": True,
            "outcome": "no_damage",
            "message": "",
        }

        if surface_type == "water" and swimming_success:
            result["outcome"] = "clean_dive"
            result["message"] = "Clean dive: no damage."
            return result
        if velocity == 0:
            result["message"] = "No effective falling distance."
            return result

        _, expression = calculate_collision_damage(result["effective_hp"], velocity)
        basic_damage, _ = roll_dice(expression)
        after_surface = max(0, basic_damage - result["surface_dr"])
        penetrating = max(0, after_surface - armor_dr)

        # For falls all worn armor counts as flexible. Blunt trauma applies
        # only when DR stops the crushing damage completely; it is not added
        # when any damage penetrates.
        blunt_trauma = 0
        if armor_dr > 0 and after_surface > 0 and penetrating == 0:
            blunt_trauma = after_surface // 5

        injury = penetrating if penetrating > 0 else blunt_trauma
        injury_result = calculate_simple_injury(
            after_surface, "cr", target_hp, armor_dr,
            flexible=True, source="Basic Set", page="430-431",
        )
        result.update({
            "damage_dice": expression,
            "damage_total": basic_damage,
            "penetrating_damage": penetrating,
            "blunt_trauma": blunt_trauma,
            "total_injury": injury,
            "injury_result": injury_result.to_dict(),
            "state_delta": injury_result.state_delta.to_dict(),
            "outcome": "injury" if injury else "stopped",
            "message": (
                f"Impact velocity: {velocity} yd/s\n"
                f"Basic damage: {expression} = {basic_damage}\n"
                f"Injury: {injury} HP"
            ),
        })
        return result

    def get_falling_velocity_table(self) -> Dict[int, int]:
        """Return every printed one-yard lookup from 1 through 112 yards."""
        return {distance: get_falling_velocity(distance) for distance in range(1, 113)}

    def calculate_blunt_trauma(
        self, damage_stopped: int, is_flexible_armor: bool = True
    ) -> int:
        if not is_flexible_armor or damage_stopped <= 0:
            return 0
        return damage_stopped // 5
