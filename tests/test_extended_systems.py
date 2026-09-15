import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace

from calculators.campaign import (
    BattleInput, CampaignSession, CampaignStateDelta, CharacterSocialProfile,
    ElementRecord, ForceRecord, InfluenceInput, MassCombatEngine, ReactionInput,
    SocialEngineeringEngine,
)
from calculators.magic import CastingInput, ResourcePool, SpellcastingEngine
from calculators.powers import AbilityBuildInput, AbilityEngine, PsionicEngine, PsiUseInput
from calculators.strength import DamageBonusInput, EffortOption, StrengthCalculationInput, StrengthEngine, StrengthProfile
from calculators.vehicles import VehicleCatalog, VehicleEngine, VehicleMovementInput, VehicleSession, VehicleState
from utils.rules_catalog import ExtendedRulesCatalog


ROOT = Path(__file__).resolve().parents[1]


class StrengthTests(unittest.TestCase):
    def setUp(self):
        self.engine = StrengthEngine()

    def test_basic_lift_and_specialized_strength(self):
        result = self.engine.calculate(StrengthCalculationInput(
            profile=StrengthProfile(st=10, lifting_st=2), task="basic_lift"))
        self.assertEqual(result.effective_st, 12)
        self.assertEqual(result.basic_lift_lb, 29)  # B15: round BL >= 10 lb.

    def test_striking_st_does_not_improve_lifting(self):
        result = self.engine.calculate(StrengthCalculationInput(
            profile=StrengthProfile(st=10, striking_st=10), task="two_handed_lift"))
        self.assertEqual(result.effective_st, 10)

    def test_super_effort_profile_and_task_gating(self):
        forbidden = self.engine.calculate(StrengthCalculationInput(
            profile=StrengthProfile(), task="basic_lift", rules_profile="basic",
            effort=EffortOption(super_effort_levels=3)))
        self.assertIn("super_effort_outside_profile", forbidden.errors)
        choke = self.engine.calculate(StrengthCalculationInput(
            profile=StrengthProfile(), task="choke", rules_profile="cinematic",
            effort=EffortOption(super_effort_levels=3, super_effort_scope="total")))
        self.assertIn("super_effort_not_applicable", choke.errors)

    def test_super_effort_uses_size_range_linear_measurement_progression(self):
        result = self.engine.calculate(StrengthCalculationInput(
            profile=StrengthProfile(st=10), task="basic_lift", rules_profile="realistic",
            effort=EffortOption(super_effort_levels=20)))
        self.assertEqual(result.effective_st, 5010)

    def test_cinematic_super_striking_adds_supervalue_damage(self):
        result = self.engine.calculate_damage(DamageBonusInput(
            profile=StrengthProfile(st=10), rules_profile="cinematic",
            effort=EffortOption(super_effort_levels=10, super_effort_scope="total")))
        self.assertEqual(result.original_damage, "1d")
        self.assertIn({"key": "super_effort_damage", "value": "13d"}, result.breakdown)
        self.assertEqual(result.fp_cost, 1)

    def test_all_out_strong_uses_best_bonus_and_converts_adds(self):
        result = self.engine.calculate_damage(DamageBonusInput(
            profile=StrengthProfile(st=20), basis="swing", maneuver="all_out_strong", convert_adds=True))
        self.assertEqual(result.original_damage, "3d+2")
        self.assertEqual(result.final_damage, "4d+1")

    def test_mighty_blows_costs_fp_as_explicit_basic_optional_rule(self):
        effort = EffortOption(mighty_blows=True)
        basic = self.engine.calculate_damage(DamageBonusInput(effort=effort))
        self.assertTrue(basic.valid)
        self.assertEqual(basic.fp_cost, 1)
        self.assertEqual(basic.state_delta.fp_change, -1)


class MagicAndPowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ExtendedRulesCatalog()

    def test_all_magic_frameworks_are_registered(self):
        systems = {item.identifier for item in self.catalog.records("magic_systems")}
        self.assertEqual(len(systems), 12)
        self.assertIn("magic.rpm", systems)
        self.assertIn("magic.sorcery", systems)

    def test_area_spell_cost_and_high_skill_reduction(self):
        spell = next(item for item in self.catalog.records("spells") if item.identifier == "spell.create-fire")
        result = SpellcastingEngine().calculate(CastingInput(
            spell=spell, skill=20, area_radius_yards=3, resources=ResourcePool(fp=20)))
        self.assertEqual(result.energy_cost, 4)

    def test_resolved_spell_spends_only_fp_after_success(self):
        spell = next(item for item in self.catalog.records("spells") if item.identifier == "spell.fireball")
        spell = replace(spell, base_cost=1, casting_time_seconds=1)  # Explicit one-second, one-energy Fireball.
        result = SpellcastingEngine().resolve(CastingInput(spell=spell, resources=ResourcePool(fp=10)), cast_roll=10)
        self.assertTrue(result.roll["success"])
        self.assertEqual(result.state_delta.fp_change, -1)

    def test_insufficient_spell_energy_blocks_resolution(self):
        spell = next(item for item in self.catalog.records("spells") if item.identifier == "spell.mind-reading")
        result = SpellcastingEngine().resolve(CastingInput(spell=spell, resources=ResourcePool(fp=0)), cast_roll=3)
        self.assertFalse(result.valid)
        self.assertIsNone(result.roll)

    def test_ability_modifiers_floor_and_alternate_cost(self):
        advantage = self.catalog.records("advantages")[0]
        modifiers = [item for item in self.catalog.records("modifiers") if item.percent < 0]
        # Duplicate test modifiers deliberately exercise the global -80% floor.
        result = AbilityEngine().calculate(AbilityBuildInput(
            advantage=advantage, modifiers=modifiers * 20, alternate_ability=True))
        self.assertEqual(result.net_modifier_percent, -80)
        self.assertGreaterEqual(result.modified_cost, 1)

    def test_psionics_is_profile_gated(self):
        ability = self.catalog.records("psi_abilities")[0]
        result = PsionicEngine().calculate(PsiUseInput(ability=ability, profile="basic"))
        self.assertIn("psionics_outside_basic_profile", result.errors)


class VehicleTests(unittest.TestCase):
    def setUp(self):
        self.catalog = VehicleCatalog(ROOT / "data" / "vehicles.json", ROOT / "unused.json", load_user=False)
        self.engine = VehicleEngine()

    def test_movement_accelerates_without_exceeding_top_speed(self):
        sedan = self.catalog.search("Sedan")[0]
        result = self.engine.calculate_movement(VehicleMovementInput(VehicleState(sedan), duration_seconds=30))
        self.assertEqual(result.final_speed, sedan.move_top_speed)

    def test_custom_vehicle_is_saved_outside_builtin_catalog(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "vehicles.json"
            catalog = VehicleCatalog(ROOT / "data" / "vehicles.json", path, load_user=False)
            builtin_before = [item.to_dict() for item in catalog.builtin]
            record = catalog.vehicles[0]
            record = type(record)(**{**record.to_dict(), "identifier": "", "name": "My Vehicle"})
            catalog.save_custom(record)
            self.assertTrue(path.exists())
            self.assertEqual([item.to_dict() for item in catalog.builtin], builtin_before)

    def test_vehicle_session_requires_explicit_apply_and_undo(self):
        sedan = self.catalog.search("Sedan")[0]
        state = VehicleState(sedan)
        session = VehicleSession({"car": state})
        result = self.engine.calculate_movement(VehicleMovementInput(state, duration_seconds=1))
        self.assertEqual(state.speed_yards_per_second, 0)
        session.apply_movement("car", result)
        self.assertGreater(state.speed_yards_per_second, 0)
        self.assertTrue(session.undo())
        self.assertEqual(session.vehicles["car"].speed_yards_per_second, 0)


class CampaignTests(unittest.TestCase):
    def test_reaction_bands(self):
        engine = SocialEngineeringEngine()
        actor = CharacterSocialProfile("a", "A", charisma=2)
        result = engine.resolve_reaction(ReactionInput(actor), roll=12)
        self.assertEqual(result.band, "good")

    def test_expanded_influence_is_a_contest(self):
        actor = CharacterSocialProfile("a", "A", skills={"Diplomacy": 14})
        target = CharacterSocialProfile("b", "B", will=12)
        result = SocialEngineeringEngine().resolve_influence(
            InfluenceInput(actor, target, "Diplomacy", expanded=True), actor_roll=9, target_roll=12)
        self.assertTrue(result.success)

    def test_mass_combat_produces_unapplied_delta(self):
        element = ElementRecord("e", "Infantry", 10, ["Inf"])
        attacker = ForceRecord("a", "A", [element], commander_strategy=14)
        defender = ForceRecord("d", "D", [ElementRecord("e2", "Infantry", 5, ["Inf"])], commander_strategy=10)
        result = MassCombatEngine().resolve(BattleInput(attacker, defender), attacker_roll=9, defender_roll=11)
        self.assertTrue(result.valid)
        self.assertEqual(attacker.troop_strength, 10)
        self.assertIn("a", result.state_delta.force_losses)

    def test_campaign_autosave_apply_and_undo(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "campaign.json"
            force = ForceRecord("a", "A", [ElementRecord("e", "Infantry", 10, ["Inf"])])
            session = CampaignSession(forces={"a": force}, autosave_path=path)
            session.apply(CampaignStateDelta(force_losses={"a": 20}))
            self.assertAlmostEqual(session.forces["a"].troop_strength, 8)
            self.assertTrue(session.undo())
            self.assertAlmostEqual(session.forces["a"].troop_strength, 10)
            self.assertTrue(path.exists())

    def test_invalid_campaign_is_preserved_for_diagnosis(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "campaign.json"
            path.write_text("not-json", encoding="utf-8")
            session = CampaignSession.load_or_new(path)
            self.assertFalse(session.history)
            self.assertTrue(list(Path(tmp).glob("campaign.json.invalid-*")))


if __name__ == "__main__":
    unittest.main()
