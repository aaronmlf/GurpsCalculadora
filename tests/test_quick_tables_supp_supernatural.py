import json
import math
from pathlib import Path
from string import Formatter
import unittest

from utils.quick_tables_cards import Localized, Quantity
from utils.quick_tables_supp_supernatural import PACKS


_CARDS = {card.key: card for cards in PACKS.values() for card in cards}


def _result(card, **values):
    return {item.key.removeprefix('qt_ssuper_'): item.arguments for item in _CARDS['sup_' + card].resolve(values).lines}


class MagicSupplementTests(unittest.TestCase):
    def test_demonic_failure_is_guarded_and_just_points_to_the_book(self):
        self.assertEqual(_result('black_critical', roll='13'), {'black_not_applicable': {}})
        self.assertEqual(_result('black_critical', failed=True), {'black_pending': {}})
        self.assertEqual(_result('black_critical', failed=True, roll='13'), {'black_ref': {'roll': 13}})
        self.assertEqual(_CARDS['sup_black_critical'].roll, ('roll', 3, 6))

    def test_calamity_threshold_trigger_and_will_at_29(self):
        for event, before, after in (('casting', '29', '30'), ('other', '31', '40'),
                                     ('maintenance', '40', '40')):
            self.assertIn('calamity_not_applicable', _result('threshold_calamity', event=event, before=before, after=after))
        for event, before, after, excess, bonus in (('other', '29', '31', 1, 0), ('casting', '45', '45', 15, 3),
                                                   ('maintenance', '31', '37', 7, 1), ('casting', '30', '35', 5, 1)):
            self.assertEqual(_result('threshold_calamity', event=event, before=before, after=after)
                             ['calamity_modifier'], {'excess': excess, 'mod': bonus})
        at_28 = _result('threshold_calamity', roll='18', after='84')
        self.assertEqual(at_28['calamity_ref'], {'roll': 18, 'total': 28})
        self.assertNotIn('calamity_casting_will', at_28)
        at_29 = _result('threshold_calamity', roll='18', after='85')
        self.assertEqual(at_29['calamity_ref'], {'roll': 18, 'total': 29})
        self.assertEqual(at_29['calamity_casting_will'], {'mod': -11})
        self.assertNotIn('calamity_casting_will', _result('threshold_calamity', event='other', roll='18', after='85'))

    def test_rpm_p19_example_and_weight_band_boundaries(self):
        # Three Sense effects and planar range, one Greater. 2+2+2+10+1 = 17; x3 = 51.
        example = _result('rpm_energy', effect='sense', duration='10m', extras='14', greater='1')
        self.assertEqual(example['rpm_total'], {'subtotal': 17, 'multiplier': 3, 'total': 51})
        for weight, added in (('', 0), ('10', 0), ('10.01', 1), ('30', 1), ('31', 2),
                              ('10000', 6), ('10001', 7), ('2700000', 11), ('2700001', 12), ('8100001', 13)):
            self.assertEqual(_result('rpm_energy', weight=weight)['rpm_breakdown']['weight'], added)


class PowersAndPsiSupplementTests(unittest.TestCase):
    def test_super_effort_p58_example_and_basic_lift(self):
        result = _result('power_lift', base_st='10', levels='20')
        self.assertEqual(result['lift_scores'], {'normal': 30, 'bonus': 5000, 'boosted': 5010, 'cost': 1})
        self.assertEqual(result['lift_capacity'], {'basic': Quantity(5_020_020, 'pounds'),
                                                  'capacity': Quantity(40_160_160, 'pounds')})

    def test_awe_or_confusion_roll_needs_a_failed_check(self):
        self.assertIn('awe_need_failure', _result('awe_confusion', roll='13'))
        self.assertIn('awe_need_roll', _result('awe_confusion', margin='4'))
        self.assertEqual(_result('awe_confusion', mode='confusion', margin='4', roll='13')['awe_ref'],
                         {'mode': Localized('qt_ssuper_confusion'), 'total': 17, 'roll': 13, 'margin': 4})

    def test_psionic_range_level_progression_and_scope(self):
        radar = _result('psi_range', level='5', offset='3')['psi_range']
        self.assertEqual(radar, {'level': 8, 'distance': Quantity(200, 'yards')})
        for level, expected in (('1', 1), ('3', 5), ('4', 10), ('14', 20_000), ('15', 50_000)):
            self.assertEqual(_result('psi_range', level=level)['psi_range']['distance'], Quantity(expected, 'yards'))
        self.assertIn('psi_bad_level', _result('psi_range', level='1', offset='-1'))
        for level, scope in (('23', 'global'), ('40', 'system'), ('79', 'universal')):
            self.assertEqual(_result('psi_range', level=level)['psi_range_scope']['scope'],
                             Localized('qt_ssuper_psi_' + scope))
        self.assertNotIn('psi_range', _result('psi_range', level='79'))

    def test_crippling_is_not_ordinary_failure_or_an_automatic_effect(self):
        self.assertIn('psi_cripple_not_applicable', _result('psi_crippling', roll='18'))
        self.assertIn('psi_cripple_pending', _result('psi_crippling', crippled=True))
        self.assertEqual(_result('psi_crippling', roll='18', crippled=True), {'psi_cripple_ref': {'roll': 18}})


class SpaceshipsSupplementTests(unittest.TestCase):
    def test_solar_travel_uses_game_values_and_does_not_invent_lunar_orbit(self):
        mars = _result('solar_body', body='mars')
        self.assertEqual(mars['solar_radius']['radius'], 1.5)
        self.assertEqual(mars['solar_gravity'], {'gravity': 0.38, 'escape': Quantity(3.1, 'miles_per_second')})
        luna = _result('solar_body', body='luna')
        self.assertNotIn('solar_orbit', luna)
        self.assertIn('solar_luna', luna)

    def test_reactionless_voyage_both_formulas_and_relativistic_guard(self):
        long = _result('reactionless_trip', scale='long_voyage', au='1', acceleration='1')
        self.assertEqual(long['voyage_long']['hours'], 68)
        self.assertAlmostEqual(long['voyage_peak']['peak'].value, 741.2)
        short = _result('reactionless_trip', scale='short_voyage', miles='240000', acceleration='1')
        self.assertAlmostEqual(short['voyage_short']['minutes'], 0.423 * math.sqrt(240_000))
        self.assertIn('voyage_relativistic', _result('reactionless_trip', au='1000', acceleration='1'))
        self.assertEqual(_result('reactionless_trip', au='1000000', acceleration='10'), {'voyage_out_of_model': {}})

    def test_sensor_range_units_are_distinct_and_zero_not_permitted(self):
        result = _result('sensors_comms', level='8')['sensor_range']
        self.assertEqual(result, {'level': 8, 'light_seconds': 1.5, 'approx': Quantity(300_000, 'miles'), 'au': 1.5})
        with self.assertRaisesRegex(ValueError, 'out_of_range'):
            _result('sensors_comms', level='0')

    def test_combat_ranges_depend_on_scale_and_situation(self):
        for scale, situation, expected in (('standard_scale', 'attack_engaged', 'short_range'),
                                          ('close_scale', 'collision_course', 'point_blank'),
                                          ('distant_scale', 'neutral', 'extreme_range'),
                                          ('distant_scale', 'rendezvous', 'zero')):
            self.assertEqual(_result('space_combat_range', scale=scale, situation=situation)
                             ['combat_range_result']['category'], Localized('qt_ssuper_' + expected))

    def test_card_schema_and_locale_parity(self):
        self.assertEqual(set(PACKS), {'magic', 'powers_psi', 'space'})
        self.assertEqual(len(_CARDS), sum(len(cards) for cards in PACKS.values()))
        locales = Path(__file__).resolve().parents[1] / 'i18n'
        en, pt = (json.loads((locales / f'{lang}.json').read_text(encoding='utf-8')) for lang in ('en_US', 'pt_BR'))
        get_keys = lambda data: {key for key in data if key.startswith('qt_ssuper_')}
        self.assertEqual(get_keys(en), get_keys(pt))
        fields = lambda text: [(key, spec) for _, key, spec, _ in Formatter().parse(text) if key]
        for key in get_keys(en):
            self.assertCountEqual(fields(en[key]), fields(pt[key]), key)
        for card in _CARDS.values():
            self.assertNotEqual(card.source, 'Basic Set Revised')
            self.assertIn(card.requirement, en)
            keys = [card.title, *(field.title for field in card.fields),
                    *(choice[1] for field in card.fields for choice in field.options),
                    *(line.key for line in card.resolve({}).lines)]
            self.assertTrue(set(keys) <= en.keys(), card.key)
