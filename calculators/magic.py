"""Spellcasting engines for standard and alternative GURPS magic systems."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import math
import re
from typing import Any, Dict, List, Optional

from calculators.injury import RuleReference, StateDelta
from calculators.contests import long_distance_modifier, quick_contest, supernatural_target
from utils.dice_roller import evaluate_success_roll, roll_3d6


MAGIC_SYSTEMS = {
    "standard", "ceremonial", "clerical", "ritual_magic", "threshold",
    "path_book", "symbol", "realm", "syntactic", "spirit_assisted",
    "ritual_path_magic", "sorcery",
}
IMPLEMENTED_MAGIC_SYSTEMS = frozenset({'standard', 'ceremonial', 'clerical'})
CASTING_CLASSES = frozenset({'regular', 'resisted', 'area', 'information', 'blocking', 'melee', 'missile'})


def _known_cost(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


@dataclass
class ResourcePool:
    fp: int = 10
    energy_reserve: int = 0
    external_energy: int = 0
    threshold: int = 0
    tally: int = 0


@dataclass
class CeremonialAssistant:
    spell_skill: int = 15
    mage: bool = True
    energy: int = 1


@dataclass
class CeremonialCasting:
    caster_energy: int = 1
    assistants: List[CeremonialAssistant] = field(default_factory=list)
    supporters: int = 0
    opponents: int = 0


@dataclass
class ResistanceCheck:
    attribute: str = "will"
    target: int = 10
    roll: Optional[int] = None
    caster_margin: Optional[int] = None
    resisted: Optional[bool] = None
    living_or_sapient: bool = True
    effective_attack: Optional[int] = None
    defender_margin: Optional[int] = None


@dataclass
class EffectPacket:
    kind: str = "narrative"
    value: float = 0.0
    damage_type: str = ""
    duration_seconds: int = 0
    area_yards: float = 0.0
    condition: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MagicSystemRecord:
    identifier: str
    name: str
    source: str
    page: str
    profile: str = "realistic"
    energy_model: str = "fp"
    skill_model: str = "spell"
    supports_maintenance: bool = True
    tags: List[str] = field(default_factory=list)

    @property
    def catalog_status(self) -> str:
        return ('calculable' if self.identifier.removeprefix('magic.') in IMPLEMENTED_MAGIC_SYSTEMS
                else 'reference_only')


@dataclass
class SpellRecord:
    identifier: str
    name: str
    source: str
    page: str
    college: str = ""
    spell_class: str = "regular"
    difficulty: str = "H"
    base_cost: int = 1
    maintenance_cost: Optional[int] = None
    casting_time_seconds: int = 1
    duration_seconds: int = 0
    resist_attribute: str = ""
    prerequisites: List[str] = field(default_factory=list)
    prereq_count: int = 0
    effects: List[EffectPacket] = field(default_factory=list)
    systems: List[str] = field(default_factory=lambda: ["standard"])
    profile: str = "basic"
    original: Dict[str, str] = field(default_factory=dict)
    rule_model: str = ''

    @property
    def resistance_notation(self) -> str:
        notation = re.search(r'(?:^|/)(R-.+)$', str(self.original.get('class', '')), flags=re.IGNORECASE)
        return notation.group(1) if notation else ('R-' + self.resist_attribute.upper() if self.resist_attribute else '')

    @property
    def requires_resistance(self) -> bool:
        return self.spell_class == 'resisted' or (self.spell_class in {'regular', 'area', 'information'}
                                                and bool(self.resistance_notation))

    @property
    def catalog_status(self) -> str:
        if self.spell_class not in CASTING_CLASSES:
            return 'reference_only'
        return ('calculable' if all(_known_cost(x) for x in (self.base_cost, self.casting_time_seconds))
                else 'requires_parameters')

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "SpellRecord":
        data = dict(value)
        data['spell_class'] = data.get('spell_class', 'regular').lower().split('/')[0]
        data['spell_class'] = {'reg.': 'regular', 'inform.': 'information', 'block.': 'blocking'}.get(data['spell_class'], data['spell_class'])
        data['difficulty'] = {'Hard': 'H', 'Very Hard': 'VH'}.get(data.get('difficulty'), data.get('difficulty', 'H'))
        notation = re.search(r'(?:^|/)R-(HT|Will|DX|IQ|ST)$', str(data.get('original', {}).get('class', '')),
                             flags=re.IGNORECASE)
        if notation and not data.get('resist_attribute'):
            data['resist_attribute'] = notation.group(1).lower()
        data["effects"] = [item if isinstance(item, EffectPacket) else EffectPacket(**item)
                           for item in data.get("effects", [])]
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CastingInput:
    spell: SpellRecord
    system: str = "standard"
    profile: str = "basic"
    skill: int = 12
    magery: int = 0
    mana_level: str = "normal"
    distance_yards: int = 0
    area_radius_yards: int = 1
    size_modifier: int = 0
    time_multiplier: float = 1.0
    energy_multiplier: float = 1.0
    maintenance_cycles: int = 0
    resources: ResourcePool = field(default_factory=ResourcePool)
    accumulated_energy: int = 0
    realm_level: int = 0
    ritual_modifiers: int = 0
    custom_modifier: int = 0
    cast_roll: Optional[int] = None
    resistance: Optional[ResistanceCheck] = None
    ceremony: Optional[CeremonialCasting] = None
    is_mage: bool = True
    target_visible: bool = True
    same_day_castings: int = 0
    physician_skill: int = 0
    maintenance_only: bool = False
    magic_resistance: int = 0
    target_waives_resistance: bool = False


@dataclass
class CastingResult:
    valid: bool
    errors: List[str]
    effective_skill: int
    energy_cost: int
    casting_time_seconds: int
    roll: Optional[Dict[str, Any]]
    resistance: Optional[ResistanceCheck]
    effects: List[EffectPacket]
    state_delta: StateDelta
    breakdown: List[Dict[str, Any]]
    pending_effects: List[Dict[str, Any]]
    references: List[RuleReference]
    resource_delta: Dict[str, int] = field(default_factory=dict)
    maintenance_cost: Optional[int] = None
    maintenance_forecast: int = 0
    duration_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SpellcastingEngine:
    """State-free spell calculator; only returned deltas mutate a session."""

    def calculate(self, data: CastingInput) -> CastingResult:
        errors: List[str] = []
        maintaining = data.maintenance_only
        numeric = () if maintaining else (data.spell.base_cost, data.spell.casting_time_seconds)
        if not all(_known_cost(value) for value in numeric):
            return CastingResult(False, ["spell_requires_parameters"], data.skill, 0, 0, None,
                deepcopy(data.resistance), [], StateDelta(), [],
                [{"kind": "spell_parameters", "original": deepcopy(data.spell.original)}],
                [RuleReference(data.spell.source, data.spell.page)])
        distances = (data.distance_yards, data.area_radius_yards, data.time_multiplier, data.energy_multiplier)
        integers = (data.skill, data.magery, data.size_modifier, data.ritual_modifiers, data.custom_modifier,
                    data.maintenance_cycles, data.same_day_castings, data.physician_skill, data.resources.fp,
                    data.resources.energy_reserve, data.resources.external_energy, data.magic_resistance)
        if (not all(_known_cost(value) for value in distances) or data.time_multiplier <= 0 or
                any(type(value) is not int for value in integers) or
                data.resistance is not None and (type(data.resistance.target) is not int or data.resistance.target < 0)):
            return CastingResult(False, ['invalid_casting_input'], data.skill, 0, 0, None, None, [],
                                 StateDelta(), [], [], [RuleReference(data.spell.source, data.spell.page)])
        if data.profile not in {"basic", "realistic", "cinematic"}:
            errors.append("invalid_profile")
        if min(data.resources.fp, data.resources.energy_reserve, data.resources.external_energy,
               data.maintenance_cycles, data.magery, data.same_day_castings, data.physician_skill,
               data.magic_resistance) < 0:
            errors.append("invalid_casting_input")
        if data.system not in MAGIC_SYSTEMS:
            errors.append("unknown_magic_system")
        elif data.system not in IMPLEMENTED_MAGIC_SYSTEMS:
            # Registration is not an implementation of a distinct magic system.
            errors.append("magic_system_resolver_not_implemented")
        if data.system not in data.spell.systems and data.system not in {"ritual_magic", "clerical", "ceremonial"}:
            errors.append("spell_not_available_in_system")
        if data.profile == "basic" and (data.system not in IMPLEMENTED_MAGIC_SYSTEMS or data.spell.profile != "basic"):
            errors.append("alternative_magic_outside_profile")
        if data.spell.spell_class not in CASTING_CLASSES:
            errors.append('catalog_reference_only')
        if data.skill < 3:
            errors.append("invalid_casting_input")
        if (not maintaining and data.spell.requires_resistance and data.resistance is None and
                not data.target_waives_resistance):
            errors.append('spell_requires_resistance')
        if not maintaining and data.spell.rule_model == 'minor_healing':
            # Magic pp. 9, 91: baseline limit 3, or higher Magery when allowed.
            limit = max(3, data.magery) if data.is_mage else 3
            if not 1 <= data.spell.base_cost <= limit or int(data.spell.base_cost) != data.spell.base_cost:
                errors.append('invalid_healing_energy')
        modifiers = data.ritual_modifiers + data.custom_modifier
        breakdown: List[Dict[str, Any]] = []
        if not maintaining and data.spell.spell_class in {"regular", "resisted", "area"}:
            # Magic p. 11: subtract distance. B9 rounds task results down;
            # floor(skill - distance) = skill - ceil(distance). Ignore one
            # representational ULP at whole-yard metric/imperial boundaries.
            distance = data.distance_yards
            range_mod = -math.ceil(math.nextafter(distance, -math.inf)) if distance else 0
            modifiers += range_mod
            breakdown.append({"key": "range", "value": range_mod, "source": "Magic", "page": "11"})
            if data.distance_yards > 0 and not data.target_visible:
                modifiers -= 5
                breakdown.append({'key': 'spell_target_not_visible', 'value': -5, 'source': 'Magic', 'page': '11'})
        elif not maintaining and data.spell.spell_class == "information" and data.distance_yards:
            range_mod = long_distance_modifier(data.distance_yards)
            modifiers += range_mod
            breakdown.append({"key": "long_distance", "value": range_mod, "source": "Magic", "page": "14"})
        mana_mod = {"very_high": 0, "high": 0, "normal": 0, "low": -5, "no_mana": -100}.get(data.mana_level)
        if mana_mod is None:
            errors.append("invalid_mana_level")
            mana_mod = 0
        if data.mana_level == "no_mana":
            errors.append("magic_unavailable_without_mana")
        if data.system in {'standard', 'ceremonial'} and data.mana_level in {'normal', 'low'} and not data.is_mage:
            errors.append('mage_required_in_mana')
        modifiers += mana_mod
        if mana_mod:
            breakdown.append({"key": "mana", "value": mana_mod, "source": "Basic Set", "page": "235"})
        if not maintaining and data.spell.rule_model == 'minor_healing' and data.same_day_castings:
            penalty = -3 * data.same_day_castings
            modifiers += penalty
            breakdown.append({'key': 'healing_repeat', 'value': penalty, 'source': 'Magic', 'page': '91'})
        resistance = None if maintaining or data.target_waives_resistance else deepcopy(data.resistance)
        if not maintaining and data.magic_resistance:
            if data.spell.spell_class in {'regular', 'resisted'} or (
                    data.spell.spell_class != 'area' and (data.spell.requires_resistance or resistance is not None)):
                modifiers -= data.magic_resistance
                breakdown.append({'key': 'magic_resistance_casting', 'value': -data.magic_resistance,
                                  'source': 'Magic', 'page': '14'})
            if resistance is not None:
                bonus = data.magic_resistance * (2 if data.spell.spell_class == 'area' else 1)
                resistance.target += bonus
                breakdown.append({'key': 'magic_resistance_defense', 'value': bonus,
                                  'source': 'Magic', 'page': '14'})
        effective = data.skill + modifiers
        if resistance is not None:
            if data.spell.resist_attribute:
                resistance.attribute = data.spell.resist_attribute
            capped = supernatural_target(effective, resistance.target, resistance.living_or_sapient)
            if capped != effective:
                breakdown.append({"key": "rule_of_16", "value": capped - effective,
                                  "source": "Basic Set", "page": "349"})
            effective = capped
        ritual_skill = data.skill + (-5 if data.mana_level == "low" else 0)

        cost = 0 if maintaining else data.spell.base_cost
        if data.spell.spell_class == "area":
            cost *= max(1, data.area_radius_yards)
        elif data.spell.spell_class in {"regular", "resisted"} and data.size_modifier > 0:
            cost *= 1 + data.size_modifier
        cost = math.ceil(cost * max(0, data.energy_multiplier))
        # Standard high-skill reductions do not apply to Blocking or ceremonial casting.
        reduction = 0
        if data.system == "standard" and data.spell.spell_class != "blocking":
            reduction = max(0, (ritual_skill - 15) // 5 + 1) if ritual_skill >= 15 else 0
            cost = max(0, cost - reduction)
            if reduction:
                breakdown.append({"key": "high_skill_energy_reduction", "value": -reduction,
                                  "source": "Magic", "page": "8"})
        maintenance = None
        if _known_cost(data.spell.maintenance_cost):
            scale = max(1, data.area_radius_yards) if data.spell.spell_class == "area" else (
                1 + max(0, data.size_modifier) if data.spell.spell_class in {"regular", "resisted"} else 1)
            maintenance = max(0, math.ceil(data.spell.maintenance_cost * scale * data.energy_multiplier) - reduction)
        if (maintaining or data.maintenance_cycles) and maintenance is None:
            errors.append('spell_cannot_be_maintained')
        forecast = (maintenance or 0) * data.maintenance_cycles
        if maintaining:
            cost = maintenance or 0
        casting_time = 0 if maintaining else max(1, math.ceil(data.spell.casting_time_seconds * max(0.01, data.time_multiplier)))
        if not maintaining and data.system == "standard" and data.spell.spell_class not in {"missile", "blocking"} and ritual_skill >= 20:
            casting_time = max(1, math.ceil(casting_time / (2 ** max(1, (ritual_skill - 15) // 5))))

        available = data.resources.fp + data.resources.energy_reserve + data.resources.external_energy
        if data.system == "threshold":
            available = 10 ** 9
        if data.system == "ritual_path_magic":
            available += max(0, data.accumulated_energy)
        if cost > available:
            errors.append("insufficient_energy")

        if data.system == "ceremonial":
            ceremony = data.ceremony
            if maintaining:
                errors.append('ceremony_maintenance_separate')
            elif ceremony is None:
                errors.append("ceremony_requires_contributions")
            else:
                amounts = [ceremony.caster_energy, ceremony.supporters, ceremony.opponents]
                amounts += [a.energy for a in ceremony.assistants]
                if any(type(v) is not int or v < 0 for v in amounts):
                    errors.append("invalid_ceremonial_contribution")
                if ritual_skill < 15 or not (ceremony.assistants or ceremony.supporters):
                    errors.append("ceremony_requires_skilled_leader_and_group")
                if data.maintenance_cycles:
                    errors.append("ceremony_maintenance_separate")
                for assistant in ceremony.assistants:
                    if (assistant.spell_skill < 15 and not assistant.mage or
                            assistant.energy > 3 and (not assistant.mage or assistant.spell_skill < 15)):
                        errors.append("invalid_ceremonial_contribution")
                contributed = ceremony.caster_energy + sum(a.energy for a in ceremony.assistants)
                contributed += min(100, ceremony.supporters)
                usable = contributed - min(100, 5 * ceremony.opponents)
                errors = [e for e in errors if e != "insufficient_energy"]
                if ceremony.caster_energy > available or usable < cost:
                    errors.append("insufficient_energy")
                excess = (usable - cost) / cost if cost > 0 else 0
                bonus = (3 + math.floor(excess) if excess >= 1 else
                         3 if excess >= .6 else 2 if excess >= .4 else 1 if excess >= .2 else 0)
                effective += bonus
                if resistance is not None:
                    effective = supernatural_target(data.skill + modifiers + bonus, resistance.target,
                                                     resistance.living_or_sapient)
                    breakdown = [item for item in breakdown if item['key'] != 'rule_of_16']
                    capped_by = effective - (data.skill + modifiers + bonus)
                    if capped_by:
                        breakdown.append({"key": "rule_of_16", "value": capped_by,
                                          "source": "Basic Set", "page": "349"})
                breakdown.append({"key": "ceremonial_energy_bonus", "value": bonus,
                                  "source": "Basic Set", "page": "238"})
                cost = contributed
            casting_time *= 10

        pending: List[Dict[str, Any]] = []
        effects = [] if maintaining else deepcopy(data.spell.effects)
        if not maintaining and data.spell.rule_model == 'minor_healing' and not errors:
            effects = [EffectPacket(kind='heal_hp', value=int(data.spell.base_cost))]
        if not maintaining and (not effects or any(effect.kind == 'narrative' for effect in effects)):
            pending.append({"kind": "gm_effect", "spell": data.spell.identifier})
        return CastingResult(
            valid=not errors, errors=list(dict.fromkeys(errors)), effective_skill=effective,
            energy_cost=cost, casting_time_seconds=casting_time, roll=None,
            resistance=resistance, effects=effects, state_delta=StateDelta(),
            breakdown=breakdown, pending_effects=pending,
            references=[RuleReference(data.spell.source, data.spell.page), RuleReference("Magic", "7-14"),
                        RuleReference("Thaumatology", "19-214")],
            maintenance_cost=maintenance, maintenance_forecast=forecast, duration_seconds=data.spell.duration_seconds,
        )

    @staticmethod
    def _debit(result: CastingResult, data: CastingInput, spent: int) -> None:
        # Explicit ledger prevents ER/external energy from being silently free.
        for pool in ('external_energy', 'energy_reserve', 'fp'):
            amount = min(getattr(data.resources, pool), spent)
            result.resource_delta[pool] = -amount
            spent -= amount
        result.state_delta.fp_change = result.resource_delta['fp']
        if data.mana_level == 'very_high' and data.is_mage and result.state_delta.fp_change:
            result.pending_effects.append({'kind': 'very_high_mana_fp_recovery', 'fp': -result.state_delta.fp_change})

    def maintain(self, data: CastingInput) -> CastingResult:
        """Renew one existing spell at the GM-confirmed end of its duration."""
        result = self.calculate(replace(data, maintenance_only=True))
        if result.valid:
            self._debit(result, data, result.energy_cost)
        return result

    def resolve(self, data: CastingInput, cast_roll: Optional[int] = None,
                resistance_roll: Optional[int] = None) -> CastingResult:
        if data.maintenance_only:
            return self.maintain(data)
        result = self.calculate(data)
        if not result.valid:
            return result
        roll_value = cast_roll if cast_roll is not None else data.cast_roll
        if roll_value is None:
            roll_value = roll_3d6()[0]
        result.roll = evaluate_success_roll(result.effective_skill, roll_value)
        result.roll['roll'] = roll_value
        if data.system == "ceremonial" and roll_value >= 16:
            result.roll.update(success=False, critical_success=False,
                               critical_failure=roll_value >= 17,
                               margin=abs(roll_value - result.effective_skill))
        if not result.roll['success'] and data.mana_level == 'very_high' and data.system in {'standard', 'ceremonial'}:
            result.roll['critical_failure'] = True
        if (result.roll['critical_failure'] and data.spell.rule_model == 'minor_healing' and
                not data.same_day_castings and data.physician_skill >= 15 and data.mana_level != 'very_high'):
            result.roll['critical_failure'] = False
        spent = result.energy_cost
        if data.system == "ceremonial":
            spent = data.ceremony.caster_energy
            result.resource_delta["ceremonial_assistants"] = -(result.energy_cost - spent)
        elif result.roll["critical_success"] and data.spell.spell_class != 'information':
            spent = 0
        elif not result.roll["success"] and not result.roll["critical_failure"] and data.spell.spell_class != "information":
            spent = min(1, spent)
        self._debit(result, data, spent)
        if not result.roll["success"]:
            result.effects = []
            result.pending_effects.append({"kind": "spell_failure", "critical": result.roll["critical_failure"]})
            return result
        if result.resistance is not None and not result.roll["critical_success"]:
            if resistance_roll is not None:
                result.resistance.roll = resistance_roll
            elif result.resistance.roll is None:
                result.resistance.roll = roll_3d6()[0]
            contest = quick_contest(result.effective_skill, result.resistance.target,
                                    roll_value, result.resistance.roll, resistance=True)
            result.resistance.caster_margin = contest.attacker_margin
            result.resistance.defender_margin = contest.defender_margin
            result.resistance.effective_attack = contest.attacker_target
            result.resistance.resisted = contest.winner != "attacker"
            if result.resistance.resisted:
                result.effects = []
        return result
