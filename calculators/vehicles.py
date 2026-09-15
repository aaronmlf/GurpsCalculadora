"""Operational vehicle and spacecraft calculations for GURPS 4e."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from calculators.collisions import CollisionsCalculator
from calculators.injury import RuleReference
from calculators.ranged_combat import RangedAttackInput, RangedAttackResult, RangedCombatCalculator, WeaponRecord


@dataclass
class VehicleRecord:
    identifier: str
    name: str
    source: str
    page: str
    tech_level: str = ""
    vehicle_type: str = "ground"
    st_hp: int = 10
    ht: int = 10
    handling: int = 0
    stability_rating: int = 4
    move_acceleration: float = 1.0
    move_top_speed: float = 10.0
    size_modifier: int = 0
    dr: int = 0
    occupants: int = 1
    load_tons: float = 0.0
    range_miles: float = 0.0
    fuel_hours: float = 0.0
    weapons: List[str] = field(default_factory=list)
    systems: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    original: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "VehicleRecord":
        record_type = SpacecraftRecord if "acceleration_g" in value else cls
        return record_type(**dict(value))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SpacecraftRecord(VehicleRecord):
    scale: int = 0
    acceleration_g: float = 0.0
    delta_v_mps: float = 0.0
    power_points: int = 0
    sections: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)


@dataclass
class VehicleState:
    record: VehicleRecord
    current_hp: Optional[int] = None
    speed_yards_per_second: float = 0.0
    fuel_remaining: Optional[float] = None
    delta_v_remaining_mps: Optional[float] = None
    systems_disabled: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.current_hp is None:
            self.current_hp = self.record.st_hp
        if self.fuel_remaining is None:
            self.fuel_remaining = self.record.fuel_hours
        if self.delta_v_remaining_mps is None and isinstance(self.record, SpacecraftRecord):
            self.delta_v_remaining_mps = self.record.delta_v_mps


@dataclass
class VehicleMovementInput:
    vehicle: VehicleState
    duration_seconds: int = 1
    acceleration_fraction: float = 1.0
    environment: str = "road"
    maneuver: str = "straight"
    travel_distance_miles: float = 0.0
    gravity_g: float = 1.0


@dataclass
class VehicleMovementResult:
    valid: bool
    errors: List[str]
    initial_speed: float
    final_speed: float
    distance_yards: float
    control_roll: Optional[int]
    fuel_used: float
    delta_v_used_mps: float
    travel_time_seconds: float
    breakdown: List[Dict[str, Any]]
    references: List[RuleReference]


@dataclass
class VehicleCollisionInput:
    first: VehicleState
    second: VehicleState
    collision_type: str = "head_on"
    surface_type: str = "normal"


@dataclass
class VehicleAttackInput:
    attacker: VehicleState
    target: VehicleState
    weapon: WeaponRecord
    gunner_skill: int = 12
    distance_m: float = 100.0
    target_speed_mps: float = 0.0
    aim_seconds: int = 0
    targeting_bonus: int = 0
    shots_fired: int = 1
    profile: str = "basic"


@dataclass
class VehicleSession:
    vehicles: Dict[str, VehicleState]
    elapsed_seconds: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    _undo: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    autosave_path: Optional[Path] = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, value, autosave_path=None):
        from utils.editor_records import validate_vehicle
        if not isinstance(value, dict) or value.get('schema') != 'gurps-calculadora.vehicle-session.v1':
            raise ValueError('invalid_vehicle_session')
        states = {}
        for key, raw in value['vehicles'].items():
            data = dict(raw)
            data['record'] = validate_vehicle(VehicleRecord.from_dict(data['record']))
            state = VehicleState(**data)
            if not isinstance(key, str) or not key:
                raise ValueError('invalid_vehicle_session')
            for number in (state.speed_yards_per_second, state.fuel_remaining, state.delta_v_remaining_mps):
                if number is not None and (isinstance(number, bool) or not math.isfinite(number) or number < 0):
                    raise ValueError('invalid_vehicle_session')
            if type(state.current_hp) is not int:
                raise ValueError('invalid_vehicle_session')
            if any(not isinstance(v, list) or any(not isinstance(s, str) for s in v)
                   for v in (state.systems_disabled, state.conditions)):
                raise ValueError('invalid_vehicle_session')
            states[key] = state
        elapsed = value.get('elapsed_seconds', 0)
        if isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('invalid_vehicle_session')
        history = value.get('history', [])
        if not isinstance(history, list) or any(not isinstance(event, dict) for event in history):
            raise ValueError('invalid_vehicle_session')
        return cls(states, elapsed, deepcopy(history[-100:]), autosave_path=autosave_path)

    @classmethod
    def load_or_new(cls, path):
        from utils.editor_records import read_document
        from uuid import uuid4
        path = Path(path)
        if not path.exists():
            return cls({}, autosave_path=path)
        try:
            return cls.from_dict(read_document(path), path)
        except (ValueError, TypeError, KeyError, AttributeError):
            backup = path.with_name(path.name + '.invalid-' + uuid4().hex)
            path.replace(backup)
            session = cls({}, autosave_path=path)
            session.recovered_file = backup
            return session

    def save(self):
        if self.autosave_path is not None:
            from utils.editor_records import write_document
            write_document(self.autosave_path, self.snapshot())

    def snapshot(self) -> Dict[str, Any]:
        return {"schema": "gurps-calculadora.vehicle-session.v1",
                "elapsed_seconds": self.elapsed_seconds, "history": deepcopy(self.history[-100:]),
                "vehicles": {key: asdict(value) for key, value in self.vehicles.items()}}

    def apply_movement(self, identifier: str, result: VehicleMovementResult,
                       initial_state=None, expected_snapshot=None) -> None:
        if expected_snapshot is not None and self.snapshot() != expected_snapshot:
            raise ValueError('stale_vehicle_movement')
        candidate = deepcopy(self)
        if identifier not in candidate.vehicles and initial_state is not None:
            candidate.vehicles[identifier] = deepcopy(initial_state)
        if not result.valid or identifier not in candidate.vehicles:
            raise ValueError("invalid_vehicle_movement")
        state = candidate.vehicles[identifier]
        values = (result.final_speed, result.fuel_used, result.delta_v_used_mps, result.travel_time_seconds)
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('invalid_vehicle_movement')
        if (not math.isclose(state.speed_yards_per_second, result.initial_speed) or
                result.fuel_used > (state.fuel_remaining or 0) or
                result.delta_v_used_mps > (state.delta_v_remaining_mps or 0)):
            raise ValueError('stale_vehicle_movement')
        candidate._undo = (candidate._undo + [self.snapshot()])[-100:]
        state.speed_yards_per_second = result.final_speed
        state.fuel_remaining = max(0.0, float(state.fuel_remaining or 0) - result.fuel_used)
        if state.delta_v_remaining_mps is not None:
            state.delta_v_remaining_mps = max(0.0, state.delta_v_remaining_mps - result.delta_v_used_mps)
        candidate.elapsed_seconds += result.travel_time_seconds
        candidate.history = (candidate.history + [{"kind": "movement", "vehicle": identifier, "result": asdict(result)}])[-100:]
        candidate.save()
        # Preserve the public live-state references, but only after disk commit.
        for key, original in self.vehicles.items():
            original.__dict__.update(candidate.vehicles[key].__dict__)
            candidate.vehicles[key] = original
        self.__dict__.update(candidate.__dict__)

    def undo(self) -> bool:
        if not self._undo:
            return False
        candidate = self.from_dict(self._undo[-1], self.autosave_path)
        candidate._undo = deepcopy(self._undo[:-1])
        candidate.save()
        self.__dict__.update(candidate.__dict__)
        return True


class VehicleEngine:
    TERRAIN_MULTIPLIERS = {"road": 1.0, "off_road": 0.5, "water": 0.75, "air": 1.0, "space": 1.0}

    def __init__(self) -> None:
        self.collisions = CollisionsCalculator()
        self.ranged = RangedCombatCalculator()

    def calculate_movement(self, data: VehicleMovementInput) -> VehicleMovementResult:
        errors: List[str] = []
        if (not all(math.isfinite(v) for v in (data.duration_seconds, data.acceleration_fraction,
                data.travel_distance_miles, data.vehicle.speed_yards_per_second)) or
                data.duration_seconds < 0 or data.travel_distance_miles < 0 or
                data.vehicle.speed_yards_per_second < 0 or not 0 <= data.acceleration_fraction <= 1):
            errors.append("invalid_movement_input")
            return VehicleMovementResult(False, errors, 0, 0, 0, None, 0, 0, 0, [], [])
        terrain = self.TERRAIN_MULTIPLIERS.get(data.environment)
        if terrain is None:
            errors.append("invalid_environment")
            terrain = 1.0
        record = data.vehicle.record
        initial = max(0.0, data.vehicle.speed_yards_per_second)
        acceleration = record.move_acceleration * data.acceleration_fraction
        delta_v = 0.0
        if isinstance(record, SpacecraftRecord):
            acceleration = record.acceleration_g * 10.73 * data.acceleration_fraction
            delta_v = acceleration * data.duration_seconds / 1760.0
            if delta_v > float(data.vehicle.delta_v_remaining_mps or 0):
                errors.append("insufficient_delta_v")
        top_speed = record.move_top_speed * terrain
        if isinstance(record, SpacecraftRecord):
            top_speed = math.inf  # Vacuum movement is limited by delta-v, not a road top speed.
        if initial > top_speed:
            errors.append("initial_speed_exceeds_limit")
        accelerating_time = min(data.duration_seconds, max(0, (top_speed - initial) / acceleration)) if acceleration > 0 else 0
        final = initial + acceleration * accelerating_time
        distance = initial * accelerating_time + acceleration * accelerating_time ** 2 / 2
        distance += final * (data.duration_seconds - accelerating_time)
        control = None
        if data.maneuver in {"hard_turn", "emergency_stop", "stunt"}:
            control = record.ht + record.handling
        fuel_used = data.duration_seconds / 3600.0 if record.fuel_hours else 0.0
        if fuel_used > float(data.vehicle.fuel_remaining or 0) and record.fuel_hours:
            errors.append("insufficient_fuel")
        travel_time = data.duration_seconds
        if data.travel_distance_miles > 0:
            requested_distance = data.travel_distance_miles * 1760
            if requested_distance <= distance and acceleration > 0:
                accelerated_distance = initial * accelerating_time + acceleration * accelerating_time ** 2 / 2
                if requested_distance <= accelerated_distance:
                    travel_time = (math.sqrt(initial ** 2 + 2 * acceleration * requested_distance) - initial) / acceleration
                    final = initial + acceleration * travel_time
                else:
                    travel_time = accelerating_time + (requested_distance - accelerated_distance) / final
            elif final > 0:
                travel_time = data.duration_seconds + (requested_distance - distance) / final
            else:
                errors.append("unreachable_travel_distance")
            distance = requested_distance
            fuel_used = travel_time / 3600.0 if record.fuel_hours else 0.0
            if isinstance(record, SpacecraftRecord):
                delta_v = acceleration * min(data.duration_seconds, travel_time) / 1760
        errors = [error for error in errors if error not in {"insufficient_fuel", "insufficient_delta_v"}]
        if record.fuel_hours and fuel_used > float(data.vehicle.fuel_remaining or 0):
            errors.append("insufficient_fuel")
        if isinstance(record, SpacecraftRecord) and delta_v > float(data.vehicle.delta_v_remaining_mps or 0):
            errors.append("insufficient_delta_v")
        return VehicleMovementResult(
            valid=not errors, errors=errors, initial_speed=initial, final_speed=round(final, 3),
            distance_yards=round(distance, 3), control_roll=control, fuel_used=round(fuel_used, 4),
            delta_v_used_mps=round(delta_v, 4), travel_time_seconds=round(travel_time, 2),
            breakdown=[{"key": "acceleration", "value": acceleration}, {"key": "terrain", "value": terrain}],
            references=[RuleReference("Basic Set", "466-470"), RuleReference("Spaceships", "37-39, 54-57")],
        )

    def calculate_collision(self, data: VehicleCollisionInput) -> Dict[str, Any]:
        return self.collisions.calculate_collision(
            data.first.record.st_hp, round(data.first.speed_yards_per_second),
            data.second.record.st_hp, round(data.second.speed_yards_per_second),
            collision_type=data.collision_type, surface_type=data.surface_type,
            object2_dr=data.second.record.dr,
        )

    def calculate_attack(self, data: VehicleAttackInput) -> RangedAttackResult:
        return self.ranged.calculate(RangedAttackInput(
            weapon=data.weapon, profile=data.profile, skill=data.gunner_skill,
            distance_m=data.distance_m, target_speed_mps=data.target_speed_mps,
            target_sm=data.target.record.size_modifier, aim_seconds=data.aim_seconds,
            targeting_system_bonus=data.targeting_bonus, shots_fired=data.shots_fired,
            target_dr=data.target.record.dr, target_hp=data.target.record.st_hp,
        ))


VEHICLE_CATALOG_SCHEMA = "gurps-calculadora.vehicle-catalog.v1"


class VehicleCatalog:
    def __init__(self, builtin_path: Path, user_path: Path, load_user: bool = True):
        self.builtin_path, self.user_path = Path(builtin_path), Path(user_path)
        self.builtin = self._read(self.builtin_path)
        self.custom = self._read(self.user_path) if load_user and self.user_path.exists() else []

    @staticmethod
    def _read(path: Path) -> List[VehicleRecord]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_catalog_json") from exc
        if document.get("schema") != VEHICLE_CATALOG_SCHEMA or not isinstance(document.get("vehicles"), list):
            raise ValueError("invalid_catalog_schema")
        records = [VehicleRecord.from_dict(item) for item in document["vehicles"]]
        if len({item.identifier for item in records}) != len(records):
            raise ValueError("duplicate_catalog_identifier")
        return records

    @property
    def vehicles(self) -> List[VehicleRecord]:
        return self.builtin + self.custom

    def search(self, query: str = "", vehicle_type: Optional[str] = None,
               source: Optional[str] = None, tech_level: Optional[str] = None) -> List[VehicleRecord]:
        needle = query.casefold().strip()
        return sorted([record for record in self.vehicles
                       if (not needle or needle in record.name.casefold())
                       and (vehicle_type is None or record.vehicle_type == vehicle_type)
                       and (source is None or source.casefold() in record.source.casefold())
                       and (tech_level is None or record.tech_level == tech_level)],
                      key=lambda item: (item.name.casefold(), item.identifier))

    def save_custom(self, record: VehicleRecord) -> None:
        if not record.identifier.startswith("custom."):
            record.identifier = "custom.vehicle." + "-".join(record.name.casefold().split())
        existing = {item.identifier: item for item in self.custom}
        existing[record.identifier] = record
        updated = sorted(existing.values(), key=lambda item: item.identifier)
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.user_path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({'schema': VEHICLE_CATALOG_SCHEMA, 'vehicles': [item.to_dict() for item in updated]},
                          handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.user_path)
            self.custom = updated
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
