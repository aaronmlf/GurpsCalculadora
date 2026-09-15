import unittest
from dataclasses import replace
from unittest.mock import patch
from calculators.campaign import (ForceRecord, ElementRecord, BattleInput, MassCombatEngine,
                                  CampaignSession, CampaignStateDelta)


class MassCombatAuditTests(unittest.TestCase):
    def test_noncombat_strategies_never_roll_or_change_session(self):
        engine = MassCombatEngine()
        pairs = [('parley', 'parley', 'parley')]
        defenses = ('defense', 'all_out_defense', 'deliberate_defense', 'mobile_defense', 'rally')
        retreats = ('full_retreat', 'fighting_retreat')
        pairs += [(a, d, 'no_battle') for a in retreats for d in retreats + defenses]
        pairs += [(a, d, 'no_battle') for a in defenses for d in retreats]
        for a, d, event in pairs:
            with self.subTest(a=a, d=d):
                data = replace(self.data(), attacker_strategy=a, defender_strategy=d,
                               attacker_position=2, attacker_casualties=15,
                               attacker_confused=a=='rally',defender_confused=d=='rally',
                               attacker_defense_bonus=1 if a=='deliberate_defense' else 0,
                               defender_defense_bonus=1 if d=='deliberate_defense' else 0)
                session = CampaignSession()
                snapshot = session.to_dict()
                with patch('calculators.campaign.roll_3d6', side_effect=AssertionError('rolled')):
                    self.assertEqual(engine.calculate(data).event, event)
                    result = engine.resolve(data)
                self.assertTrue(result.valid)
                self.assertEqual(result.outcome, event)
                self.assertEqual((result.attacker_result, result.defender_result), ({}, {}))
                self.assertEqual((result.attacker_casualty_percent, result.defender_casualty_percent), (0, 0))
                self.assertEqual(result.state_delta, CampaignStateDelta())
                with self.assertRaises(ValueError):
                    session.apply_battle_round(data, result, snapshot)
                self.assertEqual(session.to_dict(), snapshot)

    def test_unanswered_parley_is_not_resolved_as_an_attack(self):
        for a, d in [('parley', 'attack'), ('attack', 'parley'), ('parley', 'full_retreat')]:
            with patch('calculators.campaign.roll_3d6', side_effect=AssertionError('rolled')):
                result = MassCombatEngine().resolve(replace(self.data(), attacker_strategy=a, defender_strategy=d))
            self.assertFalse(result.valid)
            self.assertIn('battle_parley_decision_required', result.errors)
            self.assertEqual(result.state_delta, CampaignStateDelta())

    def test_round_commit_is_one_step_and_rejects_replay(self):
        session = CampaignSession()
        data = self.data()
        result = MassCombatEngine().resolve(data, attacker_roll=10, defender_roll=10)
        snapshot = session.to_dict()
        session.apply_battle_round(data, result, snapshot)
        self.assertEqual(len(session.history), 1)
        self.assertEqual(session.forces['a'].troop_strength, 100)
        with self.assertRaises(ValueError):
            session.apply_battle_round(data, result, snapshot)
        session.undo()
        self.assertEqual(session.to_dict(), snapshot)

    def test_round_disk_failure_preserves_state(self):
        session = CampaignSession()
        data = self.data()
        result = MassCombatEngine().resolve(data, attacker_roll=10, defender_roll=10)
        snapshot = session.to_dict()
        with patch.object(CampaignSession, 'save', side_effect=OSError('disk')):
            with self.assertRaises(OSError): session.apply_battle_round(data, result, snapshot)
        self.assertEqual(session.to_dict(), snapshot)

    def data(self):
        return BattleInput(ForceRecord('a','A',[ElementRecord('ae','A',100,['Inf'])],commander_strategy=12),
                           ForceRecord('d','D',[ElementRecord('de','D',100,['Inf'])],commander_strategy=12))

    def test_calculate_never_rolls_and_keeps_starting_ts(self):
        data = replace(self.data(), attacker_casualties=15, defender_casualties=10)
        with patch('calculators.campaign.roll_3d6', side_effect=AssertionError('rolled')):
            result = MassCombatEngine().calculate(data)
        self.assertEqual((result.attacker_ts,result.defender_ts),(100,100))
        self.assertEqual((result.attacker_target,result.defender_target),(9,11))

    def test_round_losses_are_additive_until_finalization(self):
        data=self.data()
        session=CampaignSession(forces={'a':data.attacker,'d':data.defender})
        session.apply(CampaignStateDelta(force_losses={'a':10,'d':15},battle_round=True))
        session.apply(CampaignStateDelta(force_losses={'a':5,'d':10},battle_round=True))
        self.assertEqual(session.battle_casualties,{'a':15,'d':25})
        self.assertEqual(session.forces['a'].troop_strength,100)
        restored=CampaignSession.from_dict(session.to_dict())
        self.assertEqual(restored.battle_casualties,session.battle_casualties)
        session.finalize_battle({'a':5,'d':25})  # GM-confirmed recovery/pursuit.
        self.assertEqual(session.forces['a'].troop_strength,95)
        self.assertFalse(session.battle_casualties)
        session.undo()
        self.assertEqual(session.forces['a'].troop_strength,100)
        self.assertEqual(session.battle_casualties['a'],15)

    def test_invalid_battle_does_not_roll_or_produce_delta(self):
        data=replace(self.data(),attacker_casualties=100)
        with patch('calculators.campaign.roll_3d6',side_effect=AssertionError('rolled')):
            result=MassCombatEngine().resolve(data)
        self.assertFalse(result.valid)
        self.assertFalse(result.state_delta.force_losses)

    def test_all_out_attack_works_on_either_side(self):
        data=replace(self.data(),attacker_strategy='all_out_attack',defender_strategy='all_out_attack')
        result=MassCombatEngine().resolve(data,attacker_roll=12,defender_roll=10)
        self.assertEqual(result.attacker_casualty_percent,35)
        self.assertEqual(result.defender_casualty_percent,20)
        self.assertEqual(result.state_delta.morale_changes,{})

    def test_invalid_explicit_roll_not_replaced_by_random_roll(self):
        with self.assertRaises(ValueError): MassCombatEngine().resolve(self.data(),attacker_roll=0,defender_roll=10)

    def test_result_table_boundaries(self):
        for margin, expected in ((0,(10,10,0)),(3,(15,10,1)),(4,(20,10,2)),(9,(25,5,2)),
                                 (10,(30,5,3)),(19,(35,0,3)),(20,(40,0,4))):
            self.assertEqual(MassCombatEngine._combat_results(margin),expected)
