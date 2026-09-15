import unittest
from copy import deepcopy
from calculators.contests import quick_contest, supernatural_target, long_distance_modifier
from calculators.magic import CastingInput, SpellRecord, ResistanceCheck, SpellcastingEngine
from calculators.powers import PsiUseInput, PsiAbilityRecord, PsionicEngine


class ContestTests(unittest.TestCase):
    def test_rule_of_16_examples_b349(self):
        for resistance, expected in ((10, 16), (16, 16), (17, 17), (18, 18), (20, 18)):
            self.assertEqual(supernatural_target(18, resistance), expected)
        self.assertEqual(supernatural_target(25, 10, False), 25)

    def test_ties_resist_and_failed_attack_cannot_win(self):
        self.assertEqual(quick_contest(12, 12, 10, 10).winner, "tie")
        self.assertEqual(quick_contest(12, 12, 10, 10, resistance=True).winner, "defender")
        self.assertEqual(quick_contest(10, 10, 11, 15).winner, "attacker")
        self.assertEqual(quick_contest(10, 10, 11, 15, resistance=True).winner, "defender")

    def test_distance_bands_and_extremes(self):
        limits = (200, 880, 1760, 5280, 17600, 52800, 176000, 528000, 1760000)
        for i, limit in enumerate(limits):
            self.assertEqual(long_distance_modifier(limit), -i)
            self.assertEqual(long_distance_modifier(limit + .01), -i - 1)
        self.assertEqual(long_distance_modifier(17600000), -10)
        self.assertEqual(long_distance_modifier(176000000), -12)
        for bad in (-1, float('inf'), float('nan')):
            with self.assertRaises(ValueError): long_distance_modifier(bad)

    def test_information_spell_uses_long_distance_not_weapon_table(self):
        spell = SpellRecord('s', 'S', 'Basic Set', '241', spell_class='information')
        result = SpellcastingEngine().calculate(CastingInput(spell, skill=15, distance_yards=200))
        self.assertEqual(result.effective_skill, 15)

    def test_spell_capped_before_roll_without_changing_cost_reduction(self):
        data = CastingInput(SpellRecord('s', 'S', 'Basic Set', '241', base_cost=5),
                            skill=25, resistance=ResistanceCheck(target=12))
        before = deepcopy(data)
        result = SpellcastingEngine().resolve(data, cast_roll=12, resistance_roll=8)
        self.assertEqual(result.effective_skill, 16)
        self.assertEqual(result.energy_cost, 2)
        self.assertTrue(result.resistance.resisted)
        self.assertEqual(data, before)
        critical = SpellcastingEngine().resolve(data, cast_roll=6)
        self.assertTrue(critical.roll['critical_success'])
        self.assertIsNone(critical.resistance.roll)

    def test_psi_cap_and_resistance(self):
        data = PsiUseInput(PsiAbilityRecord('p', 'P', 'Powers', '1', 'Psi', 'Skill'),
                           skill=30, resistance=ResistanceCheck(target=18))
        before = deepcopy(data)
        result = PsionicEngine().resolve(data, roll=10, resistance_roll=9)
        self.assertEqual(result.effective_skill, 18)
        self.assertTrue(result.resistance.resisted)
        self.assertEqual(data, before)
