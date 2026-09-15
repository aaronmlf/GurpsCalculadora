"""Advantage-based abilities, powers, and psionic use for GURPS 4e."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional

from calculators.injury import RuleReference, StateDelta
from calculators.magic import EffectPacket, ResistanceCheck, ResourcePool
from calculators.contests import quick_contest, supernatural_target
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

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "PsiAbilityRecord":
        data = dict(value)
        data.setdefault('reference_only', 'activation_cost' not in value and 'effects' not in value)
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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AbilityEngine:
    def calculate(self, data: AbilityBuildInput) -> AbilityBuildResult:
        errors: List[str] = []
        levels = data.levels if data.levels is not None else data.advantage.levels
        if levels < 1 or data.advantage.base_cost < 0 or data.advantage.cost_per_level < 0:
            errors.append("invalid_ability_cost")
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
            references=[RuleReference(data.advantage.source, data.advantage.page), RuleReference("Basic Set", "101-117"),
                        RuleReference("Powers", "7-13")],
        )


class PsionicEngine:
    def calculate(self, data: PsiUseInput) -> PsiUseResult:
        errors: List[str] = []
        if data.ability.reference_only:
            errors.append("catalog_reference_only")
        if data.profile not in {"basic", "realistic", "cinematic"}:
            errors.append("invalid_profile")
        if min(data.skill, data.talent, data.distance_yards, data.repeated_attempts,
               data.extra_effort, data.resources.fp, data.resources.energy_reserve) < 0:
            errors.append("invalid_psi_input")
        if data.profile == "basic":
            errors.append("psionics_outside_basic_profile")
        if data.technique and data.technique.cinematic and data.profile != "cinematic":
            errors.append("cinematic_psi_technique_outside_profile")
        effective = data.skill + data.talent
        breakdown: List[Dict[str, Any]] = []
        if data.technique:
            technique_bonus = min(data.technique.maximum, data.technique_level) + data.technique.default_penalty
            effective += technique_bonus
            breakdown.append({"key": "psi_technique", "value": technique_bonus,
                              "source": data.technique.source, "page": data.technique.page})
        if data.ability.range_model == "speed_range":
            modifier = get_range_modifier(max(1, data.distance_yards))
            effective += modifier
            breakdown.append({"key": "range", "value": modifier, "source": "Psionic Powers", "page": "6"})
        if data.repeated_attempts:
            penalty = -max(0, data.repeated_attempts)
            effective += penalty
            breakdown.append({"key": "repeated_attempt", "value": penalty,
                              "source": "Psionic Powers", "page": "6"})
        fp_cost = data.ability.activation_cost + max(0, data.extra_effort) + (data.technique.cost_fp if data.technique else 0)
        if fp_cost > data.resources.fp + data.resources.energy_reserve:
            errors.append("insufficient_energy")
        if data.resistance is not None:
            capped = supernatural_target(effective, data.resistance.target,
                                         data.resistance.living_or_sapient)
            if capped != effective:
                breakdown.append({"key": "rule_of_16", "value": capped - effective,
                                  "source": "Basic Set", "page": "349"})
            effective = capped
        return PsiUseResult(
            valid=not errors, errors=errors, effective_skill=effective, fp_cost=fp_cost,
            roll=None, resistance=deepcopy(data.resistance), effects=deepcopy(data.ability.effects),
            state_delta=StateDelta(), breakdown=breakdown, pending_effects=[],
            references=[RuleReference(data.ability.source, data.ability.page),
                        RuleReference("Psionic Powers", "5-11"), RuleReference("Powers", "154-161")],
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
        if not result.roll["success"]:
            result.effects = []
            result.pending_effects.append({"kind": "psi_failure", "critical": result.roll["critical_failure"]})
            return result
        result.state_delta.fp_change = -min(data.resources.fp, result.fp_cost)
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
