"""Collision rules from GURPS Basic Set Revised, pp. 430-432."""

from typing import Any, Dict, Tuple

from utils.dice_roller import collision_damage_expression, roll_dice
from calculators.injury import calculate_simple_injury


class CollisionsCalculator:
    """Calculate mutual crushing damage for collisions."""

    def calculate_collision(
        self,
        object1_hp: int,
        object1_velocity: int,
        object2_hp: int,
        object2_velocity: int,
        collision_type: str = "head_on",
        surface_type: str = "normal",
        immovable_object: bool = False,
        object2_dr: int = 0,
        elastic_dr: int = 5,
        obstacle_breakable: bool = False,
    ) -> Dict[str, Any]:
        if object1_hp < 1 or object2_hp < 0 or (not immovable_object and object2_hp < 1):
            raise ValueError("Moving objects need positive HP; obstacle HP cannot be negative.")
        if min(object1_velocity, object2_velocity, object2_dr, elastic_dr) < 0:
            raise ValueError("Velocities and DR cannot be negative.")
        if surface_type not in {"normal", "hard", "soft", "elastic"}:
            raise ValueError(f"Unknown surface type: {surface_type}")

        collision_velocity = self._calculate_collision_velocity(
            object1_velocity, object2_velocity, collision_type, immovable_object
        )
        result: Dict[str, Any] = {
            "object1_hp": object1_hp,
            "object1_velocity": object1_velocity,
            "object2_hp": object2_hp,
            "object2_velocity": object2_velocity,
            "object2_dr": object2_dr,
            "collision_type": collision_type,
            "surface_type": surface_type,
            "immovable_object": immovable_object,
            "obstacle_breakable": obstacle_breakable,
            "collision_velocity": collision_velocity,
            "object1_damage_dice": "0d",
            "object2_damage_dice": "0d",
            "object1_damage_total": 0,
            "object2_damage_total": 0,
            "object1_roll": 0,
            "object2_roll": 0,
            "elastic_dr": elastic_dr if surface_type == "elastic" else 0,
            "damage_cap": None,
            "valid": collision_velocity > 0,
            "outcome": "collision" if collision_velocity > 0 else "no_collision",
            "message": "",
        }
        if collision_velocity <= 0:
            result["message"] = "No collision: relative velocity is zero."
            return result

        raw1, raw2 = self._raw_damage_dice(
            object1_hp,
            object2_hp,
            object1_velocity,
            object2_velocity,
            collision_velocity,
            collision_type,
            surface_type,
            immovable_object,
        )
        _, expression1 = collision_damage_expression(raw1)
        _, expression2 = collision_damage_expression(raw2)
        damage1, _ = roll_dice(expression1)
        damage2, _ = roll_dice(expression2)

        # A breakable immovable obstacle caps both damage rolls at HP + DR.
        if immovable_object and obstacle_breakable and object2_hp > 0:
            cap = object2_hp + object2_dr
            result["damage_cap"] = cap
            damage1 = min(damage1, cap)
            damage2 = min(damage2, cap)

        # Elastic surfaces give extra DR against the damage taken by the mover.
        if immovable_object and surface_type == "elastic":
            damage2 = max(0, damage2 - elastic_dr)

        result.update({
            "object1_damage_dice": expression1,
            "object2_damage_dice": expression2,
            "object1_damage_total": damage1,
            "object2_damage_total": damage2,
            "object1_roll": damage1,
            "object2_roll": damage2,
            "object1_injury_result": calculate_simple_injury(
                damage2, "cr", object1_hp, 0, source="Basic Set", page="430-432"
            ).to_dict(),
            "object2_injury_result": calculate_simple_injury(
                damage1, "cr", max(1, object2_hp), object2_dr,
                source="Basic Set", page="430-432"
            ).to_dict(),
            "message": (
                f"Collision velocity: {collision_velocity} yd/s\n"
                f"Object 1 inflicts {damage1} ({expression1})\n"
                f"Object 2 inflicts {damage2} ({expression2})"
            ),
        })
        return result

    def _raw_damage_dice(
        self,
        hp1: int,
        hp2: int,
        velocity1: int,
        velocity2: int,
        collision_velocity: int,
        collision_type: str,
        surface_type: str,
        immovable: bool,
    ) -> Tuple[float, float]:
        raw1 = hp1 * collision_velocity / 100
        if immovable:
            effective_hp = hp1 * 2 if surface_type == "hard" else hp1
            return raw1, effective_hp * collision_velocity / 100

        raw2 = hp2 * collision_velocity / 100
        if collision_type == "head_on":
            if velocity1 < velocity2:
                raw1 = min(raw1, raw2)
            elif velocity2 < velocity1:
                raw2 = min(raw2, raw1)
        elif collision_type in {"rear_end", "side_on"}:
            raw2 = min(raw2, raw1)
        return raw1, raw2

    def _calculate_collision_velocity(
        self,
        velocity1: int,
        velocity2: int,
        collision_type: str,
        immovable_object: bool,
    ) -> int:
        if immovable_object:
            return velocity1
        if collision_type == "head_on":
            return velocity1 + velocity2
        if collision_type == "rear_end":
            return max(0, velocity1 - velocity2)
        if collision_type == "side_on":
            return velocity1
        raise ValueError(f"Unknown collision type: {collision_type}")

    def _get_collision_type_name(self, collision_type: str) -> str:
        return {
            "head_on": "Head-On",
            "rear_end": "Rear-End",
            "side_on": "Side-On",
        }.get(collision_type, "Unknown")

    def calculate_immovable_object(
        self,
        moving_hp: int,
        moving_velocity: int,
        obstacle_hp: int,
        obstacle_dr: int = 0,
        is_hard: bool = True,
        is_soft: bool = False,
        is_elastic: bool = False,
        elastic_dr: int = 5,
    ) -> Dict[str, Any]:
        """Compatibility wrapper for an immovable-object collision."""
        surface = "elastic" if is_elastic else "soft" if is_soft else "hard" if is_hard else "normal"
        collision = self.calculate_collision(
            moving_hp,
            moving_velocity,
            obstacle_hp,
            0,
            collision_type="side_on",
            surface_type=surface,
            immovable_object=True,
            object2_dr=obstacle_dr,
            elastic_dr=elastic_dr,
            obstacle_breakable=obstacle_hp > 0,
        )
        return {
            **collision,
            "moving_hp": moving_hp,
            "moving_velocity": moving_velocity,
            "obstacle_hp": obstacle_hp,
            "obstacle_dr": obstacle_dr,
            "moving_damage_dice": collision["object2_damage_dice"],
            "moving_damage_total": collision["object2_damage_total"],
            "obstacle_damage_dice": collision["object1_damage_dice"],
            "obstacle_damage_total": collision["object1_damage_total"],
        }
