from dataclasses import replace
from unittest.mock import patch
import unittest
from calculators.campaign import BattleInput,ForceRecord,ElementRecord,MassCombatEngine,CampaignSession

class InitiativeTests(unittest.TestCase):
    def setUp(self):
        self.e=MassCombatEngine()
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]),attacker_strategy='deliberate_attack',defender_strategy='attack')

    def test_optional_change_applies_to_calculate_resolve_history(self):
        data=replace(self.data,defender_response_strategy='all_out_attack')
        self.assertEqual(self.e.calculate(data).defender_target,12)
        result=self.e.resolve(data,10,10)
        self.assertEqual(result.margin,-1)
        s=CampaignSession()
        s.apply_battle_round(data,result,s.to_dict())
        self.assertEqual(s.battle_strategy_state['d']['previous'],'all_out_attack')

    def test_slow_side_cannot_change_and_two_slow_sides_cannot_change(self):
        for changes in ({'attacker_response_strategy':'attack'},
            {'defender_strategy':'deliberate_defense','defender_defense_bonus':1,'defender_response_strategy':'attack'},
            {'attacker_strategy':'attack','defender_response_strategy':'raid'}):
            with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
                self.assertFalse(self.e.resolve(replace(self.data,**changes)).valid)

    def test_parley_requires_refusal_to_change(self):
        data=replace(self.data,attacker_strategy='parley',defender_response_strategy='all_out_attack')
        self.assertFalse(self.e.calculate(replace(data,parley_response='accept')).valid)
        result=self.e.resolve(replace(data,parley_response='refuse'),10,10)
        self.assertTrue(result.valid)
        self.assertEqual(result.margin,-2)

    def test_response_still_must_be_legal(self):
        data=replace(self.data,defender_response_strategy='rally')
        self.assertFalse(self.e.calculate(data).valid)

    def test_response_cannot_open_second_exchange(self):
        data=replace(self.data,defender_response_strategy='deliberate_attack',attacker_response_strategy='raid')
        self.assertFalse(self.e.calculate(data).valid)
