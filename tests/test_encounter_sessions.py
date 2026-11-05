import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from calculators.combat_library import LEGACY_SCHEMA, SCHEMA, CombatantProfile, CombatLibrary, combatant_from_imported
from calculators.combat_session import LEGACY_SESSION_SCHEMA, MAX_COMBATANTS, SESSION_SCHEMA, CombatSession
from calculators.injury import CombatantState, StateDelta, WoundRecord
from utils.gcs_import import ImportedCharacter, ImportedEnergyTrack, ImportedLocationDR


A, B = "combatant_a", "combatant_b"


def participant(identifier="combatant", **changes):
    return CombatantState(identifier=identifier, name=changes.pop("name", "Participante"), **changes)


def energy(current=5, maximum=8):
    return {"er": {"label": "Energy Reserve", "current": current, "maximum": maximum}}


class EncounterSessionTests(unittest.TestCase):
    def test_legacy_load_is_non_mutating_then_confirmed_action_saves_v2(self):
        legacy = {
            "schema": LEGACY_SESSION_SCHEMA,
            "elapsed_seconds": 30,
            "combatants": {
                B: {"identifier": B, "name": "Guard", "current_hp": 6},
                A: {"identifier": A, "name": "Scout", "current_fp": 8},
            },
            "events": [{"actor_id": A, "target_id": B, "label": "hit",
                        "delta": {"hp_change": -4}, "applied_at": "2026-11-05T18:00:00"}],
        }
        with TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            session = CombatSession.load_or_new(path)
            self.assertEqual(session.combatant_order, [A, B])
            self.assertEqual(session.combatants[B].current_hp, 6)
            self.assertEqual(session.combatants[A].resource_pools, {})
            self.assertEqual(session.elapsed_seconds, 30)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), legacy)
            session.add_combatant(participant("guard.2"))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], SESSION_SCHEMA)
            self.assertEqual(CombatSession.load_or_new(path).to_dict(), session.to_dict())

    def test_manual_order_and_speed_sort_with_dx_and_stable_exact_ties(self):
        session = CombatSession.new()
        session.add_combatants([
            participant("first", basic_speed=7, dx=12),
            participant("higher_dx", basic_speed=7, dx=15),
            participant("manual_first", basic_speed=7, dx=12),
            participant("unknown", basic_speed=None),
        ])
        session.move_combatant("manual_first", 0)
        session.sort_combatants()
        self.assertEqual(session.combatant_order, ["higher_dx", "manual_first", "first", A, B, "unknown"])
        self.assertEqual(list(session.combatants), session.combatant_order)
        self.assertEqual(CombatSession.from_dict(session.to_dict()).combatant_order, session.combatant_order)
        session.sort_combatants(reverse=False)
        self.assertEqual(session.combatant_order, [A, B, "manual_first", "first", "higher_dx", "unknown"])
        self.assertTrue(session.undo())
        self.assertEqual(session.combatant_order, ["higher_dx", "manual_first", "first", A, B, "unknown"])

    def test_add_batch_replaces_only_entirely_pristine_defaults(self):
        session = CombatSession.new()
        state = participant(resource_pools=energy())
        actor, = session.add_combatants([state], replace_defaults=True)
        self.assertNotEqual(actor, state.identifier)
        self.assertEqual(session.combatant_order, [actor, B])
        self.assertEqual(session.selected_pair(), (actor, B))
        state.resource_pools["er"]["current"] = 0
        self.assertEqual(session.combatants[actor].resource_pools["er"]["current"], 5)
        self.assertTrue(session.undo())
        self.assertEqual(session.combatant_order, [A, B])
        self.assertFalse(session.undo())
        self.assertEqual(session.add_combatants([participant("a"), participant("b")],
                                               replace_defaults=True), ["a", "b"])
        self.assertEqual(session.combatant_order, ["a", "b"])

        session = CombatSession.new()
        session.apply(A, B, StateDelta(hp_change=-2))
        session.add_combatants([participant("guest")], replace_defaults=True)
        self.assertEqual(session.combatant_order, [A, B, "guest"])
        self.assertEqual(session.combatants[B].current_hp, 8)

    def test_minimum_roster_order_validation_and_role_fallback(self):
        session = CombatSession.new()
        with self.assertRaisesRegex(ValueError, "encounter_minimum_roster"):
            session.remove_combatant(A)
        session.add_combatant(participant("third"), index=1)
        self.assertEqual(session.combatant_order, [A, "third", B])
        session.remove_combatant(A)
        self.assertEqual(session.selected_pair(A, "third"), (B, "third"))
        self.assertEqual(session.selected_pair("third", A), ("third", B))
        self.assertEqual(session.selected_pair("third", "third"), ("third", B))
        with self.assertRaisesRegex(ValueError, "encounter_invalid_order"):
            session.move_combatant("third", 2)
        for order in (["third", "third"], [B, "missing"], [B, []], []):
            document = session.to_dict()
            document["combatant_order"] = order
            with self.subTest(order=order), self.assertRaisesRegex(ValueError, "encounter_invalid_order"):
                CombatSession.from_dict(document)

    def test_roster_limit_and_duplicate_ids_are_atomic(self):
        session = CombatSession.new()
        snapshot = session.to_dict()
        with self.assertRaisesRegex(ValueError, "encounter_duplicate_combatant"):
            session.add_combatants([participant("duplicate"), participant("duplicate")])
        self.assertEqual(session.to_dict(), snapshot)
        self.assertFalse(session.undo())
        session.add_combatants([participant(f"guest{index}") for index in range(MAX_COMBATANTS - 2)])
        with self.assertRaisesRegex(ValueError, "encounter_roster_limit"):
            session.add_combatant(participant())
        self.assertEqual(len(session.combatants), MAX_COMBATANTS)
        self.assertTrue(session.undo())
        self.assertEqual(session.to_dict(), snapshot)

    def test_state_edits_preserve_permanent_stats_and_resolve_unknown_fields(self):
        session = CombatSession.new()
        key = session.add_combatant(participant(
            "guest", unknown_defenses=["dodge", "block"], unknown_size_modifier=True,
        ))
        before = session.to_dict()
        session.edit_combatant_state(key, current_hp=-4, current_fp=-1, stunned=True,
                                     team="Guardas", group="Reserva", dodge=9, size_modifier=1,
                                     resource_pools=energy())
        state = session.combatants[key]
        self.assertEqual((state.current_hp, state.current_fp, state.st, state.max_fp), (-4, -1, 10, 10))
        self.assertEqual((state.team, state.group, state.unknown_defenses), ("Guardas", "Reserva", ["block"]))
        self.assertFalse(state.unknown_size_modifier)
        for edits in ({"st": 12}, {"max_fp": 15}, {"current_hp": 1.5}, {"current_fp": True},
                      {"resource_pools": energy(5, -1)}, {"stunned": 1}):
            with self.subTest(edits=edits), self.assertRaises(ValueError):
                session.edit_combatant_state(key, **edits)
        self.assertTrue(session.undo())
        self.assertEqual(session.to_dict(), before)

    def test_signed_and_overfilled_counters_round_trip_without_clamping(self):
        session = CombatSession.new()
        actor = session.add_combatant(participant("mage", resource_pools=energy(-3), current_fp=13))
        session = CombatSession.from_dict(session.to_dict())
        self.assertEqual(session.combatants[actor].resource_pools, energy(-3))
        self.assertEqual(session.combatants[actor].current_fp, 13)
        with self.assertRaisesRegex(ValueError, "encounter_insufficient_resource"):
            session.apply(actor, actor, StateDelta(resource_changes={"er": -1}))
        session.edit_combatant_state(actor, resource_pools=energy(12), current_hp=15)
        self.assertEqual(session.combatants[actor].current_hp, 15)
        with self.assertRaisesRegex(ValueError, "encounter_insufficient_resource"):
            session.apply(actor, actor, StateDelta(resource_changes={"er": 1}))
        session.apply(actor, actor, StateDelta(resource_changes={"er": -2}))
        self.assertEqual(session.combatants[actor].resource_pools, energy(10))

    def test_resource_spend_and_injury_are_one_transaction(self):
        session = CombatSession.new()
        actor = session.add_combatant(participant("mage", resource_pools=energy()))
        before = session.to_dict()
        with self.assertRaisesRegex(ValueError, "encounter_insufficient_resource"):
            session.apply_action(actor, B, StateDelta(hp_change=-3),
                                 StateDelta(fp_change=-1, resource_changes={"er": -6}))
        self.assertEqual(session.to_dict(), before)
        event = session.apply_action(actor, B, StateDelta(hp_change=-3),
                                     StateDelta(fp_change=-1, resource_changes={"er": -2}))
        self.assertEqual(session.combatants[B].current_hp, 7)
        self.assertEqual(session.combatants[actor].resource_pools["er"]["current"], 3)
        self.assertEqual(session.combatants[actor].current_fp, 9)
        self.assertEqual(event.actor_delta.resource_changes, {"er": -2})
        self.assertEqual(CombatSession.from_dict(session.to_dict()).events[-1], event)
        self.assertTrue(session.undo())
        self.assertEqual(session.to_dict(), before)

    def test_remove_and_replace_clear_only_relationships_with_that_combatant(self):
        session = CombatSession.new()
        session.add_combatants([participant("c"), participant("d")])
        for actor, target, status in ((A, "c", "pinned"), (B, "c", "choked"), ("c", "d", "grappled")):
            session.apply(actor, target, StateDelta(grapple_updates={actor: {"state": status}}))
        session.remove_combatant(A)
        self.assertEqual(set(session.combatants["c"].grapples), {B})
        self.assertEqual(set(session.combatants["c"].conditions), {"grappled", "choked"})
        session.replace_participant(B, participant(B))
        self.assertFalse(session.combatants["c"].grapples)
        self.assertEqual(session.combatants["c"].conditions, [])
        self.assertIn("c", session.combatants["d"].grapples)
        self.assertTrue(session.undo())
        self.assertIn(B, session.combatants["c"].grapples)

    def test_bleeding_ticks_include_all_participants(self):
        session = CombatSession.new()
        wound = WoundRecord("torso", 5, 5, "cut", bleeding=True)
        session.add_combatants([participant("c", wounds=[wound]), participant("d", wounds=[wound])])
        bleeding = session.advance_time(60, {"c": [18], "d": [3]})
        self.assertEqual([item["combatant"] for item in bleeding], ["c", "d"])
        self.assertEqual(session.combatants["c"].current_hp, 7)
        self.assertTrue(session.combatants["d"].wounds[0].bleeding_stopped)

    def test_new_mutations_roll_back_after_failed_autosave(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            session = CombatSession.new(path)
            session.add_combatant(participant("c"))
            before, disk = session.to_dict(), path.read_bytes()
            with patch("calculators.combat_session.write_atomic_json", side_effect=OSError):
                for operation in (
                    lambda: session.add_combatants([participant("d"), participant("e")]),
                    lambda: session.remove_combatant("c"),
                    lambda: session.move_combatant("c", 0),
                    lambda: session.sort_combatants("name", reverse=True),
                    lambda: session.edit_combatant_state("c", team="Blue"),
                ):
                    with self.subTest(operation=operation), self.assertRaises(OSError):
                        operation()
                    self.assertEqual(session.to_dict(), before)
                    self.assertEqual(path.read_bytes(), disk)
            self.assertTrue(session.undo())
            self.assertFalse(session.undo())


class EncounterLibraryTests(unittest.TestCase):
    def test_v1_named_snapshot_migrates_without_touching_original_until_save(self):
        raw = {
            "schema": LEGACY_SCHEMA,
            "profiles": {"Guard": {"name": "Guard", "max_hp": 11}},
            "sessions": {"Old": {"schema": LEGACY_SESSION_SCHEMA, "combatants": {
                A: {"identifier": A, "name": "A", "current_hp": 5},
                B: {"identifier": B, "name": "B"},
            }}},
        }
        with TemporaryDirectory() as folder:
            path = Path(folder) / "library.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            library = CombatLibrary(path)
            self.assertEqual(library.profiles["Guard"].instantiate("g").max_hp, 11)
            self.assertEqual(library.open_session("Old").combatants[A].current_hp, 5)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), raw)
            library.save_imported_batch({"source": participant()})
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], SCHEMA)
            self.assertEqual(document["sessions"]["Old"]["schema"], SESSION_SCHEMA)
            self.assertEqual(CombatLibrary(path).open_session("Old").combatant_order, [A, B])

    def test_import_conversion_persists_current_resources_and_preserves_unknown(self):
        imported = ImportedCharacter(
            name="Maga", st=10, dx=11, iq=13, ht=12, will=15, per=14,
            max_hp=10, current_hp=7, max_fp=12, current_fp=8, basic_speed=6.25, basic_move=None,
            size_modifier=None, dodge=None, parry=10, block=None,
            energy_tracks=(ImportedEnergyTrack("er", "Energy Reserve", 8, 5),
                           ImportedEnergyTrack("debt", "Debt", 3, -4)),
            source_id="source-123", source_format="gcs_native", source_version="5", source_name="Maga.gcs",
            location_dr=(ImportedLocationDR(("skull",), "Skull", 2), ImportedLocationDR(("torso",), "Torso", 3)),
        )
        state = combatant_from_imported(imported)
        self.assertEqual((state.current_hp, state.current_fp, state.will, state.per), (7, 8, 15, 14))
        self.assertEqual((state.basic_speed, state.basic_move), (6.25, None))
        self.assertEqual((state.dodge, state.parry, state.block), (0, 10, 0))
        self.assertEqual(state.unknown_defenses, ["dodge", "block"])
        self.assertTrue(state.unknown_size_modifier)
        self.assertEqual(state.armor.natural_dr, 0)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "library.json"
            library = CombatLibrary(path)
            library.save_imported_batch({state.source_id: state})
            restored = CombatLibrary(path)
            loaded = restored.open_imported(state.source_id)
            self.assertEqual(loaded, state)
            loaded.resource_pools["er"]["current"] = 0
            self.assertEqual(restored.open_imported(state.source_id).resource_pools, {
                **energy(), "debt": {"label": "Debt", "maximum": 3, "current": -4},
            })
            snapshot = path.read_bytes()
            with patch("calculators.combat_library.write_atomic_json", side_effect=OSError):
                with self.assertRaises(OSError):
                    restored.save_imported_batch({"second": participant()})
            self.assertEqual(path.read_bytes(), snapshot)
            self.assertNotIn("second", restored.imported)

    def test_named_session_and_profile_remain_separate(self):
        session = CombatSession.new()
        actor = session.add_combatant(participant("guest", resource_pools=energy(3), team="Blue"))
        session.move_combatant(actor, 0)
        session.apply(A, actor, StateDelta(hp_change=-4))
        with TemporaryDirectory() as folder:
            path = Path(folder) / "library.json"
            library = CombatLibrary(path)
            profile = CombatantProfile.from_state(session.combatants[actor])
            library.save_profile(profile)
            library.save_session("Ambush", session)
            restored = CombatLibrary(path)
            snapshot = restored.open_session("Ambush")
            self.assertEqual(snapshot.combatant_order, [actor, A, B])
            self.assertEqual(snapshot.combatants[actor].team, "Blue")
            self.assertEqual(snapshot.combatants[actor].resource_pools, energy(3))
            self.assertEqual(snapshot.combatants[actor].current_hp, 6)
            fresh = restored.profiles[profile.name].instantiate("fresh")
            self.assertEqual(fresh.resource_pools, energy(8))
            self.assertEqual(fresh.current_hp, 10)
