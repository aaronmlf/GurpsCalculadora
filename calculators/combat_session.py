"""Ordered encounter roster with explicit, atomic state application."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence
from uuid import uuid4

from calculators.battle_map import BattleMap
from calculators.injury import ArmorLayer, ArmorRecord, CombatantState, StateDelta, active_bleeding_wounds
from utils.dice_roller import evaluate_success_roll, roll_3d6
from utils.local_json import quarantine_json, write_atomic_json


LEGACY_SESSION_SCHEMA = "gurps-calculadora.combat-session.v1"
PREVIOUS_SESSION_SCHEMA = "gurps-calculadora.combat-session.v2"
SESSION_SCHEMA = "gurps-calculadora.combat-session.v3"
MAP_CHANGE_EVENT = "battle_map_updated"
SESSION_HISTORY_LIMIT = 100
MAX_COMBATANTS = 100
COMBATANT_IDS = ("combatant_a", "combatant_b")
DEFENSES = ("dodge", "parry", "block")
EDITABLE_STATE_FIELDS = frozenset({
    "name", "team", "group", "current_hp", "current_fp", "posture", "facing", "aware",
    "conditions", "stunned", "unconscious", "dead", "shock", "resource_pools", "size_modifier",
    *DEFENSES,
})
GRAPPLE_CONDITIONS = {"grappled", "pinned", "choked", "arm_lock", "leg_lock", "neck_lock"}
COMBATANT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
TRANSIENT_ACTION_CONDITIONS = {
    "all_out_attack_no_defense",
    "committed_attack_defense_restrictions",
    "defensive_attack_parry_bonus",
}


def _valid_text(value, maximum, *, blank=False):
    return (isinstance(value, str) and len(value) <= maximum
            and (blank or bool(value.strip())) and not any(ord(char) < 32 for char in value))


def _valid_id(identifier):
    return isinstance(identifier, str) and identifier != "system" and COMBATANT_ID.fullmatch(identifier)


def normalize_resource_pools(pools):
    if not isinstance(pools, Mapping) or len(pools) > 32:
        raise ValueError("encounter_invalid_resource")
    normalized = {}
    for identifier, pool in pools.items():
        if (not _valid_text(identifier, 128) or not isinstance(pool, Mapping)
                or set(pool) - {"label", "current", "maximum"}):
            raise ValueError("encounter_invalid_resource")
        current, maximum, label = pool.get("current"), pool.get("maximum"), pool.get("label", identifier)
        if (type(current) is not int or type(maximum) is not int or maximum < 0
                or not _valid_text(label, 128)):
            raise ValueError("encounter_invalid_resource")
        normalized[identifier] = {"label": label.strip(), "current": current, "maximum": maximum}
    return normalized


def _valid_resource_changes(changes):
    return isinstance(changes, Mapping) and all(
        _valid_text(identifier, 128) and type(change) is int
        for identifier, change in changes.items()
    )


def validated_combatant(state):
    """Validate encounter fields and return a copy detached from the caller."""
    if not isinstance(state, CombatantState):
        raise ValueError("invalid_session_combatants")
    for attr in ("max_hp", "current_hp", "max_fp", "current_fp", "st", "dx", "iq", "ht",
                 "dodge", "parry", "block", "shock", "personal_seconds", "action_count",
                 "size_modifier"):
        if type(getattr(state, attr)) is not int:
            raise ValueError("invalid_session_combatants")
    move = state.basic_move
    speed = state.basic_speed
    if (not _valid_id(state.identifier) or not _valid_text(state.name, 128)
            or state.max_hp < 1 or state.max_fp < 0
            or (move is not None and (type(move) is not int or move < 0))
            or (speed is not None and (type(speed) not in (int, float)
                                       or speed < 0 or not math.isfinite(speed)))
            or type(state.unknown_size_modifier) is not bool or not isinstance(state.unknown_defenses, list)
            or any(key not in DEFENSES for key in state.unknown_defenses)
            or not isinstance(state.conditions, list)
            or any(not _valid_text(condition, 128) for condition in state.conditions)
            or not isinstance(state.grapples, dict)
            or any(not _valid_id(key) or not isinstance(relation, dict)
                   for key, relation in state.grapples.items())):
        raise ValueError("invalid_session_combatants")
    for field_name, limit in (("team", 80), ("group", 80), ("source_id", 256),
                              ("source_format", 80), ("source_version", 80), ("source_name", 256)):
        if not _valid_text(getattr(state, field_name), limit, blank=True):
            raise ValueError("invalid_session_combatants")
    for attr in ("will", "per"):
        value = getattr(state, attr)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("invalid_session_combatants")
    result = deepcopy(state)
    result.resource_pools = normalize_resource_pools(result.resource_pools)
    result.unknown_defenses = [name for name in DEFENSES if name in result.unknown_defenses]
    return result


@dataclass
class SessionEvent:
    actor_id: str
    target_id: str
    label: str
    delta: StateDelta
    applied_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    actor_delta: Optional[StateDelta] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CombatSession:
    combatants: Dict[str, CombatantState]
    elapsed_seconds: int = 0
    events: List[SessionEvent] = field(default_factory=list)
    _undo_snapshots: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    autosave_path: Optional[Path] = field(default=None, repr=False)
    load_warning: Optional[str] = field(default=None, repr=False)
    combatant_order: List[str] = field(default_factory=list)
    battle_map: BattleMap = field(default_factory=BattleMap)
    active_pair: Optional[tuple[str, str]] = None

    def __post_init__(self):
        if not self.combatant_order:
            self.combatant_order = list(self.combatants)

    @classmethod
    def new(cls, autosave_path: Optional[Path] = None) -> "CombatSession":
        return cls(
            combatants={
                "combatant_a": CombatantState(identifier="combatant_a", name="Combatant A"),
                "combatant_b": CombatantState(identifier="combatant_b", name="Combatant B"),
            },
            autosave_path=autosave_path,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], autosave_path: Optional[Path] = None) -> "CombatSession":
        if not isinstance(value, Mapping) or value.get("schema") not in (
            SESSION_SCHEMA, PREVIOUS_SESSION_SCHEMA, LEGACY_SESSION_SCHEMA,
        ):
            raise ValueError("invalid_session_schema")
        raw_combatants = value.get("combatants")
        if not isinstance(raw_combatants, Mapping) or not 2 <= len(raw_combatants) <= MAX_COMBATANTS:
            raise ValueError("invalid_session_combatants")
        if value["schema"] == LEGACY_SESSION_SCHEMA:
            if set(raw_combatants) != set(COMBATANT_IDS):
                raise ValueError("invalid_session_combatants")
            order = list(COMBATANT_IDS)
        else:
            order = value.get("combatant_order")
            if (not isinstance(order, list) or len(order) != len(raw_combatants)
                    or any(not _valid_id(key) for key in order) or set(order) != set(raw_combatants)):
                raise ValueError("encounter_invalid_order")
        combatants = {
            identifier: validated_combatant(CombatantState.from_dict(raw_combatants[identifier]))
            for identifier in order
        }
        for identifier, state in combatants.items():
            if state.identifier != identifier:
                raise ValueError("invalid_session_combatants")
        battle_map = (
            BattleMap.from_dict(value.get("battle_map")) if value["schema"] == SESSION_SCHEMA else BattleMap()
        )
        if battle_map.tokens.keys() - combatants.keys():
            raise ValueError("unknown_combatant")
        # Optional in v3: snapshots made before role persistence keep their
        # roster and map, falling back to the first two members.
        pair = value.get("active_pair")
        if (not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(key, str) or key not in combatants for key in pair)
                or pair[0] == pair[1]):
            pair = None
        events = []
        for item in value.get("events", [])[-SESSION_HISTORY_LIMIT:]:
            event = deepcopy(dict(item))
            event["delta"] = StateDelta.from_dict(event["delta"])
            if event.get("actor_delta") is not None:
                event["actor_delta"] = StateDelta.from_dict(event["actor_delta"])
            if any(not _valid_resource_changes(delta.resource_changes)
                   for delta in (event["delta"], event.get("actor_delta")) if delta is not None):
                raise ValueError("encounter_invalid_resource")
            events.append(SessionEvent(**event))
        return cls(
            combatants=combatants,
            elapsed_seconds=max(0, int(value.get("elapsed_seconds", 0))),
            events=events,
            autosave_path=autosave_path,
            combatant_order=list(order),
            battle_map=battle_map,
            active_pair=tuple(pair) if pair is not None else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": SESSION_SCHEMA,
            "elapsed_seconds": self.elapsed_seconds,
            "combatant_order": list(self.combatant_order),
            "combatants": {identifier: state.to_dict() for identifier, state in self.combatants.items()},
            "events": [event.to_dict() for event in self.events[-SESSION_HISTORY_LIMIT:]],
            "battle_map": self.battle_map.to_dict(),
            **({"active_pair": list(self.active_pair)} if self.active_pair is not None else {}),
        }

    def _candidate(self) -> "CombatSession":
        return CombatSession(combatants=deepcopy(self.combatants), elapsed_seconds=self.elapsed_seconds,
                             events=deepcopy(self.events), combatant_order=list(self.combatant_order),
                             battle_map=self.battle_map, active_pair=self.active_pair,
                             _undo_snapshots=(self._undo_snapshots + [self.to_dict()])[-SESSION_HISTORY_LIMIT:],
                             autosave_path=self.autosave_path)

    def _commit(self, candidate: "CombatSession") -> None:
        candidate.save()
        self.combatants = candidate.combatants
        self.combatant_order = candidate.combatant_order
        self.battle_map = candidate.battle_map
        self.active_pair = candidate.active_pair
        self.elapsed_seconds = candidate.elapsed_seconds
        self.events = candidate.events
        self._undo_snapshots = candidate._undo_snapshots

    def selected_pair(self, actor_id=None, target_id=None):
        """Keep valid distinct UI selections, falling back to the manual roster order."""
        if actor_id is None and target_id is None and self.active_pair is not None:
            actor_id, target_id = self.active_pair
        if actor_id not in self.combatants:
            actor_id = next(key for key in self.combatant_order if key != target_id)
        if target_id not in self.combatants or target_id == actor_id:
            target_id = next(key for key in self.combatant_order if key != actor_id)
        return actor_id, target_id

    def set_active_pair(self, actor_id, target_id):
        """Save the encounter's active roles without spending a turn or adding history."""
        pair = self.selected_pair(actor_id, target_id)
        if pair != self.active_pair:
            candidate = replace(self, active_pair=pair)
            self._commit(candidate)

    def _set_order(self, order):
        self.combatant_order = list(order)
        self.combatants = {key: self.combatants[key] for key in self.combatant_order}
        if self.active_pair is not None:
            self.active_pair = self.selected_pair(*self.active_pair)
        for key in self.battle_map.tokens.keys() - self.combatants.keys():
            self.battle_map = self.battle_map.without_token(key)

    def _record(self, event):
        self.events.append(event)
        self.events = self.events[-SESSION_HISTORY_LIMIT:]

    def _record_roster_change(self, label, target_id="system"):
        self._record(SessionEvent("system", target_id, label, StateDelta()))

    def _pristine_defaults(self):
        # Preparing only the map background/grid need not keep both generic
        # placeholders when the GM adds their first combatants.
        return (all(event.label == MAP_CHANGE_EVENT and event.actor_id == event.target_id == "system"
                    for event in self.events) and not self.battle_map.tokens and not self.elapsed_seconds
                and self.combatant_order == list(COMBATANT_IDS)
                and self.combatants == CombatSession.new().combatants)

    def set_battle_map(self, battle_map: BattleMap) -> None:
        """Confirm one scene edit; never expose a partial map on save failure."""
        if not isinstance(battle_map, BattleMap):
            raise ValueError("map_invalid_document")
        if battle_map.tokens.keys() - self.combatants.keys():
            raise ValueError("unknown_combatant")
        if battle_map != self.battle_map:
            candidate = self._candidate()
            candidate.battle_map = battle_map
            candidate._record_roster_change(MAP_CHANGE_EVENT)
            self._commit(candidate)

    def add_combatants(self, states, *, replace_defaults=False, index=None):
        """Add a batch in one undo step; never discard already-used placeholders."""
        states = list(states)
        if not states:
            return []
        replace_defaults = replace_defaults and self._pristine_defaults()
        order = list(self.combatant_order)
        if replace_defaults:
            order = [COMBATANT_IDS[1]] if len(states) == 1 else []
        if len(order) + len(states) > MAX_COMBATANTS:
            raise ValueError("encounter_roster_limit")
        if index is None:
            index = 0 if replace_defaults else len(order)
        if type(index) is not int or not 0 <= index <= len(order):
            raise ValueError("encounter_invalid_order")
        prepared = []
        used = set(order)
        for state in states:
            fresh = validated_combatant(state)
            if fresh.identifier == "combatant":
                fresh.identifier = f"combatant_{uuid4().hex}"
            if fresh.identifier in used:
                raise ValueError("encounter_duplicate_combatant")
            used.add(fresh.identifier)
            prepared.append(fresh)
        candidate = self._candidate()
        ids = [item.identifier for item in prepared]
        candidate.combatants.update({item.identifier: item for item in prepared})
        candidate._set_order(order[:index] + ids + order[index:])
        candidate._record_roster_change("encounter_add_combatants", ids[0])
        self._commit(candidate)
        return ids

    def add_combatant(self, state, index=None):
        return self.add_combatants([state], index=index)[0]

    def remove_combatant(self, identifier):
        if identifier not in self.combatants:
            raise ValueError("unknown_combatant")
        if len(self.combatants) <= 2:
            raise ValueError("encounter_minimum_roster")
        candidate = self._candidate()
        candidate._set_order([key for key in self.combatant_order if key != identifier])
        candidate._clear_outgoing_grapples(identifier)
        candidate._record_roster_change("encounter_remove_combatant", identifier)
        self._commit(candidate)

    def move_combatant(self, identifier, new_index):
        if identifier not in self.combatants:
            raise ValueError("unknown_combatant")
        if type(new_index) is not int or not 0 <= new_index < len(self.combatant_order):
            raise ValueError("encounter_invalid_order")
        order = list(self.combatant_order)
        order.remove(identifier)
        order.insert(new_index, identifier)
        self._reorder(order)

    def sort_combatants(self, by="basic_speed", reverse=None):
        if by not in {"basic_speed", "dx", "name", "team", "group"} or (
            reverse is not None and type(reverse) is not bool
        ):
            raise ValueError("encounter_invalid_order")
        descending = by in {"basic_speed", "dx"} if reverse is None else reverse

        def sort_key(identifier):
            state = self.combatants[identifier]
            if by == "basic_speed":
                # Basic Speed, then DX (B363); exact ties keep the current manual order.
                return state.basic_speed, state.dx
            value = getattr(state, by)
            return value.casefold() if isinstance(value, str) else value

        unknown = (
            [key for key in self.combatant_order if self.combatants[key].basic_speed is None]
            if by == "basic_speed" else []
        )
        known = [key for key in self.combatant_order if key not in unknown]
        self._reorder(sorted(known, key=sort_key, reverse=descending) + unknown)

    def _reorder(self, order):
        if order != self.combatant_order:
            candidate = self._candidate()
            candidate._set_order(order)
            candidate._record_roster_change("encounter_reorder_combatants")
            self._commit(candidate)

    def edit_combatant_state(self, identifier, **changes):
        if identifier not in self.combatants:
            raise ValueError("unknown_combatant")
        if set(changes) - EDITABLE_STATE_FIELDS:
            raise ValueError("encounter_invalid_edit")
        state = deepcopy(self.combatants[identifier])
        for key, value in changes.items():
            if key in {"current_hp", "current_fp", "shock", "size_modifier", *DEFENSES}:
                if type(value) is not int:
                    raise ValueError("encounter_invalid_edit")
            if key in {"aware", "stunned", "unconscious", "dead"} and type(value) is not bool:
                raise ValueError("encounter_invalid_edit")
            if key in {"posture", "facing"} and not _valid_text(value, 32):
                raise ValueError("encounter_invalid_edit")
            if (key == "shock" and not 0 <= value <= 4) or (key in DEFENSES and value < 0):
                raise ValueError("encounter_invalid_edit")
            if key in DEFENSES and key in state.unknown_defenses:
                state.unknown_defenses.remove(key)
            if key == "size_modifier":
                state.unknown_size_modifier = False
            setattr(state, key, value)
        state = validated_combatant(state)
        if state != self.combatants[identifier]:
            candidate = self._candidate()
            candidate.combatants[identifier] = state
            candidate._record_roster_change("encounter_edit_combatant", identifier)
            self._commit(candidate)

    @staticmethod
    def _sync_grapple_conditions(state, affected):
        remaining = {relation.get("state", "grappled") for relation in state.grapples.values()}
        if state.grapples:
            remaining.add("grappled")
        state.conditions = [key for key in state.conditions if key not in affected or key in remaining]
        CombatSession._append_unique(state.conditions, sorted(remaining & GRAPPLE_CONDITIONS))

    def _clear_outgoing_grapples(self, identifier):
        for key, state in self.combatants.items():
            if key != identifier and identifier in state.grapples:
                previous = state.grapples.pop(identifier)
                self._sync_grapple_conditions(state, {"grappled", previous.get("state", "grappled")})

    def replace_participant(self, identifier: str, state: CombatantState) -> None:
        if identifier not in self.combatants or state.identifier != identifier:
            raise ValueError("unknown_combatant")
        candidate = self._candidate()
        candidate.combatants[identifier] = validated_combatant(state)
        candidate.battle_map = candidate.battle_map.without_token(identifier)
        candidate._clear_outgoing_grapples(identifier)
        self._commit(candidate)

    @staticmethod
    def _append_unique(target: List[str], values: Sequence[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)

    @staticmethod
    def _apply_delta_to_state(state: CombatantState, delta: StateDelta) -> None:
        if not _valid_resource_changes(delta.resource_changes):
            raise ValueError("encounter_invalid_resource")
        for identifier, change in delta.resource_changes.items():
            if identifier not in state.resource_pools:
                raise ValueError("encounter_invalid_resource")
            pool = state.resource_pools[identifier]
            current = pool["current"] + change
            # Imported custom counters may already be negative or overfilled.
            # Keep their exact values without letting automatic use create debt
            # or automatic recovery go over the normal maximum.
            if (change < 0 and current < 0) or (change > 0 and current > pool["maximum"]):
                raise ValueError("encounter_insufficient_resource")
            pool["current"] = current
        state.current_hp += int(delta.hp_change)
        state.current_fp += int(delta.fp_change)
        state.shock = max(state.shock, int(delta.shock))
        if delta.posture is not None:
            state.posture = delta.posture
        if delta.set_stunned is not None:
            state.stunned = delta.set_stunned
        if delta.set_unconscious is not None:
            state.unconscious = delta.set_unconscious
        if delta.set_dead is not None:
            state.dead = delta.set_dead
        CombatSession._append_unique(state.conditions, delta.add_conditions)
        state.conditions = [item for item in state.conditions if item not in delta.remove_conditions]
        state.wounds.extend(deepcopy(delta.wounds))
        CombatSession._append_unique(state.crippled_locations, delta.crippled_locations)
        CombatSession._append_unique(state.destroyed_locations, delta.destroyed_locations)
        state.pending_checks.extend(deepcopy(delta.pending_checks))
        for identifier, loss in delta.armor_dr_loss.items():
            for layer in state.armor.layers:
                if layer.armor.identifier == identifier:
                    layer.current_dr_loss += max(0, int(loss))
                    break
        affected = set()
        for key, update in delta.grapple_updates.items():
            previous = state.grapples.get(key)
            if previous is not None:
                affected.add(previous.get("state", "grappled"))
            if update is None:
                state.grapples.pop(key, None)
            else:
                state.grapples[key] = deepcopy(update)
        if delta.grapple_updates:
            CombatSession._sync_grapple_conditions(state, affected | {"grappled"})

    def apply(self, actor_id: str, target_id: str, delta: StateDelta,
              label: str = "resolved_action", advance_action: bool = True) -> SessionEvent:
        if actor_id not in self.combatants or target_id not in self.combatants:
            raise KeyError("unknown_combatant")
        candidate = self._candidate()
        actor = candidate.combatants[actor_id]
        target = candidate.combatants[target_id]
        self._apply_delta_to_state(target, delta)
        if advance_action:
            actor.conditions = [
                item for item in actor.conditions if item not in TRANSIENT_ACTION_CONDITIONS
            ]
            actor.action_count += 1
            actor.personal_seconds += 1
            actor.shock = 0
        event = SessionEvent(actor_id=actor_id, target_id=target_id, label=label, delta=deepcopy(delta))
        candidate._record(event)
        self._commit(candidate)
        return event

    def apply_action(self, actor_id: str, target_id: str, target_delta: StateDelta,
                     actor_delta: Optional[StateDelta] = None,
                     label: str = "resolved_action", *, advance_action: bool = True) -> SessionEvent:
        """Atomically apply both sides of one action and create one undo step."""

        if actor_id not in self.combatants or target_id not in self.combatants:
            raise KeyError("unknown_combatant")
        candidate = self._candidate()
        actor = candidate.combatants[actor_id]
        target = candidate.combatants[target_id]
        self._apply_delta_to_state(target, target_delta)
        if advance_action:
            actor.conditions = [
                item for item in actor.conditions if item not in TRANSIENT_ACTION_CONDITIONS
            ]
        if actor_delta is not None:
            self._apply_delta_to_state(actor, actor_delta)
        if advance_action:
            actor.action_count += 1
            actor.personal_seconds += 1
            actor.shock = 0
        event = SessionEvent(actor_id=actor_id, target_id=target_id, label=label,
                             delta=deepcopy(target_delta), actor_delta=deepcopy(actor_delta))
        candidate._record(event)
        self._commit(candidate)
        return event

    def recover_from_stun(self, combatant_id: str, roll: Optional[int] = None) -> Dict[str, Any]:
        if combatant_id not in self.combatants:
            raise KeyError("unknown_combatant")
        state = self.combatants[combatant_id]
        chosen, dice = (roll, None) if roll is not None else roll_3d6()
        outcome = evaluate_success_roll(state.ht, int(chosen))
        delta = StateDelta()
        if outcome["success"]:
            delta.set_stunned = False
            delta.remove_conditions.append("stunned")
        self.apply(combatant_id, combatant_id, delta, "do_nothing_stun_recovery")
        return {"roll": chosen, "dice": dice, "target": state.ht, **outcome}

    def equip_armor(self, combatant_id: str, armor: ArmorRecord, replace: bool = False) -> None:
        if combatant_id not in self.combatants:
            raise KeyError("unknown_combatant")
        candidate = self._candidate()
        loadout = candidate.combatants[combatant_id].armor
        if replace:
            loadout.layers = []
        existing = {layer.armor.identifier: layer for layer in loadout.layers}
        existing[armor.identifier] = ArmorLayer(deepcopy(armor))
        loadout.layers = list(existing.values())
        self._commit(candidate)

    def clear_armor(self, combatant_id: str) -> None:
        if combatant_id not in self.combatants:
            raise KeyError("unknown_combatant")
        candidate = self._candidate()
        candidate.combatants[combatant_id].armor.layers = []
        self._commit(candidate)

    def advance_time(self, seconds: int, bleeding_rolls: Optional[Mapping[str, Sequence[int]]] = None) -> List[Dict[str, Any]]:
        if seconds not in (30, 60):
            raise ValueError("time_step_must_be_30_or_60_seconds")
        candidate = self._candidate()
        old_minute = candidate.elapsed_seconds // 60
        candidate.elapsed_seconds += seconds
        new_minute = candidate.elapsed_seconds // 60
        results: List[Dict[str, Any]] = []
        if new_minute > old_minute:
            supplied = bleeding_rolls or {}
            for identifier, state in candidate.combatants.items():
                rolls = list(supplied.get(identifier, []))
                for index, wound in enumerate(active_bleeding_wounds(state.wounds)):
                    target = state.ht - wound.injury // 5
                    if index < len(rolls):
                        chosen, dice = int(rolls[index]), None
                    else:
                        chosen, dice = roll_3d6()
                    outcome = evaluate_success_roll(target, chosen)
                    loss = 0
                    if outcome["critical_success"]:
                        wound.bleeding_stopped = True
                    elif outcome["critical_failure"]:
                        loss = 3
                        wound.successful_bleeding_rolls = 0
                    elif outcome["success"]:
                        wound.successful_bleeding_rolls += 1
                        if wound.successful_bleeding_rolls >= 3:
                            wound.bleeding_stopped = True
                    else:
                        loss = 1
                        wound.successful_bleeding_rolls = 0
                    state.current_hp -= loss
                    results.append({
                        "combatant": identifier, "location": wound.location,
                        "target": target, "roll": chosen, "dice": dice,
                        "hp_loss": loss, "stopped": wound.bleeding_stopped, **outcome,
                    })
        candidate._record(SessionEvent(
            actor_id="system", target_id="system", label=f"advance_time_{seconds}", delta=StateDelta()
        ))
        self._commit(candidate)
        return results

    def undo(self) -> bool:
        if not self._undo_snapshots:
            return False
        snapshot = self._undo_snapshots[-1]
        restored = CombatSession.from_dict(snapshot, self.autosave_path)
        if self.active_pair is not None and all(key in restored.combatants for key in self.active_pair):
            restored.active_pair = self.active_pair
        restored._undo_snapshots = self._undo_snapshots[:-1]
        self._commit(restored)
        return True

    def save(self, path: Optional[Path] = None) -> None:
        destination = Path(path or self.autosave_path) if (path or self.autosave_path) else None
        if destination is None:
            return
        write_atomic_json(destination, self.to_dict())

    @classmethod
    def load_or_new(cls, path: Path) -> "CombatSession":
        source = Path(path)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
            return cls.from_dict(document, source)
        except FileNotFoundError:
            return cls.new(source)
        except OSError:
            clean = cls.new()
            clean.load_warning = str(source)
            return clean
        except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError):
            clean = cls.new(source)
            try:
                clean.load_warning = str(quarantine_json(source))
            except OSError:
                clean.autosave_path = None
                clean.load_warning = str(source)
                return clean
            try:
                clean.save()
            except OSError:
                pass  # retry on the next confirmed change
            return clean
