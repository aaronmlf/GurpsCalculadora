import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from calculators.combat_session import CombatSession, SESSION_SCHEMA
from calculators.injury import (
    ArmorLayer,
    ArmorLoadout,
    ArmorRecord,
    CombatantState,
    DamagePacket,
    InjuryEngine,
    InjuryInput,
    OptionalInjuryRules,
    StateDelta,
)


def target(**changes):
    values = dict(identifier="target", name="Target", max_hp=10, current_hp=10, ht=10)
    values.update(changes)
    return CombatantState(**values)


class InjuryEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = InjuryEngine()

    def calculate(self, damage=10, damage_type="cr", **changes):
        target_state = changes.pop("target", target())
        profile = changes.pop("profile", "basic")
        optional = changes.pop("optional_rules", OptionalInjuryRules())
        packet = DamagePacket(damage, damage_type, **changes)
        return self.engine.calculate(InjuryInput(packet, target_state, profile=profile, optional_rules=optional))

    def test_armor_divisor_rounds_effective_dr_up(self):
        armored = target(armor=ArmorLoadout(natural_dr=5))
        result = self.calculate(9, "pi+", target=armored, armor_divisor=2)
        self.assertEqual(result.effective_dr, 3)
        self.assertEqual(result.penetrating_damage, 6)
        self.assertEqual(result.injury, 9)
        self.assertEqual(result.rounding[0]["operation"], "ceil")

    def test_split_dr_and_direction_are_intrinsic_properties(self):
        armor = ArmorRecord(
            "vest", "High-Tech", "66", "Vest", locations=["torso"], dr=12,
            dr_by_type={"*": 5, "cut": 12, "pi": 12}, direction="front", flexible=True,
        )
        state = target(armor=ArmorLoadout([ArmorLayer(armor)]))
        front_pi = self.calculate(15, "pi", target=state)
        front_cr = self.calculate(15, "cr", target=state)
        rear = self.calculate(15, "pi", target=state, direction="back")
        self.assertEqual(front_pi.effective_dr, 12)
        self.assertEqual(front_cr.effective_dr, 5)
        self.assertEqual(rear.effective_dr, 0)

    def test_flexible_armor_causes_blunt_trauma_only_when_stopped(self):
        armor = ArmorRecord("flex", "Basic Set", "379", "Flex", locations=["all"], dr=10, flexible=True)
        state = target(armor=ArmorLoadout([ArmorLayer(armor)]))
        stopped = self.calculate(10, "cr", target=state)
        penetrated = self.calculate(11, "cr", target=state)
        self.assertEqual(stopped.blunt_trauma, 2)
        self.assertEqual(stopped.injury, 2)
        self.assertEqual(penetrated.blunt_trauma, 0)
        self.assertEqual(penetrated.injury, 1)

    def test_partial_coverage_and_skull_natural_dr(self):
        armor = ArmorRecord("cap", "Basic Set", "284", "Cap", locations=["skull"], dr=2, coverage=3)
        state = target(armor=ArmorLoadout([ArmorLayer(armor)]))
        covered = self.engine.calculate(InjuryInput(
            DamagePacket(8, "cr", hit_location="skull"), state, coverage_rolls={"cap": 2}
        ))
        missed = self.engine.calculate(InjuryInput(
            DamagePacket(8, "cr", hit_location="skull"), state, coverage_rolls={"cap": 4}
        ))
        self.assertEqual(covered.effective_dr, 4)
        self.assertEqual(missed.effective_dr, 2)
        self.assertEqual(missed.injury, 24)

    def test_resolve_rolls_unspecified_partial_coverage(self):
        armor = ArmorRecord("partial", "Basic Set", "284", "Partial", locations=["torso"], dr=5, coverage=3)
        state = target(armor=ArmorLoadout([ArmorLayer(armor)]))
        with patch("calculators.injury.roll_1d6", return_value=4):
            result = self.engine.resolve(InjuryInput(DamagePacket(8, "cr"), state))
        self.assertEqual(result.armor_layers[0]["coverage_roll"], 4)
        self.assertTrue(result.armor_layers[0]["coverage_missed"])
        self.assertEqual(result.effective_dr, 0)

    def test_location_and_tolerance_wounding_modifiers(self):
        self.assertEqual(self.calculate(4, "imp", hit_location="vitals").injury, 12)
        self.assertEqual(self.calculate(4, "cut", hit_location="neck").injury, 8)
        self.assertEqual(self.calculate(4, "pi++", hit_location="arm").uncapped_injury, 4)
        unliving = self.calculate(6, "pi", target=target(injury_tolerance="unliving"))
        homogenous = self.calculate(6, "pi", target=target(injury_tolerance="homogenous"))
        diffuse = self.calculate(20, "pi", target=target(injury_tolerance="diffuse"))
        self.assertEqual(unliving.injury, 2)
        self.assertEqual(homogenous.injury, 1)
        self.assertEqual(diffuse.injury, 1)

    def test_limb_cap_crippling_and_dismemberment(self):
        result = self.calculate(10, "cut", hit_location="arm")
        self.assertEqual(result.uncapped_injury, 15)
        self.assertEqual(result.injury, 6)
        self.assertTrue(result.crippling)
        self.assertTrue(result.dismemberment)
        self.assertIn("arm", result.state_delta.destroyed_locations)

    def test_major_wound_knockdown_and_unconsciousness_are_resolved(self):
        result = self.engine.resolve(
            InjuryInput(DamagePacket(6, "cr"), target()), knockdown_roll=15
        )
        self.assertTrue(result.major_wound)
        self.assertEqual(result.state_delta.posture, "prone")
        self.assertTrue(result.state_delta.set_unconscious)

    def test_shock_scales_for_high_hp_and_never_affects_defense(self):
        result = self.calculate(8, "cr", target=target(max_hp=25, current_hp=25))
        self.assertEqual(result.state_delta.shock, 4)

    def test_death_thresholds_and_automatic_death(self):
        state = target(current_hp=1)
        resolved = self.engine.resolve(
            InjuryInput(DamagePacket(22, "cr"), state), knockdown_roll=10,
            consciousness_roll=10, death_rolls=[15, 10],
        )
        death_checks = [item for item in resolved.checks if item["kind"] == "death"]
        self.assertEqual(len(death_checks), 2)
        self.assertTrue(resolved.state_delta.set_dead)
        automatic = self.calculate(60, "cr", target=target(current_hp=1))
        self.assertTrue(automatic.state_delta.set_dead)
        self.assertIn("automatic_death", automatic.notes)

    def test_bleeding_is_optional_and_profile_gated(self):
        basic = self.calculate(4, "cut")
        self.assertFalse(basic.state_delta.wounds[0].bleeding)
        rejected = self.calculate(
            4, "cut", optional_rules=OptionalInjuryRules(bleeding=True)
        )
        self.assertFalse(rejected.valid)
        enabled = self.calculate(
            4, "cut", profile="realistic",
            optional_rules=OptionalInjuryRules(bleeding=True),
        )
        self.assertTrue(enabled.state_delta.wounds[0].bleeding)

    def test_expanded_locations_require_non_basic_profile(self):
        self.assertIn("expanded_hit_location_outside_profile", self.calculate(4, "cut", hit_location="jaw").errors)
        self.assertTrue(self.calculate(4, "cut", hit_location="jaw", profile="realistic").valid)

    def test_overpenetration_returns_only_eligible_residual_packet(self):
        result = self.calculate(12, "pi", ranged=True, cover_dr=7)
        self.assertEqual(result.residual_packet.basic_damage, 5)
        melee = self.calculate(12, "imp", ranged=False, cover_dr=7)
        wide_burn = self.calculate(12, "burn", ranged=True, tight_beam=False, cover_dr=7)
        self.assertIsNone(melee.residual_packet)
        self.assertIsNone(wide_burn.residual_packet)

    def test_corrosion_and_ablative_armor_produce_dr_loss(self):
        armor = ArmorRecord(
            "ablative", "Ultra-Tech", "174", "Ablative", locations=["all"], dr=10, ablative=True
        )
        state = target(armor=ArmorLoadout([ArmorLayer(armor)]))
        result = self.calculate(12, "cor", target=state)
        self.assertGreaterEqual(result.state_delta.armor_dr_loss["ablative"], 2)

    def test_optional_edge_layering_and_plate_modules_are_explicit(self):
        layers = ArmorLoadout([
            ArmorLayer(ArmorRecord("plate", "Low-Tech", "110", "Plate", locations=["torso"], dr=4, rigid=True)),
            ArmorLayer(ArmorRecord("mail", "Low-Tech", "110", "Mail", locations=["torso"], dr=2, flexible=True, rigid=False)),
        ])
        result = self.calculate(
            10, "cut", target=target(armor=layers), profile="realistic",
            optional_rules=OptionalInjuryRules(
                edge_protection=True, harsh_layering=True, plate_degradation=True,
            ),
        )
        self.assertEqual(result.wounding_modifier, 1.0)
        self.assertIn("edge_protection_converted_cutting_to_crushing", result.notes)
        kinds = {item["kind"] for item in result.checks}
        self.assertIn("harsh_layering", kinds)
        self.assertIn("plate_degradation", kinds)


class CombatSessionTests(unittest.TestCase):
    def test_apply_is_explicit_advances_actor_and_can_undo(self):
        session = CombatSession.new()
        session.apply("combatant_a", "combatant_b", StateDelta(hp_change=-3, shock=3), "hit")
        self.assertEqual(session.combatants["combatant_b"].current_hp, 7)
        self.assertEqual(session.combatants["combatant_a"].personal_seconds, 1)
        self.assertTrue(session.undo())
        self.assertEqual(session.combatants["combatant_b"].current_hp, 10)

    def test_bleeding_checks_run_only_when_a_minute_boundary_is_crossed(self):
        engine = InjuryEngine()
        result = engine.calculate(InjuryInput(
            DamagePacket(5, "cut"), CombatSession.new().combatants["combatant_b"],
            profile="realistic", optional_rules=OptionalInjuryRules(bleeding=True),
        ))
        session = CombatSession.new()
        session.apply("combatant_a", "combatant_b", result.state_delta)
        self.assertEqual(session.advance_time(30), [])
        bleeding = session.advance_time(30, {"combatant_b": [18]})
        self.assertEqual(bleeding[0]["hp_loss"], 3)

    def test_autosave_roundtrip_and_invalid_file_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            session = CombatSession.new(path)
            session.apply("combatant_a", "combatant_b", StateDelta(hp_change=-2))
            loaded = CombatSession.load_or_new(path)
            self.assertEqual(loaded.combatants["combatant_b"].current_hp, 8)
            self.assertEqual(json.loads(path.read_text())["schema"], SESSION_SCHEMA)
            path.write_text("not-json", encoding="utf-8")
            clean = CombatSession.load_or_new(path)
            self.assertEqual(clean.combatants["combatant_b"].current_hp, 10)
            self.assertTrue(list(Path(folder).glob("session.invalid-*.json")))

    def test_previous_maneuver_restriction_expires_on_the_actors_next_action(self):
        session = CombatSession.new()
        session.combatants["combatant_a"].conditions.append("all_out_attack_no_defense")
        session.apply_action("combatant_a", "combatant_b", StateDelta(), StateDelta(), "next_action")
        self.assertNotIn("all_out_attack_no_defense", session.combatants["combatant_a"].conditions)


if __name__ == "__main__":
    unittest.main()
