"""Explosion rules from GURPS Basic Set Revised, pp. 414-415."""

import math
from typing import Any, Dict, List, Optional

from utils.dice_roller import (
    evaluate_success_roll,
    get_range_modifier,
    roll_3d6,
    roll_dice,
)
from calculators.injury import calculate_simple_injury


REF_TABLE = {
    "serpentine_powder": 0.3,
    "ammonium_nitrate": 0.4,
    "black_powder_early": 0.4,
    "black_powder_late": 0.5,
    "diesel_fertilizer": 0.5,
    "dynamite": 0.8,
    "tnt": 1.0,
    "amatol": 1.2,
    "nitroglycerine": 1.5,
    "tetryl": 1.3,
    "composition_b": 1.4,
    "c4": 1.4,
    "octanitrocubane": 4.0,
    "metallic_hydrogen": 6.0,
}


class ExplosionsCalculator:
    """Resolve blast and fragmentation as separate attacks."""

    def calculate_explosion(
        self,
        basic_damage_dice: int,
        fragmentation_dice: int,
        distance_yards: int,
        target_dr: int = 0,
        blast_radius_multiplier: int = 2,
        damage_divisor: int = 3,
        direct_hit: bool = False,
        target_sm: int = 0,
        posture_modifier: int = 0,
        fragment_attack_roll: Optional[int] = None,
        dodge_and_drop_success: bool = False,
        blast_roll: Optional[int] = None,
        fragment_damage_rolls: Optional[List[int]] = None,
        target_hp: int = 10,
    ) -> Dict[str, Any]:
        if min(basic_damage_dice, fragmentation_dice, distance_yards, target_dr) < 0:
            raise ValueError("Damage dice, distance, and DR cannot be negative.")
        if damage_divisor < 1 or blast_radius_multiplier < 1:
            raise ValueError("Explosion divisors and radius multipliers must be positive.")

        blast_radius = basic_damage_dice * blast_radius_multiplier
        fragment_radius = fragmentation_dice * 5
        in_blast = basic_damage_dice > 0 and (direct_hit or distance_yards <= blast_radius)
        in_fragment_zone = fragmentation_dice > 0 and distance_yards <= fragment_radius

        result: Dict[str, Any] = {
            "basic_damage_dice": basic_damage_dice,
            "fragmentation_dice": fragmentation_dice,
            "distance_yards": distance_yards,
            "target_dr": target_dr,
            "direct_hit": direct_hit,
            "blast_radius": blast_radius,
            "fragment_radius": fragment_radius,
            "collateral_damage_dice": "0d",
            "collateral_damage_total": 0,
            "blast_injury": 0,
            "fragment_attack_skill": None,
            "fragment_attack_roll": None,
            "fragment_hits": 0,
            "fragment_damage_dice": f"{fragmentation_dice}d" if fragmentation_dice else "0d",
            "fragment_damage_rolls": [],
            "fragment_damage_total": 0,
            "fragment_injury_total": 0,
            "total_damage": 0,
            "injury": 0,
            "in_danger_zone": in_blast,
            "in_fragment_zone": in_fragment_zone,
            "valid": True,
            "outcome": "outside_blast",
            "message": "",
        }

        if in_blast:
            rolled_blast = blast_roll if blast_roll is not None else roll_dice(f"{basic_damage_dice}d")[0]
            if direct_hit:
                blast_damage = rolled_blast
                blast_expression = f"{basic_damage_dice}d"
            else:
                divisor = damage_divisor * max(1, distance_yards)
                blast_damage = rolled_blast // divisor
                blast_expression = f"{basic_damage_dice}d/{divisor}"
            result["collateral_damage_dice"] = blast_expression
            result["collateral_damage_total"] = blast_damage
            result["blast_injury"] = max(0, blast_damage - target_dr)

        if in_fragment_zone and not dodge_and_drop_success:
            hits = 0
            if direct_hit:
                hits = 1
            else:
                effective_skill = 15 + get_range_modifier(distance_yards) + posture_modifier + target_sm
                fragment_attack_roll = (
                    fragment_attack_roll if fragment_attack_roll is not None else roll_3d6()[0]
                )
                result["fragment_attack_skill"] = effective_skill
                result["fragment_attack_roll"] = fragment_attack_roll
                if effective_skill >= 3:
                    attack = evaluate_success_roll(effective_skill, fragment_attack_roll)
                    if attack["success"]:
                        hits = 1 + int(attack["margin"]) // 3

            damage_rolls: List[int] = []
            injury_total = 0
            supplied_fragments = fragment_damage_rolls or []
            for index in range(hits):
                damage = (supplied_fragments[index] if index < len(supplied_fragments)
                          else roll_dice(f"{fragmentation_dice}d", minimum=1)[0])
                damage_rolls.append(damage)
                penetrating = max(0, damage - target_dr)
                if penetrating:
                    injury_total += max(1, math.floor(penetrating * 1.5))
            result["fragment_hits"] = hits
            result["fragment_damage_rolls"] = damage_rolls
            result["fragment_damage_total"] = sum(damage_rolls)
            result["fragment_injury_total"] = injury_total

        result["total_damage"] = (
            result["collateral_damage_total"] + result["fragment_damage_total"]
        )
        result["injury"] = result["blast_injury"] + result["fragment_injury_total"]
        result["blast_injury_result"] = calculate_simple_injury(
            result["collateral_damage_total"], "cr", target_hp, target_dr,
            source="Basic Set", page="414-415",
        ).to_dict()
        result["fragment_injury_results"] = [
            calculate_simple_injury(
                damage, "cut", target_hp, target_dr,
                source="Basic Set", page="414-415",
            ).to_dict()
            for damage in result["fragment_damage_rolls"]
        ]
        if result["injury"]:
            result["outcome"] = "injury"
        elif in_blast or in_fragment_zone:
            result["outcome"] = "no_injury"
        result["message"] = (
            f"Blast injury: {result['blast_injury']}\n"
            f"Fragment hits: {result['fragment_hits']}\n"
            f"Fragment injury: {result['fragment_injury_total']}"
        )
        return result

    def calculate_internal_explosion(
        self,
        damage_dice: int,
        target_hp: int,
        target_dr: int = 0,
        location: str = "vitals",
    ) -> Dict[str, Any]:
        """Resolve an internal explosion: DR is ignored and injury is ×3."""
        if damage_dice < 1 or target_hp < 1:
            raise ValueError("Damage dice and target HP must be positive.")
        damage, _ = roll_dice(f"{damage_dice}d")
        injury = damage * 3
        return {
            "damage_dice": damage_dice,
            "target_hp": target_hp,
            "target_dr": target_dr,
            "location": "vitals",
            "damage_total": damage,
            "wounding_modifier": 3.0,
            "injury": injury,
            "valid": True,
            "message": f"Internal explosion: {damage} × 3 = {injury} injury",
        }

    def calculate_demolition_charge(
        self, required_damage_dice: int, explosive_type: str = "tnt"
    ) -> Dict[str, Any]:
        if required_damage_dice <= 0 or required_damage_dice % 6:
            raise ValueError("Required damage must be a positive multiple of 6d.")
        ref = REF_TABLE.get(explosive_type)
        if ref is None:
            raise ValueError(f"Unknown explosive type: {explosive_type}")
        multiplier = required_damage_dice / 6
        weight_tnt = (multiplier * multiplier) / 4
        weight_actual = weight_tnt / ref
        return {
            "required_damage": f"6d×{multiplier:g}",
            "explosive_type": explosive_type,
            "ref": ref,
            "weight_tnt_lbs": weight_tnt,
            "weight_actual_lbs": weight_actual,
            "weight_actual_kg": weight_actual * 0.453592,
            "message": f"Required weight: {weight_actual:.2f} lb",
        }

    def calculate_explosive_damage(
        self, weight_lbs: float, explosive_type: str = "tnt"
    ) -> Dict[str, Any]:
        if weight_lbs <= 0:
            raise ValueError("Explosive weight must be positive.")
        ref = REF_TABLE.get(explosive_type)
        if ref is None:
            raise ValueError(f"Unknown explosive type: {explosive_type}")
        multiplier = math.sqrt(weight_lbs * 4 * ref)
        return {
            "weight_lbs": weight_lbs,
            "weight_kg": weight_lbs * 0.453592,
            "explosive_type": explosive_type,
            "ref": ref,
            "damage_multiplier": multiplier,
            "damage_dice": 6,
            "damage_expression": f"6d×{multiplier:g}",
            "message": f"Damage: 6d × {multiplier:g}",
        }
