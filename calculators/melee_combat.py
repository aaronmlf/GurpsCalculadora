"""Melee combat and Basic Set + Martial Arts grappling for GURPS 4e."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from calculators.injury import (
    CombatantState,
    DamagePacket,
    InjuryEngine,
    InjuryInput,
    InjuryResult,
    OptionalInjuryRules,
    RuleReference,
    StateDelta,
    hit_location_penalty,
)
from utils.dice_roller import evaluate_success_roll, get_damage_dice, roll_3d6, roll_dice
from calculators.strength import DamageBonusInput, EffortOption, StrengthEngine, StrengthProfile


@dataclass
class MeleeDamageMode:
    damage: str
    damage_type: str
    reach: List[str] = field(default_factory=lambda: ["C"])
    parry: str = "0"
    armor_divisor: float = 1.0
    minimum_st: int = 0
    two_handed: bool = False
    becomes_unready: bool = False
    requires_ready_to_change_reach: bool = False
    attack_label: str = ""
    linked_effects: List[Dict[str, Any]] = field(default_factory=list)
    raw: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MeleeDamageMode":
        data = dict(value)
        reach = data.get("reach", ["C"])
        if isinstance(reach, str):
            data["reach"] = [part.strip() for part in reach.split(",") if part.strip()]
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MeleeWeaponRecord:
    identifier: str
    source: str
    page: str
    name: str
    tech_level: str
    category: str
    skills: List[str]
    damage_modes: List[MeleeDamageMode]
    cost: str = ""
    weight: float = 0.0
    legality_class: str = ""
    quality: str = "normal"
    natural_weapon: bool = False
    training_weapon: bool = False
    tags: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    original: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MeleeWeaponRecord":
        data = dict(value)
        data["damage_modes"] = [MeleeDamageMode.from_dict(mode) for mode in data.get("damage_modes", [])]
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TechniqueRecord:
    identifier: str
    source: str
    page: str
    name: str
    difficulty: str
    prerequisites: List[str]
    defaults: List[str]
    maximum: str
    profile: str = "realistic"
    silly: bool = False
    automatable: bool = False
    attack_modifier: int = 0
    defense_modifier: int = 0
    damage_modifier: int = 0
    damage_per_die: int = 0
    effects: Dict[str, Any] = field(default_factory=dict)
    style_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    original: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TechniqueRecord":
        return cls(**dict(value))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StyleRecord:
    identifier: str
    source: str
    page: str
    name: str
    required_skills: List[str]
    techniques: List[str]
    cinematic_skills: List[str] = field(default_factory=list)
    cinematic_techniques: List[str] = field(default_factory=list)
    perks: List[str] = field(default_factory=list)
    optional_traits: List[str] = field(default_factory=list)
    minimum_cost: int = 1
    profile: str = "realistic"
    origin: str = ""
    period: str = ""
    original: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StyleRecord":
        return cls(**dict(value))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MeleeAttackInput:
    weapon: MeleeWeaponRecord
    attacker: CombatantState = field(default_factory=lambda: CombatantState(identifier="attacker", name="Attacker"))
    target: CombatantState = field(default_factory=lambda: CombatantState(identifier="target", name="Target"))
    profile: str = "basic"
    source_set: List[str] = field(default_factory=lambda: ["Basic Set"])
    skill: int = 12
    damage_mode: int = 0
    maneuver: str = "attack"
    maneuver_option: str = ""
    technique: Optional[TechniqueRecord] = None
    style: Optional[StyleRecord] = None
    allow_silly: bool = False
    distance_yards: float = 1.0
    hit_location: str = "torso"
    deceptive_attack_penalty: int = 0
    telegraphic_attack: bool = False
    rapid_strike_attacks: int = 1
    trained_by_master: bool = False
    weapon_master: bool = False
    strength_profile: Optional[StrengthProfile] = None
    effort: EffortOption = field(default_factory=EffortOption)
    weapon_skill_relative: int = 0
    dual_weapon_attack: bool = False
    offhand: bool = False
    ambidextrous: bool = False
    grip: str = "normal"
    weapon_ready: bool = True
    attacker_posture_modifier: int = 0
    target_posture_modifier: int = 0
    evaluate_turns: int = 0
    feint_defense_penalty: int = 0
    feint_condition: str = ""
    feint_target_skill: Optional[int] = None
    feint_roll: Optional[int] = None
    feint_target_roll: Optional[int] = None
    stun_recovery_roll: Optional[int] = None
    new_posture: str = "standing"
    custom_modifier: int = 0
    target_aware: bool = True
    defense_type: str = "dodge"
    defense_score: Optional[int] = None
    defense_attempt_number: int = 1
    defender_fencing: bool = False
    defender_trained_by_master: bool = False
    retreat: str = "none"
    optional_injury_rules: OptionalInjuryRules = field(default_factory=OptionalInjuryRules)
    attack_rolls: List[int] = field(default_factory=list)
    defense_rolls: List[int] = field(default_factory=list)
    damage_rolls: List[int] = field(default_factory=list)
    knockdown_rolls: List[int] = field(default_factory=list)
    consciousness_rolls: List[int] = field(default_factory=list)
    death_rolls: List[List[int]] = field(default_factory=list)


@dataclass
class MeleeAttackResult:
    valid: bool
    errors: List[str]
    profile: str
    modifiers: List[Dict[str, Any]]
    attack_count: int
    effective_skill: int
    probability: float
    defense_score: Optional[int]
    defense_restrictions: List[str] = field(default_factory=list)
    attacks: List[Dict[str, Any]] = field(default_factory=list)
    attacker_delta: StateDelta = field(default_factory=StateDelta)
    state_delta: StateDelta = field(default_factory=StateDelta)
    pending_effects: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    references: List[RuleReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GrappleActionInput:
    actor: CombatantState
    target: CombatantState
    action: str = "grapple"
    profile: str = "basic"
    skill: int = 12
    resistance: Optional[int] = None
    defense_score: Optional[int] = None
    defense_type: str = "dodge"
    location: str = "torso"
    two_handed: bool = True
    technique: Optional[TechniqueRecord] = None
    attack_roll: Optional[int] = None
    defense_roll: Optional[int] = None
    actor_contest_roll: Optional[int] = None
    target_contest_roll: Optional[int] = None
    damage_roll: Optional[int] = None


@dataclass
class GrappleActionResult:
    valid: bool
    errors: List[str]
    action: str
    success: bool = False
    attack: Optional[Dict[str, Any]] = None
    defense: Optional[Dict[str, Any]] = None
    contest: Optional[Dict[str, Any]] = None
    damage: Optional[InjuryResult] = None
    actor_delta: StateDelta = field(default_factory=StateDelta)
    target_delta: StateDelta = field(default_factory=StateDelta)
    pending_effects: List[Dict[str, Any]] = field(default_factory=list)
    references: List[RuleReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_NON_ATTACK_MANEUVERS = {"evaluate", "feint", "ready", "change_posture", "do_nothing", "wait"}
_MARTIAL_ARTS_MANEUVERS = {"committed_determined", "committed_strong", "defensive_attack"}
_ALL_OUT_MANEUVERS = {"all_out_determined", "all_out_strong", "all_out_double", "all_out_feint"}


def success_probability(target: int) -> float:
    successes = sum(
        1 for first in range(1, 7) for second in range(1, 7) for third in range(1, 7)
        if evaluate_success_roll(target, first + second + third)["success"]
    )
    return round(100.0 * successes / 216.0, 2)


def _modifier(key: str, value: int, source: str, page: str, detail: str = "") -> Dict[str, Any]:
    return {"key": key, "value": value, "source": source, "page": page, "detail": detail}


def _parse_parry(value: str) -> Tuple[int, bool, bool]:
    text = str(value).upper()
    match = re.search(r"[+-]?\d+", text)
    return (int(match.group(0)) if match else 0, "F" in text, "U" in text)


def _damage_expression(st: int, printed: str) -> str:
    match = re.fullmatch(r"(thr|sw)([+-]\d+)?", printed.strip(), re.I)
    if not match:
        return printed
    thrust, swing = get_damage_dice(st)
    base = thrust if match.group(1).lower() == "thr" else swing
    return _modify_damage(base, int(match.group(2) or 0))


def _modify_damage(expression: str, flat: int = 0, per_die: int = 0) -> str:
    match = re.fullmatch(r"(\d+)d(?:([+-]\d+))?", expression.strip(), re.I)
    if not match:
        return expression
    dice = int(match.group(1))
    total = int(match.group(2) or 0) + flat + dice * per_die
    return f"{dice}d" + (f"{total:+d}" if total else "")


def _reach_allows(reaches: Sequence[str], distance: float) -> bool:
    for raw in reaches:
        token = str(raw).strip().upper().replace("*", "")
        if token == "C" and distance <= 0.5:
            return True
        if token.isdigit() and math.isclose(distance, float(token), abs_tol=0.01):
            return True
        match = re.fullmatch(r"(\d+)-(\d+)", token)
        if match and int(match.group(1)) <= distance <= int(match.group(2)):
            return True
    return False


def _merge_delta(target: StateDelta, addition: StateDelta) -> None:
    target.hp_change += addition.hp_change
    target.fp_change += addition.fp_change
    target.shock = max(target.shock, addition.shock)
    if addition.posture is not None:
        target.posture = addition.posture
    for attr in ("set_stunned", "set_unconscious", "set_dead"):
        value = getattr(addition, attr)
        if value is not None:
            setattr(target, attr, value)
    for attr in (
        "add_conditions", "remove_conditions", "crippled_locations",
        "destroyed_locations", "pending_checks", "notes",
    ):
        current = getattr(target, attr)
        for value in getattr(addition, attr):
            if value not in current:
                current.append(deepcopy(value))
    target.wounds.extend(deepcopy(addition.wounds))
    for key, value in addition.armor_dr_loss.items():
        target.armor_dr_loss[key] = target.armor_dr_loss.get(key, 0) + value
    target.grapple_updates.update(deepcopy(addition.grapple_updates))


def _preview_apply(state: CombatantState, delta: StateDelta) -> None:
    state.current_hp += delta.hp_change
    state.current_fp += delta.fp_change
    state.shock = max(state.shock, delta.shock)
    state.wounds.extend(deepcopy(delta.wounds))
    for item in delta.crippled_locations:
        if item not in state.crippled_locations:
            state.crippled_locations.append(item)
    for item in delta.destroyed_locations:
        if item not in state.destroyed_locations:
            state.destroyed_locations.append(item)


class MeleeCombatCalculator:
    """Calculate or resolve one melee maneuver against one target."""

    PROFILES = ("basic", "realistic", "cinematic")

    def __init__(self) -> None:
        self.injury_engine = InjuryEngine()
        self.strength_engine = StrengthEngine()

    @staticmethod
    def _mode(data: MeleeAttackInput) -> MeleeDamageMode:
        if not data.weapon.damage_modes or not 0 <= data.damage_mode < len(data.weapon.damage_modes):
            raise ValueError("invalid_damage_mode")
        return data.weapon.damage_modes[data.damage_mode]

    def _validate(self, data: MeleeAttackInput) -> List[str]:
        errors: List[str] = []
        if data.profile not in self.PROFILES:
            errors.append("invalid_profile")
        if data.skill < 0 or data.attacker.st < 1:
            errors.append("invalid_attacker_stats")
        if data.target.max_hp < 1:
            errors.append("invalid_target_stats")
        if data.maneuver in _MARTIAL_ARTS_MANEUVERS and data.profile == "basic":
            errors.append("martial_arts_maneuver_outside_profile")
        if data.telegraphic_attack and data.profile == "basic":
            errors.append("telegraphic_attack_outside_profile")
        if data.telegraphic_attack and data.deceptive_attack_penalty:
            errors.append("telegraphic_and_deceptive_conflict")
        if data.deceptive_attack_penalty < 0 or data.deceptive_attack_penalty % 2:
            errors.append("invalid_deceptive_attack")
        if data.rapid_strike_attacks < 1:
            errors.append("invalid_rapid_strike_count")
        if data.profile == "basic" and data.rapid_strike_attacks > 2:
            errors.append("too_many_basic_rapid_strikes")
        if data.defense_attempt_number < 1:
            errors.append("invalid_defense_attempt")
        if data.technique:
            if data.technique.profile == "cinematic" and data.profile != "cinematic":
                errors.append("cinematic_technique_outside_profile")
            if data.technique.silly and not (data.profile == "cinematic" and data.allow_silly):
                errors.append("silly_technique_disabled")
            if data.profile == "basic" and data.technique.source == "Martial Arts":
                errors.append("technique_outside_profile")
        try:
            mode = self._mode(data)
            if data.maneuver not in _NON_ATTACK_MANEUVERS and not _reach_allows(mode.reach, data.distance_yards):
                errors.append("target_out_of_reach")
            if not data.weapon_ready and data.maneuver not in {"ready", "do_nothing"}:
                errors.append("weapon_not_ready")
            if mode.two_handed and data.grip == "one_handed":
                errors.append("two_handed_weapon")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            hit_location_penalty(data.hit_location, data.profile)
        except ValueError as exc:
            errors.append(str(exc))
        return list(dict.fromkeys(errors))

    def calculate(self, data: MeleeAttackInput) -> MeleeAttackResult:
        errors = self._validate(data)
        modifiers: List[Dict[str, Any]] = []
        mode = self._mode(data) if data.weapon.damage_modes and 0 <= data.damage_mode < len(data.weapon.damage_modes) else None
        attack_count = max(1, data.rapid_strike_attacks)
        if data.maneuver == "all_out_double":
            attack_count = max(2, attack_count)
        if data.dual_weapon_attack:
            attack_count = max(2, attack_count)
        if mode and data.maneuver not in _NON_ATTACK_MANEUVERS:
            effort_result = self._strength_damage(data, mode)
            if effort_result is not None:
                errors.extend(effort_result.errors)
                if effort_result.fp_cost * attack_count > data.attacker.current_fp:
                    errors.append("insufficient_fp")
            elif data.effort.mighty_blows or data.effort.super_effort_levels or data.effort.extra_effort_percent:
                errors.append("effort_requires_strength_based_damage")

        if data.hit_location != "torso":
            try:
                modifiers.append(_modifier(
                    "hit_location", hit_location_penalty(data.hit_location, data.profile),
                    "Martial Arts" if data.hit_location in {"jaw", "neck_artery", "limb_artery", "elbow", "knee", "shoulder", "hip", "nose", "ear", "spine"} else "Basic Set",
                    "137" if data.profile != "basic" else "398-400", data.hit_location,
                ))
            except ValueError:
                pass
        if data.maneuver == "all_out_determined":
            modifiers.append(_modifier("all_out_determined", 4, "Basic Set", "365"))
        elif data.maneuver == "move_and_attack":
            modifiers.append(_modifier("move_and_attack", -4, "Basic Set", "365"))
        elif data.maneuver == "committed_determined":
            modifiers.append(_modifier("committed_determined", 2, "Martial Arts", "99"))
        if data.telegraphic_attack:
            modifiers.append(_modifier("telegraphic_attack", 4, "Martial Arts", "113"))
        if data.deceptive_attack_penalty:
            modifiers.append(_modifier(
                "deceptive_attack", -data.deceptive_attack_penalty, "Basic Set", "369",
                f"defense {-data.deceptive_attack_penalty // 2}",
            ))
        if attack_count > 1 and data.maneuver != "all_out_double" and not data.dual_weapon_attack:
            per_extra = 3 if (data.trained_by_master or data.weapon_master) else 6
            penalty = -per_extra * (attack_count - 1)
            modifiers.append(_modifier("rapid_strike", penalty, "Martial Arts", "127", str(attack_count)))
        if data.dual_weapon_attack:
            modifiers.append(_modifier("dual_weapon_attack", -4, "Basic Set", "417"))
        if data.offhand and not data.ambidextrous:
            modifiers.append(_modifier("offhand", -4, "Basic Set", "14"))
        if data.attacker.shock:
            modifiers.append(_modifier("shock", -min(4, data.attacker.shock), "Basic Set", "419"))
        if mode and mode.minimum_st > data.attacker.st:
            modifiers.append(_modifier(
                "insufficient_strength", -(mode.minimum_st - data.attacker.st), "Basic Set", "270"
            ))
        if data.attacker_posture_modifier:
            modifiers.append(_modifier("attacker_posture", data.attacker_posture_modifier, "Basic Set", "551"))
        if data.evaluate_turns:
            modifiers.append(_modifier("evaluate", min(3, max(0, data.evaluate_turns)), "Basic Set", "364"))
        if data.technique:
            modifiers.append(_modifier(
                "technique", data.technique.attack_modifier, data.technique.source,
                data.technique.page, data.technique.name,
            ))
        if data.custom_modifier:
            modifiers.append(_modifier("custom", data.custom_modifier, "User", "-"))

        effective = data.skill + sum(item["value"] for item in modifiers)
        if data.maneuver == "move_and_attack":
            effective = min(effective, 9)
        if data.deceptive_attack_penalty and effective < 10:
            errors.append("deceptive_attack_requires_final_skill_10")

        defense_score: Optional[int]
        defense_restrictions: List[str] = []
        if (
            not data.target_aware or data.target.unconscious
            or "all_out_attack_no_defense" in data.target.conditions
        ):
            defense_score = None
            defense_restrictions.append("no_active_defense")
        else:
            base = data.defense_score
            if base is None:
                base = {
                    "dodge": data.target.dodge,
                    "parry": data.target.parry,
                    "block": data.target.block,
                }.get(data.defense_type)
            defense_score = base
            if defense_score is not None:
                defense_score -= data.deceptive_attack_penalty // 2
                defense_score += data.target_posture_modifier
                defense_score -= max(0, data.feint_defense_penalty)
                if "committed_attack_defense_restrictions" in data.target.conditions:
                    defense_score -= 2
                if (
                    "defensive_attack_parry_bonus" in data.target.conditions
                    and data.defense_type == "parry"
                ):
                    defense_score += 1
                if data.telegraphic_attack:
                    defense_score += 2
                if (
                    data.retreat != "none"
                    and "committed_attack_defense_restrictions" not in data.target.conditions
                ):
                    if data.defense_type == "dodge":
                        defense_score += 3
                    elif data.defense_type == "parry" and data.defender_fencing:
                        defense_score += 3
                    else:
                        defense_score += 1
                if data.defense_type == "parry" and data.defense_attempt_number > 1:
                    divisor = 2 if (data.defender_fencing or data.defender_trained_by_master) else 1
                    if data.defender_fencing and data.defender_trained_by_master:
                        divisor = 4
                    defense_score -= (4 // divisor) * (data.defense_attempt_number - 1)
                if data.defense_type == "block" and data.defense_attempt_number > 1:
                    defense_restrictions.append("block_already_used")
                    errors.append("multiple_block_not_allowed")
                if data.target.stunned:
                    defense_score -= 4

        if data.maneuver in _ALL_OUT_MANEUVERS:
            defense_restrictions.append("attacker_no_active_defense_until_next_turn")
        elif data.maneuver.startswith("committed_"):
            defense_restrictions.extend(["attacker_defenses_minus_2", "attacker_cannot_retreat"])
        elif data.maneuver == "defensive_attack":
            defense_restrictions.append("attacker_same_weapon_parry_plus_1")

        pending: List[Dict[str, Any]] = []
        if data.maneuver in _NON_ATTACK_MANEUVERS:
            pending.append({"kind": data.maneuver, "requires_follow_up": data.maneuver in {"evaluate", "wait"}})
        if data.technique and not data.technique.automatable:
            pending.append({
                "kind": "technique_effect", "technique": data.technique.identifier,
                "effects": deepcopy(data.technique.effects), "source": data.technique.source,
                "page": data.technique.page,
            })

        notes: List[str] = []
        if data.style and data.technique:
            allowed = set(data.style.techniques) | set(data.style.cinematic_techniques)
            if data.technique.name not in allowed and data.technique.identifier not in allowed:
                notes.append("technique_not_listed_in_selected_style")
        return MeleeAttackResult(
            valid=not errors,
            errors=list(dict.fromkeys(errors)),
            profile=data.profile,
            modifiers=modifiers,
            attack_count=attack_count,
            effective_skill=effective,
            probability=success_probability(effective),
            defense_score=defense_score,
            defense_restrictions=defense_restrictions,
            pending_effects=pending,
            notes=notes,
            references=[
                RuleReference("Basic Set", "369-371"),
                RuleReference("Basic Set", "374-377"),
                RuleReference("Martial Arts", "96-129") if data.profile != "basic" else RuleReference("Basic Set", "398-400"),
            ],
        )

    def _strength_damage(self, data: MeleeAttackInput, mode: MeleeDamageMode):
        printed = re.fullmatch(r"(thr|sw)([+-]\d+)?", mode.damage.strip(), re.I)
        if not printed:
            return None
        profile = deepcopy(data.strength_profile) if data.strength_profile else StrengthProfile(
            st=data.attacker.st, hp=data.attacker.max_hp, current_fp=data.attacker.current_fp,
            trained_by_master=data.trained_by_master, weapon_master=data.weapon_master,
        )
        profile.current_fp = data.attacker.current_fp
        profile.max_fp = data.attacker.max_fp
        if mode.minimum_st:
            # B270: maximum effective ST for weapon damage is three times Min ST.
            profile.st = min(profile.st + profile.striking_st + profile.arm_st, 3 * mode.minimum_st)
            profile.striking_st = profile.arm_st = 0
        return self.strength_engine.calculate_damage(DamageBonusInput(
            profile=profile, rules_profile=data.profile,
            basis="thrust" if printed.group(1).lower() == "thr" else "swing",
            weapon_modifier=int(printed.group(2) or 0), maneuver=data.maneuver,
            effort=data.effort, weapon_master=data.weapon_master,
            weapon_skill_relative=data.weapon_skill_relative,
            technique_flat_bonus=data.technique.damage_modifier if data.technique else 0,
            technique_per_die=data.technique.damage_per_die if data.technique else 0,
        ))

    def _damage_for_hit(self, data: MeleeAttackInput, mode: MeleeDamageMode,
                        supplied: Optional[int], preview_target: CombatantState,
                        hit_index: int) -> Tuple[Dict[str, Any], InjuryResult]:
        damage_st = data.attacker.st
        if mode.minimum_st:
            damage_st = min(damage_st, 3 * mode.minimum_st)
        printed_match = re.fullmatch(r"(thr|sw)([+-]\d+)?", mode.damage.strip(), re.I)
        if printed_match:
            damage_result = self._strength_damage(data, mode)
            expression = damage_result.final_damage
        else:
            expression = _damage_expression(damage_st, mode.damage)
        match = re.fullmatch(r"(\d+)d(?:([+-]\d+))?", expression)
        dice_count = int(match.group(1)) if match else 1
        flat = 0
        per_die = 0
        if data.maneuver == "all_out_strong" and not printed_match:
            flat += max(2, dice_count)
        elif data.maneuver == "committed_strong":
            flat += max(1, dice_count // 2)
        elif data.maneuver == "defensive_attack":
            flat -= max(2, dice_count)
        if data.technique and not printed_match:
            flat += data.technique.damage_modifier
            per_die += data.technique.damage_per_die
        expression = _modify_damage(expression, flat, per_die)
        if supplied is None:
            basic, dice = roll_dice(expression)
        else:
            basic, dice = max(0, int(supplied)), None
        knockdown = data.knockdown_rolls[hit_index] if hit_index < len(data.knockdown_rolls) else None
        consciousness = (
            data.consciousness_rolls[hit_index] if hit_index < len(data.consciousness_rolls) else None
        )
        deaths = data.death_rolls[hit_index] if hit_index < len(data.death_rolls) else None
        injury = self.injury_engine.resolve(InjuryInput(
            packet=DamagePacket(
                basic_damage=basic,
                damage_type=mode.damage_type,
                armor_divisor=mode.armor_divisor,
                hit_location=data.hit_location,
                source=data.weapon.source,
                page=data.weapon.page,
                expression=expression,
                linked_effects=deepcopy(mode.linked_effects),
                raw=mode.raw,
            ),
            target=preview_target,
            profile=data.profile,
            optional_rules=data.optional_injury_rules,
        ), knockdown_roll=knockdown, consciousness_roll=consciousness, death_rolls=deaths)
        return {
            "expression": expression, "rolls": dice, "basic_damage": basic,
            "mode": mode.attack_label, "damage_type": mode.damage_type,
            "injury": injury.to_dict(),
        }, injury

    def resolve(self, data: MeleeAttackInput, *, attack_rolls: Optional[Sequence[int]] = None,
                defense_rolls: Optional[Sequence[int]] = None,
                damage_rolls: Optional[Sequence[int]] = None,
                resolve_defense: bool = True, resolve_damage: bool = True) -> MeleeAttackResult:
        result = self.calculate(data)
        if not result.valid:
            return result
        if data.maneuver == "feint":
            target_skill = data.feint_target_skill
            if target_skill is None:
                target_skill = data.defense_score if data.defense_score is not None else data.target.dx
            contest = GrapplingEngine._contest(
                result.effective_skill, max(0, int(target_skill)),
                data.feint_roll, data.feint_target_roll,
            )
            penalty = max(0, contest["actor_margin"] - contest["target_margin"]) if contest["actor_wins"] else 0
            result.pending_effects = [item for item in result.pending_effects if item.get("kind") != "feint"]
            result.pending_effects.append({
                "kind": "feint", "contest": contest, "defense_penalty": penalty,
                "applies_to": "next_melee_defense", "requires_follow_up": True,
            })
            if penalty:
                result.state_delta.add_conditions.append(
                    f"feint:{data.attacker.identifier}:{penalty}"
                )
            return result
        if data.maneuver == "do_nothing" and data.attacker.stunned:
            recovery = GrapplingEngine._roll(data.attacker.ht, data.stun_recovery_roll)
            result.pending_effects.append({"kind": "stun_recovery", "roll": recovery})
            if recovery["success"]:
                result.attacker_delta.set_stunned = False
                result.attacker_delta.remove_conditions.append("stunned")
            return result
        if data.maneuver in _NON_ATTACK_MANEUVERS:
            if data.maneuver == "ready":
                result.attacker_delta.remove_conditions.append("weapon_unready")
            elif data.maneuver == "change_posture":
                result.attacker_delta.posture = data.new_posture
                result.attacker_delta.remove_conditions.extend([
                    "crouching", "kneeling", "sitting", "crawling", "prone", "lying",
                ])
                if data.new_posture != "standing":
                    result.attacker_delta.add_conditions.append(data.new_posture)
            return result
        mode = self._mode(data)
        supplied_attacks = list(attack_rolls if attack_rolls is not None else data.attack_rolls)
        supplied_defenses = list(defense_rolls if defense_rolls is not None else data.defense_rolls)
        supplied_damage = list(damage_rolls if damage_rolls is not None else data.damage_rolls)
        preview_target = deepcopy(data.target)
        aggregate = StateDelta()
        defense_index = 0
        damage_index = 0
        for index in range(result.attack_count):
            effort_result = self._strength_damage(data, mode)
            if effort_result is not None:
                # B357: pay per attempted attack, even on a miss or successful defense.
                _merge_delta(result.attacker_delta, effort_result.state_delta)
            if index < len(supplied_attacks):
                attack_roll, attack_dice = supplied_attacks[index], None
            else:
                attack_roll, attack_dice = roll_3d6()
            attack_outcome = evaluate_success_roll(result.effective_skill, attack_roll)
            if data.effort.mighty_blows and attack_outcome["critical_failure"]:
                result.attacker_delta.hp_change -= 1
                result.pending_effects.append({
                    "kind": "extra_effort_critical_injury", "injury": 1,
                    "location": "attacking_limb", "ignores_dr": True,
                    "source": "Basic Set", "page": "357",
                    "requires_location_confirmation": True,
                })
            attack_record: Dict[str, Any] = {
                "index": index + 1,
                "attack": {"roll": attack_roll, "dice": attack_dice, **attack_outcome},
                "defense": None,
                "hit": False,
                "damage": None,
            }
            if not attack_outcome["success"]:
                result.attacks.append(attack_record)
                continue
            defended = False
            if (resolve_defense and result.defense_score is not None and not attack_outcome["critical_success"]):
                defense_target = result.defense_score + (
                    data.feint_defense_penalty if index > 0 else 0
                )
                if defense_index < len(supplied_defenses):
                    defense_roll, defense_dice = supplied_defenses[defense_index], None
                else:
                    defense_roll, defense_dice = roll_3d6()
                defense_index += 1
                defense_outcome = evaluate_success_roll(defense_target, defense_roll)
                defended = bool(defense_outcome["success"])
                attack_record["defense"] = {
                    "type": data.defense_type, "target": defense_target,
                    "roll": defense_roll, "dice": defense_dice, **defense_outcome,
                }
            attack_record["hit"] = not defended
            if attack_record["hit"] and resolve_damage:
                supplied = supplied_damage[damage_index] if damage_index < len(supplied_damage) else None
                damage_index += 1
                damage_record, injury = self._damage_for_hit(data, mode, supplied, preview_target, index)
                attack_record["damage"] = damage_record
                _merge_delta(aggregate, injury.state_delta)
                _preview_apply(preview_target, injury.state_delta)
            result.attacks.append(attack_record)
        attacker_delta = StateDelta()
        if data.maneuver in _ALL_OUT_MANEUVERS:
            attacker_delta.add_conditions.append("all_out_attack_no_defense")
        elif data.maneuver.startswith("committed_"):
            attacker_delta.add_conditions.append("committed_attack_defense_restrictions")
        elif data.maneuver == "defensive_attack":
            attacker_delta.add_conditions.append("defensive_attack_parry_bonus")
        if mode.becomes_unready and any(item["hit"] for item in result.attacks):
            attacker_delta.add_conditions.append("weapon_unready")
        if data.feint_condition:
            aggregate.remove_conditions.append(data.feint_condition)
        _merge_delta(attacker_delta, result.attacker_delta)
        result.attacker_delta = attacker_delta
        result.state_delta = aggregate
        return result


class GrapplingEngine:
    """Resolve state transitions for Basic Set and Martial Arts grappling."""

    ACTIONS = {
        "grapple", "shift_grip", "break_free", "takedown", "pin",
        "choke", "strangle", "arm_lock", "leg_lock", "neck_lock",
        "throw", "wrench", "shove",
    }

    def __init__(self) -> None:
        self.injury_engine = InjuryEngine()

    @staticmethod
    def _roll(target: int, supplied: Optional[int]) -> Dict[str, Any]:
        if supplied is None:
            chosen, dice = roll_3d6()
        else:
            chosen, dice = supplied, None
        return {"target": target, "roll": chosen, "dice": dice, **evaluate_success_roll(target, chosen)}

    @staticmethod
    def _contest(actor_skill: int, target_skill: int, actor_roll: Optional[int],
                 target_roll: Optional[int]) -> Dict[str, Any]:
        actor = GrapplingEngine._roll(actor_skill, actor_roll)
        target = GrapplingEngine._roll(target_skill, target_roll)
        actor_margin = actor_skill - actor["roll"]
        target_margin = target_skill - target["roll"]
        actor_wins = actor["success"] and (not target["success"] or actor_margin > target_margin)
        return {
            "actor": actor, "target": target, "actor_margin": actor_margin,
            "target_margin": target_margin, "actor_wins": actor_wins,
            "tie": actor["success"] == target["success"] and actor_margin == target_margin,
        }

    def resolve(self, data: GrappleActionInput) -> GrappleActionResult:
        errors: List[str] = []
        if data.action not in self.ACTIONS:
            errors.append("invalid_grapple_action")
        if data.profile not in ("basic", "realistic", "cinematic"):
            errors.append("invalid_profile")
        martial_actions = {"shift_grip", "arm_lock", "leg_lock", "neck_lock", "throw", "wrench", "shove"}
        if data.profile == "basic" and data.action in martial_actions:
            errors.append("martial_arts_grapple_action_outside_profile")
        offensive_relation = data.target.grapples.get(data.actor.identifier)
        escape_relation = data.actor.grapples.get(data.target.identifier)
        relation = escape_relation if data.action == "break_free" else offensive_relation
        if data.action not in {"grapple", "shove"} and relation is None:
            errors.append("target_not_grappled_by_actor")
        if data.action == "pin" and data.target.posture not in {"prone", "lying"}:
            errors.append("pin_requires_grounded_target")
        result = GrappleActionResult(
            valid=not errors, errors=errors, action=data.action,
            references=[
                RuleReference("Basic Set", "370-371"),
                RuleReference("Martial Arts", "115-119") if data.profile != "basic" else RuleReference("Basic Set", "370"),
            ],
        )
        if errors:
            return result

        key = data.actor.identifier
        if data.action in {"grapple", "shove"}:
            result.attack = self._roll(data.skill, data.attack_roll)
            if not result.attack["success"]:
                return result
            if data.target.aware and not result.attack["critical_success"]:
                defense_target = data.defense_score
                if defense_target is None:
                    defense_target = {
                        "dodge": data.target.dodge,
                        "parry": data.target.parry,
                        "block": data.target.block,
                    }.get(data.defense_type, data.target.dodge)
                result.defense = self._roll(defense_target, data.defense_roll)
                if result.defense["success"]:
                    return result
            result.success = True
            if data.action == "grapple":
                result.target_delta.grapple_updates[key] = {
                    "attacker": key, "location": data.location,
                    "two_handed": data.two_handed, "dx_penalty": -4,
                    "state": "grappled", "source": "Basic Set", "page": "370",
                }
                result.target_delta.add_conditions.append("grappled")
            else:
                result.pending_effects.append({"kind": "knockback", "source": "Martial Arts", "page": "118"})
            return result

        resistance = data.resistance if data.resistance is not None else max(data.target.st, data.target.dx)
        if data.action == "shift_grip":
            result.attack = self._roll(data.skill, data.attack_roll)
            result.success = bool(result.attack["success"])
            if result.success and relation is not None:
                update = deepcopy(relation)
                update["location"] = data.location
                result.target_delta.grapple_updates[key] = update
            return result

        result.contest = self._contest(
            max(data.skill, data.actor.st), resistance,
            data.actor_contest_roll, data.target_contest_roll,
        )
        if not result.contest["actor_wins"]:
            return result
        result.success = True
        if data.action == "break_free":
            result.actor_delta.grapple_updates.pop(data.target.identifier, None)
            result.actor_delta.grapple_updates[data.target.identifier] = None
            result.actor_delta.remove_conditions.append("grappled")
        elif data.action == "takedown":
            result.target_delta.posture = "prone"
            result.target_delta.add_conditions.append("prone")
        elif data.action == "pin":
            update = deepcopy(relation or {})
            update["state"] = "pinned"
            result.target_delta.grapple_updates[key] = update
            result.target_delta.add_conditions.append("pinned")
        elif data.action in {"choke", "strangle"}:
            update = deepcopy(relation or {})
            update["state"] = "choked"
            update["location"] = "neck"
            result.target_delta.grapple_updates[key] = update
            result.target_delta.add_conditions.append("choked")
            result.pending_effects.append({"kind": "suffocation", "fp_loss": 1, "per_seconds": 1})
        elif data.action in {"arm_lock", "leg_lock", "neck_lock"}:
            update = deepcopy(relation or {})
            update["state"] = data.action
            update["location"] = {"arm_lock": "arm", "leg_lock": "leg", "neck_lock": "neck"}[data.action]
            result.target_delta.grapple_updates[key] = update
            result.target_delta.add_conditions.append(data.action)
        elif data.action == "throw":
            result.target_delta.posture = "prone"
            result.target_delta.add_conditions.append("prone")
            result.pending_effects.append({"kind": "throw_damage", "damage": "thr-1 cr"})
        elif data.action == "wrench":
            location = (relation or {}).get("location", data.location)
            expression = get_damage_dice(data.actor.st)[0]
            if data.damage_roll is None:
                basic, _ = roll_dice(expression)
            else:
                basic = max(0, data.damage_roll)
            result.damage = self.injury_engine.resolve(InjuryInput(
                packet=DamagePacket(
                    basic_damage=basic, damage_type="cr", hit_location=location,
                    source="Martial Arts", page="118", expression=expression,
                ),
                target=data.target,
                profile=data.profile,
            ))
            _merge_delta(result.target_delta, result.damage.state_delta)
        return result
