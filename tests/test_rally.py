from dataclasses import replace
import unittest
from unittest.mock import patch
from calculators.campaign import BattleInput,ForceRecord,ElementRecord,MassCombatEngine,CampaignSession


class RallyTests(unittest.TestCase):
    def setUp(self):
        self.engine=MassCombatEngine()
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]),attacker_strategy='rally',
            defender_strategy='attack',attacker_confused=True,attacker_leadership=12,attacker_rally_roll=10)

    def test_explicit_rally_and_apply_undo(self):
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            result=self.engine.resolve(self.data,10,10)
        self.assertEqual(result.rally_results['attacker']['target'],10)
        self.assertTrue(result.rally_results['attacker']['success'])
        s=CampaignSession()
        before=s.to_dict()
        self.assertFalse(s.battle_conditions)
        s.apply_battle_round(self.data,result,before)
        self.assertEqual(s.battle_conditions['a'],{'confused':False,'started_confused':True,'mobile':False})
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).battle_conditions,s.battle_conditions)
        s.undo()
        self.assertEqual(s.to_dict(),before)

    def test_failure_keeps_confusion(self):
        data=replace(self.data,attacker_rally_roll=11)
        result=self.engine.resolve(data,10,10)
        self.assertFalse(result.rally_results['attacker']['success'])
        s=CampaignSession()
        s.apply_battle_round(data,result,s.to_dict())
        self.assertTrue(s.battle_conditions['a']['confused'])

    def test_destroyed_force_never_rolls_rally(self):
        data=replace(self.data,attacker_casualties=95,attacker_rally_roll=None)
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            result=self.engine.resolve(data,18,3)
        self.assertFalse(result.rally_results)

    def test_calculate_never_rolls_rally(self):
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            self.assertTrue(self.engine.calculate(replace(self.data,attacker_rally_roll=None)).valid)

    def test_invalid_roll_no_attack_roll(self):
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            self.assertFalse(self.engine.resolve(replace(self.data,attacker_rally_roll=0)).valid)
