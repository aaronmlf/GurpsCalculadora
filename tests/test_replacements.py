import unittest
from dataclasses import replace
from unittest.mock import patch
from calculators.campaign import CampaignSession, ForceRecord, ElementRecord
from calculators.replacements import ReplacementOrder, start_replacement, advance_replacement


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.s=CampaignSession(forces={'a':ForceRecord('a','Army',[ElementRecord('e','Element',90,['Inf'])],resources=1000)})
        self.o=ReplacementOrder('a','e',100,1000,120,10)

    def test_published_proportional_cost_and_time(self):
        self.assertEqual((self.o.cost,self.o.days,self.o.strength),(100,12,10))

    def test_pay_once_complete_after_time_and_undo(self):
        before=self.s.to_dict()
        start_replacement(self.s,self.o,before)
        self.assertEqual(self.s.forces['a'].resources,900)
        self.assertEqual(self.s.forces['a'].troop_strength,90)
        self.assertFalse(advance_replacement(self.s,'a','e',11,self.s.to_dict()))
        saved=self.s.to_dict()
        self.s=CampaignSession.from_dict(saved)
        self.assertTrue(advance_replacement(self.s,'a','e',1,saved))
        self.assertEqual(self.s.forces['a'].troop_strength,100)
        self.assertEqual(self.s.forces['a'].resources,900)
        with self.assertRaises(ValueError):advance_replacement(self.s,'a','e',1,self.s.to_dict())
        self.s.undo()
        self.assertEqual(self.s.to_dict(),saved)

    def test_atomic_failure_and_duplicate(self):
        before=self.s.to_dict()
        with patch.object(CampaignSession,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):start_replacement(self.s,self.o,before)
        self.assertEqual(self.s.to_dict(),before)
        start_replacement(self.s,self.o,before)
        with self.assertRaises(ValueError):start_replacement(self.s,self.o,self.s.to_dict())
        saved=self.s.to_dict()
        with patch.object(CampaignSession,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):advance_replacement(self.s,'a','e',12,saved)
        self.assertEqual(self.s.to_dict(),saved)

    def test_invalid_and_over_replacement(self):
        for change in ({'percent':20},{'percent':0},{'full_days':float('nan')},{'elapsed_days':10},{'full_cost':20000}):
            with self.subTest(change=change),self.assertRaises(ValueError):start_replacement(self.s,replace(self.o,**change),self.s.to_dict())

    def test_zero_survivors_and_reduced_readiness(self):
        self.s.forces['a'].elements[0].troop_strength=0
        self.s.forces['a'].readiness_multiplier=.5
        start_replacement(self.s,self.o,self.s.to_dict())
        advance_replacement(self.s,'a','e',12,self.s.to_dict())
        self.assertEqual(self.s.forces['a'].troop_strength,5)

    def test_corrupt_order_rejected(self):
        start_replacement(self.s,self.o,self.s.to_dict())
        raw=self.s.to_dict()
        raw['replacement_orders'][0]['percent']=-1
        with self.assertRaises(ValueError):CampaignSession.from_dict(raw)

    def test_active_battle_rejected(self):
        self.s.battle_casualties={'a':10}
        with self.assertRaises(ValueError):start_replacement(self.s,self.o,self.s.to_dict())
