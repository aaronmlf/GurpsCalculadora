"""Advantage-based abilities, powers, and psionic use for GURPS 4e."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional

from calculators.injury import RuleReference, StateDelta
from calculators.magic import EffectPacket, ResistanceCheck, ResourcePool
from calculators.contests import long_distance_modifier, quick_contest, supernatural_target
from utils.dice_roller import evaluate_success_roll, get_range_modifier, roll_3d6


@dataclass
class AdvantageRecord:
    identifier: str
    name: str
    source: str
    page: str
    base_cost: float
    cost_per_level: float = 0.0
    levels: int = 1
    tags: List[str] = field(default_factory=list)


@dataclass
class ModifierRecord:
    identifier: str
    name: str
    source: str
    page: str
    percent: int
    kind: str = "enhancement"
    applies_to: List[str] = field(default_factory=list)


@dataclass
class PowerRecord:
    identifier: str
    name: str
    source: str
    page: str
    power_modifier: int = -10
    talents: List[str] = field(default_factory=list)
    origin: str = "supernatural"


@dataclass
class AbilityBuildInput:
    advantage: AdvantageRecord
    modifiers: List[ModifierRecord] = field(default_factory=list)
    power: Optional[PowerRecord] = None
    levels: Optional[int] = None
    alternate_ability: bool = False


@dataclass
class AbilityBuildResult:
    valid: bool
    errors: List[str]
    unmodified_cost: float
    net_modifier_percent: int
    modified_cost: int
    breakdown: List[Dict[str, Any]]
    references: List[RuleReference]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PsiAbilityRecord:
    identifier: str
    name: str
    source: str
    page: str
    power: str
    skill: str
    base_skill: int = 10
    talent: str = ""
    activation_cost: int = 0
    range_model: str = "none"
    effects: List[EffectPacket] = field(default_factory=list)
    profile: str = "realistic"
    levels: Any = None
    cost: Any = None  # Character-point cost, never activation FP.
    notes: Optional[str] = None
    reference_only: bool = False
    operational_model: str = ''
    activation_time_seconds: Optional[int] = None
    character_points_by_level: List[int] = field(default_factory=list)
    range_by_level: List[str] = field(default_factory=list)
    activation_time_by_level: List[int] = field(default_factory=list)
    resist_attribute: str = ''

    @property
    def catalog_status(self) -> str:
        return 'reference_only' if self.reference_only else 'calculable'

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "PsiAbilityRecord":
        data = dict(value)
        data.setdefault('reference_only', 'activation_cost' not in value or not value.get('effects'))
        data["effects"] = [item if isinstance(item, EffectPacket) else EffectPacket(**item)
                           for item in data.get("effects", [])]
        return cls(**data)


@dataclass
class PsiTechniqueRecord:
    identifier: str
    name: str
    source: str
    page: str
    default_penalty: int
    maximum: int = 0
    cinematic: bool = False
    cost_fp: int = 0
    notes: Optional[str] = None


@dataclass
class PsiUseInput:
    ability: PsiAbilityRecord
    profile: str = "realistic"
    skill: int = 10
    talent: int = 0
    technique: Optional[PsiTechniqueRecord] = None
    technique_level: int = 0
    distance_yards: int = 0
    repeated_attempts: int = 0
    extra_effort: int = 0
    resources: ResourcePool = field(default_factory=ResourcePool)
    resistance: Optional[ResistanceCheck] = None
    roll: Optional[int] = None
    level: int = 1
    contact: str = 'none'
    target_living_sapient: bool = True
    repeat_cost_due: bool = True
    target_willing: bool = False
    target_restrained: bool = False
    changed_disadvantage_points: int = 5


@dataclass
class PsiUseResult:
    valid: bool
    errors: List[str]
    effective_skill: int
    fp_cost: int
    roll: Optional[Dict[str, Any]]
    resistance: Optional[ResistanceCheck]
    effects: List[EffectPacket]
    state_delta: StateDelta
    breakdown: List[Dict[str, Any]]
    pending_effects: List[Dict[str, Any]]
    references: List[RuleReference]
    activation_time_seconds: Optional[int] = None
    character_point_cost: Optional[int] = None
    resource_delta: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AbilityEngine:
    def calculate(self, data: AbilityBuildInput) -> AbilityBuildResult:
        errors: List[str] = []
        levels = data.levels if data.levels is not None else data.advantage.levels
        refs = [RuleReference(data.advantage.source, data.advantage.page), RuleReference("Basic Set", "101-117"),
                RuleReference("Powers", "7-13")]
        costs = (data.advantage.base_cost, data.advantage.cost_per_level)
        modifiers = [item.percent for item in data.modifiers] + ([data.power.power_modifier] if data.power else [])
        if (type(levels) is not int or levels < 1 or any(type(value) not in (int, float) or
                not math.isfinite(value) or value < 0 for value in costs) or
                any(type(value) is not int for value in modifiers)):
            return AbilityBuildResult(False, ["invalid_ability_cost"], 0, 0, 0, [], refs)
        base = data.advantage.base_cost
        if data.advantage.cost_per_level:
            base += data.advantage.cost_per_level * max(0, levels - 1)
        net = sum(item.percent for item in data.modifiers)
        breakdown = [{"key": item.identifier, "value": item.percent, "source": item.source, "page": item.page}
                     for item in data.modifiers]
        if data.power:
            net += data.power.power_modifier
            breakdown.append({"key": "power_modifier", "value": data.power.power_modifier,
                              "source": data.power.source, "page": data.power.page})
        if net < -80:
            net = -80
            breakdown.append({"key": "limitation_floor", "value": -80, "source": "Basic Set", "page": "110"})
        cost = max(1, math.ceil(base * (100 + net) / 100.0)) if base else 0
        if data.alternate_ability:
            cost = max(1, math.ceil(cost / 5.0))
            breakdown.append({"key": "alternate_ability", "value": "1/5", "source": "Powers", "page": "11"})
        return AbilityBuildResult(
            valid=not errors, errors=errors, unmodified_cost=base, net_modifier_percent=net,
            modified_cost=cost, breakdown=breakdown,
            references=refs,
        )


class PsionicEngine:
    def calculate(self, data: PsiUseInput) -> PsiUseResult:
        errors: List[str] = []
        if data.ability.reference_only or data.ability.operational_model not in {'', 'emotion_sense', 'mental_surgery'}:
            errors.append("catalog_reference_only")
        if data.profile not in {"basic", "realistic", "cinematic"}:
            errors.append("invalid_profile")
        numeric = (data.skill, data.talent, data.distance_yards, data.repeated_attempts,
                   data.extra_effort, data.resources.fp, data.resources.energy_reserve)
        integers = (data.skill, data.talent, data.repeated_attempts, data.extra_effort,
                    data.resources.fp, data.resources.energy_reserve)
        if (any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in numeric) or
                any(type(value) is not int for value in integers)):
            errors.append("invalid_psi_input")
            return PsiUseResult(False, errors, 0, 0, None, None, [], StateDelta(), [], [],
                                [RuleReference(data.ability.source, data.ability.page)])
        if data.profile == "basic":
            errors.append("psionics_outside_basic_profile")
        if data.technique and data.technique.cinematic and data.profile != "cinematic":
            errors.append("cinematic_psi_technique_outside_profile")
        effective = data.skill + data.talent
        breakdown: List[Dict[str, Any]] = []
        range_model = data.ability.range_model
        time = data.ability.activation_time_seconds
        time_levels = data.ability.activation_time_by_level
        points = None
        resistance = deepcopy(data.resistance)
        effects = deepcopy(data.ability.effects)
        model = data.ability.operational_model
        if model in {'emotion_sense', 'mental_surgery'}:
            if (type(data.level) is not int or not 1 <= data.level <= len(data.ability.range_by_level) or
                    len(data.ability.range_by_level) != len(data.ability.character_points_by_level) or
                    time_levels and len(time_levels) != len(data.ability.range_by_level)):
                errors.append('invalid_psi_level')
            else:
                range_model = data.ability.range_by_level[data.level - 1]
                points = data.ability.character_points_by_level[data.level - 1]
                if time_levels:
                    time = time_levels[data.level - 1]
            if model == 'emotion_sense' and not data.target_living_sapient:
                errors.append('psi_emotion_sense_target')
            if model == 'mental_surgery':
                if not (data.target_willing or data.target_restrained):
                    errors.append('psi_mental_surgery_control')
                if type(data.changed_disadvantage_points) is not int or data.changed_disadvantage_points < 1:
                    errors.append('psi_mental_surgery_points')
                else:
                    # Psionic Powers p. 61: -1 per complete five points.
                    penalty = -(data.changed_disadvantage_points // 5)
                    effective += penalty
                    breakdown.append({'key': 'psi_mental_surgery_points', 'value': penalty,
                                      'source': 'Psionic Powers', 'page': '61'})
                    for effect in effects:
                        effect.metadata['changed_disadvantage_points'] = data.changed_disadvantage_points
            if data.contact not in {'none', 'touch', 'skin'} or data.contact != 'none' and data.distance_yards:
                errors.append('invalid_psi_contact')
            if range_model == 'skin_contact' and (data.contact != 'skin' or data.distance_yards):
                errors.append('psi_skin_contact_required')
            elif range_model != 'skin_contact' and data.contact in {'touch', 'skin'}:
                bonus = 2 if data.contact == 'skin' else 1
                effective += bonus
                breakdown.append({'key': 'psi_contact', 'value': bonus, 'source': 'Psionic Powers', 'page': '6'})
            if model == 'mental_surgery' and data.target_willing:
                resistance = None
            elif resistance is None:
                errors.append('psi_requires_resistance')
            else:
                resistance.attribute = data.ability.resist_attribute
                resistance.living_or_sapient = True
            if data.technique is not None or data.extra_effort:
                errors.append('psi_unimplemented_option')
        elif data.technique:
            technique_bonus = min(data.technique.maximum, data.technique_level) + data.technique.default_penalty
            effective += technique_bonus
            breakdown.append({"key": "psi_technique", "value": technique_bonus,
                              "source": data.technique.source, "page": data.technique.page})
        if range_model == "speed_range":
            modifier = get_range_modifier(max(1, data.distance_yards))
            effective += modifier
            breakdown.append({"key": "range", "value": modifier, "source": "Basic Set", "page": "550"})
        elif range_model == 'long_distance':
            modifier = long_distance_modifier(data.distance_yards)
            effective += modifier
            breakdown.append({'key': 'long_distance', 'value': modifier, 'source': 'Basic Set', 'page': '241'})
        if data.repeated_attempts:
            penalty = -max(0, data.repeated_attempts)
            effective += penalty
            breakdown.append({"key": "repeated_attempt", "value": penalty,
                              "source": "Psionic Powers", "page": "6"})
        fp_cost = (data.ability.activation_cost + max(0, data.extra_effort) +
                   (data.technique.cost_fp if data.technique else 0) +
                   int(bool(data.repeated_attempts) and data.repeat_cost_due))
        if fp_cost > data.resources.fp + data.resources.energy_reserve:
            errors.append("insufficient_energy")
        if resistance is not None and (type(resistance.target) is not int or resistance.target < 0):
            errors.append('invalid_psi_input')
        elif resistance is not None:
            capped = supernatural_target(effective, resistance.target, resistance.living_or_sapient)
            if capped != effective:
                breakdown.append({"key": "rule_of_16", "value": capped - effective,
                                  "source": "Basic Set", "page": "349"})
            effective = capped
        if model and effective < 3:
            errors.append('invalid_psi_input')
        return PsiUseResult(
            valid=not errors, errors=errors, effective_skill=effective, fp_cost=fp_cost,
            roll=None, resistance=resistance, effects=effects,
            state_delta=StateDelta(), breakdown=breakdown, pending_effects=[],
            references=[RuleReference(data.ability.source, data.ability.page),
                        RuleReference("Psionic Powers", "5-11"), RuleReference("Powers", "154-161")],
            activation_time_seconds=time, character_point_cost=points,
        )

    def resolve(self, data: PsiUseInput, roll: Optional[int] = None,
                resistance_roll: Optional[int] = None) -> PsiUseResult:
        result = self.calculate(data)
        if not result.valid:
            return result
        value = roll if roll is not None else data.roll
        if value is None:
            value = roll_3d6()[0]
        result.roll = evaluate_success_roll(result.effective_skill, value)
        result.roll['roll'] = value
        spent = 0 if result.roll['critical_success'] else result.fp_cost
        from_reserve = min(data.resources.energy_reserve, spent)
        result.resource_delta = {'energy_reserve': -from_reserve, 'fp': -(spent - from_reserve)}
        result.state_delta.fp_change = result.resource_delta['fp']
        if not result.roll["success"]:
            result.effects = []
            result.pending_effects.append({"kind": "psi_failure", "critical": result.roll["critical_failure"]})
            return result
        if result.resistance is not None:
            if resistance_roll is not None:
                result.resistance.roll = resistance_roll
            elif result.resistance.roll is None:
                result.resistance.roll = roll_3d6()[0]
            contest = quick_contest(result.effective_skill, result.resistance.target,
                                    value, result.resistance.roll, resistance=True)
            result.resistance.caster_margin = contest.attacker_margin
            result.resistance.defender_margin = contest.defender_margin
            result.resistance.effective_attack = contest.attacker_target
            result.resistance.resisted = contest.winner != "attacker"
            if result.resistance.resisted:
                result.effects = []
        if any(effect.kind == "narrative" for effect in result.effects):
            result.pending_effects.append({"kind": "gm_effect", "ability": data.ability.identifier})
        return result
