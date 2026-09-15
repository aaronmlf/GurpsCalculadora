from dataclasses import replace
import unittest
from calculators.campaign import BattleInput, ForceRecord, ElementRecord, MassCombatEngine


class DefenseBonusTests(unittest.TestCase):
    def setUp(self):
        self.engine=MassCombatEngine()
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]))

    def test_defense_bonus_is_separate_from_position(self):
        data=replace(self.data,defender_defense_bonus=5,defender_position=2)
        self.assertEqual(self.engine.calculate(data).defender_target,18)
        data=replace(data,attacker_strategy='deliberate_attack')
        self.assertEqual(self.engine.calculate(data).defender_target,16)
        self.assertEqual(self.engine.resolve(data,10,10).margin,-5)

    def test_halving_rounds_up_for_both_sides(self):
        for db,expected in ((0,0),(1,1),(2,1),(3,2),(4,2),(5,3)):
            data=replace(self.data,attacker_strategy='deliberate_attack',defender_defense_bonus=db)
            self.assertEqual(self.engine.calculate(data).defender_target,11+expected)
            data=replace(self.data,attacker_strategy='defense',defender_strategy='deliberate_attack',attacker_defense_bonus=db)
            self.assertEqual(self.engine.calculate(data).attacker_target,11+expected)

    def test_no_defensive_bonus_on_attack_or_skirmish(self):
        for strategy in ('attack','skirmish','raid','full_retreat'):
            data=replace(self.data,attacker_strategy=strategy,attacker_defense_bonus=5)
            plain=replace(data,attacker_defense_bonus=0)
            self.assertEqual(self.engine.calculate(data).attacker_target,self.engine.calculate(plain).attacker_target)

    def test_invalid_bonus(self):
        for value in (-1,True,1.5,'five'):
            self.assertFalse(self.engine.calculate(replace(self.data,attacker_defense_bonus=value)).valid)

    def test_encounter_disallows_deliberate_before_stalemate_conversion(self):
        from unittest.mock import patch
        for strategy in ('deliberate_attack','deliberate_defense'):
            for side in ('attacker','defender'):
                data=replace(self.data,encounter_battle=True,**{side+'_strategy':strategy})
                with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
                    result=self.engine.resolve(data)
                self.assertFalse(result.valid)
                self.assertIn('invalid_encounter_strategy',result.errors)
