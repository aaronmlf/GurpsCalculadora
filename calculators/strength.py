"""Strength, lifting, super-effort, and damage bonus rules for GURPS 4e."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import math
import re
from typing import Any, Dict, List, Optional

from calculators.injury import RuleReference, StateDelta
from utils.dice_roller import evaluate_success_roll, get_damage_dice, roll_3d6


@dataclass
class StrengthProfile:
    st: int = 10
    lifting_st: int = 0
    striking_st: int = 0
    arm_st: int = 0
    hp: int = 10
    will: int = 10
    current_fp: int = 10
    trained_by_master: bool = False
    weapon_master: bool = False
    strongbow: bool = False
    power_blow_level: int = 0
    throwing_art_level: int = 0
    max_fp: int = 10
    lifting_skill_will: Optional[int] = None
    machine: bool = False
    lifting_skill_ht: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EffortOption:
    extra_effort_percent: int = 0
    super_effort_levels: int = 0
    super_effort_scope: str = "lifting"  # lifting, striking, total
    mighty_blows: bool = False
    continuous: bool = False
    will_roll: Optional[int] = None
    use_lifting_skill: bool = False
    motivated: bool = False  # GM-approved B357 +5, never inferred.
    sustained_use: str = "hold"  # hold (hour), carry (minute)
    trained_lift: bool = False
    lifting_roll: Optional[int] = None
    power_blow: bool = False
    power_blow_roll: Optional[int] = None
    concentration_seconds: int = 0
    triple_strength: bool = False


@dataclass
class StrengthCalculationInput:
    profile: StrengthProfile = field(default_factory=StrengthProfile)
    task: str = "basic_lift"
    rules_profile: str = "basic"
    effort: EffortOption = field(default_factory=EffortOption)
    load_lb: float = 0.0
    duration_seconds: int = 1


@dataclass
class StrengthCalculationResult:
    valid: bool
    errors: List[str]
    task: str
    base_st: int
    effective_st: int
    basic_lift_lb: float
    capacity_lb: float
    thrust: str
    swing: str
    fp_cost: int = 0
    success_roll: Optional[Dict[str, Any]] = None
    state_delta: StateDelta = field(default_factory=StateDelta)
    breakdown: List[Dict[str, Any]] = field(default_factory=list)
    references: List[RuleReference] = field(default_factory=list)
    required_roll_target: Optional[int] = None
    intervals: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DamageBonusInput:
    profile: StrengthProfile = field(default_factory=StrengthProfile)
    rules_profile: str = "basic"
    basis: str = "swing"
    weapon_modifier: int = 0
    maneuver: str = "attack"
    effort: EffortOption = field(default_factory=EffortOption)
    weapon_master: bool = False
    weapon_skill_relative: int = 0
    technique_flat_bonus: int = 0
    technique_per_die: int = 0
    convert_adds: bool = False  # Optional rule, Basic Set p. 269.


@dataclass
class DamageBonusResult:
    valid: bool
    errors: List[str]
    strength_used: int
    original_damage: str
    final_damage: str
    fp_cost: int
    state_delta: StateDelta
    breakdown: List[Dict[str, Any]]
    references: List[RuleReference]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _super_value(levels: int) -> int:
    """Powers p. 58: read levels on the SSR progression as a ST bonus."""
    if levels <= 0:
        return 0
    sequence = (3, 5, 7, 10, 15, 20, 30, 50, 70, 100, 150, 200,
                300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000)
    if levels <= len(sequence):
        return sequence[levels - 1]
    cycles, index = divmod(levels - 1, 6)
    return (3, 5, 7, 10, 15, 20)[index] * (10 ** cycles)


def _parse_damage(expression: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)d(?:([+-]\d+))?", expression)
    if not match:
        raise ValueError("invalid_damage_expression")
    return int(match.group(1)), int(match.group(2) or 0)


def _format_damage(dice: int, adds: int, convert_adds: bool = False) -> str:
    # B269 converts positive adds only: +7 -> 2d, then +4 -> 1d.
    if convert_adds and adds >= 0:
        pairs, adds = divmod(adds, 7)
        dice += pairs * 2
        if adds >= 4:
            dice += 1
            adds -= 4
    return f"{max(1, dice)}d" + (f"{adds:+d}" if adds else "")


class StrengthEngine:
    TASK_MULTIPLIERS = {
        "basic_lift": 1.0,
        "one_handed_lift": 2.0,
        "two_handed_lift": 8.0,
        "shift_slightly": 50.0,
        "carry_unencumbered": 1.0,
        "carry_light": 2.0,
        "carry_medium": 3.0,
        "carry_heavy": 6.0,
        "carry_extra_heavy": 10.0,
        "push": 12.0,
        "pull": 12.0,
    }

    def _validate_effort(self, data: StrengthCalculationInput) -> List[str]:
        errors: List[str] = []
        effort = data.effort
        if data.rules_profile not in {"basic", "realistic", "cinematic"}:
            errors.append("invalid_profile")
        if (data.profile.st < 1 or data.profile.hp < 1 or
                min(data.profile.lifting_st, data.profile.striking_st,
                    data.profile.arm_st, data.profile.current_fp) < 0):
            errors.append("invalid_strength_profile")
        if effort.super_effort_levels < 0 or effort.extra_effort_percent < 0:
            errors.append("invalid_effort")
        if effort.super_effort_levels and data.rules_profile == "basic":
            errors.append("super_effort_outside_profile")
        if effort.super_effort_scope not in {"lifting", "striking", "total"}:
            errors.append("invalid_super_effort_scope")
        if effort.super_effort_levels and effort.super_effort_scope in {"striking", "total"} and data.rules_profile != "cinematic":
            errors.append("cinematic_super_effort_required")
        if effort.super_effort_levels and effort.extra_effort_percent:
            errors.append("incompatible_effort_options")
        if effort.extra_effort_percent and data.task not in set(self.TASK_MULTIPLIERS) | {"throwing"}:
            errors.append("extra_effort_not_applicable")
        if effort.will_roll is not None and not 3 <= effort.will_roll <= 18:
            errors.append("invalid_effort_roll")
        if data.duration_seconds < 1 or not math.isfinite(data.load_lb) or data.load_lb < 0:
            errors.append("invalid_strength_input")
        if data.profile.max_fp < 1 or data.profile.current_fp > data.profile.max_fp:
            errors.append("invalid_fatigue_pool")
        if effort.sustained_use not in {"hold", "carry"}:
            errors.append("invalid_sustained_use")
        if effort.use_lifting_skill and (data.task not in self.TASK_MULTIPLIERS or
                data.profile.lifting_skill_will is None or data.profile.lifting_skill_will < 1):
            errors.append("lifting_skill_not_available")
        if data.profile.machine and (effort.extra_effort_percent or effort.mighty_blows):
            errors.append("machine_cannot_use_extra_effort")
        if effort.extra_effort_percent and effort.continuous and data.duration_seconds > 60:
            # Each interval needs its own Will roll with the updated fatigue pool.
            errors.append("resolve_extra_effort_one_minute_at_a_time")
        if effort.trained_lift:
            if (data.profile.lifting_skill_ht is None or data.profile.lifting_skill_ht < 1 or
                    data.task not in {'one_handed_lift', 'two_handed_lift', 'shift_slightly'}):
                errors.append('trained_lifting_not_available')
        if effort.power_blow:
            if (data.rules_profile != 'cinematic' or data.profile.power_blow_level < 1 or
                    not (data.profile.trained_by_master or data.profile.weapon_master)):
                errors.append('power_blow_prerequisites')
            if data.task not in {'striking', 'one_handed_lift', 'two_handed_lift', 'shift_slightly'}:
                errors.append('power_blow_not_applicable')
            if effort.triple_strength and data.profile.power_blow_level <= 20:
                errors.append('power_blow_triple_requires_skill')
            if effort.concentration_seconds < 0:
                errors.append('invalid_effort')
        if sum(bool(v) for v in (effort.power_blow, effort.trained_lift, effort.extra_effort_percent, effort.super_effort_levels)) > 1:
            errors.append('incompatible_effort_options')
        for roll in (effort.lifting_roll, effort.power_blow_roll):
            if roll is not None and (type(roll) is not int or not 3 <= roll <= 18):
                errors.append('invalid_effort_roll')
        return errors

    def calculate(self, data: StrengthCalculationInput) -> StrengthCalculationResult:
        errors = self._validate_effort(data)
        if data.task not in self.TASK_MULTIPLIERS and data.task not in {
            "striking", "throwing", "knockback_resistance", "grappling", "choke", "collision"
        }:
            errors.append("invalid_strength_task")
        base = data.profile.st
        if data.task in self.TASK_MULTIPLIERS or data.task in {"grappling", "choke"}:
            base += data.profile.lifting_st
        if data.task == "striking":
            base += data.profile.striking_st + data.profile.arm_st
        if data.task == "collision":
            base = data.profile.hp
        breakdown: List[Dict[str, Any]] = [{"key": "base_st", "value": data.profile.st}]
        if base != data.profile.st:
            breakdown.append({"key": "specialized_st", "value": base - data.profile.st})

        effective = base
        fp_cost = 0
        if data.effort.extra_effort_percent:
            fp_cost += 1
            breakdown.append({"key": "extra_effort_percent", "value": data.effort.extra_effort_percent})
        if data.effort.super_effort_levels:
            allowed = data.effort.super_effort_scope == "total" or (
                data.effort.super_effort_scope == "lifting" and
                data.task in set(self.TASK_MULTIPLIERS)
            ) or (data.effort.super_effort_scope == "striking" and data.task == "striking")
            if data.task in {"grappling", "choke", "collision"}:
                allowed = False
            if allowed:
                bonus = _super_value(data.effort.super_effort_levels)
                effective += bonus
                interval = 60 if data.effort.sustained_use == "carry" else 3600
                fp_cost += max(1, math.ceil(data.duration_seconds / interval)) if data.effort.continuous else 1
                breakdown.append({"key": "super_effort", "value": bonus})
            else:
                errors.append("super_effort_not_applicable")

        success_roll = None
        effort_target = None
        if data.effort.power_blow:
            seconds = data.effort.concentration_seconds
            penalty = -10 if seconds <= 0 else min(0, -5 + int(math.log2(seconds)))
            effort_target = data.profile.power_blow_level + penalty - (10 if data.effort.triple_strength else 0)
            fp_cost += 1
            if data.effort.power_blow_roll is not None and 3 <= data.effort.power_blow_roll <= 18:
                success_roll = evaluate_success_roll(effort_target, data.effort.power_blow_roll)
                success_roll['roll'] = data.effort.power_blow_roll
            if success_roll is None or success_roll['success']:
                effective *= 3 if data.effort.triple_strength else 2
            breakdown.append({'key': 'power_blow', 'value': effective - base, 'source': 'Basic Set', 'page': '215'})
        if data.effort.trained_lift:
            effort_target = data.profile.lifting_skill_ht
            if (effort_target is not None and data.effort.lifting_roll is not None
                    and 3 <= data.effort.lifting_roll <= 18):
                success_roll = evaluate_success_roll(effort_target, data.effort.lifting_roll)
                success_roll['roll'] = data.effort.lifting_roll
        if data.effort.extra_effort_percent:
            target_base = data.profile.lifting_skill_will if data.effort.use_lifting_skill else data.profile.will
            increment = 10 if data.effort.use_lifting_skill else 5
            missing_fp = max(0, data.profile.max_fp - data.profile.current_fp)
            effort_target = (target_base if target_base is not None else data.profile.will) - math.ceil(data.effort.extra_effort_percent / increment) - missing_fp
            if data.effort.motivated:
                effort_target += 5
            breakdown.extend([
                {"key": "fatigue_penalty", "value": -missing_fp},
                {"key": "effort_roll_target", "value": effort_target},
            ])
        if data.effort.extra_effort_percent and data.effort.will_roll is not None and not errors:
            success_roll = evaluate_success_roll(effort_target, data.effort.will_roll)
            success_roll["target"] = effort_target
            if not success_roll["success"]:
                errors.append("effort_roll_failed")
            if success_roll["critical_success"]:
                fp_cost = 0
        effort_succeeded = success_roll is None or success_roll["success"]
        if data.task == "throwing" and data.effort.extra_effort_percent and effort_succeeded:
            effective = math.floor(base * (1 + data.effort.extra_effort_percent / 100))
        # Throwing effort changes throwing ST, not throwable load (B357).
        lift_st = base if data.task == "throwing" else effective
        basic_lift = lift_st * lift_st / 5.0
        basic_lift = math.floor(basic_lift + 0.5) if basic_lift >= 10 else basic_lift
        if data.task in self.TASK_MULTIPLIERS and data.effort.extra_effort_percent and effort_succeeded:
            basic_lift *= 1 + data.effort.extra_effort_percent / 100.0
        if data.effort.trained_lift and success_roll is not None and success_roll['success']:
            bonus = max(0, success_roll['margin']) * 5
            basic_lift *= 1 + bonus / 100
            breakdown.append({'key': 'trained_lifting', 'value': bonus, 'source': 'Basic Set', 'page': '205'})
        capacity = round(basic_lift * self.TASK_MULTIPLIERS.get(data.task, 1.0), 2)
        if data.load_lb > capacity and data.task in self.TASK_MULTIPLIERS:
            errors.append("load_exceeds_capacity")
        if fp_cost > data.profile.current_fp:
            errors.append("insufficient_fp")
        delta = StateDelta()
        if not errors or (success_roll is not None and set(errors) <= {"effort_roll_failed", "load_exceeds_capacity"}):
            delta.fp_change = -fp_cost
            if data.effort.extra_effort_percent and success_roll and success_roll["critical_failure"]:
                delta.hp_change = -fp_cost
        thrust, swing = get_damage_dice(effective)
        return StrengthCalculationResult(
            valid=not errors, errors=list(dict.fromkeys(errors)), task=data.task,
            base_st=base, effective_st=effective, basic_lift_lb=basic_lift,
            capacity_lb=capacity, thrust=thrust, swing=swing, fp_cost=fp_cost,
            success_roll=success_roll, state_delta=delta,
            breakdown=breakdown,
            required_roll_target=effort_target,
            references=[RuleReference("Basic Set", "15-17, 205, 215, 353-357"), RuleReference("Powers", "58"),
                        RuleReference("Supers", "24-25")],
        )

    def resolve(self, data: StrengthCalculationInput, will_roll: Optional[int] = None,
                interval_rolls: Optional[List[int]] = None) -> StrengthCalculationResult:
        if data.effort.extra_effort_percent and data.effort.continuous and data.duration_seconds > 60:
            return self.resolve_intervals(data, interval_rolls)
        if data.effort.power_blow:
            value = data.effort.power_blow_roll if data.effort.power_blow_roll is not None else roll_3d6()[0]
            return self.calculate(replace(data, effort=replace(data.effort, power_blow_roll=value)))
        if data.effort.trained_lift:
            value = data.effort.lifting_roll if data.effort.lifting_roll is not None else roll_3d6()[0]
            return self.calculate(replace(data, effort=replace(data.effort, lifting_roll=value)))
        if will_roll is None and data.effort.extra_effort_percent:
            will_roll = roll_3d6()[0]
        return self.calculate(replace(data, effort=replace(data.effort, will_roll=will_roll)))

    def resolve_intervals(self, data: StrengthCalculationInput,
                          rolls: Optional[List[int]] = None) -> StrengthCalculationResult:
        """B356–357: each minute is a new effort, with updated missing FP.

        Stop at the first failed effort or exhausted pool. Returned deltas sum
        only attempted intervals and never mutate the supplied character.
        """
        count = math.ceil(data.duration_seconds / 60)
        if (not data.effort.extra_effort_percent or not data.effort.continuous or
                not 1 <= count <= 1440 or rolls is not None and
                (len(rolls) != count or any(type(r) is not int or not 3 <= r <= 18 for r in rolls))):
            result = self.calculate(data)
            result.valid = False
            result.errors.append('invalid_effort_intervals')
            result.state_delta = StateDelta()
            return result
        profile = data.profile
        intervals, total_fp, total_hp = [], 0, 0
        result = None
        for index in range(count):
            seconds = min(60, data.duration_seconds - index * 60)
            item = replace(data, profile=profile, duration_seconds=seconds,
                           effort=replace(data.effort, will_roll=None))
            preview = self.calculate(item)
            if not preview.valid:
                result = preview
                break
            result = self.resolve(item, will_roll=rolls[index] if rolls is not None else None)
            total_fp += result.fp_cost
            total_hp += result.state_delta.hp_change
            intervals.append({'index': index + 1, 'seconds': seconds,
                              'target': result.required_roll_target,
                              'fp_before': profile.current_fp, 'fp_cost': result.fp_cost,
                              'success': bool(result.success_roll and result.success_roll['success'])})
            profile = replace(profile, current_fp=profile.current_fp - result.fp_cost)
            if not result.valid:
                break
        result.intervals = intervals
        result.fp_cost = total_fp
        result.state_delta = StateDelta(fp_change=-total_fp, hp_change=total_hp)
        return result

    def calculate_damage(self, data: DamageBonusInput) -> DamageBonusResult:
        errors: List[str] = []
        striking_super = (
            data.effort.super_effort_levels > 0
            and data.effort.super_effort_scope in {"striking", "total"}
        )
        strike_effort = replace(data.effort,
            super_effort_levels=0 if striking_super or data.effort.super_effort_scope == "lifting" else data.effort.super_effort_levels,
        )
        st_input = StrengthCalculationInput(
            profile=data.profile, task="striking", rules_profile=data.rules_profile, effort=strike_effort
        )
        strength = self.calculate(st_input)
        errors.extend(strength.errors)
        thrust, swing = get_damage_dice(strength.effective_st)
        original = thrust if data.basis == "thrust" else swing if data.basis == "swing" else ""
        if not original:
            errors.append("invalid_damage_basis")
            original = thrust
        dice, adds = _parse_damage(original)
        breakdown: List[Dict[str, Any]] = [{"key": "weapon_modifier", "value": data.weapon_modifier}]
        adds += data.weapon_modifier
        if striking_super:
            if data.rules_profile != "cinematic":
                errors.append("cinematic_super_effort_required")
            else:
                super_st = _super_value(data.effort.super_effort_levels)
                super_thrust, super_swing = get_damage_dice(super_st)
                extra_expression = super_thrust if data.basis == "thrust" else super_swing
                extra_dice, extra_adds = _parse_damage(extra_expression)
                dice += extra_dice
                adds += extra_adds
                strength.fp_cost += 1
                strength.state_delta.fp_change -= 1
                breakdown.append({"key": "super_effort_damage", "value": extra_expression})
        if data.maneuver == "all_out_strong":
            bonus = max(2, dice)
            adds += bonus
            breakdown.append({"key": "all_out_strong", "value": bonus})
        if data.effort.mighty_blows:
            if data.maneuver != "attack":
                errors.append("mighty_blows_requires_attack")
            bonus = max(2, dice)
            adds += bonus
            strength.fp_cost += 1
            strength.state_delta.fp_change -= 1
            breakdown.append({"key": "mighty_blows", "value": bonus})
        if data.weapon_master or data.profile.weapon_master:
            per_die = 2 if data.weapon_skill_relative >= 2 else 1 if data.weapon_skill_relative >= 1 else 0
            adds += per_die * dice
            breakdown.append({"key": "weapon_master", "value": per_die * dice})
        adds += data.technique_flat_bonus + data.technique_per_die * dice
        if data.technique_flat_bonus or data.technique_per_die:
            breakdown.append({"key": "technique", "value": data.technique_flat_bonus + data.technique_per_die * dice})
        if strength.fp_cost > data.profile.current_fp:
            errors.append("insufficient_fp")
        if errors:
            strength.state_delta = StateDelta()
        return DamageBonusResult(
            valid=not errors, errors=list(dict.fromkeys(errors)), strength_used=strength.effective_st,
            original_damage=original, final_damage=_format_damage(dice, adds, data.convert_adds), fp_cost=strength.fp_cost,
            state_delta=strength.state_delta, breakdown=breakdown,
            references=[RuleReference("Basic Set", "365"), RuleReference("Basic Set", "99"),
                        RuleReference("Powers", "58"), RuleReference("Supers", "24-25")],
        )
