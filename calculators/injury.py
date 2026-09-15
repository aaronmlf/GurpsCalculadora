"""Shared GURPS Fourth Edition damage, armor, and injury engine.

The engine is intentionally state-free.  ``calculate`` explains a damage
packet and returns a :class:`StateDelta`; ``resolve`` additionally rolls the
immediate HT checks.  A caller must explicitly apply the delta to a combat
session.  This keeps previews, tests, and UI calculations free of side
effects.

Rules references are stored as short book/page labels.  No descriptive book
text is embedded in the application.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from utils.dice_roller import evaluate_success_roll, roll_1d6, roll_3d6


RULE_PROFILES = ("basic", "realistic", "cinematic")


@dataclass(frozen=True)
class RuleReference:
    source: str
    page: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass
class OptionalInjuryRules:
    """Optional record-keeping rules; every option defaults to off."""

    bleeding: bool = False
    severe_bleeding: bool = False
    accumulated_wounds: bool = False
    partial_injury: bool = False
    lasting_injury: bool = False
    armor_gaps: bool = False
    harsh_layering: bool = False
    edge_protection: bool = False
    plate_degradation: bool = False

    def enabled(self) -> List[str]:
        return [name for name, value in asdict(self).items() if value]


@dataclass
class DamagePacket:
    """One already-rolled instance of basic damage."""

    basic_damage: int
    damage_type: str = "cr"
    armor_divisor: float = 1.0
    hit_location: str = "torso"
    direction: str = "front"
    source: str = "Basic Set"
    page: str = "377-381"
    expression: str = ""
    ranged: bool = False
    tight_beam: bool = False
    explosive: bool = False
    large_area: bool = False
    ignore_dr: bool = False
    chinks: bool = False
    armor_gap: bool = False
    cover_dr: Optional[int] = None
    linked_effects: List[Dict[str, Any]] = field(default_factory=list)
    raw: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DamagePacket":
        return cls(**dict(value))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArmorRecord:
    identifier: str
    source: str
    page: str
    name: str
    tech_level: str = ""
    locations: List[str] = field(default_factory=lambda: ["torso"])
    dr: int = 0
    dr_by_type: Dict[str, int] = field(default_factory=dict)
    direction: str = "all"
    coverage: int = 6
    flexible: bool = False
    rigid: bool = True
    ablative: bool = False
    semi_ablative: bool = False
    weight: float = 0.0
    cost: str = ""
    don_time: str = ""
    dx_penalty: int = 0
    move_penalty: int = 0
    legality_class: str = ""
    tags: List[str] = field(default_factory=list)
    original: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArmorRecord":
        data = dict(value)
        data["dr_by_type"] = {str(key): int(item) for key, item in data.get("dr_by_type", {}).items()}
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def protects(self, location: str, direction: str) -> bool:
        locations = set(self.locations)
        location_ok = "all" in locations or location in locations
        direction_ok = self.direction == "all" or self.direction == direction
        return location_ok and direction_ok

    def dr_for(self, damage_type: str) -> int:
        canonical = canonical_damage_type(damage_type)
        return max(0, int(self.dr_by_type.get(canonical, self.dr_by_type.get("*", self.dr))))


@dataclass
class ArmorLayer:
    armor: ArmorRecord
    current_dr_loss: int = 0
    coverage_roll: Optional[int] = None
    enabled: bool = True

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArmorLayer":
        data = dict(value)
        armor = data.get("armor")
        if isinstance(armor, Mapping):
            data["armor"] = ArmorRecord.from_dict(armor)
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArmorLoadout:
    layers: List[ArmorLayer] = field(default_factory=list)
    natural_dr: int = 0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArmorLoadout":
        return cls(
            layers=[ArmorLayer.from_dict(layer) for layer in value.get("layers", [])],
            natural_dr=int(value.get("natural_dr", 0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WoundRecord:
    location: str
    injury: int
    uncapped_injury: int
    damage_type: str
    bleeding: bool = False
    bleeding_stopped: bool = False
    successful_bleeding_rolls: int = 0
    source: str = ""
    page: str = ""

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WoundRecord":
        return cls(**dict(value))


@dataclass
class CombatantState:
    identifier: str = "combatant"
    name: str = "Combatant"
    max_hp: int = 10
    current_hp: int = 10
    max_fp: int = 10
    current_fp: int = 10
    st: int = 10
    dx: int = 10
    iq: int = 10
    ht: int = 10
    basic_speed: float = 5.0
    basic_move: int = 5
    size_modifier: int = 0
    dodge: int = 8
    parry: int = 8
    block: int = 8
    posture: str = "standing"
    facing: str = "front"
    aware: bool = True
    injury_tolerance: str = "living"
    high_pain_threshold: bool = False
    low_pain_threshold: bool = False
    shock: int = 0
    stunned: bool = False
    unconscious: bool = False
    dead: bool = False
    wounds: List[WoundRecord] = field(default_factory=list)
    crippled_locations: List[str] = field(default_factory=list)
    destroyed_locations: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    pending_checks: List[Dict[str, Any]] = field(default_factory=list)
    armor: ArmorLoadout = field(default_factory=ArmorLoadout)
    grapples: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    action_count: int = 0
    personal_seconds: int = 0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CombatantState":
        data = dict(value)
        data["wounds"] = [
            wound if isinstance(wound, WoundRecord) else WoundRecord.from_dict(wound)
            for wound in data.get("wounds", [])
        ]
        armor = data.get("armor", {})
        if not isinstance(armor, ArmorLoadout):
            data["armor"] = ArmorLoadout.from_dict(armor)
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StateDelta:
    hp_change: int = 0
    fp_change: int = 0
    shock: int = 0
    posture: Optional[str] = None
    add_conditions: List[str] = field(default_factory=list)
    remove_conditions: List[str] = field(default_factory=list)
    set_stunned: Optional[bool] = None
    set_unconscious: Optional[bool] = None
    set_dead: Optional[bool] = None
    wounds: List[WoundRecord] = field(default_factory=list)
    crippled_locations: List[str] = field(default_factory=list)
    destroyed_locations: List[str] = field(default_factory=list)
    pending_checks: List[Dict[str, Any]] = field(default_factory=list)
    armor_dr_loss: Dict[str, int] = field(default_factory=dict)
    grapple_updates: Dict[str, Optional[Dict[str, Any]]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StateDelta":
        data = dict(value)
        data["wounds"] = [
            wound if isinstance(wound, WoundRecord) else WoundRecord.from_dict(wound)
            for wound in data.get("wounds", [])
        ]
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InjuryInput:
    packet: DamagePacket
    target: CombatantState
    armor: Optional[ArmorLoadout] = None
    profile: str = "basic"
    optional_rules: OptionalInjuryRules = field(default_factory=OptionalInjuryRules)
    coverage_rolls: Dict[str, int] = field(default_factory=dict)
    accumulated_injury: Optional[int] = None
    knockdown_roll: Optional[int] = None
    consciousness_roll: Optional[int] = None
    death_rolls: List[int] = field(default_factory=list)


@dataclass
class InjuryResult:
    valid: bool
    errors: List[str]
    profile: str
    packet: DamagePacket
    target_hp_before: int
    target_hp_after: int
    armor_layers: List[Dict[str, Any]] = field(default_factory=list)
    total_dr: int = 0
    effective_dr: int = 0
    penetrating_damage: int = 0
    blunt_trauma: int = 0
    wounding_modifier: float = 1.0
    uncapped_injury: int = 0
    injury: int = 0
    major_wound: bool = False
    crippling: bool = False
    dismemberment: bool = False
    knockdown_target: Optional[int] = None
    checks: List[Dict[str, Any]] = field(default_factory=list)
    residual_packet: Optional[DamagePacket] = None
    state_delta: StateDelta = field(default_factory=StateDelta)
    rounding: List[Dict[str, Any]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    references: List[RuleReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DAMAGE_ALIASES = {
    "burning": "burn", "corrosion": "cor", "crushing": "cr",
    "cutting": "cut", "fatigue": "fat", "impaling": "imp",
    "small_piercing": "pi-", "piercing": "pi", "large_piercing": "pi+",
    "huge_piercing": "pi++", "toxic": "tox",
}

_BASE_WOUNDING = {
    "burn": 1.0, "cor": 1.0, "cr": 1.0, "cut": 1.5, "fat": 1.0,
    "imp": 2.0, "pi-": 0.5, "pi": 1.0, "pi+": 1.5,
    "pi++": 2.0, "tox": 1.0,
}

_PIERCING = {"pi-", "pi", "pi+", "pi++"}
_OVERPENETRATION_TYPES = _PIERCING | {"imp", "burn"}
_LIMBS = {"arm", "leg", "wing", "tail", "elbow", "knee", "shoulder", "hip"}
_EXTREMITIES = {"hand", "foot", "paw"}
_HEAD = {"skull", "face", "eye", "jaw", "nose", "ear"}
_EXPANDED_LOCATIONS = {"jaw", "neck_artery", "limb_artery", "elbow", "knee", "shoulder", "hip", "nose", "ear", "spine"}

_LOCATION_ATTACK_PENALTIES = {
    "torso": 0, "vitals": -3, "skull": -7, "eye": -9, "face": -5,
    "jaw": -6, "neck": -5, "groin": -3, "arm": -2, "leg": -2,
    "hand": -4, "foot": -4, "weapon": -5, "neck_artery": -8,
    "limb_artery": -5, "elbow": -5, "knee": -5, "shoulder": -5,
    "hip": -5, "nose": -7, "ear": -7, "spine": -8,
}


def canonical_damage_type(value: str) -> str:
    key = str(value).strip().lower().replace(" ", "_")
    return _DAMAGE_ALIASES.get(key, key)


def hit_location_penalty(location: str, profile: str = "basic") -> int:
    if profile == "basic" and location in _EXPANDED_LOCATIONS:
        raise ValueError("expanded_hit_location_outside_profile")
    if location not in _LOCATION_ATTACK_PENALTIES:
        raise ValueError("invalid_hit_location")
    return _LOCATION_ATTACK_PENALTIES[location]


def _location_natural_dr(location: str) -> int:
    return 2 if location == "skull" else 0


def _base_wounding_modifier(damage_type: str, tolerance: str) -> float:
    damage_type = canonical_damage_type(damage_type)
    tolerance = tolerance.lower()
    if tolerance == "unliving":
        return {"imp": 1.0, "pi-": 0.2, "pi": 1 / 3, "pi+": 0.5, "pi++": 1.0}.get(
            damage_type, _BASE_WOUNDING.get(damage_type, 1.0)
        )
    if tolerance == "homogenous":
        return {"imp": 0.5, "pi-": 0.1, "pi": 0.2, "pi+": 1 / 3, "pi++": 0.5}.get(
            damage_type, _BASE_WOUNDING.get(damage_type, 1.0)
        )
    return _BASE_WOUNDING.get(damage_type, 1.0)


def wounding_modifier(damage_type: str, location: str, tolerance: str = "living") -> float:
    """Return the final location/tolerance wounding modifier."""

    dtype = canonical_damage_type(damage_type)
    if tolerance.lower() in {"unliving", "homogenous", "diffuse"}:
        return _base_wounding_modifier(dtype, tolerance)
    multiplier = _base_wounding_modifier(dtype, tolerance)
    if location == "vitals":
        if dtype in _PIERCING or dtype == "imp":
            return 3.0
        if dtype == "burn":
            return 2.0
    if location in {"skull", "eye"} and dtype not in {"tox", "fat"}:
        return 4.0
    if location == "neck":
        if dtype == "cut":
            return 2.0
        if dtype in {"cr", "cor"}:
            return 1.5
    if location in {"neck_artery", "limb_artery"}:
        if dtype == "cut":
            return 2.0
        if dtype in _PIERCING or dtype == "imp":
            return max(multiplier, 1.5)
    if location in _LIMBS | _EXTREMITIES and dtype in {"imp", "pi+", "pi++"}:
        return 1.0
    return multiplier


def _crippling_threshold(location: str, hp: int) -> Optional[int]:
    if location in _LIMBS:
        return math.floor(hp / 2) + 1
    if location in _EXTREMITIES:
        return math.floor(hp / 3) + 1
    if location == "eye":
        return math.floor(hp / 10) + 1
    if location in {"ear", "nose"}:
        return math.floor(hp / 4) + 1
    return None


def _shock_penalty(injury: int, hp: int, high_pain_threshold: bool) -> int:
    if injury <= 0 or high_pain_threshold:
        return 0
    divisor = max(1, hp // 10) if hp >= 20 else 1
    return min(4, injury // divisor)


def _crossed_negative_hp_multiples(before: int, after: int, hp: int) -> List[int]:
    if after >= before or hp <= 0:
        return []
    crossed = []
    multiple = 1
    while multiple <= 4:
        threshold = -multiple * hp
        if before > threshold >= after:
            crossed.append(multiple)
        multiple += 1
    return crossed


class InjuryEngine:
    """Calculate GURPS damage and the resulting state delta."""

    def _validate(self, data: InjuryInput) -> List[str]:
        errors: List[str] = []
        if data.profile not in RULE_PROFILES:
            errors.append("invalid_profile")
        if data.packet.basic_damage < 0:
            errors.append("negative_damage")
        if data.packet.armor_divisor <= 0:
            errors.append("invalid_armor_divisor")
        if data.target.max_hp <= 0:
            errors.append("invalid_target_hp")
        try:
            hit_location_penalty(data.packet.hit_location, data.profile)
        except ValueError as exc:
            errors.append(str(exc))
        if data.profile == "basic" and data.optional_rules.enabled():
            errors.append("optional_rule_outside_profile")
        if data.packet.armor_gap and not data.optional_rules.armor_gaps:
            errors.append("armor_gap_rule_disabled")
        return errors

    @staticmethod
    def _layer_dr(layer: ArmorLayer, packet: DamagePacket,
                  supplied_roll: Optional[int]) -> Tuple[int, Dict[str, Any]]:
        armor = layer.armor
        detail: Dict[str, Any] = {
            "identifier": armor.identifier,
            "name": armor.name,
            "source": armor.source,
            "page": armor.page,
            "protects": False,
            "coverage": armor.coverage,
            "coverage_roll": supplied_roll if supplied_roll is not None else layer.coverage_roll,
            "dr": 0,
            "flexible": armor.flexible,
            "ablative": armor.ablative,
            "semi_ablative": armor.semi_ablative,
        }
        if not layer.enabled or not armor.protects(packet.hit_location, packet.direction):
            return 0, detail
        roll = supplied_roll if supplied_roll is not None else layer.coverage_roll
        if armor.coverage < 6 and roll is not None and roll > armor.coverage:
            detail["coverage_missed"] = True
            return 0, detail
        dr = max(0, armor.dr_for(packet.damage_type) - layer.current_dr_loss)
        detail["protects"] = True
        detail["coverage_pending"] = armor.coverage < 6 and roll is None
        detail["dr"] = dr
        detail["current_dr_loss"] = layer.current_dr_loss
        return dr, detail

    def calculate(self, data: InjuryInput) -> InjuryResult:
        errors = self._validate(data)
        packet = replace(data.packet, damage_type=canonical_damage_type(data.packet.damage_type))
        result = InjuryResult(
            valid=not errors,
            errors=errors,
            profile=data.profile,
            packet=packet,
            target_hp_before=data.target.current_hp,
            target_hp_after=data.target.current_hp,
            references=[
                RuleReference("Basic Set", "377-381"),
                RuleReference("Basic Set", "398-400"),
                RuleReference("Basic Set", "419-424"),
            ],
        )
        if errors:
            return result

        armor = data.armor if data.armor is not None else data.target.armor
        total_dr = max(0, armor.natural_dr) + _location_natural_dr(packet.hit_location)
        flexible = False
        for layer in armor.layers:
            supplied = data.coverage_rolls.get(layer.armor.identifier)
            layer_dr, detail = self._layer_dr(layer, packet, supplied)
            result.armor_layers.append(detail)
            if detail["protects"]:
                total_dr += layer_dr
                flexible = flexible or layer.armor.flexible

        if packet.ignore_dr:
            effective_dr = 0
            result.notes.append("ignores_dr")
        else:
            if packet.chinks or packet.armor_gap:
                total_dr = total_dr // 2
                result.notes.append("halved_dr_for_chinks_or_gap")
            effective_dr = math.ceil(total_dr / packet.armor_divisor)
            result.rounding.append({
                "stage": "armor_divisor", "operation": "ceil",
                "input": total_dr / packet.armor_divisor, "output": effective_dr,
            })
        result.total_dr = total_dr
        result.effective_dr = effective_dr
        result.penetrating_damage = max(0, packet.basic_damage - effective_dr)

        if result.penetrating_damage == 0 and flexible and packet.basic_damage > 0:
            divisor = 5 if packet.damage_type == "cr" else 10
            result.blunt_trauma = packet.basic_damage // divisor
            if result.blunt_trauma:
                result.notes.append("flexible_armor_blunt_trauma")

        result.wounding_modifier = wounding_modifier(
            packet.damage_type, packet.hit_location, data.target.injury_tolerance
        )
        if (
            data.optional_rules.edge_protection
            and packet.damage_type == "cut"
            and effective_dr > 0
            and result.penetrating_damage > 0
            and packet.basic_damage <= 2 * effective_dr
        ):
            result.wounding_modifier = 1.0
            result.notes.append("edge_protection_converted_cutting_to_crushing")
            result.references.append(RuleReference("Low-Tech", "102"))
        raw_injury = math.floor(result.penetrating_damage * result.wounding_modifier)
        if result.penetrating_damage > 0:
            raw_injury = max(1, raw_injury)
        raw_injury += result.blunt_trauma

        if data.target.injury_tolerance.lower() == "diffuse" and not packet.large_area:
            cap = 1 if packet.damage_type in _PIERCING | {"imp"} else 2
            raw_injury = min(raw_injury, cap)
            result.notes.append("diffuse_injury_cap")

        result.uncapped_injury = raw_injury
        threshold = _crippling_threshold(packet.hit_location, data.target.max_hp)
        accumulated = data.accumulated_injury
        if accumulated is None:
            accumulated = sum(
                wound.uncapped_injury for wound in data.target.wounds
                if wound.location == packet.hit_location
            )
        crippling_basis = raw_injury + (accumulated if data.optional_rules.accumulated_wounds else 0)
        if threshold is not None and crippling_basis >= threshold:
            result.crippling = True
            if packet.hit_location != "eye":
                raw_injury = min(raw_injury, threshold)
            if result.uncapped_injury >= 2 * threshold:
                result.dismemberment = True
        result.injury = raw_injury
        result.major_wound = result.injury > data.target.max_hp / 2 or result.crippling
        result.target_hp_after = data.target.current_hp - result.injury

        shock = _shock_penalty(result.injury, data.target.max_hp, data.target.high_pain_threshold)
        delta = StateDelta(hp_change=-result.injury, shock=shock)
        bleeding = (
            data.optional_rules.bleeding
            and result.injury > 0
            and (
                packet.damage_type in {"cut", "imp"} | _PIERCING
                or (packet.damage_type in {"burn", "cor"} and result.major_wound)
            )
        )
        wound = WoundRecord(
            location=packet.hit_location,
            injury=result.injury,
            uncapped_injury=result.uncapped_injury,
            damage_type=packet.damage_type,
            bleeding=bleeding,
            source=packet.source,
            page=packet.page,
        )
        if result.injury > 0:
            delta.wounds.append(wound)
        if result.crippling:
            delta.crippled_locations.append(packet.hit_location)
        if result.dismemberment:
            delta.destroyed_locations.append(packet.hit_location)
        if packet.damage_type == "cor" and packet.basic_damage >= 5:
            loss = packet.basic_damage // 5
            for layer in armor.layers:
                if layer.enabled and layer.armor.protects(packet.hit_location, packet.direction):
                    delta.armor_dr_loss[layer.armor.identifier] = loss
                    break
        for layer_detail in result.armor_layers:
            if not layer_detail.get("protects"):
                continue
            identifier = str(layer_detail["identifier"])
            if layer_detail.get("ablative"):
                delta.armor_dr_loss[identifier] = delta.armor_dr_loss.get(identifier, 0) + min(
                    layer_detail["dr"], packet.basic_damage
                )
            elif layer_detail.get("semi_ablative") and packet.basic_damage >= 10:
                delta.armor_dr_loss[identifier] = delta.armor_dr_loss.get(identifier, 0) + packet.basic_damage // 10

        needs_knockdown = result.major_wound or (
            result.injury > 0 and packet.hit_location in _HEAD | {"vitals", "groin"}
        )
        if needs_knockdown:
            modifier = 3 if data.target.high_pain_threshold else -4 if data.target.low_pain_threshold else 0
            if result.major_wound and packet.hit_location in {"face", "vitals", "groin", "jaw"}:
                modifier -= 5
            if result.major_wound and packet.hit_location in {"skull", "eye"}:
                modifier -= 10
            result.knockdown_target = data.target.ht + modifier
            pending = {
                "kind": "knockdown_and_stunning",
                "target": result.knockdown_target,
                "source": "Basic Set",
                "page": "420",
            }
            result.checks.append(pending)
            delta.pending_checks.append(dict(pending))

        if result.target_hp_after <= 0 and data.target.current_hp > 0:
            pending = {"kind": "consciousness", "target": data.target.ht, "source": "Basic Set", "page": "419"}
            result.checks.append(pending)
            delta.pending_checks.append(dict(pending))

        for multiple in _crossed_negative_hp_multiples(
            data.target.current_hp, result.target_hp_after, data.target.max_hp
        ):
            pending = {
                "kind": "death", "multiple": multiple, "target": data.target.ht,
                "source": "Basic Set", "page": "419",
            }
            result.checks.append(pending)
            delta.pending_checks.append(dict(pending))
        if result.target_hp_after <= -5 * data.target.max_hp:
            delta.set_dead = True
            delta.add_conditions.append("dead")
            result.notes.append("automatic_death")

        if packet.ranged and packet.damage_type in _OVERPENETRATION_TYPES and packet.cover_dr is not None:
            allowed = packet.damage_type != "burn" or packet.tight_beam
            if allowed:
                residual = max(0, packet.basic_damage - max(0, packet.cover_dr))
                if residual:
                    result.residual_packet = replace(packet, basic_damage=residual, cover_dr=None)
                result.notes.append("overpenetration_checked")
                result.references.append(RuleReference("Basic Set", "408"))

        if data.optional_rules.partial_injury and result.crippling:
            pending = {"kind": "partial_injury", "source": "Martial Arts", "page": "136"}
            delta.pending_checks.append(pending)
            result.checks.append(dict(pending))
        if data.optional_rules.lasting_injury and result.major_wound:
            pending = {"kind": "lasting_injury", "source": "Basic Set", "page": "422"}
            delta.pending_checks.append(pending)
            result.checks.append(dict(pending))
        if data.optional_rules.severe_bleeding and bleeding and packet.hit_location in {
            "neck", "vitals", "neck_artery", "limb_artery"
        }:
            delta.add_conditions.append("severe_bleeding")
            result.references.append(RuleReference("Martial Arts", "138"))
        protecting_layers = [item for item in result.armor_layers if item.get("protects")]
        if data.optional_rules.harsh_layering and len(protecting_layers) > 1:
            pending = {
                "kind": "harsh_layering", "layers": len(protecting_layers),
                "source": "Low-Tech", "page": "103",
            }
            delta.pending_checks.append(pending)
            result.checks.append(dict(pending))
            result.notes.append("harsh_layering_requires_mobility_penalty")
        if (
            data.optional_rules.plate_degradation
            and result.penetrating_damage > 0
            and any(layer.armor.rigid and layer.enabled for layer in armor.layers)
        ):
            pending = {
                "kind": "plate_degradation", "basic_damage": packet.basic_damage,
                "source": "Low-Tech", "page": "102",
            }
            delta.pending_checks.append(pending)
            result.checks.append(dict(pending))
            result.notes.append("plate_degradation_requires_material_check")

        result.state_delta = delta
        return result

    @staticmethod
    def _resolve_check(kind: str, target: int, supplied: Optional[int]) -> Dict[str, Any]:
        if supplied is None:
            roll, dice = roll_3d6()
        else:
            roll, dice = supplied, None
        outcome = evaluate_success_roll(target, roll)
        return {"kind": kind, "target": target, "roll": roll, "dice": dice, **outcome}

    def resolve(self, data: InjuryInput, *, knockdown_roll: Optional[int] = None,
                consciousness_roll: Optional[int] = None,
                death_rolls: Optional[Sequence[int]] = None) -> InjuryResult:
        armor = data.armor if data.armor is not None else data.target.armor
        coverage_rolls = dict(data.coverage_rolls)
        for layer in armor.layers:
            if (
                layer.enabled and layer.armor.coverage < 6
                and layer.armor.identifier not in coverage_rolls
                and layer.coverage_roll is None
            ):
                coverage_rolls[layer.armor.identifier] = roll_1d6()
        resolved_input = replace(data, coverage_rolls=coverage_rolls)
        result = self.calculate(resolved_input)
        if not result.valid:
            return result
        supplied_death = list(death_rolls if death_rolls is not None else data.death_rolls)
        resolved: List[Dict[str, Any]] = []
        death_index = 0
        pending_after: List[Dict[str, Any]] = []
        for check in result.checks:
            kind = check["kind"]
            if kind == "knockdown_and_stunning":
                supplied = knockdown_roll if knockdown_roll is not None else data.knockdown_roll
            elif kind == "consciousness":
                supplied = consciousness_roll if consciousness_roll is not None else data.consciousness_roll
            elif kind == "death":
                supplied = supplied_death[death_index] if death_index < len(supplied_death) else None
                death_index += 1
            else:
                pending_after.append(check)
                continue
            outcome = self._resolve_check(kind, int(check["target"]), supplied)
            outcome.update({key: value for key, value in check.items() if key not in outcome})
            resolved.append(outcome)
            if kind == "knockdown_and_stunning" and not outcome["success"]:
                result.state_delta.posture = "prone"
                if outcome["critical_failure"] or outcome["margin"] >= 5:
                    result.state_delta.set_unconscious = True
                    result.state_delta.add_conditions.append("unconscious")
                else:
                    result.state_delta.set_stunned = True
                    result.state_delta.add_conditions.append("stunned")
            elif kind == "consciousness" and not outcome["success"]:
                result.state_delta.set_unconscious = True
                result.state_delta.add_conditions.append("unconscious")
            elif kind == "death" and not outcome["success"]:
                result.state_delta.set_dead = True
                result.state_delta.add_conditions.append("dead")
        result.checks = resolved + pending_after
        result.state_delta.pending_checks = pending_after
        return result


def armor_dr_for(loadout: ArmorLoadout, location: str, damage_type: str,
                 direction: str = "front") -> int:
    """Convenience helper used by UI summaries and other calculators."""

    packet = DamagePacket(0, damage_type, hit_location=location, direction=direction)
    total = loadout.natural_dr + _location_natural_dr(location)
    for layer in loadout.layers:
        dr, _ = InjuryEngine._layer_dr(layer, packet, None)
        total += dr
    return total


def active_bleeding_wounds(wounds: Iterable[WoundRecord]) -> List[WoundRecord]:
    return [wound for wound in wounds if wound.bleeding and not wound.bleeding_stopped]


def calculate_simple_injury(basic_damage: int, damage_type: str, target_hp: int,
                            target_dr: int = 0, *, flexible: bool = False,
                            hit_location: str = "torso", source: str = "Basic Set",
                            page: str = "377-381") -> InjuryResult:
    """Bridge legacy calculators into the shared engine without state changes."""

    layers: List[ArmorLayer] = []
    natural_dr = max(0, target_dr)
    if flexible and target_dr > 0:
        natural_dr = 0
        layers.append(ArmorLayer(ArmorRecord(
            identifier="legacy.flexible-armor",
            source=source,
            page=page,
            name="Flexible armor",
            locations=["all"],
            dr=target_dr,
            flexible=True,
            rigid=False,
        )))
    target = CombatantState(
        identifier="legacy_target", name="Target", max_hp=target_hp,
        current_hp=target_hp, armor=ArmorLoadout(layers=layers, natural_dr=natural_dr),
    )
    return InjuryEngine().calculate(InjuryInput(
        packet=DamagePacket(
            basic_damage=max(0, basic_damage), damage_type=damage_type,
            hit_location=hit_location, source=source, page=page,
        ),
        target=target,
    ))
