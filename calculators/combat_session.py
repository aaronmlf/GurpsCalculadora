"""Two-combatant lightweight session with explicit state application."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from calculators.injury import ArmorLayer, ArmorRecord, CombatantState, StateDelta, active_bleeding_wounds
from utils.dice_roller import evaluate_success_roll, roll_3d6


SESSION_SCHEMA = "gurps-calculadora.combat-session.v1"
SESSION_HISTORY_LIMIT = 100
TRANSIENT_ACTION_CONDITIONS = {
    "all_out_attack_no_defense",
    "committed_attack_defense_restrictions",
    "defensive_attack_parry_bonus",
}


@dataclass
class SessionEvent:
    actor_id: str
    target_id: str
    label: str
    delta: StateDelta
    applied_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CombatSession:
    combatants: Dict[str, CombatantState]
    elapsed_seconds: int = 0
    events: List[SessionEvent] = field(default_factory=list)
    _undo_snapshots: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    autosave_path: Optional[Path] = field(default=None, repr=False)

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
        if value.get("schema") != SESSION_SCHEMA:
            raise ValueError("invalid_session_schema")
        raw_combatants = value.get("combatants")
        if not isinstance(raw_combatants, Mapping) or len(raw_combatants) != 2:
            raise ValueError("invalid_session_combatants")
        combatants = {
            str(identifier): CombatantState.from_dict(record)
            for identifier, record in raw_combatants.items()
        }
        events = []
        for item in value.get("events", []):
            event = dict(item)
            event["delta"] = StateDelta.from_dict(event["delta"])
            events.append(SessionEvent(**event))
        return cls(
            combatants=combatants,
            elapsed_seconds=max(0, int(value.get("elapsed_seconds", 0))),
            events=events[-SESSION_HISTORY_LIMIT:],
            autosave_path=autosave_path,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": SESSION_SCHEMA,
            "elapsed_seconds": self.elapsed_seconds,
            "combatants": {identifier: state.to_dict() for identifier, state in self.combatants.items()},
            "events": [event.to_dict() for event in self.events[-SESSION_HISTORY_LIMIT:]],
        }

    def _snapshot(self) -> Dict[str, Any]:
        return self.to_dict()

    def _remember_undo(self) -> None:
        self._undo_snapshots.append(self._snapshot())
        self._undo_snapshots = self._undo_snapshots[-SESSION_HISTORY_LIMIT:]

    @staticmethod
    def _append_unique(target: List[str], values: Sequence[str]) -> None:
        for value in values:
            if value not in target:
                target.append(value)

    @staticmethod
    def _apply_delta_to_state(state: CombatantState, delta: StateDelta) -> None:
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
        for key, update in delta.grapple_updates.items():
            if update is None:
                state.grapples.pop(key, None)
            else:
                state.grapples[key] = deepcopy(update)

    def apply(self, actor_id: str, target_id: str, delta: StateDelta,
              label: str = "resolved_action", advance_action: bool = True) -> SessionEvent:
        if actor_id not in self.combatants or target_id not in self.combatants:
            raise KeyError("unknown_combatant")
        self._remember_undo()
        actor = self.combatants[actor_id]
        target = self.combatants[target_id]
        self._apply_delta_to_state(target, delta)
        if advance_action:
            actor.conditions = [
                item for item in actor.conditions if item not in TRANSIENT_ACTION_CONDITIONS
            ]
            actor.action_count += 1
            actor.personal_seconds += 1
            actor.shock = 0
        event = SessionEvent(actor_id=actor_id, target_id=target_id, label=label, delta=deepcopy(delta))
        self.events.append(event)
        self.events = self.events[-SESSION_HISTORY_LIMIT:]
        self.save()
        return event

    def apply_action(self, actor_id: str, target_id: str, target_delta: StateDelta,
                     actor_delta: Optional[StateDelta] = None,
                     label: str = "resolved_action") -> SessionEvent:
        """Atomically apply both sides of one action and create one undo step."""

        if actor_id not in self.combatants or target_id not in self.combatants:
            raise KeyError("unknown_combatant")
        self._remember_undo()
        actor = self.combatants[actor_id]
        target = self.combatants[target_id]
        self._apply_delta_to_state(target, target_delta)
        actor.conditions = [
            item for item in actor.conditions if item not in TRANSIENT_ACTION_CONDITIONS
        ]
        if actor_delta is not None:
            self._apply_delta_to_state(actor, actor_delta)
        actor.action_count += 1
        actor.personal_seconds += 1
        actor.shock = 0
        event = SessionEvent(actor_id=actor_id, target_id=target_id, label=label, delta=deepcopy(target_delta))
        self.events.append(event)
        self.events = self.events[-SESSION_HISTORY_LIMIT:]
        self.save()
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
        self._remember_undo()
        loadout = self.combatants[combatant_id].armor
        if replace:
            loadout.layers = []
        existing = {layer.armor.identifier: layer for layer in loadout.layers}
        existing[armor.identifier] = ArmorLayer(deepcopy(armor))
        loadout.layers = list(existing.values())
        self.save()

    def clear_armor(self, combatant_id: str) -> None:
        if combatant_id not in self.combatants:
            raise KeyError("unknown_combatant")
        self._remember_undo()
        self.combatants[combatant_id].armor.layers = []
        self.save()

    def advance_time(self, seconds: int, bleeding_rolls: Optional[Mapping[str, Sequence[int]]] = None) -> List[Dict[str, Any]]:
        if seconds not in (30, 60):
            raise ValueError("time_step_must_be_30_or_60_seconds")
        self._remember_undo()
        old_minute = self.elapsed_seconds // 60
        self.elapsed_seconds += seconds
        new_minute = self.elapsed_seconds // 60
        results: List[Dict[str, Any]] = []
        if new_minute > old_minute:
            supplied = bleeding_rolls or {}
            for identifier, state in self.combatants.items():
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
        self.events.append(SessionEvent(
            actor_id="system", target_id="system", label=f"advance_time_{seconds}", delta=StateDelta()
        ))
        self.events = self.events[-SESSION_HISTORY_LIMIT:]
        self.save()
        return results

    def undo(self) -> bool:
        if not self._undo_snapshots:
            return False
        snapshot = self._undo_snapshots.pop()
        restored = CombatSession.from_dict(snapshot, self.autosave_path)
        self.combatants = restored.combatants
        self.elapsed_seconds = restored.elapsed_seconds
        self.events = restored.events
        self.save()
        return True

    def save(self, path: Optional[Path] = None) -> None:
        destination = Path(path or self.autosave_path) if (path or self.autosave_path) else None
        if destination is None:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)

    @classmethod
    def load_or_new(cls, path: Path) -> "CombatSession":
        source = Path(path)
        if not source.exists():
            return cls.new(source)
        try:
            document = json.loads(source.read_text(encoding="utf-8"))
            return cls.from_dict(document, source)
        except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = source.with_name(f"{source.stem}.invalid-{stamp}{source.suffix}")
            try:
                os.replace(source, backup)
            except OSError:
                pass
            clean = cls.new(source)
            clean.save()
            return clean
