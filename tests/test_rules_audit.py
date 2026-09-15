"""Regressions from source review, not snapshots of existing implementation."""
import unittest
from copy import deepcopy
from dataclasses import replace

from calculators.strength import StrengthEngine, StrengthProfile, StrengthCalculationInput, EffortOption, DamageBonusInput
from calculators.magic import SpellRecord, CastingInput, SpellcastingEngine, ResourcePool, ResistanceCheck
from calculators.vehicles import VehicleEngine, VehicleRecord, VehicleState, VehicleMovementInput, SpacecraftRecord, VehicleSession
from calculators.melee_combat import MeleeAttackInput, MeleeCombatCalculator
from calculators.injury import CombatantState
from utils.combat_catalog import MeleeWeaponCatalog
from calculators.campaign import CharacterSocialProfile, InfluenceInput, SocialEngineeringEngine
from calculators.powers import PsionicEngine, PsiUseInput
from utils.rules_catalog import ExtendedRulesCatalog


class StrengthAuditTests(unittest.TestCase):
    def test_effort_target_accounts_for_missing_fp_before_payment(self):
        data = StrengthCalculationInput(profile=StrengthProfile(will=14, max_fp=12, current_fp=9),
                                        effort=EffortOption(extra_effort_percent=10))
        engine = StrengthEngine()
        self.assertEqual(engine.calculate(data).required_roll_target, 9)
        result = engine.resolve(data, will_roll=9)
        self.assertTrue(result.success_roll["success"])
        self.assertEqual(result.state_delta.fp_change, -1)
        self.assertEqual(data.profile.current_fp, 9)

    def test_lifting_uses_will_based_skill_and_ten_percent_steps(self):
        result = StrengthEngine().calculate(StrengthCalculationInput(
            profile=StrengthProfile(will=10, lifting_skill_will=14),
            effort=EffortOption(extra_effort_percent=20, use_lifting_skill=True)))
        self.assertEqual(result.required_roll_target, 12)
        self.assertEqual(result.basic_lift_lb, 24)

    def test_missing_lifting_skill_is_rejected(self):
        result = StrengthEngine().calculate(StrengthCalculationInput(
            effort=EffortOption(extra_effort_percent=20, use_lifting_skill=True)))
        self.assertIn("lifting_skill_not_available", result.errors)

    def test_super_effort_carry_cost_is_per_minute_not_hour(self):
        data = StrengthCalculationInput(rules_profile="realistic", duration_seconds=121,
            effort=EffortOption(super_effort_levels=5, continuous=True, sustained_use="carry"))
        engine = StrengthEngine()
        self.assertEqual(engine.calculate(data).fp_cost, 3)
        self.assertEqual(engine.calculate(replace(data, effort=replace(data.effort, sustained_use="hold"))).fp_cost, 1)

    def test_extra_effort_multiple_minutes_requires_separate_rolls(self):
        result = StrengthEngine().calculate(StrengthCalculationInput(duration_seconds=61,
            effort=EffortOption(extra_effort_percent=10, continuous=True)))
        self.assertFalse(result.valid)
        self.assertEqual(result.state_delta.fp_change, 0)

    def test_machine_cannot_use_mighty_blows(self):
        result = StrengthEngine().calculate_damage(DamageBonusInput(
            profile=StrengthProfile(machine=True), effort=EffortOption(mighty_blows=True)))
        self.assertIn("machine_cannot_use_extra_effort", result.errors)
        self.assertEqual(result.state_delta.fp_change, 0)

    def test_optional_conversion_seven_adds_become_two_dice(self):
        data = DamageBonusInput(weapon_modifier=7)
        engine = StrengthEngine()
        self.assertEqual(engine.calculate_damage(data).final_damage, "1d+7")
        self.assertEqual(engine.calculate_damage(replace(data, convert_adds=True)).final_damage, "3d")

    def test_mighty_blows_cannot_stack_all_out_attack(self):
        result = StrengthEngine().calculate_damage(DamageBonusInput(
            maneuver="all_out_strong", effort=EffortOption(mighty_blows=True)))
        self.assertFalse(result.valid)
        self.assertEqual(result.state_delta.fp_change, 0)

    def test_insufficient_fatigue_does_not_create_delta(self):
        result = StrengthEngine().calculate_damage(DamageBonusInput(
            profile=StrengthProfile(current_fp=0), effort=EffortOption(mighty_blows=True)))
        self.assertIn("insufficient_fp", result.errors)
        self.assertEqual(result.state_delta.fp_change, 0)

    def test_lifting_super_effort_does_not_modify_throwing(self):
        result = StrengthEngine().calculate(StrengthCalculationInput(
            task="throwing", rules_profile="realistic", effort=EffortOption(super_effort_levels=10)))
        self.assertIn("super_effort_not_applicable", result.errors)

    def test_collision_uses_hp_not_specialized_strength(self):
        result = StrengthEngine().calculate(StrengthCalculationInput(
            task="collision", profile=StrengthProfile(st=10, hp=25, lifting_st=50, striking_st=50)))
        self.assertEqual(result.effective_st, 25)

    def test_failed_effort_uses_normal_capacity_without_mutating_input(self):
        data = StrengthCalculationInput(effort=EffortOption(extra_effort_percent=10))
        before = deepcopy(data)
        result = StrengthEngine().resolve(data, will_roll=12)
        self.assertEqual(data, before)
        self.assertEqual(result.basic_lift_lb, 20)
        self.assertEqual(result.state_delta.fp_change, -1)

    def test_critical_effort_success_is_free(self):
        result = StrengthEngine().resolve(StrengthCalculationInput(
            effort=EffortOption(extra_effort_percent=10)), will_roll=3)
        self.assertEqual(result.fp_cost, 0)

    def test_melee_effort_is_paid_on_miss_and_defense(self):
        weapon = next(w for w in MeleeWeaponCatalog(load_user=False).weapons
                      if w.name == "Broadsword" and w.source == "Basic Set")
        data = MeleeAttackInput(weapon=weapon,
            attacker=CombatantState(identifier="a", name="A"),
            target=CombatantState(identifier="b", name="B"),
            skill=14, distance_yards=1, defense_score=12, effort=EffortOption(mighty_blows=True))
        engine = MeleeCombatCalculator()
        for attack, defense in ((16, 10), (10, 8)):
            result = engine.resolve(data, attack_rolls=[attack], defense_rolls=[defense])
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(result.attacker_delta.fp_change, -1)
            self.assertFalse(result.attacks[0]["hit"])
        self.assertEqual(data.attacker.current_fp, 10)
        critical = engine.resolve(data, attack_rolls=[18])
        self.assertEqual(critical.attacker_delta.fp_change, -1)
        self.assertEqual(critical.attacker_delta.hp_change, -1)
        self.assertTrue(any(p["kind"] == "extra_effort_critical_injury" for p in critical.pending_effects))


class MagicAuditTests(unittest.TestCase):
    def data(self, **changes):
        return CastingInput(spell=SpellRecord("test", "Test", "Magic", "8", base_cost=3,
                                              casting_time_seconds=5), **changes)

    def test_base_skill_reduction_ignores_distance_but_not_low_mana(self):
        engine = SpellcastingEngine()
        self.assertEqual(engine.calculate(self.data(skill=20, distance_yards=8)).energy_cost, 1)
        self.assertEqual(engine.calculate(self.data(skill=20, mana_level="low")).energy_cost, 2)
        self.assertEqual(engine.calculate(self.data(skill=20)).casting_time_seconds, 3)

    def test_no_mana_cannot_be_bypassed_by_critical_success(self):
        result = SpellcastingEngine().resolve(self.data(mana_level="no_mana"), cast_roll=3)
        self.assertFalse(result.valid)
        self.assertIsNone(result.roll)

    def test_failure_cost_critical_cost_and_resource_ledger(self):
        engine = SpellcastingEngine()
        data = self.data()
        self.assertEqual(engine.resolve(data, cast_roll=13).state_delta.fp_change, -1)
        self.assertEqual(engine.resolve(data, cast_roll=18).state_delta.fp_change, -3)
        self.assertEqual(engine.resolve(data, cast_roll=3).state_delta.fp_change, 0)
        reserved = engine.resolve(self.data(resources=ResourcePool(fp=10, energy_reserve=2)), cast_roll=10)
        self.assertEqual(reserved.resource_delta, {"external_energy": 0, "energy_reserve": -2, "fp": -1})

    def test_resistance_input_remains_unchanged(self):
        data = self.data(resistance=ResistanceCheck(target=12))
        before = deepcopy(data)
        SpellcastingEngine().resolve(data, cast_roll=10, resistance_roll=10)
        self.assertEqual(data, before)


class VehicleAuditTests(unittest.TestCase):
    def test_distance_after_reaching_top_speed(self):
        record = VehicleRecord("test", "Test", "Custom", "", move_acceleration=2, move_top_speed=10)
        result = VehicleEngine().calculate_movement(VehicleMovementInput(VehicleState(record), duration_seconds=10))
        self.assertEqual(result.distance_yards, 75)  # 25 accelerating + 50 cruising.

    def test_trip_rechecks_fuel(self):
        record = VehicleRecord("test", "Test", "Custom", "", fuel_hours=1)
        result = VehicleEngine().calculate_movement(VehicleMovementInput(
            VehicleState(record, speed_yards_per_second=10), travel_distance_miles=100))
        self.assertIn("insufficient_fuel", result.errors)

    def test_spacecraft_does_not_use_road_speed_cap_and_survives_undo(self):
        record = SpacecraftRecord("test", "Test", "Custom", "", acceleration_g=1, delta_v_mps=10)
        session = VehicleSession({"s": VehicleState(record)})
        result = VehicleEngine().calculate_movement(VehicleMovementInput(
            session.vehicles["s"], duration_seconds=10, environment="space"))
        self.assertGreater(result.final_speed, record.move_top_speed)
        session.apply_movement("s", result)
        self.assertTrue(session.undo())
        self.assertIsInstance(session.vehicles["s"].record, SpacecraftRecord)

    def test_nan_is_rejected(self):
        record = VehicleRecord("test", "Test", "Custom", "")
        result = VehicleEngine().calculate_movement(VehicleMovementInput(VehicleState(record), duration_seconds=float("nan")))
        self.assertFalse(result.valid)


class SocialAndPsiAuditTests(unittest.TestCase):
    def test_basic_influence_requires_winning_contest(self):
        data = InfluenceInput(CharacterSocialProfile("a", "A", skills={"Diplomacy": 14}),
                              CharacterSocialProfile("b", "B", will=14), "Diplomacy")
        result = SocialEngineeringEngine().resolve_influence(data, actor_roll=10, target_roll=8)
        self.assertFalse(result.success)
        self.assertEqual(result.reaction_band, "bad")
        self.assertTrue(any(p["kind"] == "take_better_reaction_roll" for p in result.pending_effects))

    def test_psi_resolution_does_not_mutate_resistance(self):
        ability = ExtendedRulesCatalog().records("psi_abilities")[0]
        data = PsiUseInput(ability=ability, profile="realistic", resistance=ResistanceCheck())
        before = deepcopy(data)
        PsionicEngine().resolve(data, roll=3, resistance_roll=12)
        self.assertEqual(data, before)

    def test_psi_rejects_unknown_profile(self):
        ability = ExtendedRulesCatalog().records("psi_abilities")[0]
        result = PsionicEngine().calculate(PsiUseInput(ability=ability, profile="unknown"))
        self.assertIn("invalid_profile", result.errors)
