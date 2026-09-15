import unittest
from copy import deepcopy
from dataclasses import replace
from calculators.strength import StrengthEngine, StrengthCalculationInput, StrengthProfile, EffortOption, DamageBonusInput


class StrengthSkillTests(unittest.TestCase):
    def test_continuous_effort_updates_fatigue_each_minute(self):
        data = StrengthCalculationInput(StrengthProfile(will=15), task='two_handed_lift', duration_seconds=121,
                                        effort=EffortOption(extra_effort_percent=10, continuous=True))
        before = deepcopy(data)
        result = StrengthEngine().resolve(data, interval_rolls=[10, 10, 10])
        self.assertTrue(result.valid, result.errors)
        self.assertEqual([i['target'] for i in result.intervals], [13, 12, 11])
        self.assertEqual([i['seconds'] for i in result.intervals], [60, 60, 1])
        self.assertEqual(result.state_delta.fp_change, -3)
        self.assertEqual(data, before)

    def test_continuous_effort_stops_after_failure(self):
        data = StrengthCalculationInput(StrengthProfile(will=15), task='two_handed_lift', duration_seconds=180,
                                        effort=EffortOption(extra_effort_percent=10, continuous=True))
        result = StrengthEngine().resolve(data, interval_rolls=[10, 18, 10])
        self.assertFalse(result.valid)
        self.assertEqual(len(result.intervals), 2)
        self.assertEqual(result.state_delta.fp_change, -2)
        self.assertEqual(result.state_delta.hp_change, -1)

    def test_lifting_margin_increases_lift_but_not_st(self):
        data = StrengthCalculationInput(StrengthProfile(lifting_skill_ht=14), task='two_handed_lift',
                                        effort=EffortOption(trained_lift=True, lifting_roll=10))
        result = StrengthEngine().resolve(data)
        self.assertEqual(result.basic_lift_lb, 24)
        self.assertEqual(result.capacity_lb, 192)
        self.assertEqual(result.effective_st, 10)
        self.assertEqual(result.fp_cost, 0)
        self.assertFalse(StrengthEngine().calculate(replace(data, task='carry_heavy')).valid)

    def test_power_blow_concentration_bands_and_prerequisites(self):
        data = StrengthCalculationInput(StrengthProfile(power_blow_level=25, trained_by_master=True),
                                        task='striking', rules_profile='cinematic', effort=EffortOption(power_blow=True))
        for seconds, penalty in ((0, -10), (1, -5), (2, -4), (3, -4), (4, -3), (8, -2), (16, -1), (32, 0), (64, 0)):
            result = StrengthEngine().calculate(replace(data, effort=replace(data.effort, concentration_seconds=seconds)))
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(result.required_roll_target, 25 + penalty)
        self.assertFalse(StrengthEngine().calculate(replace(data, rules_profile='basic')).valid)
        self.assertFalse(StrengthEngine().calculate(replace(data, profile=StrengthProfile(power_blow_level=25))).valid)

    def test_power_blow_failure_pays_fp_without_extra_effort_hp_loss(self):
        data = StrengthCalculationInput(StrengthProfile(power_blow_level=20, weapon_master=True),
                                        task='striking', rules_profile='cinematic',
                                        effort=EffortOption(power_blow=True, power_blow_roll=18))
        before = deepcopy(data)
        result = StrengthEngine().resolve(data)
        self.assertEqual(result.effective_st, 10)
        self.assertEqual(result.state_delta.fp_change, -1)
        self.assertEqual(result.state_delta.hp_change, 0)
        self.assertEqual(data, before)

    def test_power_blow_triples_only_above_twenty_and_strong_attack_stacks(self):
        profile = StrengthProfile(power_blow_level=21, trained_by_master=True)
        effort = EffortOption(power_blow=True, triple_strength=True, concentration_seconds=32, power_blow_roll=10)
        result = StrengthEngine().calculate_damage(DamageBonusInput(profile=profile, rules_profile='cinematic',
                                                                    effort=effort, maneuver='all_out_strong'))
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.strength_used, 30)
        self.assertEqual(result.fp_cost, 1)
        invalid = StrengthEngine().calculate(StrengthCalculationInput(replace(profile, power_blow_level=20),
                    task='striking', rules_profile='cinematic', effort=effort))
        self.assertFalse(invalid.valid)
