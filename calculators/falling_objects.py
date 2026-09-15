"""Falling-object and Dropping rules (Basic Set Revised, pp. 189 and 431)."""

from typing import Any, Dict, Optional

from utils.dice_roller import (
    calculate_collision_damage,
    evaluate_success_roll,
    get_falling_velocity,
    get_range_modifier,
    roll_3d6,
    roll_dice,
)
from calculators.injury import calculate_simple_injury


class FallingObjectsCalculator:
    """Resolve a ranged Dropping attack from above and its collision damage."""

    def calculate_falling_object(
        self,
        distance_yards: int,
        object_hp: int,
        target_hp: int,
        target_sm: int = 0,
        object_sm: int = 0,
        target_aware: bool = False,
        dropping_skill: int = 15,
        target_dodge: int = 8,
        aimed: bool = False,
        attack_roll: Optional[int] = None,
        dodge_roll: Optional[int] = None,
    ) -> Dict[str, Any]:
        if distance_yards < 0 or object_hp < 1 or target_hp < 1:
            raise ValueError("Distance cannot be negative and HP must be positive.")

        velocity = get_falling_velocity(distance_yards)
        _, expression = calculate_collision_damage(object_hp, velocity)
        range_modifier = get_range_modifier(distance_yards)
        effective_skill = dropping_skill + range_modifier + (1 if aimed else 0)
        attack_roll = attack_roll if attack_roll is not None else roll_3d6()[0]
        attack = (
            evaluate_success_roll(effective_skill, attack_roll)
            if effective_skill >= 3
            else {"success": False, "critical_success": False,
                  "critical_failure": False, "margin": attack_roll - effective_skill}
        )

        hit = bool(attack["success"])
        target_can_dodge = bool(target_aware and hit)
        dodge_success = False
        if target_can_dodge:
            dodge_roll = dodge_roll if dodge_roll is not None else roll_3d6()[0]
            dodge_success = bool(evaluate_success_roll(target_dodge, dodge_roll)["success"])
            hit = not dodge_success

        damage = roll_dice(expression)[0] if hit and expression != "0d" else 0
        impedes = hit and object_sm >= target_sm
        result: Dict[str, Any] = {
            "distance_yards": distance_yards,
            "object_hp": object_hp,
            "target_hp": target_hp,
            "target_sm": target_sm,
            "object_sm": object_sm,
            "target_aware": target_aware,
            "dropping_skill": dropping_skill,
            "range_modifier": range_modifier,
            "effective_skill": effective_skill,
            "attack_roll": attack_roll,
            "attack_success": attack["success"],
            "critical_hit": attack["critical_success"],
            "critical_miss": attack["critical_failure"],
            "velocity": velocity,
            "damage_dice": expression,
            "damage_total": damage,
            "injury_result": calculate_simple_injury(
                damage, "cr", target_hp, source="Basic Set", page="431"
            ).to_dict(),
            "hit": hit,
            "hit_automatically": False,
            "target_can_dodge": target_can_dodge,
            "target_dodge": target_dodge,
            "dodge_roll": dodge_roll,
            "dodge_success": dodge_success,
            "next_turn_move": 1 if impedes else None,
            "move_penalty": 1 if impedes else 0,
            "defense_penalty": 3 if impedes else 0,
            "valid": True,
            "outcome": "hit" if hit else "dodged" if dodge_success else "miss",
            "message": (
                f"Dropping roll: {attack_roll} vs. {effective_skill}\n"
                f"Impact damage: {expression} = {damage}"
            ),
        }
        return result

    def calculate_drop_attack(
        self,
        distance_yards: int,
        object_hp: int,
        object_sm: int,
        target_sm: int,
        dropping_skill: int = 15,
        target_dodge: int = 10,
        target_aware: bool = True,
        attack_roll: Optional[int] = None,
        dodge_roll: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Compatibility wrapper returning a fully resolved Dropping attack."""
        return self.calculate_falling_object(
            distance_yards=distance_yards,
            object_hp=object_hp,
            target_hp=1,
            target_sm=target_sm,
            object_sm=object_sm,
            target_aware=target_aware,
            dropping_skill=dropping_skill,
            target_dodge=target_dodge,
            attack_roll=attack_roll,
            dodge_roll=dodge_roll,
        )
