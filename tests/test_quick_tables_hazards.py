import unittest
from unittest.mock import patch

from utils.quick_tables_hazards import CARDS


BY_KEY = {card.key: card for card in CARDS}


def resolve(key, **values):
    return {row.key.removeprefix('qt_hazard_'): row.arguments for row in BY_KEY[key].resolve(values).lines}


class HazardQuickTableTests(unittest.TestCase):
    def test_every_lookup_has_valid_defaults_without_rolling(self):
        self.assertEqual(len(BY_KEY), len(CARDS))
        with patch('random.randint', side_effect=AssertionError('unexpected roll')):
            for card in CARDS:
                with self.subTest(card=card.key):
                    result = card.resolve({})
                    self.assertTrue(result.lines)
                    self.assertIn(card.section, ('trauma', 'hazards'))

    def test_basic_damage_example_preserves_order_and_shared_engine(self):
        result = resolve('direct_injury')
        self.assertEqual(result['damage_penetration'], {'basic': 8, 'dr': 3, 'penetrating': 5})
        self.assertEqual(result['damage_injury'], {'multiplier': '1.5', 'injury': 7})
        self.assertEqual(result['damage_shock']['modifier'], -4)
        self.assertIn('damage_major', result)
        result = resolve('direct_injury', basic_damage='4', rigid_dr='3', damage_type='pi-')
        self.assertEqual(result['damage_injury']['injury'], 1)  # Positive penetration, minimum injury.
        result = resolve('direct_injury', basic_damage='7', rigid_dr='7', damage_type='cr')
        self.assertEqual(result['damage_injury']['injury'], 0)  # No rigid-armor blunt trauma.

    def test_hp_fp_one_third_and_negative_boundaries(self):
        self.assertIn('vitals_no_thresholds', resolve('vitals', max_hp='12', hp='4', max_fp='12', fp='4'))
        result = resolve('vitals', max_hp='12', hp='3', max_fp='12', fp='3')
        self.assertIn('vitals_low_hp', result)
        self.assertIn('vitals_low_fp', result)
        result = resolve('vitals', hp='-19', fp='0')
        self.assertEqual(result['vitals_collapse']['modifier'], -1)
        self.assertEqual(result['vitals_death_rolls']['fourth'], -40)
        self.assertIn('vitals_will', result)
        self.assertEqual(resolve('vitals', hp='-20')['vitals_collapse']['modifier'], -2)
        self.assertIn('vitals_fp_unconscious', resolve('vitals', fp='-10'))
        self.assertIn('vitals_dead', resolve('vitals', hp='-50'))
        self.assertIn('vitals_destroyed', resolve('vitals', hp='-100'))
        with self.assertRaisesRegex(ValueError, 'qt_hazard_invalid_vitals'):
            resolve('vitals', fp='-11')

    def test_first_aid_tl_rows_and_high_hp_single_bandage_award(self):
        checks = ((0, 30, '1d6-4', 2), (1, 30, '1d6-4', 2), (2, 30, '1d6-3', 3),
                  (3, 30, '1d6-3', 3), (4, 30, '1d6-2', 4), (5, 20, '1d6-2', 4),
                  (6, 20, '1d6-1', 5), (7, 20, '1d6-1', 5), (8, 10, '1d6', 6), (9, 10, '1d6+1', 7))
        for tl, time, expression, maximum in checks:
            with self.subTest(tl=tl):
                self.assertEqual(resolve('first_aid', tl=str(tl))['aid_treatment'],
                                 dict(time=time, expression=expression, minimum=2 if tl >= 9 else 1, maximum=maximum))
        data = resolve('first_aid', tl='0', aid_die='1', max_hp='20')
        self.assertEqual(data['aid_bandage']['amount'], 2)
        self.assertEqual(data['aid_success_roll'], {'roll': 1, 'total': 2, 'extra': 0})
        data = resolve('first_aid', tl='9', aid_die='6', max_hp='39')
        self.assertEqual(data['aid_success_roll'], {'roll': 6, 'total': 21, 'extra': 18})
        self.assertEqual(data['aid_critical']['maximum'], 21)

    def test_bleeding_applies_exact_hp_penalty_and_stops_on_third_minute(self):
        data = resolve('bleeding', ht='11', lost_hp='9')
        self.assertEqual(data['bleed_check'], {'modifier': -1, 'target': 10})
        self.assertEqual(resolve('bleeding', lost_hp='10')['bleed_check']['target'], 8)
        self.assertEqual(resolve('bleeding', bleed_roll='18')['bleed_hit']['amount'], 3)
        self.assertEqual(resolve('bleeding', bleed_roll='12')['bleed_hit']['amount'], 1)
        self.assertIn('bleed_stop', resolve('bleeding', bleed_roll='4'))
        self.assertEqual(resolve('bleeding', bleed_roll='8', bleed_successes='1')['bleed_continue']['successes'], 2)
        self.assertIn('bleed_prior_stop', resolve('bleeding', bleed_roll='8', bleed_successes='2'))
        self.assertNotIn('bleed_check', resolve('bleeding', bleed_successes='3'))

    def test_fire_profiles_and_clothing_thresholds_are_separate(self):
        self.assertIn('fire_partial_turn_result', resolve('fire'))
        self.assertIn('fire_full_turn_result', resolve('fire', fire_exposure='fire_full_turn'))
        self.assertIn('fire_intense_result', resolve('fire', fire_exposure='fire_intense'))
        for damage, outcome in ((2, 'no'), (3, 'partial'), (9, 'partial'), (10, 'full')):
            with self.subTest(damage=damage):
                self.assertIn(f'fire_{outcome}_clothes', resolve('fire', fire_damage=str(damage)))
                self.assertIn(f'fire_{outcome}_clothes', resolve('fire', fire_damage=str(damage * 10),
                                                                fire_tight_beam=True))
        self.assertIn('fire_no_clothes', resolve('fire', fire_damage='29', fire_tight_beam=True))

    def test_airless_use_zero_and_floor_without_double_counting_fatigue(self):
        for seconds, remaining, injury in ((9, 1, 0), (10, 0, 0), (11, -1, 1), (20, -10, 10), (23, -10, 13)):
            with self.subTest(seconds=seconds):
                result = resolve('suffocation', airless_seconds=str(seconds))
                self.assertEqual(result['airless_result'], {'fp': remaining, 'damage': injury})
        self.assertEqual(resolve('suffocation', fp='-7', airless_seconds='10')['airless_result'],
                         {'fp': -10, 'damage': 10})
        self.assertNotIn('airless_brain', resolve('suffocation', airless_seconds='120'))
        self.assertIn('airless_brain', resolve('suffocation', airless_seconds='121'))
        self.assertIn('airless_death', resolve('suffocation', airless_seconds='240'))

    def test_radiation_example_shielding_and_overlapping_printed_band(self):
        for days, remaining in ((30, '200'), (31, '190'), (47, '30'), (48, '20'), (100, '20')):
            with self.subTest(days=days):
                self.assertEqual(resolve('radiation', dose_days=str(days))['rad_result']['remaining'], remaining)
        self.assertEqual(resolve('radiation', incoming_rads='200', protection_factor='10', other_rads='6')['rad_result'],
                         {'dose': '20', 'remaining': '2', 'permanent': '2', 'accumulated': '8'})
        for dose, modifier in ((10, '+0'), (11, '+0'), (41, '-1'), (81, '-3'), (161, '-4'), (799, '-4'), (801, '-5')):
            with self.subTest(dose=dose):
                self.assertEqual(resolve('radiation', incoming_rads=str(dose), dose_days='0')['rad_band']['modifier'],
                                 modifier)
        self.assertIn('rad_ambiguous', resolve('radiation', incoming_rads='800', dose_days='0'))
        self.assertIn('rad_below_table', resolve('radiation', incoming_rads='0'))

    def test_hazard_links_use_existing_tools_without_mirroring_engines(self):
        for key, tool in (('falls', 2), ('collisions', 3), ('explosions', 4)):
            self.assertEqual(BY_KEY[key].tool, tool)
            self.assertFalse(BY_KEY[key].fields)
            self.assertEqual(len(resolve(key)), 1)
