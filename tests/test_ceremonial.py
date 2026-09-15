import unittest
from copy import deepcopy
from dataclasses import replace
from calculators.magic import (CastingInput, SpellRecord, SpellcastingEngine, CeremonialCasting,
                               CeremonialAssistant, ResourcePool)


class CeremonialTests(unittest.TestCase):
    def data(self, total=10):
        return CastingInput(SpellRecord('s', 'S', 'Basic Set', '238', base_cost=10, casting_time_seconds=2),
                            skill=20, system='ceremonial', resources=ResourcePool(fp=20),
                            ceremony=CeremonialCasting(5, [CeremonialAssistant(15, True, total - 5)]))

    def test_energy_bonus_bands_no_high_skill_reduction(self):
        for energy, bonus in ((10, 0), (11, 0), (12, 1), (14, 2), (16, 3), (19, 3), (20, 4), (30, 5)):
            result = SpellcastingEngine().calculate(self.data(energy))
            self.assertTrue(result.valid, result.errors)
            self.assertEqual(result.effective_skill, 20 + bonus)
            self.assertEqual(result.energy_cost, energy)
            self.assertEqual(result.casting_time_seconds, 20)

    def test_all_energy_spent_for_every_outcome(self):
        for roll in (3, 10, 16, 17, 18):
            data = self.data()
            before = deepcopy(data)
            result = SpellcastingEngine().resolve(data, cast_roll=roll)
            self.assertEqual(result.resource_delta['fp'], -5)
            self.assertEqual(result.resource_delta['ceremonial_assistants'], -5)
            self.assertEqual(result.roll['success'], roll < 16)
            self.assertEqual(result.roll['critical_failure'], roll >= 17)
            self.assertEqual(data, before)

    def test_leader_group_and_assistant_limits(self):
        engine = SpellcastingEngine()
        for data in (replace(self.data(), skill=14), replace(self.data(), ceremony=None),
                     replace(self.data(), ceremony=CeremonialCasting(10)),
                     replace(self.data(), ceremony=CeremonialCasting(5, [CeremonialAssistant(15, False, 5)]))):
            self.assertFalse(engine.calculate(data).valid)

    def test_spectator_caps_and_opposition(self):
        data = replace(self.data(), ceremony=CeremonialCasting(10, [], 150, 50))
        result = SpellcastingEngine().calculate(data)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.energy_cost, 110)
        self.assertEqual(result.effective_skill, 20)
