import unittest
from dataclasses import replace
from calculators.battle_end import battle_end
from calculators.campaign import BattleInput,ForceRecord,ElementRecord,MassCombatEngine,CampaignSession

class BattleEndTests(unittest.TestCase):
    def test_end_without_combat_preserves_losses_and_undo(self):
        from unittest.mock import patch
        data=replace(self.data,attacker_strategy='fighting_retreat',attacker_casualties=15,defender_casualties=10)
        s=CampaignSession()
        before=s.to_dict()
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            s.end_without_combat(data,before)
        self.assertEqual(s.battle_casualties,{'a':15,'d':10})
        self.assertEqual(s.forces['a'].troop_strength,100)
        self.assertEqual(s.battle_round_number,1)
        self.assertEqual(s.battle_ended['victor'],'defender')
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).to_dict(),s.to_dict())
        with self.assertRaises(ValueError):s.end_without_combat(data,s.to_dict())
        s.undo()
        self.assertEqual(s.to_dict(),before)

    def test_no_battle_disk_failure_atomic(self):
        from unittest.mock import patch
        data=replace(self.data,attacker_strategy='full_retreat')
        s=CampaignSession()
        before=s.to_dict()
        with patch.object(CampaignSession,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):s.end_without_combat(data,before)
        self.assertEqual(s.to_dict(),before)

    def setUp(self):
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]))

    def test_full_retreat_loses_even_if_round_won(self):
        data=replace(self.data,attacker_strategy='full_retreat',defender_strategy='attack')
        self.assertEqual(battle_end(data,20,0,0)['victor'],'defender')

    def test_fighting_retreat_escapes_only_on_win_or_tie(self):
        data=replace(self.data,attacker_strategy='fighting_retreat',defender_strategy='attack')
        self.assertEqual(battle_end(data,0,10,10)['victor'],'defender')
        self.assertFalse(battle_end(data,-1,10,10))

    def test_annihilation(self):
        self.assertEqual(battle_end(self.data,0,100,100)['victor'],'mutual')
        self.assertEqual(battle_end(self.data,0,0,100)['victor'],'attacker')

    def test_end_persists_and_prevents_new_round(self):
        data=replace(self.data,attacker_strategy='full_retreat',defender_strategy='attack')
        e=MassCombatEngine()
        result=e.resolve(data,10,10)
        s=CampaignSession()
        before=s.to_dict()
        s.apply_battle_round(data,result,before)
        self.assertEqual(s.battle_ended['victor'],'defender')
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).battle_ended,s.battle_ended)
        with self.assertRaises(ValueError):s.apply_battle_round(data,result,s.to_dict())
        s.undo()
        self.assertEqual(s.to_dict(),before)
