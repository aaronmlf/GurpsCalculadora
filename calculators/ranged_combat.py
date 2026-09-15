"""Ranged combat engine for GURPS Fourth Edition.

The public dataclasses deliberately keep printed weapon notation alongside
structured values.  This makes the rules engine useful without copying any
descriptive text from the source books.
"""

from dataclasses import asdict, dataclass, field, replace
import math
import random
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from utils.dice_roller import evaluate_success_roll, get_damage_dice, get_range_modifier, roll_3d6, roll_dice
from calculators.explosions import ExplosionsCalculator
from calculators.injury import (
    ArmorLoadout,
    CombatantState,
    DamagePacket,
    InjuryEngine,
    InjuryInput,
)


METERS_TO_YARDS = 1.0 / 0.9144


@dataclass
class DamageMode:
    dice: str
    damage_type: str
    armor_divisor: float = 1.0
    minimum_range: float = 0.0
    half_damage_range: Optional[float] = None
    max_range: Optional[float] = None
    follow_up: Optional["DamageMode"] = None
    explosive: bool = False
    fragmentation: Optional[str] = None
    resistance: Optional[str] = None
    effect_shape: str = "projectile"
    area_radius_yards: Optional[float] = None
    cone_width_yards: Optional[float] = None
    raw: str = ""

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "DamageMode":
        data = dict(value)
        if isinstance(data.get("follow_up"), dict):
            data["follow_up"] = cls.from_dict(data["follow_up"])
        return cls(**data)


@dataclass
class WeaponRecord:
    identifier: str
    source: str
    page: str
    name: str
    tech_level: str
    category: str
    skills: List[str]
    damage_modes: List[DamageMode]
    accuracy: int
    accuracy_secondary: int = 0
    range_raw: str = ""
    weight_raw: str = ""
    rate_of_fire_modes: List[float] = field(default_factory=lambda: [1.0])
    projectiles_per_shot: int = 1
    shots_raw: str = ""
    shots_capacity: Optional[int] = None
    chamber_capacity: int = 0
    reload_seconds: Optional[int] = None
    reload_individual: bool = False
    strength: Optional[int] = None
    strength_flags: str = ""
    bulk: Optional[int] = None
    recoil: int = 1
    recoil_secondary: Optional[int] = None
    malfunction: int = 17
    full_auto_only: bool = False
    cost: str = ""
    legality_class: str = ""
    tags: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    original: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "WeaponRecord":
        data = dict(value)
        data["damage_modes"] = [DamageMode.from_dict(mode) for mode in data.get("damage_modes", [])]
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RangedAttackInput:
    weapon: WeaponRecord
    profile: str = "basic"
    skill: int = 12
    damage_mode: int = 0
    distance_m: float = 1.0
    target_speed_mps: float = 0.0
    target_sm: int = 0
    aim_seconds: int = 0
    aim_lost: bool = False
    braced: bool = False
    scope_bonus: int = 0
    laser_bonus: int = 0
    targeting_system_bonus: int = 0
    maneuver: str = "attack"
    shots_fired: int = 1
    hit_location: str = "torso"
    posture_modifier: int = 0
    cover_modifier: int = 0
    visibility_modifier: int = 0
    cannot_see_target: bool = False
    offhand: bool = False
    shock: int = 0
    shooter_strength: Optional[int] = None
    custom_modifier: int = 0
    target_aware: bool = True
    dodge: Optional[int] = None
    target_dr: int = 0
    target_hp: int = 10
    effect_distance_m: float = 0.0
    rangefinder_bonus: int = 0
    precision_aiming_bonus: int = 0
    follow_up_aim_bonus: int = 0
    fast_firing_modifier: int = 0
    cinematic_modifier: int = 0
    ammunition: str = "standard"
    minute_of_angle: bool = False
    use_simplified_range: bool = True
    attack_roll: Optional[int] = None
    defense_roll: Optional[int] = None
    damage_rolls: Optional[List[int]] = None
    follow_up_damage_rolls: Optional[List[int]] = None


@dataclass
class RangedAttackResult:
    valid: bool
    errors: List[str]
    profile: str
    range_valid: bool
    distance_yards: float
    speed_yards_per_second: float
    range_band: str
    beyond_half_damage: bool
    modifiers: List[Dict[str, Any]]
    effective_skill: int
    probability: float
    rate_of_fire_bonus: int
    attack: Optional[Dict[str, Any]] = None
    hits_before_defense: int = 0
    defense: Optional[Dict[str, Any]] = None
    hits_after_defense: int = 0
    damages: List[Dict[str, Any]] = field(default_factory=list)
    malfunction: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DAMAGE_TYPES = {
    "burn": 1.0, "cor": 1.0, "cr": 1.0, "crushing": 1.0,
    "cut": 1.5, "cutting": 1.5, "fat": 1.0, "imp": 2.0, "impaling": 2.0,
    "pi-": 0.5, "small_piercing": 0.5, "pi": 1.0, "piercing": 1.0,
    "pi+": 1.5, "large_piercing": 1.5, "pi++": 2.0,
    "huge_piercing": 2.0, "tox": 1.0, "toxic": 1.0,
}

_HIT_LOCATIONS = {
    "torso": (0, 1.0, 0),
    "vitals": (-3, 3.0, 0),
    "skull": (-7, 4.0, 2),
    "face": (-5, 1.0, 0),
    "eye": (-9, 4.0, 0),
    "groin": (-3, 1.0, 0),
    "arm": (-2, 1.0, 0),
    "leg": (-2, 1.0, 0),
    "hand": (-4, 1.0, 0),
    "foot": (-4, 1.0, 0),
    "weapon": (-5, 1.0, 0),
}


def rapid_fire_bonus(shots: int) -> int:
    """Return the Rapid-Fire bonus from the Basic Set table (p. 373)."""
    if shots < 5:
        return 0
    if shots < 9:
        return 1
    if shots < 13:
        return 2
    if shots < 17:
        return 3
    if shots < 25:
        return 4
    if shots < 50:
        return 5
    if shots < 100:
        return 6
    return 7 + int(math.log(shots / 100.0, 2))


def success_probability(target: int) -> float:
    successes = 0
    for first in range(1, 7):
        for second in range(1, 7):
            for third in range(1, 7):
                if evaluate_success_roll(target, first + second + third)["success"]:
                    successes += 1
    return round(successes * 100.0 / 216.0, 2)


def simplified_range_modifier(distance_yards: float) -> Tuple[int, str]:
    """Gun Fu's optional broad range bands (p. 7)."""
    if distance_yards <= 5:
        return 0, "close"
    if distance_yards <= 20:
        return -3, "short"
    if distance_yards <= 100:
        return -7, "medium"
    if distance_yards <= 500:
        return -11, "long"
    return -15, "extreme"


class RangedCombatCalculator:
    """Calculate or resolve a single-target ranged attack."""

    PROFILES = ("basic", "realistic", "cinematic")

    def __init__(self) -> None:
        self.injury_engine = InjuryEngine()

    @staticmethod
    def _modifier(key: str, value: int, source: str, page: str, detail: str = "") -> Dict[str, Any]:
        return {"key": key, "value": value, "source": source, "page": page, "detail": detail}

    @staticmethod
    def _selected_mode(attack: RangedAttackInput) -> DamageMode:
        if not attack.weapon.damage_modes:
            raise ValueError("Weapon has no damage mode.")
        if not 0 <= attack.damage_mode < len(attack.weapon.damage_modes):
            raise ValueError("Invalid damage mode index.")
        return attack.weapon.damage_modes[attack.damage_mode]

    @staticmethod
    def _adjust_damage_per_die(expression: str, bonus_per_die: int) -> str:
        match = re.fullmatch(r"(\d+)d([+-]\d+)?", expression)
        if not match:
            return expression
        modifier = int(match.group(2) or 0) + int(match.group(1)) * bonus_per_die
        return match.group(1) + "d" + ("{:+d}".format(modifier) if modifier else "")

    def _effective_mode(self, attack: RangedAttackInput) -> DamageMode:
        mode = self._selected_mode(attack)
        if attack.profile != "realistic" or attack.ammunition == "standard":
            return mode
        piercing_up = {"pi-": "pi", "pi": "pi+", "pi+": "pi++", "pi++": "pi++"}
        piercing_down = {"pi++": "pi+", "pi+": "pi", "pi": "pi-", "pi-": "pi-"}
        if attack.ammunition == "hollow_point":
            return replace(mode, armor_divisor=0.5,
                           damage_type=piercing_up.get(mode.damage_type, mode.damage_type))
        if attack.ammunition in ("aphc", "apds"):
            updates = {
                "armor_divisor": 2.0,
                "damage_type": piercing_down.get(mode.damage_type, mode.damage_type),
            }
            if attack.ammunition == "apds":
                updates["dice"] = self._adjust_damage_per_die(mode.dice, 1)
                updates["half_damage_range"] = (None if mode.half_damage_range is None
                                                else mode.half_damage_range * 1.5)
                updates["max_range"] = None if mode.max_range is None else mode.max_range * 1.5
            return replace(mode, **updates)
        return mode

    @staticmethod
    def _validate(attack: RangedAttackInput) -> List[str]:
        errors = []
        if attack.profile not in RangedCombatCalculator.PROFILES:
            errors.append("invalid_profile")
        if attack.skill < 0:
            errors.append("invalid_skill")
        if attack.distance_m < 0 or attack.target_speed_mps < 0:
            errors.append("negative_distance_or_speed")
        if attack.shots_fired < 1:
            errors.append("invalid_shots")
        if attack.target_dr < 0 or attack.target_hp < 1:
            errors.append("invalid_target")
        return errors

    def calculate(self, attack: RangedAttackInput) -> RangedAttackResult:
        errors = self._validate(attack)
        mode = self._effective_mode(attack)
        distance = attack.distance_m * METERS_TO_YARDS
        speed = attack.target_speed_mps * METERS_TO_YARDS
        range_valid = distance >= mode.minimum_range and (
            mode.max_range is None or distance <= mode.max_range
        )
        beyond_half = bool(mode.half_damage_range is not None and distance > mode.half_damage_range)

        modifiers: List[Dict[str, Any]] = []
        if attack.profile == "cinematic" and attack.use_simplified_range:
            range_mod, range_band = simplified_range_modifier(distance)
            modifiers.append(self._modifier("simplified_range", range_mod, "Gun Fu", "7", range_band))
            if speed > 0:
                speed_mod = get_range_modifier(math.ceil(speed))
                modifiers.append(self._modifier("target_speed", speed_mod, "Basic Set", "550"))
        else:
            combined = math.ceil(distance + speed)
            range_mod = get_range_modifier(combined)
            range_band = "standard"
            modifiers.append(self._modifier("range_and_speed", range_mod, "Basic Set", "550",
                                            "{:.2f} yd + {:.2f} yd/s".format(distance, speed)))

        if attack.target_sm:
            modifiers.append(self._modifier("size_modifier", attack.target_sm, "Basic Set", "19, 550"))

        location = _HIT_LOCATIONS.get(attack.hit_location, _HIT_LOCATIONS["torso"])
        if location[0]:
            modifiers.append(self._modifier("hit_location", location[0], "Basic Set", "398-400", attack.hit_location))
        for key, value in (("posture", attack.posture_modifier), ("cover", attack.cover_modifier),
                           ("visibility", attack.visibility_modifier)):
            if value:
                modifiers.append(self._modifier(key, value, "Basic Set", "548-549"))

        base_acc = max(0, attack.weapon.accuracy + (
            1 if attack.profile == "realistic" and attack.ammunition == "match" else 0
        ))
        if attack.aim_seconds > 0 and not attack.aim_lost:
            aim = min(2 * base_acc, base_acc + min(2, attack.aim_seconds - 1))
            remaining_aim = max(0, 2 * base_acc - aim)
            modifiers.append(self._modifier("aim", aim, "Basic Set", "364", "{} s".format(attack.aim_seconds)))
            if attack.braced:
                braced_bonus = min(1, remaining_aim)
                remaining_aim -= braced_bonus
                if braced_bonus:
                    modifiers.append(self._modifier("braced", braced_bonus, "Basic Set", "364"))
            devices = max(0, attack.scope_bonus) + max(0, attack.laser_bonus) + max(0, attack.targeting_system_bonus)
            devices = min(base_acc, devices, remaining_aim)
            if devices:
                modifiers.append(self._modifier("targeting_devices", devices, "Basic Set", "364, 412"))
        elif attack.aim_lost:
            modifiers.append(self._modifier("aim_lost", 0, "Basic Set", "364"))

        if attack.maneuver == "all_out_determined":
            modifiers.append(self._modifier("all_out_determined", 1, "Basic Set", "365"))
        elif attack.maneuver == "move_and_attack":
            penalty = min(-2, attack.weapon.bulk if attack.weapon.bulk is not None else -2)
            modifiers.append(self._modifier("move_and_attack", penalty, "Basic Set", "365"))
        elif attack.maneuver == "pop_up":
            modifiers.append(self._modifier("pop_up", -2, "Basic Set", "390"))

        actual_shots = attack.shots_fired
        if attack.weapon.full_auto_only:
            maximum_rof = max(attack.weapon.rate_of_fire_modes or [1])
            minimum = max(1, math.ceil(maximum_rof / 4.0))
            if actual_shots < minimum:
                errors.append("full_auto_minimum")
        close_shotgun = (
            attack.weapon.projectiles_per_shot > 1
            and mode.half_damage_range is not None
            and distance < mode.half_damage_range * 0.1
        )
        if attack.weapon.projectiles_per_shot > 1 and not close_shotgun:
            actual_projectiles = actual_shots * attack.weapon.projectiles_per_shot
        else:
            actual_projectiles = actual_shots
        rof_bonus = rapid_fire_bonus(actual_projectiles)
        if rof_bonus:
            modifiers.append(self._modifier("rapid_fire", rof_bonus, "Basic Set", "373", str(actual_projectiles)))

        if attack.offhand:
            modifiers.append(self._modifier("offhand", -4, "Basic Set", "14, 548"))
        if attack.shock:
            modifiers.append(self._modifier("shock", -min(4, abs(attack.shock)), "Basic Set", "419"))
        if attack.shooter_strength is not None and attack.weapon.strength is not None:
            deficit = max(0, attack.weapon.strength - attack.shooter_strength)
            if deficit:
                modifiers.append(self._modifier("insufficient_strength", -deficit, "Basic Set", "270"))
        if attack.custom_modifier:
            modifiers.append(self._modifier("custom", attack.custom_modifier, "User", "-"))

        if attack.profile == "realistic":
            for key, value, page in (
                ("rangefinder", attack.rangefinder_bonus, "27"),
                ("precision_aiming", attack.precision_aiming_bonus, "26"),
                ("follow_up_aim", attack.follow_up_aim_bonus, "14"),
                ("fast_firing", attack.fast_firing_modifier, "44"),
            ):
                if value:
                    modifiers.append(self._modifier(key, value, "Tactical Shooting", page))
        elif any((attack.rangefinder_bonus, attack.precision_aiming_bonus,
                  attack.follow_up_aim_bonus, attack.fast_firing_modifier)):
            errors.append("realistic_rule_outside_profile")

        if attack.profile == "cinematic" and attack.cinematic_modifier:
            modifiers.append(self._modifier("cinematic", attack.cinematic_modifier, "Gun Fu", "5-8"))
        elif attack.cinematic_modifier:
            errors.append("cinematic_rule_outside_profile")

        if attack.ammunition != "standard":
            if attack.profile != "realistic":
                errors.append("ammunition_outside_realistic_profile")
            else:
                modifiers.append(self._modifier("ammunition", 0, "High-Tech", "166-177",
                                                attack.ammunition))

        if attack.minute_of_angle:
            if attack.profile != "realistic":
                errors.append("minute_of_angle_outside_realistic_profile")
            else:
                spatial_keys = {"range_and_speed", "simplified_range", "target_speed", "size_modifier"}
                pre_spatial = attack.skill + sum(item["value"] for item in modifiers
                                                 if item["key"] not in spatial_keys)
                moa_cap = 22 + 2 * base_acc
                if pre_spatial > moa_cap:
                    modifiers.append(self._modifier("minute_of_angle", moa_cap - pre_spatial,
                                                    "Tactical Shooting", "32", str(moa_cap)))

        effective_skill = attack.skill + sum(item["value"] for item in modifiers)
        if attack.cannot_see_target:
            effective_skill = min(9, effective_skill)
        return RangedAttackResult(
            valid=not errors and range_valid,
            errors=errors + ([] if range_valid else ["out_of_range"]),
            profile=attack.profile,
            range_valid=range_valid,
            distance_yards=round(distance, 4),
            speed_yards_per_second=round(speed, 4),
            range_band=range_band,
            beyond_half_damage=beyond_half,
            modifiers=modifiers,
            effective_skill=effective_skill,
            probability=success_probability(effective_skill),
            rate_of_fire_bonus=rof_bonus,
            notes=(["half_damage"] if beyond_half else []) + (["close_shotgun"] if close_shotgun else []),
        )

    @staticmethod
    def _damage_total(expression: str, supplied: Optional[int]) -> Tuple[int, Optional[List[int]]]:
        if supplied is not None:
            return max(0, int(supplied)), None
        total, dice = roll_dice(expression)
        return total, dice

    def _resolve_damage(self, attack: RangedAttackInput, mode: DamageMode,
                        supplied: Optional[int], close_shotgun: bool = False,
                        follow_up_supplied: Optional[int] = None) -> Dict[str, Any]:
        expression = mode.dice
        effect_distance_yards = attack.effect_distance_m * METERS_TO_YARDS
        if (mode.effect_shape == "area" and mode.area_radius_yards is not None
                and effect_distance_yards > mode.area_radius_yards):
            return {
                "expression": expression,
                "original_expression": mode.dice,
                "basic_damage": 0,
                "penetrating_damage": 0,
                "injury": 0,
                "effect_type": "area",
                "affected": False,
                "effect_distance_yards": round(effect_distance_yards, 4),
                "area_radius_yards": mode.area_radius_yards,
                "rounding": "none",
            }
        if mode.damage_type == "aff" or mode.resistance:
            effect = {
                "expression": expression,
                "original_expression": mode.dice,
                "rolls": None,
                "basic_damage": 0,
                "armor_divisor": mode.armor_divisor,
                "target_dr": attack.target_dr,
                "effective_dr": math.ceil(attack.target_dr / max(0.01, mode.armor_divisor)),
                "penetrating_damage": 0,
                "damage_type": "aff",
                "wounding_modifier": 0.0,
                "hit_location": attack.hit_location,
                "injury": 0,
                "rounding": "none",
                "resistance": mode.resistance or mode.raw,
                "effect_type": "affliction",
            }
            if mode.effect_shape != "projectile":
                effect["effect_shape"] = mode.effect_shape
                effect["area_radius_yards"] = mode.area_radius_yards
                effect["cone_width_yards"] = mode.cone_width_yards
                effect["affected"] = True
            return effect
        muscle_match = re.fullmatch(r"(thr|sw)([+-]\d+)?", expression, re.I)
        if muscle_match:
            if attack.shooter_strength is None:
                raise ValueError("shooter_strength_required")
            expression = muscle_powered_damage(
                attack.shooter_strength,
                "thrust" if muscle_match.group(1).lower() == "thr" else "swing",
                int(muscle_match.group(2) or 0),
            )
        basic, dice = self._damage_total(expression, supplied)
        if mode.half_damage_range is not None and attack.distance_m * METERS_TO_YARDS > mode.half_damage_range:
            basic //= 2

        dr_multiplier = 1
        damage_multiplier = 1
        if close_shotgun:
            damage_multiplier = max(1, attack.weapon.projectiles_per_shot // 2)
            dr_multiplier = damage_multiplier
            basic *= damage_multiplier

        target = CombatantState(
            identifier="ranged_target",
            name="Ranged target",
            max_hp=attack.target_hp,
            current_hp=attack.target_hp,
            armor=ArmorLoadout(natural_dr=attack.target_dr * dr_multiplier),
        )
        injury_result = self.injury_engine.calculate(InjuryInput(
            packet=DamagePacket(
                basic_damage=basic,
                damage_type=mode.damage_type,
                armor_divisor=mode.armor_divisor,
                hit_location=attack.hit_location,
                source=attack.weapon.source,
                page=attack.weapon.page,
                expression=expression,
                ranged=True,
                tight_beam=(mode.damage_type == "burn" and "tight-beam" in mode.raw.casefold()),
                explosive=mode.explosive,
            ),
            target=target,
            profile=attack.profile,
        ))
        adjusted_dr = injury_result.effective_dr
        penetrating = injury_result.penetrating_damage
        wound_multiplier = injury_result.wounding_modifier
        injury = injury_result.injury
        result = {
            "expression": expression,
            "original_expression": mode.dice,
            "rolls": dice,
            "basic_damage": basic,
            "armor_divisor": mode.armor_divisor,
            "target_dr": attack.target_dr,
            "effective_dr": adjusted_dr,
            "penetrating_damage": penetrating,
            "damage_type": mode.damage_type,
            "wounding_modifier": wound_multiplier,
            "hit_location": attack.hit_location,
            "injury": injury,
            "rounding": "floor",
            "injury_result": injury_result.to_dict(),
            "state_delta": injury_result.state_delta.to_dict(),
        }
        if damage_multiplier > 1:
            result["close_shotgun_multiplier"] = damage_multiplier
            result["shotgun_dr_multiplier"] = dr_multiplier
        if mode.follow_up:
            if penetrating > 0:
                follow_up_attack = replace(attack, target_dr=0)
                result["follow_up"] = self._resolve_damage(
                    follow_up_attack, mode.follow_up, follow_up_supplied, False, None
                )
            else:
                result["follow_up"] = {"applied": False, "reason": "carrier_did_not_penetrate"}
        if mode.explosive:
            dice_match = re.match(r"(\d+)d(?:[×*](\d+(?:\.\d+)?))?", expression)
            dice_equivalent = 1
            if dice_match:
                dice_equivalent = max(1, math.ceil(int(dice_match.group(1)) * float(dice_match.group(2) or 1)))
            fragment_match = re.search(r"(\d+)d", mode.fragmentation or "")
            result["explosion"] = ExplosionsCalculator().calculate_explosion(
                basic_damage_dice=dice_equivalent,
                fragmentation_dice=int(fragment_match.group(1)) if fragment_match else 0,
                distance_yards=0,
                target_dr=attack.target_dr,
                direct_hit=True,
                target_sm=attack.target_sm,
                blast_roll=basic,
            )
        if mode.fragmentation:
            result["fragmentation"] = mode.fragmentation
        if mode.resistance:
            result["resistance"] = mode.resistance
        if mode.effect_shape != "projectile":
            result["effect_shape"] = mode.effect_shape
            result["area_radius_yards"] = mode.area_radius_yards
            result["cone_width_yards"] = mode.cone_width_yards
            result["effect_distance_yards"] = round(effect_distance_yards, 4)
            result["affected"] = True
        return result

    def resolve(self, attack: RangedAttackInput, attack_roll: Optional[int] = None,
                defense_roll: Optional[int] = None,
                damage_rolls: Optional[Sequence[int]] = None,
                resolve_defense: bool = True,
                resolve_damage: bool = True) -> RangedAttackResult:
        result = self.calculate(attack)
        if not result.valid:
            return result

        mode = self._effective_mode(attack)
        chosen_attack_roll = attack_roll if attack_roll is not None else attack.attack_roll
        if chosen_attack_roll is None:
            chosen_attack_roll, attack_dice = roll_3d6()
        else:
            attack_dice = None
        outcome = evaluate_success_roll(result.effective_skill, chosen_attack_roll)
        result.attack = dict(outcome, roll=chosen_attack_roll, dice=attack_dice)
        result.malfunction = chosen_attack_roll >= attack.weapon.malfunction
        if result.malfunction:
            result.notes.append("malfunction")
        if not outcome["success"]:
            return result

        close_shotgun = (
            attack.weapon.projectiles_per_shot > 1
            and mode.half_damage_range is not None
            and result.distance_yards < mode.half_damage_range * 0.1
        )
        projectiles = attack.shots_fired * (1 if close_shotgun else max(1, attack.weapon.projectiles_per_shot))
        result.hits_before_defense = min(projectiles, 1 + outcome["margin"] // max(1, attack.weapon.recoil))
        result.hits_after_defense = result.hits_before_defense

        if (resolve_defense and attack.target_aware and attack.dodge is not None
                and not outcome["critical_success"]):
            chosen_defense_roll = defense_roll if defense_roll is not None else attack.defense_roll
            if chosen_defense_roll is None:
                chosen_defense_roll, defense_dice = roll_3d6()
            else:
                defense_dice = None
            defense = evaluate_success_roll(attack.dodge, chosen_defense_roll)
            avoided = 0
            if defense["success"]:
                avoided = result.hits_before_defense if defense["critical_success"] else 1 + defense["margin"]
            result.hits_after_defense = max(0, result.hits_before_defense - avoided)
            result.defense = dict(defense, roll=chosen_defense_roll, dice=defense_dice,
                                  hits_avoided=min(result.hits_before_defense, avoided))

        if not resolve_damage:
            return result

        damage_count = result.hits_after_defense
        if close_shotgun:
            damage_count = min(attack.shots_fired, damage_count)
            result.notes.append("close_shotgun")
        supplied_rolls = list(damage_rolls if damage_rolls is not None else (attack.damage_rolls or []))
        supplied_follow_ups = list(attack.follow_up_damage_rolls or [])
        for index in range(damage_count):
            supplied = supplied_rolls[index] if index < len(supplied_rolls) else None
            follow_up_supplied = supplied_follow_ups[index] if index < len(supplied_follow_ups) else None
            result.damages.append(self._resolve_damage(
                attack, mode, supplied, close_shotgun, follow_up_supplied
            ))
        return result


def muscle_powered_damage(st: int, basis: str = "thrust", modifier: int = 0) -> str:
    """Return a structured-weapon damage expression derived from ST."""
    thrust, swing = get_damage_dice(st)
    expression = thrust if basis == "thrust" else swing
    if modifier == 0:
        return expression
    match = re.fullmatch(r"(\d+d)([+-]\d+)?", expression)
    if not match:
        return expression
    current = int(match.group(2) or 0)
    total = current + modifier
    return match.group(1) + ("{:+d}".format(total) if total else "")
