import unittest
from dataclasses import replace
from unittest.mock import patch
from calculators.battle_aftermath import AftermathInput, BattleAftermathEngine


class AftermathTests(unittest.TestCase):
    def setUp(self):
        self.engine = BattleAftermathEngine()
        self.data = AftermathInput(35, 60, 75.5, 100, 'attacker')

    def test_book_recovery_example(self):
        result = self.engine.calculate(replace(self.data, defender_casualties=100))
        self.assertEqual(result.final_casualties, {'attacker': 15, 'defender': 100})
        self.assertEqual(result.remaining_ts, {'attacker': 64, 'defender': 0})
        self.assertEqual(result.logistic_losses['defender'], 100)

    def test_mutual_annihilation_recovers_both_not_logistics(self):
        result = self.engine.calculate(replace(self.data, attacker_casualties=100, defender_casualties=100, victor='mutual'))
        self.assertEqual(result.final_casualties, {'attacker':50, 'defender':50})
        self.assertEqual(result.logistic_losses, {'attacker':100, 'defender':100})

    def test_hold_reduces_before_halving(self):
        data = replace(self.data, attacker_casualties=30, voluntary_retreat=True, leadership_roll=8)
        result = self.engine.calculate(data)
        self.assertEqual(result.action, 'hold')
        self.assertEqual(result.final_casualties['attacker'], 10)
        self.assertEqual(result.final_casualties['defender'], 60)

    def test_pursuit_and_both_superiorities(self):
        data = replace(self.data, voluntary_retreat=True, leadership_roll=8, choice='pursue',
                       cavalry_superiority=True, air_superiority=True, logistic_roll=4,
                       defender_logistic_losses=10)
        result = self.engine.calculate(data)
        self.assertEqual(result.final_casualties, {'attacker':15, 'defender':75})
        self.assertEqual(result.logistic_losses['defender'], 30)

    def test_failed_leadership_uses_random_reaction(self):
        data = replace(self.data, voluntary_retreat=True, leadership_roll=18, logistic_roll=1)
        for roll in range(1,7):
            result = self.engine.calculate(replace(data, reaction_roll=roll))
            self.assertEqual(result.action, 'pursue' if roll <= 3 else 'hold')

    def test_pending_has_no_applicable_losses_and_calculate_never_rolls(self):
        with patch('calculators.battle_aftermath.roll_3d6', side_effect=AssertionError):
            result = self.engine.calculate(replace(self.data, voluntary_retreat=True))
        self.assertFalse(result.complete)
        self.assertEqual(result.pending, ['leadership_roll'])
        self.assertFalse(result.final_casualties)

    def test_resolve_only_rolls_necessary_dice(self):
        with patch('calculators.battle_aftermath.roll_3d6', return_value=(18, [])) as leadership, \
             patch('calculators.battle_aftermath.roll_1d6', side_effect=[2, 6]) as dice:
            result = self.engine.resolve(replace(self.data, voluntary_retreat=True))
        self.assertTrue(result.complete)
        self.assertEqual(result.rolls, {'leadership':18, 'reaction':2, 'logistics':6})
        self.assertEqual(dice.call_count, 2)
        leadership.assert_called_once()

    def test_invalid_inputs_do_not_roll(self):
        for changes in ({'leadership_roll':0}, {'logistic_roll':7}, {'attacker_casualties':float('nan')},
                        {'victor':'mutual'}, {'attacker_casualties':100}, {'voluntary_retreat':1}):
            with self.subTest(changes=changes), patch('calculators.battle_aftermath.roll_3d6', side_effect=AssertionError):
                with self.assertRaises(ValueError): self.engine.resolve(replace(self.data, **changes))

    def test_pursuit_destruction_overruns_rear(self):
        result = self.engine.calculate(replace(self.data, defender_casualties=95, voluntary_retreat=True,
            leadership_roll=8, choice='pursue', logistic_roll=1))
        self.assertEqual(result.logistic_losses['defender'], 100)

    def test_swap_sides(self):
        result = self.engine.calculate(AftermathInput(60, 35, 100, 75.5, 'defender'))
        self.assertEqual(result.final_casualties, {'attacker':60, 'defender':15})
        self.assertEqual(result.remaining_ts['defender'], 64)

    def test_session_atomic_finalize_persist_undo_and_replay(self):
        from calculators.campaign import CampaignSession, ForceRecord, ElementRecord
        session = CampaignSession(forces={
            'a': ForceRecord('a', 'A', [ElementRecord('ae','A',75.5,['Inf'])]),
            'd': ForceRecord('d', 'D', [ElementRecord('de','D',100,['Inf'])])},
            battle_casualties={'a':35,'d':60},
            force_logistic_strengths={'d':{'land':200}}, battle_logistic_casualties={'d':10})
        data = replace(self.data, attacker_id='a', defender_id='d', voluntary_retreat=True,
            leadership_roll=8, choice='pursue', logistic_roll=4, defender_logistic_losses=10)
        result = self.engine.calculate(data)
        before = session.to_dict()
        with patch.object(CampaignSession, 'save', side_effect=OSError('disk')):
            with self.assertRaises(OSError): session.finalize_aftermath(data,result,before)
        self.assertEqual(session.to_dict(), before)
        session.finalize_aftermath(data,result,before)
        self.assertEqual(session.forces['a'].troop_strength,64)
        self.assertEqual(session.forces['d'].troop_strength,35)
        self.assertEqual(session.force_logistic_strengths['d']['land'],140)
        self.assertFalse(session.battle_casualties)
        self.assertFalse(session.battle_logistic_casualties)
        self.assertEqual(CampaignSession.from_dict(session.to_dict()).to_dict(),session.to_dict())
        with self.assertRaises(ValueError): session.finalize_aftermath(data,result,before)
        session.undo()
        self.assertEqual(session.to_dict(),before)

    def test_corrupt_logistics_rejected_and_legacy_defaults(self):
        from calculators.campaign import CampaignSession
        raw = CampaignSession().to_dict()
        raw.pop('force_logistic_strengths')
        raw.pop('battle_logistic_casualties')
        self.assertEqual(CampaignSession.from_dict(raw).force_logistic_strengths,{})
        for value in ({'unknown':{'land':1}}, {'unknown':{'land':float('nan')}}, []):
            with self.assertRaises(ValueError):
                CampaignSession.from_dict({**raw,'force_logistic_strengths':value})
