from dataclasses import replace
import unittest
from calculators.campaign import BattleInput, ForceRecord, ElementRecord, MassCombatEngine, CampaignSession


class StrategyHistoryTests(unittest.TestCase):
    def test_desperate_threshold_and_forbidden_strategies(self):
        for losses,valid in ((24.99,False),(25,True),(30,True)):
            data=replace(self.data,attacker_strategy='attack',attacker_desperate=True,attacker_casualties=losses)
            self.assertEqual(self.engine.calculate(data).valid,valid)
        for strategy in ('deliberate_attack','deliberate_defense','skirmish'):
            self.assertFalse(self.engine.calculate(replace(self.data,attacker_strategy=strategy,
                attacker_desperate=True,attacker_casualties=30)).valid)

    def test_desperate_bonus_and_automatic_losses(self):
        base=replace(self.data,attacker_strategy='attack',attacker_casualties=25)
        data=replace(base,attacker_desperate=True)
        self.assertEqual(self.engine.calculate(data).attacker_target-self.engine.calculate(base).attacker_target,4)
        # Offset the +4 with explicit rolls to compare the same contest margin.
        normal=self.engine.resolve(base,8,10)
        desperate=self.engine.resolve(data,12,10)
        self.assertEqual(normal.margin,desperate.margin)
        self.assertEqual(desperate.attacker_casualty_percent,normal.attacker_casualty_percent+10)
        self.assertEqual(next(x for x in desperate.breakdown if x['key']=='desperate_misfortune')['attacker'],1)

    def test_desperate_losses_not_redirected_by_enemy_raid(self):
        data=replace(self.data,attacker_strategy='raid',attacker_raid_logistics=True,
            defender_desperate=True,defender_casualties=25)
        result=self.engine.resolve(data,3,18)
        self.assertGreater(result.margin,0)
        self.assertEqual(result.defender_casualty_percent,10)
        self.assertGreater(result.state_delta.logistic_losses['d'],0)

    def setUp(self):
        self.engine=MassCombatEngine()
        self.data=BattleInput(ForceRecord('a','A',[ElementRecord('ae','A',100,['Inf'])],commander_strategy=16),
            ForceRecord('d','D',[ElementRecord('de','D',100,['Inf'])],commander_strategy=10),
            attacker_strategy='indirect_attack',defender_strategy='attack')

    def test_first_and_repeated_margin_round_up(self):
        self.assertEqual(self.engine.resolve(self.data,10,10).margin,6)
        data=replace(self.data,attacker_indirect_uses=1,attacker_previous_strategy='attack')
        self.assertEqual(self.engine.resolve(data,10,10).margin,5)
        data=replace(data,attacker_previous_strategy='indirect_attack')
        self.assertEqual(self.engine.resolve(data,10,10).margin,2)

    def test_negative_winning_margin_rounds_away_from_zero(self):
        data=BattleInput(self.data.defender,self.data.attacker,defender_strategy='indirect_attack',
            defender_indirect_uses=1,defender_previous_strategy='attack')
        self.assertEqual(self.engine.resolve(data,10,10).margin,-5)

    def test_history_saved_only_on_apply_then_undo(self):
        s=CampaignSession()
        before=s.to_dict()
        result=self.engine.resolve(self.data,10,10)
        self.assertFalse(s.battle_strategy_state)
        s.apply_battle_round(self.data,result,before)
        self.assertEqual(s.battle_strategy_state['a'],{'uses':1,'previous':'indirect_attack'})
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).to_dict(),s.to_dict())
        s.undo()
        self.assertEqual(s.to_dict(),before)

    def test_history_cannot_be_omitted_after_applied_round(self):
        s=CampaignSession()
        s.apply_battle_round(self.data,self.engine.resolve(self.data,10,10),s.to_dict())
        data=replace(self.data,attacker_casualties=s.battle_casualties['a'],defender_casualties=s.battle_casualties['d'],
            attacker_position=s.battle_positions.get('a',0),defender_position=s.battle_positions.get('d',0))
        before=s.to_dict()
        with self.assertRaises(ValueError):s.apply_battle_round(data,self.engine.resolve(data,10,10),before)
        self.assertEqual(s.to_dict(),before)

    def test_bad_history_is_invalid(self):
        for kwargs in ({'attacker_indirect_uses':-1},{'attacker_indirect_uses':True},
                       {'attacker_previous_strategy':'indirect_attack'},{'attacker_previous_strategy':'unknown'}):
            self.assertFalse(self.engine.calculate(replace(self.data,**kwargs)).valid)

    def test_finalization_clears_history(self):
        s=CampaignSession()
        s.apply_battle_round(self.data,self.engine.resolve(self.data,10,10),s.to_dict())
        s.finalize_battle({'a':0,'d':20})
        self.assertFalse(s.battle_strategy_state)
        s.undo()
        self.assertEqual(s.battle_strategy_state['a']['uses'],1)

    def test_raid_superiority_stacks_per_class_plus_recon(self):
        data=replace(self.data,attacker_strategy='raid',attacker_recon_superiority=True,
            attacker_classes={'Air':[5,0],'Cav':[5,0],'Nav':[5,0]})
        result=self.engine.calculate(data)
        bonus=next(x for x in result.breakdown if x['key']=='strategy_superiority')
        self.assertEqual(bonus['attacker'],4)

    def test_raid_can_redirect_losses_and_persist_logistics(self):
        data=replace(self.data,attacker_strategy='raid',attacker_raid_logistics=True)
        result=self.engine.resolve(data,10,10)
        self.assertEqual(result.defender_casualty_percent,0)
        self.assertEqual(result.state_delta.logistic_losses,{'d':20})
        s=CampaignSession()
        before=s.to_dict()
        s.apply_battle_round(data,result,before)
        self.assertEqual(s.battle_logistic_casualties,{'d':20})
        self.assertEqual(s.battle_casualties['d'],0)
        self.assertEqual(CampaignSession.from_dict(s.to_dict()).battle_logistic_casualties,{'d':20})
        s.undo()
        self.assertEqual(s.to_dict(),before)

    def test_retreat_losses_include_logistics_without_doubling(self):
        for strategy in ('full_retreat','fighting_retreat'):
            data=replace(self.data,attacker_strategy='attack',defender_strategy=strategy)
            result=self.engine.resolve(data,5,15)
            self.assertEqual(result.state_delta.logistic_losses['d'],result.defender_casualty_percent)

    def test_losing_raid_does_not_redirect(self):
        data=replace(self.data,attacker_strategy='raid',attacker_raid_logistics=True)
        result=self.engine.resolve(data,18,3)
        self.assertFalse(result.state_delta.logistic_losses)
        self.assertGreater(result.defender_casualty_percent,0)
