"""Reference examples for Basic Set Revised perception and travel cards."""

import json
import math
from pathlib import Path
import unittest

from utils.quick_tables_cards import Localized, Quantity
from utils.quick_tables_explore import CARDS
from utils.units import UnitSystem


_CARDS = {card.key: card for card in CARDS}
_PREFIX = 'qt_explore_'


def _result(card, **overrides):
    return _CARDS[card].resolve(overrides)


def _lines(result):
    return {entry.key.removeprefix(_PREFIX): entry.arguments for entry in result.lines}


class ExploreQuickTablesTests(unittest.TestCase):
    def test_hearing_steps_and_trait_adjustments(self):
        for distance, modifier in (('.5', 1), ('.75', 0), ('1', 0), ('.25', 2), ('1.01', -1), ('8', -3),
                                   (repr(math.nextafter(1., math.inf)), 0), ('1e308', -1024)):
            with self.subTest(distance=distance):
                result = _lines(_result('hearing', hearing_distance=distance, sense_base='12', acute='2',
                                        hearing_trait='discriminatory', circumstances='-1'))
                self.assertEqual(result['hearing_baseline']['distance'], Quantity(1., 'yards'))
                self.assertEqual(result['hearing_distance_modifier']['modifier'], modifier)
                self.assertEqual(result['hearing_trait_modifier']['modifier'], 4)
                self.assertEqual(result['sense_target']['target'], 17 + modifier)
        jet = _lines(_result('hearing', sound='jet', hearing_distance='256', hearing_trait='hard'))
        self.assertEqual(jet['hearing_baseline']['distance'], Quantity(128, 'yards'))
        self.assertEqual(jet['hearing_distance_modifier']['modifier'], -1)
        self.assertEqual(jet['sense_target']['target'], 5)
        deaf = _lines(_result('hearing', hearing_trait='deaf'))
        self.assertIn('hearing_deaf', deaf)
        self.assertNotIn('sense_target', deaf)
        with self.assertRaises(ValueError):
            _result('hearing', hearing_distance='0')

    def test_vision_bonuses_are_conditional_never_stack_and_do_not_bypass_darkness(self):
        for task, watching, plain, found, expected in (
            ('notice', True, True, False, 10), ('notice', False, True, True, 0),
            ('notice', True, False, True, 0), ('detail', True, True, True, 20),
            ('detail', True, True, False, 0), ('detail', False, True, True, 0),
            ('passive', True, True, True, 0), ('concealment', True, True, True, 0),
            ('other', True, True, True, 0),
        ):
            with self.subTest(task=task, watching=watching, plain=plain, found=found):
                result = _lines(_result('vision_check', vision_task=task, actively_watching=watching,
                                        plain_target=plain, located_target=found, circumstances='-3', acute='1'))
                self.assertEqual(result['vision_bonus']['bonus'], expected)
                self.assertEqual(result['sense_target']['target'], 8 + expected)
        blind = _lines(_result('vision_check', vision_unavailable=True, plain_target=True))
        self.assertIn('vision_no_roll', blind)
        self.assertNotIn('sense_target', blind)

    def test_horizon_and_light_signal_visibility(self):
        example = _lines(_result('visual_signals', observer_sm='0', signal_sm='4', signal_distance='9.5',
                                 deliberate_signal=True, light_signal=True, darkness='-7'))
        self.assertEqual(example['horizon_distance']['maximum'], Quantity(9.5, 'miles'))
        self.assertEqual(example['horizon_status']['status'], Localized(_PREFIX + 'horizon_within'))
        self.assertEqual(example['horizon_light']['bonus'], 7)
        self.assertIn('horizon_plain', example)
        distant = _lines(_result('visual_signals', observer_sm='-10', signal_sm='11', signal_distance='26',
                                 deliberate_signal=True, light_signal=True, darkness='-10'))
        self.assertEqual(distant['horizon_distance']['maximum'], Quantity(25.4, 'miles'))
        self.assertEqual(distant['horizon_status']['status'], Localized(_PREFIX + 'horizon_beyond'))
        self.assertNotIn('horizon_plain', distant)
        self.assertNotIn('horizon_light', distant)

    def test_taste_or_smell_combines_applicable_traits_and_gm_adjustments(self):
        scent = _lines(_result('taste_smell', taste_smell_trait='discriminatory', acute='3', circumstances='-2'))
        self.assertEqual(scent['taste_smell_trait_modifier'], {
            'sense': Localized(_PREFIX + 'taste_smell_sense_smell'), 'modifier': 4,
        })
        self.assertEqual(scent['sense_target']['target'], 15)
        flavor = _lines(_result('taste_smell', taste_smell_sense='taste', taste_smell_trait='absent'))
        self.assertEqual(flavor['taste_smell_unavailable']['sense'], Localized(_PREFIX + 'taste_smell_sense_taste'))
        self.assertNotIn('sense_target', flavor)

    def test_terrain_dice_extremes_tracking_exceptions_and_underwater(self):
        arctic = _result('terrain', terrain='arctic', track_conditions='loose_calm', terrain_travel_surface='ski')
        lines = _lines(arctic)
        self.assertEqual(arctic.expression, '1d6')
        self.assertEqual(lines['terrain_foraging'], {'modifier': -4, 'formula': '1d6-7', 'low': -6, 'high': -1})
        self.assertEqual(lines['terrain_tracking']['modifier'], 0)
        self.assertEqual(lines['terrain_travel']['factor'], 1)
        desert = _lines(_result('terrain', terrain='desert', track_conditions='loose_wind_water',
                                terrain_travel_surface='fast', foraging_method='minimum'))
        self.assertEqual(desert['terrain_foraging']['modifier'], -6)
        self.assertEqual(desert['terrain_tracking']['modifier'], -4)
        self.assertEqual(desert['terrain_travel']['factor'], 1.25)
        island = _result('terrain', terrain='island', foraging_method='roll', foraging_roll='12')
        self.assertEqual(island.expression, '2d6')
        self.assertEqual(_lines(island)['terrain_foraging']['modifier'], 5)
        reef = _lines(_result('terrain', terrain='reef', foraging_method='maximum'))
        self.assertEqual(reef['terrain_foraging']['modifier'], 6)
        self.assertIn('terrain_underwater', reef)
        self.assertNotIn('terrain_tracking', reef)
        self.assertNotIn('terrain_travel', reef)
        ocean = _lines(_result('terrain', terrain='ocean'))
        self.assertEqual(ocean['terrain_foraging']['modifier'], -1)
        with self.assertRaisesRegex(ValueError, 'invalid_foraging_roll'):
            _result('terrain', terrain='arctic', foraging_method='roll', foraging_roll='7')
        with self.assertRaisesRegex(ValueError, 'invalid_terrain_surface'):
            _result('terrain', terrain='jungle', terrain_travel_surface='skate')

    def test_standard_and_revised_daily_marching(self):
        basic = _lines(_result('hiking', trail_move='5', hiking_success=True, trail_terrain='.2', trail_weather='.5'))
        self.assertEqual(basic['hiking_mileage']['distance'], Quantity(6., 'miles'))
        unskilled = _lines(_result('hiking', hiking_model='unskilled'))
        skilled = _lines(_result('hiking', hiking_model='skilled'))
        self.assertEqual(unskilled['hiking_hours']['hours'], 8)
        self.assertEqual(unskilled['hiking_mileage']['distance'], Quantity(20., 'miles'))
        self.assertEqual(skilled['hiking_mileage']['distance'], Quantity(30., 'miles'))
        interrupted = _lines(_result('hiking', hiking_model='skilled', hiking_foraging_hours='2'))
        self.assertEqual(interrupted['hiking_hours']['hours'], 10)
        self.assertEqual(interrupted['hiking_mileage']['distance'], Quantity(25., 'miles'))
        with self.assertRaisesRegex(ValueError, 'invalid_hiking_hours'):
            _result('hiking', hiking_model='unskilled', hiking_foraging_hours='9')

    def test_climbing_ordinary_and_combat_rates(self):
        ladder = _lines(_result('climbing', climb_kind='ladder_up', climb_rungs='12', climb_in_combat=True))
        self.assertIn('climb_no_roll', ladder)
        self.assertEqual(ladder['climb_ladder_speed'], {'rate': 3, 'seconds': 4.})
        self.assertIn('climb_fatigue_note', ladder)
        wall = _lines(_result('climbing', climb_kind='stone_wall', climb_distance='12', encumbrance='3'))
        self.assertAlmostEqual(wall['climb_speed']['seconds'], 540.)
        self.assertEqual(wall['climb_modifier']['total'], -6)
        lowering = _lines(_result('climbing', climb_kind='equipment_down', climb_distance='12'))
        self.assertEqual(lowering['climb_speed']['rate'], Quantity(4., 'yards_per_second'))
        self.assertEqual(lowering['climb_speed']['seconds'], 3.)

    def test_swimming_examples_and_fatigue_interval(self):
        human = _lines(_result('swimming', swim_move='7', encumbrance='3', swim_intentional=True, swim_build='fat'))
        self.assertEqual(human['swim_speed']['speed'], Quantity(.4, 'yards_per_second'))
        self.assertEqual(human['swim_speed']['distance'], Quantity(4., 'yards'))
        self.assertEqual(human['swim_entry']['modifier'], 0)
        self.assertEqual(human['swim_fatigue']['minutes'], 1)
        aquatic = _lines(_result('swimming', swim_move='7', aquatic=True, swim_top_speed=False))
        self.assertEqual(aquatic['swim_speed']['distance'], Quantity(70., 'yards'))
        self.assertNotIn('swim_entry', aquatic)
        self.assertEqual(aquatic['swim_fatigue']['minutes'], 30)

    def test_defaults_title_fields_options_and_lines_render_in_both_languages(self):
        root = Path(__file__).resolve().parents[1]
        for lang, unit_system in (('en_US', 'imperial'), ('pt_BR', 'metric')):
            translations = json.loads((root / 'i18n' / (lang + '.json')).read_text(encoding='utf-8'))
            for card in CARDS:
                with self.subTest(lang=lang, card=card.key):
                    self.assertTrue(translations[card.title])
                    for field in card.fields:
                        self.assertTrue(translations[field.title])
                        for _, key in field.options:
                            self.assertTrue(translations[key])
                    for entry in card.resolve({}).lines:
                        args = {k: (UnitSystem(unit_system).display(v.value, v.unit) if isinstance(v, Quantity)
                                    else translations[v.key] if isinstance(v, Localized) else v)
                                for k, v in entry.arguments.items()}
                        self.assertTrue(translations[entry.key].format(**args))


if __name__ == '__main__':
    unittest.main()
