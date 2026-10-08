"""Validated user editor documents. No rule text or executable content."""
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import tempfile
from calculators.vehicles import VehicleRecord
from calculators.powers import AdvantageRecord, ModifierRecord, PowerRecord, AbilityBuildInput


VEHICLE_FIELDS = {
    'st_hp': int, 'ht': int, 'handling': int, 'stability_rating': int,
    'move_acceleration': float, 'move_top_speed': float, 'size_modifier': int,
    'dr': int, 'occupants': int, 'range_miles': float, 'fuel_hours': float,
}


def number(raw, kind):
    if isinstance(raw, bool):
        raise ValueError('invalid_editor_number')
    value = float(str(raw).replace(',', '.'))
    if not math.isfinite(value) or kind is int and not value.is_integer():
        raise ValueError('invalid_editor_number')
    return kind(value)


def validate_vehicle(record):
    if not isinstance(record.identifier, str) or not record.identifier:
        raise ValueError('invalid_editor_vehicle')
    if not isinstance(record.name, str) or not record.name.strip():
        raise ValueError('invalid_editor_name')
    for field, kind in VEHICLE_FIELDS.items():
        value = number(getattr(record, field), kind)
        minimum = 1 if field in ('st_hp', 'ht') else 0
        if field not in ('handling', 'size_modifier') and value < minimum:
            raise ValueError('invalid_editor_number')
        setattr(record, field, value)
    if not isinstance(record.vehicle_type, str) or not record.vehicle_type.strip():
        raise ValueError('invalid_editor_vehicle')
    for field in ('weapons', 'tags'):
        value = getattr(record, field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError('invalid_editor_vehicle')
    if not isinstance(record.systems, list) or not all(isinstance(item, dict) for item in record.systems) or not isinstance(record.original, dict):
        raise ValueError('invalid_editor_vehicle')
    if number(record.load_tons, float) < 0:
        raise ValueError('invalid_editor_number')
    if hasattr(record, 'acceleration_g'):
        for field in ('acceleration_g', 'delta_v_mps', 'power_points', 'scale'):
            if number(getattr(record, field), float) < 0:
                raise ValueError('invalid_editor_number')
        if not isinstance(record.sections, dict):
            raise ValueError('invalid_editor_vehicle')
    return record


def vehicle_document(record):
    return {'schema': 'gurps-calculadora.vehicle-editor.v1', 'vehicle': asdict(validate_vehicle(record))}


def load_vehicle_document(data):
    if not isinstance(data, dict) or data.get('schema') != 'gurps-calculadora.vehicle-editor.v1':
        raise ValueError('invalid_editor_document')
    try:
        return validate_vehicle(VehicleRecord.from_dict(data['vehicle']))
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('invalid_editor_document') from exc


def ability_document(name, build):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('invalid_editor_name')
    build.advantage.base_cost = number(build.advantage.base_cost, float)
    build.advantage.cost_per_level = number(build.advantage.cost_per_level, float)
    build.levels = number(build.levels, int)
    if min(build.advantage.base_cost, build.advantage.cost_per_level) < 0 or build.levels < 1:
        raise ValueError('invalid_editor_number')
    ids = [item.identifier for item in build.modifiers]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate_editor_modifier')
    for item in build.modifiers:
        item.percent = number(item.percent, int)
        if not isinstance(item.identifier, str) or not item.identifier or not isinstance(item.name, str):
            raise ValueError('invalid_editor_document')
    if build.power:
        build.power.power_modifier = number(build.power.power_modifier, int)
    return {'schema': 'gurps-calculadora.ability-editor.v1', 'name': name, 'build': asdict(build)}


def load_ability_document(data):
    if not isinstance(data, dict) or data.get('schema') != 'gurps-calculadora.ability-editor.v1':
        raise ValueError('invalid_editor_document')
    try:
        raw = dict(data['build'])
        raw['advantage'] = AdvantageRecord(**raw['advantage'])
        raw['modifiers'] = [ModifierRecord(**item) for item in raw['modifiers']]
        if raw.get('power'):
            raw['power'] = PowerRecord(**raw['power'])
        if type(raw.get('alternate_ability', False)) is not bool:
            raise ValueError('invalid_editor_document')
        build = AbilityBuildInput(**raw)
        ability_document(data['name'], build)
        return data['name'], build
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('invalid_editor_document') from exc


def read_document(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('invalid_editor_document')
    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError('invalid_editor_document')
            data[key] = value
        return data
    def invalid_constant(value):
        raise ValueError('invalid_editor_number')
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique, parse_constant=invalid_constant)
    except RecursionError as exc:
        raise ValueError('invalid_editor_document') from exc


def write_document(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(document, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
