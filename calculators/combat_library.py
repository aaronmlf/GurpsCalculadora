"""Named combatant templates and explicit combat session snapshots."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
import json
from pathlib import Path
from typing import Mapping, Optional

from calculators.combat_session import DEFENSES, CombatSession, normalize_resource_pools, validated_combatant
from calculators.injury import ArmorLoadout, CombatantState
from utils.local_json import quarantine_json, write_atomic_json


LEGACY_SCHEMA = "gurps-calculadora.combat-library.v1"
SCHEMA = "gurps-calculadora.combat-library.v2"
PROFILE_SCORES = ("st", "dx", "iq", "ht", "max_hp", "max_fp", "dodge", "parry", "block")
MAX_ENTRIES = 250


def clean_name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise ValueError("combat_library_invalid_name")
    return value.strip()


@dataclass
class CombatantProfile:
    name: str
    st: int = 10
    dx: int = 10
    iq: int = 10
    ht: int = 10
    max_hp: int = 10
    max_fp: int = 10
    dodge: int = 8
    parry: int = 8
    block: int = 8
    size_modifier: int = 0
    armor: ArmorLoadout = field(default_factory=ArmorLoadout)
    melee_weapon_id: str = ""
    ranged_weapon_id: str = ""
    will: Optional[int] = None
    per: Optional[int] = None
    basic_speed: Optional[float] = 5.0
    basic_move: Optional[int] = 5
    resource_pools: dict = field(default_factory=dict)
    unknown_defenses: list = field(default_factory=list)
    unknown_size_modifier: bool = False

    def __post_init__(self):
        self.name = clean_name(self.name)
        for key in PROFILE_SCORES:
            value = getattr(self, key)
            minimum = 0 if key in ("max_fp", "dodge", "parry", "block") else 1
            if type(value) is not int or not minimum <= value <= 100000:
                raise ValueError("combat_library_invalid_score")
        if type(self.size_modifier) is not int or abs(self.size_modifier) > 100:
            raise ValueError("combat_library_invalid_score")
        for key in ("melee_weapon_id", "ranged_weapon_id"):
            if not isinstance(getattr(self, key), str):
                raise ValueError("combat_library_invalid_profile")
        if type(self.armor.natural_dr) is not int or self.armor.natural_dr < 0:
            raise ValueError("combat_library_invalid_score")
        self.resource_pools = normalize_resource_pools(self.resource_pools)
        self.instantiate("combatant")  # Validate the extra state fields on load, too.

    @classmethod
    def from_state(cls, state):
        armor = deepcopy(state.armor)
        for layer in armor.layers:
            layer.current_dr_loss = 0
        return cls(state.name, **{key: getattr(state, key) for key in PROFILE_SCORES},
                   size_modifier=state.size_modifier, armor=armor,
                   melee_weapon_id=state.melee_weapon_id, ranged_weapon_id=state.ranged_weapon_id,
                   will=state.will, per=state.per, basic_speed=state.basic_speed, basic_move=state.basic_move,
                   resource_pools=deepcopy(state.resource_pools),
                   unknown_defenses=list(state.unknown_defenses), unknown_size_modifier=state.unknown_size_modifier)

    @classmethod
    def from_dict(cls, data):
        return cls(**dict(data, armor=ArmorLoadout.from_dict(data.get("armor", {}))))

    def to_dict(self):
        return asdict(self)

    def instantiate(self, identifier):
        data = self.to_dict()
        for pool in data["resource_pools"].values():
            pool["current"] = pool["maximum"]
        return validated_combatant(CombatantState.from_dict(dict(
            data, identifier=identifier, current_hp=self.max_hp, current_fp=self.max_fp,
        )))


def combatant_from_imported(character):
    """Convert normalized sheet data without estimating missing defenses or armor."""
    scores = {name: getattr(character, name) for name in DEFENSES}
    return validated_combatant(CombatantState(
        name=character.name, st=character.st, dx=character.dx, iq=character.iq, ht=character.ht,
        will=character.will, per=character.per,
        max_hp=character.max_hp, current_hp=character.current_hp,
        max_fp=character.max_fp, current_fp=character.current_fp,
        basic_speed=character.basic_speed, basic_move=character.basic_move,
        size_modifier=0 if character.size_modifier is None else character.size_modifier,
        unknown_size_modifier=character.size_modifier is None,
        unknown_defenses=[name for name, value in scores.items() if value is None],
        resource_pools={
            track.identifier: {"label": track.name, "maximum": track.maximum, "current": track.current}
            for track in character.energy_tracks
        },
        source_id=character.source_id, source_format=character.source_format,
        source_version=character.source_version, source_name=character.source_name,
        **{name: value if value is not None else 0 for name, value in scores.items()},
    ))


class CombatLibrary:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = {}
        self.sessions = {}
        self.imported = {}
        self.warning = None
        self.read_only = False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") not in (SCHEMA, LEGACY_SCHEMA):
                raise ValueError("combat_library_invalid_schema")
            profiles = {clean_name(key): CombatantProfile.from_dict(item)
                        for key, item in data["profiles"].items()}
            sessions = {clean_name(key): CombatSession.from_dict(item).to_dict()
                        for key, item in data["sessions"].items()}
            imported = self._imported_records({
                key: CombatantState.from_dict(item) for key, item in data.get("imported", {}).items()
            })
            if max(len(profiles), len(sessions), len(imported)) > MAX_ENTRIES:
                raise ValueError("combat_library_limit")
            self.profiles, self.sessions, self.imported = profiles, sessions, imported
        except FileNotFoundError:
            pass
        except OSError:
            self.warning, self.read_only = self.path, True
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            try:
                self.warning = quarantine_json(self.path)
            except OSError:
                self.warning, self.read_only = self.path, True

    @staticmethod
    def _imported_records(records):
        if not isinstance(records, Mapping) or len(records) > MAX_ENTRIES:
            raise ValueError("combat_library_limit")
        normalized = {}
        for identifier, state in records.items():
            if (not isinstance(identifier, str) or not identifier.strip()
                    or not isinstance(state, CombatantState)
                    or (state.source_id and state.source_id != identifier)):
                raise ValueError("combat_library_invalid_profile")
            normalized[identifier] = validated_combatant(replace(state, source_id=identifier, identifier="combatant"))
        return normalized

    def _commit(self, profiles, sessions, imported=None):
        imported = self.imported if imported is None else imported
        if self.read_only:
            raise PermissionError(str(self.path))
        if max(len(profiles), len(sessions), len(imported)) > MAX_ENTRIES:
            raise ValueError("combat_library_limit")
        write_atomic_json(self.path, {"schema": SCHEMA,
                                     "profiles": {key: item.to_dict() for key, item in profiles.items()},
                                     "sessions": sessions,
                                     "imported": {key: item.to_dict() for key, item in imported.items()}})
        self.profiles, self.sessions, self.imported = profiles, sessions, imported

    def save_profile(self, profile):
        self._commit(dict(self.profiles, **{profile.name: deepcopy(profile)}), self.sessions)

    def save_session(self, name, session):
        self._commit(self.profiles, dict(self.sessions, **{clean_name(name): session.to_dict()}))

    def open_session(self, name, autosave_path=None):
        return CombatSession.from_dict(deepcopy(self.sessions[name]), autosave_path)

    def save_imported_batch(self, records):
        updates = self._imported_records(records)
        if updates:
            self._commit(self.profiles, self.sessions, {**self.imported, **updates})

    def open_imported(self, source_id):
        return deepcopy(self.imported[source_id])
