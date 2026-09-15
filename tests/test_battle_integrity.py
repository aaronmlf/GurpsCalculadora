import unittest
from copy import deepcopy
from unittest.mock import patch
from calculators.campaign import BattleInput,ForceRecord,ElementRecord,MassCombatEngine,CampaignSession


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('a','A',100,['Inf'])]),
            ForceRecord('d','D',[ElementRecord('d','D',100,['Inf'])]),siege=True,defender_defense_bonus=4)
        self.result=MassCombatEngine().resolve(self.data,10,10)

    def test_apply_rechecks_without_rolling(self):
        s=CampaignSession()
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
            s.apply_battle_round(self.data,self.result,s.to_dict())
        self.assertEqual(s.battle_settings,{'siege':True,'attacker_db':0,'defender_db':4})
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).battle_settings,s.battle_settings)

    def test_forged_delta_rejected_atomically(self):
        for key in ('force_losses','logistic_losses','battle_positions'):
            s=CampaignSession()
            before=s.to_dict()
            result=deepcopy(self.result)
            getattr(result.state_delta,key)['a']=99
            with patch('calculators.campaign.roll_3d6',side_effect=AssertionError):
                with self.assertRaises(ValueError):s.apply_battle_round(self.data,result,before)
            self.assertEqual(s.to_dict(),before)

    def test_bad_settings_do_not_load(self):
        raw=CampaignSession().to_dict()
        raw['battle_settings']={'siege':True,'attacker_db':-1,'defender_db':0}
        with self.assertRaises(ValueError):CampaignSession.from_dict(raw)

    def test_explicit_context_change_no_round_and_undo(self):
        s=CampaignSession()
        s.apply_battle_round(self.data,self.result,s.to_dict())
        before=s.to_dict()
        conditions=deepcopy(s.battle_conditions)
        conditions['a']['confused']=True
        s.update_battle_context(conditions,s.battle_settings,False,before)
        self.assertTrue(s.battle_conditions['a']['confused'])
        self.assertEqual(s.battle_round_number,2)
        self.assertEqual(s.battle_casualties,before['battle_casualties'])
        s.undo()
        self.assertEqual(s.to_dict(),before)
