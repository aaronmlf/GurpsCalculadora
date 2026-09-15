"""Slam rules from GURPS Basic Set, Fourth Edition Revised, p. 371."""

from typing import Any, Dict

from utils.dice_roller import (
    calculate_collision_damage,
    evaluate_success_roll,
    roll_dice,
)
from calculators.injury import calculate_simple_injury


class SlamCalculator:
    """Resolve slam damage and the resulting knockdown checks."""

    def calculate_slam(
        self,
        attacker_hp: int,
        attacker_velocity: int,
        defender_hp: int,
        defender_velocity: int,
        collision_type: str = "head_on",
        attacker_skill_bonus: int = 0,
        defender_skill_bonus: int = 0,
    ) -> Dict[str, Any]:
        """Roll the mutual crushing damage caused by a successful slam.

        ``attacker_skill_bonus`` represents the attacker's Brawling, Sumo
        Wrestling, or All-Out Attack (Strong) damage bonus. The defender does
        not add such a bonus; ``defender_skill_bonus`` is retained only for API
        compatibility and is deliberately ignored.
        """
        if attacker_hp < 1 or defender_hp < 1:
            raise ValueError("HP must be at least 1.")
        if attacker_velocity < 0 or defender_velocity < 0:
            raise ValueError("Velocity cannot be negative.")

        collision_velocity = self._calculate_collision_velocity(
            attacker_velocity, defender_velocity, collision_type
        )
        result: Dict[str, Any] = {
            "collision_type": collision_type,
            "attacker_hp": attacker_hp,
            "attacker_velocity": attacker_velocity,
            "defender_hp": defender_hp,
            "defender_velocity": defender_velocity,
            "collision_velocity": collision_velocity,
            "attacker_damage_dice": "0d",
            "defender_damage_dice": "0d",
            "attacker_damage_total": 0,
            "defender_damage_total": 0,
            "attacker_roll": 0,
            "defender_roll": 0,
            "attacker_fall": False,
            "defender_fall": False,
            "attacker_dx_roll_required": False,
            "defender_dx_roll_required": False,
            "outcome": "no_collision",
            "result_text": "",
            "valid": collision_velocity > 0,
            "message": "",
        }
        if collision_velocity <= 0:
            result["message"] = "No collision: relative velocity is zero."
            return result

        _, attacker_expression = calculate_collision_damage(attacker_hp, collision_velocity)
        _, defender_expression = calculate_collision_damage(defender_hp, collision_velocity)
        attacker_roll, _ = roll_dice(attacker_expression)
        defender_roll, _ = roll_dice(defender_expression)
        attacker_damage = max(0, attacker_roll + attacker_skill_bonus)
        defender_damage = defender_roll

        result.update({
            "attacker_damage_dice": attacker_expression,
            "defender_damage_dice": defender_expression,
            "attacker_damage_total": attacker_damage,
            "defender_damage_total": defender_damage,
            "attacker_roll": attacker_roll,
            "defender_roll": defender_roll,
            "attacker_injury_result": calculate_simple_injury(
                defender_damage, "cr", attacker_hp, source="Basic Set", page="371"
            ).to_dict(),
            "defender_injury_result": calculate_simple_injury(
                attacker_damage, "cr", defender_hp, source="Basic Set", page="371"
            ).to_dict(),
        })

        if attacker_damage == 0 and defender_damage == 0:
            result["outcome"] = "no_effect"
        elif attacker_damage >= 2 * defender_damage:
            result["defender_fall"] = True
            result["outcome"] = "defender_falls_automatically"
        elif defender_damage >= 2 * attacker_damage:
            result["attacker_fall"] = True
            result["outcome"] = "attacker_falls_instead"
        elif attacker_damage >= defender_damage:
            result["defender_dx_roll_required"] = True
            result["outcome"] = "defender_dx_roll"
        else:
            result["outcome"] = "no_knockdown"

        result["result_text"] = result["outcome"]
        result["message"] = (
            f"Collision velocity: {collision_velocity} yd/s\n"
            f"Attacker damage: {attacker_damage}\n"
            f"Defender damage: {defender_damage}"
        )
        return result

    def _calculate_collision_velocity(
        self, velocity1: int, velocity2: int, collision_type: str
    ) -> int:
        if collision_type == "head_on":
            return velocity1 + velocity2
        if collision_type == "rear_end":
            return max(0, velocity1 - velocity2)
        if collision_type == "side_on":
            return velocity1
        raise ValueError(f"Unknown collision type: {collision_type}")

    def calculate_slam_attack_roll(
        self,
        skill: int,
        roll_result: int,
        is_move_and_attack: bool = False,
    ) -> Dict[str, Any]:
        """Resolve the DX, Brawling, or Sumo Wrestling roll to hit."""
        effective_skill = skill
        if is_move_and_attack:
            effective_skill = min(skill - 4, 9)
        outcome = evaluate_success_roll(effective_skill, roll_result)
        return {
            "skill": skill,
            "effective_skill": effective_skill,
            "roll_result": roll_result,
            "success": outcome["success"],
            "critical_hit": outcome["critical_success"],
            "critical_miss": outcome["critical_failure"],
            "margin": outcome["margin"],
            "outcome": (
                "critical_hit" if outcome["critical_success"] else
                "critical_miss" if outcome["critical_failure"] else
                "hit" if outcome["success"] else "miss"
            ),
        }
