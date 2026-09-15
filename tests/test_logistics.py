from dataclasses import replace
import unittest
from unittest.mock import patch
from calculators.logistics import LogisticsEngine, LogisticsInput, SupplyGroup


class LogisticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = LogisticsEngine()
        self.data = LogisticsInput(groups=[SupplyGroup('army',100000)], strengths={'land':100},
                                   funds=1000000, administration_roll=10)

    def test_published_land_and_naval_example(self):
        result = self.engine.calculate(LogisticsInput(groups=[SupplyGroup('army',5500000)],
            strengths={'land':5500,'naval':5500}, naval_base=True, inland_sea_supply=True,
            funds=20000000, administration_roll=10))
        self.assertTrue(result.complete)
        self.assertEqual(result.raise_costs, {'land':27500000,'naval':55000000,'air':0})
        self.assertEqual(result.logistic_costs, {'land':2750000,'naval':5500000,'air':0})
        self.assertEqual(result.total_cost,13750000)

    def test_administration_outcomes(self):
        for skill, roll, factor in ((10,3,.85),(15,10,.9),(10,10,1),(10,11,1.1),(10,18,1.15)):
            r=self.engine.calculate(replace(self.data, administration=skill,administration_roll=roll))
            self.assertAlmostEqual(r.administration_factor,factor)
            self.assertAlmostEqual(r.total_cost,150000*factor)

    def test_calculate_is_pending_without_dice(self):
        with patch('calculators.logistics.roll_3d6',side_effect=AssertionError):
            r=self.engine.calculate(replace(self.data,administration_roll=None))
        self.assertFalse(r.complete)
        self.assertEqual(r.pending,['administration_roll'])

    def test_resolve_uses_explicit_roll_and_rejects_invalid(self):
        with patch('calculators.logistics.roll_3d6',side_effect=AssertionError):
            self.assertTrue(self.engine.resolve(self.data).complete)
            with self.assertRaises(ValueError):self.engine.resolve(replace(self.data,administration_roll=0))

    def test_supply_routes_and_shared_naval_capacity(self):
        both = replace(self.data, groups=[SupplyGroup('army',100000),SupplyGroup('navy',100000,'naval')],
                       strengths={'naval':150}, naval_base=True, land_via_port=True)
        self.assertEqual(self.engine.calculate(both).capacity_shortfall,50)
        self.assertEqual(self.engine.calculate(replace(both,airbase=True,strengths={'naval':150,'air':50})).capacity_shortfall,0)
        self.assertEqual(self.engine.calculate(replace(self.data,land_supply_line=False)).capacity_shortfall,100)
        sea = replace(self.data,inland_sea_supply=True,naval_base=True,strengths={'land':100,'naval':40})
        self.assertEqual(self.engine.calculate(sea).capacity_shortfall,60)

    def test_air_requires_airbase(self):
        data=replace(self.data,strengths={'air':100},land_supply_line=False)
        self.assertEqual(self.engine.calculate(data).capacity_shortfall,100)
        self.assertTrue(self.engine.calculate(replace(data,airbase=True)).complete)

    def test_low_readiness_and_one_month_recovery(self):
        for readiness, recovering, cost, multiplier, next_recovery, losses in (
            ('low',False,50000,.5,True,0),('none',False,0,.5,True,5),
            ('full',True,100000,.5,False,0),('full',False,100000,1,False,0)):
            r=self.engine.calculate(replace(self.data,groups=[SupplyGroup('army',100000,readiness=readiness,recovering=recovering)]))
            self.assertEqual(r.group_costs['army'],cost)
            self.assertEqual(r.effects['army'],{'ts_multiplier':multiplier,'casualties':losses,'recovering_next_month':next_recovery})

    def test_terrain_features_and_transport(self):
        for terrain, feature, network, factor in (('woodlands',False,False,1.5),('woodlands',True,False,1),
            ('desert',False,False,2),('desert',True,False,1.5),('desert',False,True,1)):
            r=self.engine.calculate(replace(self.data,groups=[SupplyGroup('army',100000,terrain=terrain,
                terrain_feature=feature,transport_network=network)]))
            self.assertEqual(r.group_costs['army'],100000*factor)

    def test_season_only_low_tech_land_air_and_rural(self):
        data=replace(self.data,campaign_season=True,rural=True,logistic_tl={'land':5},
            groups=[SupplyGroup('army',100000,tl=5)])
        self.assertEqual(self.engine.calculate(data).total_cost,75000)
        self.assertEqual(self.engine.calculate(replace(data,rural=False)).total_cost,150000)
        naval=replace(data,groups=[SupplyGroup('navy',100000,'naval',tl=5)],
                      strengths={'naval':100},logistic_tl={'naval':5},naval_base=True)
        self.assertEqual(self.engine.calculate(naval).total_cost,200000)

    def test_logistics_paid_first_and_no_silent_readiness_change(self):
        r=self.engine.calculate(replace(self.data,funds=40000))
        self.assertEqual(r.logistic_funding_shortfall,10000)
        self.assertEqual(r.combat_funding_shortfall,100000)
        self.assertFalse(r.complete)
        self.assertEqual(r.effects['army']['ts_multiplier'],1)

    def test_replacement_cost_and_time_proportional(self):
        r=self.engine.calculate(replace(self.data,replacement_raise_cost=1000000,replacement_raise_days=120,replacement_percent=10))
        self.assertEqual(r.replacement_cost,100000)
        self.assertEqual(r.replacement_days,12)

    def test_bad_inputs(self):
        for changes in ({'funds':float('nan')},{'strengths':{'space':1}}, {'strengths':{'land':True}},
                        {'groups':[SupplyGroup('a',-1)]},{'replacement_percent':101},
                        {'groups':[SupplyGroup('a',1),SupplyGroup('a',2)]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.engine.calculate(replace(self.data,**changes))

    def test_monthly_campaign_application_and_recovery(self):
        from calculators.campaign import CampaignSession, ForceRecord, ElementRecord
        session = CampaignSession(forces={'army':ForceRecord('army','Army',
            [ElementRecord('a','A',100,['Inf'])],resources=1000000)},
            force_logistic_strengths={'army':{'land':100}})
        before=session.to_dict()
        data=replace(self.data,groups=[SupplyGroup('army',100000,readiness='none')])
        result=self.engine.calculate(data)
        with patch.object(CampaignSession,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):session.apply_maintenance(data,result,before)
        self.assertEqual(session.to_dict(),before)
        session.apply_maintenance(data,result,before)
        force=session.forces['army']
        self.assertEqual(force.base_troop_strength,95)
        self.assertEqual(force.troop_strength,47.5)
        self.assertEqual(force.resources,950000)
        self.assertEqual(force.maintenance_month,1)
        with self.assertRaises(ValueError):session.apply_maintenance(data,result,before)
        self.assertEqual(CampaignSession.from_dict(session.to_dict()).to_dict(),session.to_dict())
        # First month of full maintenance still operates at half TS.
        data=replace(self.data,funds=950000,groups=[SupplyGroup('army',100000,recovering=True)])
        session.apply_maintenance(data,self.engine.calculate(data),session.to_dict())
        self.assertEqual(session.forces['army'].troop_strength,47.5)
        data=replace(self.data,funds=800000)
        session.apply_maintenance(data,self.engine.calculate(data),session.to_dict())
        self.assertEqual(session.forces['army'].troop_strength,95)
        for _ in range(3):session.undo()
        self.assertEqual(session.to_dict(),before)

    def test_active_battle_maintenance_is_rejected(self):
        from calculators.campaign import CampaignSession, ForceRecord, ElementRecord
        session=CampaignSession(forces={'army':ForceRecord('army','Army',[ElementRecord('a','A',100,['Inf'])])},
                                battle_casualties={'army':10})
        before=session.to_dict()
        with self.assertRaises(ValueError):session.apply_maintenance(self.data,self.engine.calculate(self.data),before)
        self.assertEqual(session.to_dict(),before)

    def test_configuration_persists_validated_plan_atomically(self):
        from calculators.campaign import CampaignSession, ForceRecord, ElementRecord
        force=ForceRecord('army','Army',[ElementRecord('a','A',100,['Inf'])])
        session=CampaignSession()
        before=session.to_dict()
        with patch.object(CampaignSession,'save',side_effect=OSError('disk')):
            with self.assertRaises(OSError):session.configure_logistics(force,self.data,before)
        self.assertEqual(session.to_dict(),before)
        session.configure_logistics(force,self.data,before)
        stored=session.to_dict()
        self.assertEqual(CampaignSession.from_dict(stored).to_dict(),stored)
        self.assertEqual(session.forces['army'].resources,1000000)
        self.assertEqual(session.forces['army'].troop_strength,100)
        stored['logistics_plans']['army']['groups'][0]['monthly_cost']=-1
        with self.assertRaises(ValueError):CampaignSession.from_dict(stored)
        session.undo()
        self.assertEqual(session.to_dict(),before)
