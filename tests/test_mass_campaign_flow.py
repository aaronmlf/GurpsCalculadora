"""Cross-module campaign regression: Raid -> retreat -> pursuit -> finalization."""
import unittest
from calculators.campaign import BattleInput,ForceRecord,ElementRecord,MassCombatEngine,CampaignSession
from calculators.battle_aftermath import AftermathInput,BattleAftermathEngine

class CampaignFlowTests(unittest.TestCase):
    def test_logistic_losses_flow_once_through_battle_and_recovery(self):
        a=ForceRecord('a','A',[ElementRecord('ae','A',100,['Inf'])],commander_strategy=14)
        d=ForceRecord('d','D',[ElementRecord('de','D',100,['Inf'])],commander_strategy=10)
        s=CampaignSession(forces={'a':a,'d':d},force_logistic_strengths={'a':{'land':100},'d':{'land':100}})
        engine=MassCombatEngine()
        first=BattleInput(a,d,attacker_strategy='raid',defender_strategy='attack',attacker_raid_logistics=True)
        s.apply_battle_round(first,engine.resolve(first,8,12),s.to_dict())
        prior_logistics=s.battle_logistic_casualties['d']
        self.assertGreater(prior_logistics,0)
        fields={}
        for side,key in (('attacker','a'),('defender','d')):
            fields.update({side+'_casualties':s.battle_casualties[key],side+'_position':s.battle_positions.get(key,0),
                side+'_indirect_uses':s.battle_strategy_state[key]['uses'],side+'_previous_strategy':s.battle_strategy_state[key]['previous']})
        second=BattleInput(s.forces['a'],s.forces['d'],attacker_strategy='attack',defender_strategy='full_retreat',round_number=2,**fields)
        result=engine.resolve(second,10,10)
        s.apply_battle_round(second,result,s.to_dict())
        self.assertEqual(s.battle_ended['victor'],'attacker')
        self.assertEqual(s.battle_logistic_casualties['d'],prior_logistics+result.state_delta.logistic_losses['d'])
        data=AftermathInput(s.battle_casualties['a'],s.battle_casualties['d'],100,100,'attacker',
            voluntary_retreat=True,leadership=12,leadership_roll=10,choice='pursue',logistic_roll=2,
            attacker_id='a',defender_id='d',defender_logistic_losses=s.battle_logistic_casualties['d'])
        final=BattleAftermathEngine().calculate(data)
        before=s.to_dict()
        s.finalize_aftermath(data,final,before)
        self.assertAlmostEqual(s.force_logistic_strengths['d']['land'],100-final.logistic_losses['defender'])
        self.assertEqual(s.forces['d'].troop_strength,final.remaining_ts['defender'])
        self.assertFalse(s.battle_ended)
        self.assertFalse(s.battle_casualties)
        s.undo()
        self.assertEqual(s.to_dict(),before)
