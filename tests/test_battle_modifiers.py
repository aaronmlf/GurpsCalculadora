import unittest
from calculators.battle_modifiers import class_superiority, position_after_round
from calculators.campaign import CampaignSession, BattleInput, ForceRecord, ElementRecord, MassCombatEngine


class BattleModifierTests(unittest.TestCase):
    def test_strategy_superiority_is_a_single_adjustment(self):
        engine = MassCombatEngine()
        for strategy, classes in (
            ('deliberate_attack', ('Art',)), ('indirect_attack', ('C3I',)),
            ('deliberate_defense', ('F',)), ('mobile_defense', ('Cav', 'Nav')),
            ('skirmish', ('Air', 'Art', 'F'))):
            with self.subTest(strategy=strategy):
                self.assertEqual(engine._strategy_superiority_bonus(strategy, {}), 0)
                self.assertEqual(engine._strategy_superiority_bonus(strategy, {k: 0 for k in classes}), 0)
                self.assertEqual(engine._strategy_superiority_bonus(strategy, {k: 3 for k in classes}), 1)
                self.assertEqual(engine._strategy_superiority_bonus(strategy, {'Arm': 3}), 0)

    def test_strategy_adjustment_is_symmetric_and_explained(self):
        from dataclasses import replace
        engine = MassCombatEngine()
        a = ForceRecord('a', 'A', [ElementRecord('ae', 'A', 100, ['Inf'])])
        d = ForceRecord('d', 'D', [ElementRecord('de', 'D', 100, ['Inf'])])
        for side in ('attacker', 'defender'):
            for strategy, cls in [('deliberate_attack','Art'), ('indirect_attack','C3I'),
                                  ('deliberate_defense','F'), ('mobile_defense','Cav'), ('skirmish','Air')]:
                base = replace(BattleInput(a, d, attacker_strategy='attack', defender_strategy='attack'),
                               **{side + '_strategy': strategy})
                data = replace(base, **{side + '_classes': {cls: [5, 0]}})
                before, result = engine.calculate(base), engine.calculate(data)
                self.assertEqual(getattr(result, side + '_target') - getattr(before, side + '_target'), 4)
                entry = next(x for x in result.breakdown if x['key'] == 'strategy_superiority')
                self.assertEqual(entry[side], 1)
                resolved = engine.resolve(data, attacker_roll=10, defender_roll=10)
                self.assertIn(entry, resolved.breakdown)

    def test_encounter_can_remove_strategy_superiority(self):
        engine = MassCombatEngine()
        a = ForceRecord('a', 'A', [ElementRecord('ae', 'A', 100, ['Inf'])])
        d = ForceRecord('d', 'D', [ElementRecord('de', 'D', 100, ['Inf'])])
        result = engine.calculate(BattleInput(a, d, attacker_strategy='indirect_attack',
            attacker_classes={'C3I':[2,0]}, defender_classes={'C3I':[1,0]}, encounter_battle=True))
        self.assertEqual(next(x for x in result.breakdown if x['key']=='strategy_superiority')['attacker'], 0)

    def test_invalid_class_values_are_rejected(self):
        for value in ({'Unknown':[1,0]}, {'F':[float('nan'),0]}, {'F':[-1,0]}, {'F':[True,0]}):
            with self.assertRaises(ValueError): class_superiority(value,{},100,100)

    def test_pb_special_strategy_adjustments(self):
        self.assertEqual(position_after_round(0,3,'attack','all_out_defense',5,2), (0,2))
        self.assertEqual(position_after_round(0,0,'defense','mobile_defense',0,0), (1,0))
        self.assertEqual(position_after_round(0,0,'defense','fighting_retreat',5,2), (1,0))

    def test_class_thresholds(self):
        for amount, expected in ((1.99, 0), (2, 1), (3, 2), (4.99, 2), (5, 3)):
            a, d = class_superiority({'F': [amount, 0]}, {'F': [1, 0]}, 100, 100)
            self.assertEqual(a['F'], expected)
            self.assertEqual(d['F'], 0)

    def test_neutralizers_only_deny_and_minimum_one_percent(self):
        a,d = class_superiority({'Air': [5,0]}, {'Air': [0,4]}, 100, 100)
        self.assertEqual((a['Air'],d['Air']), (0,0))
        a,d = class_superiority({'F': [.99,0]}, {}, 100,100)
        self.assertEqual(a['F'],0)
        a,d = class_superiority({'F': [1,0]}, {}, 100,100)
        self.assertEqual(a['F'],3)

    def test_encounter_reduction_and_cumulative_classes(self):
        a,d = class_superiority({'Air':[10,0], 'F':[10,0]}, {}, 100,100,True)
        self.assertEqual(a, {'Air':2,'F':3})

    def test_pb_transfer_example_page_37_and_raid(self):
        self.assertEqual(position_after_round(0,1,'attack','defense',5,2), (1,0))
        self.assertEqual(position_after_round(1,0,'attack','defense',5,2), (3,0))
        self.assertEqual(position_after_round(0,1,'raid','defense',5,2), (0,0))
        self.assertEqual(position_after_round(0,1,'defense','attack',5,2), (0,1))

    def test_position_persists_rounds_and_undo(self):
        a=ForceRecord('a','A',[ElementRecord('ae','A',100,['Inf'])])
        d=ForceRecord('d','D',[ElementRecord('de','D',100,['Inf'])])
        data=BattleInput(a,d,attacker_classes={'F':[5,0]})
        result=MassCombatEngine().resolve(data,attacker_roll=8,defender_roll=12)
        session=CampaignSession()
        before=session.to_dict()
        session.apply_battle_round(data,result,before)
        self.assertGreater(session.battle_positions['a'],0)
        restored=CampaignSession.from_dict(session.to_dict())
        self.assertEqual(restored.to_dict(),session.to_dict())
        self.assertEqual(restored.battle_class_strengths['a'],{'F':[5,0]})
        session.undo()
        self.assertEqual(session.to_dict(),before)

    def test_two_defenses_become_skirmish(self):
        a=ForceRecord('a','A',[ElementRecord('ae','A',100,['Inf'])])
        d=ForceRecord('d','D',[ElementRecord('de','D',100,['Inf'])])
        data=BattleInput(a,d,attacker_strategy='defense',defender_strategy='defense')
        result=MassCombatEngine().resolve(data,attacker_roll=10,defender_roll=10)
        self.assertEqual(result.attacker_casualty_percent,5)
        self.assertEqual(result.state_delta.battle_positions,{'a':0,'d':0})
