import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculators.combat_library import CombatantProfile, CombatLibrary
from calculators.combat_session import CombatSession
from calculators.injury import ArmorLayer, ArmorLoadout, ArmorRecord, InjuryEngine, InjuryInput, StateDelta
from calculators.ranged_combat import DamageMode, RangedAttackInput, RangedCombatCalculator, WeaponRecord
from calculators.vehicles import VehicleAttackInput, VehicleCollisionInput, VehicleEngine, VehicleRecord, VehicleState
from utils.ranged_handoff import RangedHitDraft
from utils.weapon_catalog import WeaponCatalog


A, B = "combatant_a", "combatant_b"


def sample_weapon(mode=None):
    return WeaponRecord("test.1", "Basic Set", "278", "Test weapon", "6", "GUNS", ["Guns"],
                        [mode or DamageMode("2d", "pi", armor_divisor=2, half_damage_range=5)], 2)


class TableWorkflowTests(unittest.TestCase):
    def test_failed_commit_leaves_both_sides_events_and_undo_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "combat_session.json"
            session = CombatSession.new(path)
            session.apply(A, B, StateDelta(hp_change=-1))
            before = session.to_dict()
            disk = path.read_bytes()
            with patch("calculators.combat_session.write_atomic_json", side_effect=OSError("disk full")):
                for action in (
                    lambda: session.apply(A, B, StateDelta(hp_change=-3)),
                    lambda: session.apply_action(A, B, StateDelta(hp_change=-3), StateDelta(fp_change=-1)),
                    lambda: session.advance_time(60),
                    lambda: session.clear_armor(B),
                    lambda: session.replace_participant(B, CombatantProfile("Orc").instantiate(B)),
                    session.undo,
                ):
                    with self.subTest(action=action), self.assertRaises(OSError):
                        action()
                    self.assertEqual(session.to_dict(), before)
                    self.assertEqual(path.read_bytes(), disk)
            self.assertTrue(session.undo())
            self.assertFalse(session.undo())
            self.assertEqual(session.combatants[B].current_hp, 10)

    def test_bad_local_documents_never_overwrite_the_only_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            session_file, presets = base / "session.json", base / "weapons.json"
            session_file.write_text("[]", encoding="utf-8")
            presets.write_text("bad", encoding="utf-8")
            session = CombatSession.load_or_new(session_file)
            catalog = WeaponCatalog(user_path=presets)
            self.assertEqual(Path(session.load_warning).read_text(), "[]")
            self.assertEqual(catalog.load_warning.read_text(), "bad")
            self.assertTrue(catalog.builtin)
            self.assertFalse(catalog.custom)
            presets.write_text("not writable", encoding="utf-8")
            with patch("utils.weapon_catalog.quarantine_json", side_effect=PermissionError):
                fallback = WeaponCatalog(user_path=presets)
                with self.assertRaises(PermissionError):
                    fallback.save_custom(sample_weapon())
            self.assertEqual(presets.read_text(), "not writable")

    def test_library_reopens_wounds_but_profile_starts_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "combat_library.json"
            library = CombatLibrary(path)
            session = CombatSession.new()
            profile = CombatantProfile("Guarda", max_hp=12, max_fp=13, ranged_weapon_id="test.1",
                                       armor=ArmorLoadout([ArmorLayer(ArmorRecord("vest", "Test", "1", "Vest"))]))
            session.replace_participant(B, profile.instantiate(B))
            session.apply(A, B, StateDelta(hp_change=-4, fp_change=-1, armor_dr_loss={"vest": 1}))
            library.save_profile(CombatantProfile.from_state(session.combatants[B]))
            library.save_session("Porto", session)
            loaded = CombatLibrary(path)
            fresh = loaded.profiles["Guarda"].instantiate(A)
            restored = loaded.open_session("Porto").combatants[B]
            self.assertEqual((fresh.current_hp, fresh.current_fp, fresh.ranged_weapon_id), (12, 13, "test.1"))
            self.assertEqual((restored.current_hp, restored.current_fp), (8, 12))
            self.assertEqual(fresh.armor.layers[0].current_dr_loss, 0)
            self.assertEqual(restored.armor.layers[0].current_dr_loss, 1)
            self.assertEqual(len(json.loads(path.read_text())["sessions"]), 1)
            with patch("calculators.combat_library.write_atomic_json", side_effect=OSError):
                with self.assertRaises(OSError):
                    loaded.save_profile(CombatantProfile("Fichas novas"))
            self.assertNotIn("Fichas novas", loaded.profiles)

    def test_ranged_draft_keeps_post_range_damage_and_recalculates_dr(self):
        weapon = sample_weapon()
        result = RangedCombatCalculator().resolve(
            RangedAttackInput(weapon, skill=16, distance_m=6, target_dr=100, hit_location="vitals"),
            attack_roll=8, damage_rolls=[12],
        )
        draft = RangedHitDraft.from_result(result, weapon, 0)
        self.assertTrue(draft.half_damage_applied)
        self.assertEqual((draft.packet.basic_damage, draft.packet.armor_divisor, draft.packet.hit_location),
                         (6, 2, "vitals"))
        self.assertEqual(result.damages[0]["injury"], 0)
        target = CombatantProfile("Guard", armor=ArmorLoadout(natural_dr=4)).instantiate(B)
        computed = InjuryEngine().calculate(InjuryInput(draft.packet, target))
        self.assertEqual((computed.effective_dr, computed.penetrating_damage, computed.injury), (2, 4, 12))
        result.damages[0]["follow_up"] = {}
        with self.assertRaisesRegex(ValueError, "handoff_special_hit"):
            RangedHitDraft.from_result(result, weapon, 0)

    def test_vehicle_uses_both_dr_values_and_attack_engine(self):
        first = VehicleState(VehicleRecord("a", "A", "Basic Set", "462", dr=8), speed_yards_per_second=20)
        second = VehicleState(VehicleRecord("b", "B", "Basic Set", "462", dr=6, size_modifier=2),
                              speed_yards_per_second=5)
        engine = VehicleEngine()
        collision = engine.calculate_collision(VehicleCollisionInput(first, second))
        self.assertEqual(collision["collision_velocity"], 25)
        self.assertEqual(collision["object1_injury_result"]["effective_dr"], 8)
        self.assertEqual(collision["object2_injury_result"]["effective_dr"], 6)
        attack = engine.resolve_attack(VehicleAttackInput(first, second, sample_weapon(), distance_m=1),
                                       attack_roll=8, damage_rolls=[9])
        self.assertEqual(attack.damages[0]["effective_dr"], 3)
        self.assertEqual((first.current_hp, second.current_hp), (10, 10))
