from dataclasses import replace
import unittest
from calculators.campaign import BattleInput,ForceRecord,ElementRecord,MassCombatEngine,CampaignSession


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.engine=MassCombatEngine()
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]))

    def test_deliberate_defense_first_round_or_siege(self):
        data=replace(self.data,defender_strategy='deliberate_defense')
        self.assertFalse(self.engine.calculate(data).valid)
        self.assertTrue(self.engine.calculate(replace(data,defender_defense_bonus=2)).valid)
        self.assertFalse(self.engine.calculate(replace(data,defender_defense_bonus=2,round_number=2)).valid)
        self.assertTrue(self.engine.calculate(replace(data,siege=True,round_number=2)).valid)

    def test_confused_and_rally(self):
        self.assertFalse(self.engine.calculate(replace(self.data,attacker_confused=True)).valid)
        self.assertFalse(self.engine.calculate(replace(self.data,attacker_strategy='rally')).valid)
        self.assertTrue(self.engine.calculate(replace(self.data,attacker_strategy='rally',attacker_confused=True)).valid)

    def test_mobile_encounter(self):
        data=replace(self.data,encounter_battle=True,attacker_mobile=True,defender_strategy='attack')
        for strategy in ('defense','all_out_defense','full_retreat','fighting_retreat'):
            self.assertFalse(self.engine.calculate(replace(data,attacker_strategy=strategy)).valid)
            self.assertTrue(self.engine.calculate(replace(data,attacker_strategy=strategy,round_number=2)).valid)
        self.assertTrue(self.engine.calculate(replace(data,attacker_strategy='mobile_defense')).valid)

    def test_round_persistence_undo_reset(self):
        s=CampaignSession()
        before=s.to_dict()
        s.apply_battle_round(self.data,self.engine.resolve(self.data,10,10),before)
        self.assertEqual(s.battle_round_number,2)
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).battle_round_number,2)
        s.finalize_battle({'a':5,'d':5})
        self.assertEqual(s.battle_round_number,1)
        s.undo()
        self.assertEqual(s.battle_round_number,2)
        s.undo()
        self.assertEqual(s.to_dict(),before)
