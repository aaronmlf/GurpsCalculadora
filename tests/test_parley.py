from dataclasses import replace
import unittest
from unittest.mock import patch
from calculators.campaign import BattleInput, ForceRecord, ElementRecord, MassCombatEngine, CampaignSession


class ParleyTests(unittest.TestCase):
    def setUp(self):
        self.engine=MassCombatEngine()
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]),attacker_strategy='parley',defender_strategy='attack')

    def test_accepted_never_rolls_or_changes_positions(self):
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            result=self.engine.resolve(replace(self.data,parley_response='accept',attacker_position=3))
        self.assertTrue(result.valid)
        self.assertEqual(result.outcome,'parley')
        self.assertFalse(result.state_delta.battle_positions)

    def test_refused_is_defense_with_extra_minus_one(self):
        data=replace(self.data,parley_response='refuse')
        calc=self.engine.calculate(data)
        self.assertEqual(calc.attacker_target,10)
        result=self.engine.resolve(data,10,10)
        self.assertEqual(result.margin,0)
        s=CampaignSession()
        s.apply_battle_round(data,result,s.to_dict())
        self.assertEqual(s.battle_strategy_state['a']['previous'],'defense')

    def test_refusal_against_retreat_is_no_battle(self):
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            result=self.engine.resolve(replace(self.data,parley_response='refuse',defender_strategy='full_retreat'))
        self.assertEqual(result.outcome,'no_battle')

    def test_bilateral_parley_always_pauses(self):
        for response in ('pending','accept','refuse'):
            self.assertEqual(self.engine.resolve(replace(self.data,defender_strategy='parley',parley_response=response)).outcome,'parley')

    def test_symmetry(self):
        data=replace(self.data,attacker_strategy='attack',defender_strategy='parley',parley_response='refuse')
        self.assertEqual(self.engine.calculate(data).defender_target,10)

    def test_bad_response_is_invalid_without_roll(self):
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            self.assertFalse(self.engine.resolve(replace(self.data,parley_response='unknown')).valid)
