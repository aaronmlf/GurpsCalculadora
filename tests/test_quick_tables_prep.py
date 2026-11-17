import json
from pathlib import Path
from string import Formatter
import unittest

from utils.quick_tables_cards import Localized, Quantity
from utils.quick_tables_prep import CARDS


_CARDS = {card.key: card for card in CARDS}


def _result(key, **values):
    return {item.key: item.arguments for item in _CARDS[key].resolve(values).lines}


class ObjectReferenceTests(unittest.TestCase):
    def test_hp_formula_uses_empty_weight_and_rounds_up(self):
        for weight, model, expected in (
            ('8', 'unliving', 8), ('8,0001', 'unliving', 9), ('2', 'homogenous', 11),
            ('8', 'diffuse', 16), ('1000', 'homogenous', 80), ('16000', 'building', 200),
        ):
            with self.subTest(weight=weight, model=model):
                result = _result('object_hp', weight=weight, model=model)['qt_prep_hp_result']
                self.assertEqual(result['hp'], expected)
                self.assertEqual(result['weight'], Quantity(float(weight.replace(',', '.')), 'pounds'))

    def test_cover_ratings_and_overpenetration_are_distinct(self):
        rating = _result('cover_material', material='reinforced_concrete', thickness=str(2 / 36))
        self.assertEqual(rating['qt_prep_material_result']['low'], 20)
        self.assertEqual(rating['qt_prep_material_result']['high'], 24)
        self.assertIn('qt_prep_material_wear', rating)
        self.assertNotIn('qt_prep_material_wear', _result('cover_material', material='sandbags'))
        for model, contribution in (('homogenous', 5), ('unliving', 10), ('slab', 0)):
            self.assertEqual(_result('cover_barrier', model=model, hp='21', dr='4')['qt_prep_cover_result'],
                             {'total': 4 + contribution, 'dr': 4, 'hp': contribution})

    def test_artifact_thresholds_distinguish_stress_and_collapse(self):
        cases = (('3', {}, 'above_thresholds'), ('2', {}, 'impaired'), ('0', {}, 'stress_check'),
                 ('0', {'stressed': False}, 'wait_for_stress'), ('0', {'model': 'building'}, 'building_disable_check'),
                 ('-9', {}, 'destruction_check'), ('-9', {'model': 'building'}, 'collapse_check'),
                 ('-45', {}, 'destroyed'), ('-45', {'model': 'building'}, 'collapse'))
        for current, options, state in cases:
            with self.subTest(current=current, options=options):
                self.assertIn('qt_prep_artifact_' + state,
                              _result('artifact_condition', hp='9', current_hp=current, **options))

    def test_collision_example_preview_breakable_cap_and_elastic_dr(self):
        baseline = _result('fixed_obstacle', hp='10', velocity='19', surface='hard')
        self.assertEqual(baseline['qt_prep_collision_dice'], {'incoming': '4d', 'outgoing': '2d'})
        self.assertNotIn('qt_prep_collision_cap', baseline)
        cap = _result('fixed_obstacle', breakable=True, obstacle_hp='8', dr='3', surface='elastic', elastic_dr='7')
        self.assertEqual(cap['qt_prep_collision_cap'], {'cap': 11})
        self.assertEqual(cap['qt_prep_collision_elastic'], {'dr': 7})
        self.assertEqual(cap['qt_prep_collision_dice']['incoming'], cap['qt_prep_collision_dice']['outgoing'])
        self.assertIn('qt_prep_collision_none', _result('fixed_obstacle', velocity='0'))

    def test_vehicle_does_not_invent_mounted_parts(self):
        card = _CARDS['vehicle_hit']
        self.assertEqual(card.roll, ('roll', 3, 6))
        self.assertIn('qt_prep_vehicle_pending', _result('vehicle_hit', roll='3', location='G'))
        picked = _result('vehicle_hit', roll='3', location='g')
        self.assertEqual(picked['qt_prep_vehicle_result']['part'], Localized('qt_prep_small_window'))
        self.assertEqual(picked['qt_prep_vehicle_penalty']['penalty'], -7)
        for total, code in (('3', 'no_candidate'), ('10', 'unconfirmed')):
            self.assertEqual(_result('vehicle_hit', roll=total, location=code)['qt_prep_vehicle_result']['part'],
                             Localized('qt_prep_hull'))
        self.assertIn('qt_prep_vehicle_animal', _result('vehicle_hit', roll='14', location='D'))
        self.assertIn('qt_prep_vehicle_pending', _result('vehicle_hit', roll='18'))


class MagicAndPreparationReferenceTests(unittest.TestCase):
    def test_casting_uses_only_mana_adjusted_base_skill_for_reduction(self):
        for skill, mana, kind, time, expected in (
            ('9', 'normal', 'normal_spell', '5', (3, 0, 10)),
            ('14', 'normal', 'normal_spell', '5', (3, 0, 5)),
            ('15', 'normal', 'normal_spell', '5', (2, 1, 5)),
            ('20', 'normal', 'normal_spell', '5', (1, 2, 3)),
            ('25', 'normal', 'normal_spell', '5', (0, 3, 2)),
            ('30', 'normal', 'normal_spell', '5', (0, 4, 1)),
            ('20', 'low', 'normal_spell', '5', (2, 1, 5)),
            ('20', 'normal', 'missile', '5', (1, 2, 5)),
            ('20', 'normal', 'blocking', '5', (3, 0, 0)),
        ):
            with self.subTest(skill=skill, mana=mana, kind=kind):
                result = _result('magic_preparation', skill=skill, mana=mana, kind=kind, time=time,
                                 cost='3', maintenance='2')
                casting = result['qt_prep_magic_effect']
                self.assertEqual((casting['cost'], casting['reduction'], casting['seconds']), expected)
                if kind == 'blocking':
                    self.assertNotIn('qt_prep_magic_maintenance_cost', result)
                else:
                    self.assertEqual(result['qt_prep_magic_maintenance_cost']['cost'], max(0, 2 - expected[1]))

    def test_mana_gates_casting_and_does_not_refund_non_mages(self):
        self.assertIn('qt_prep_magic_need_magery', _result('magic_preparation', mage=False))
        self.assertIn('qt_prep_magic_no_mana', _result('magic_preparation', mana='no_mana'))
        novice = _result('magic_preparation', mana='very_high', mage=False)
        self.assertIn('qt_prep_magic_very_high', novice)
        self.assertNotIn('qt_prep_magic_very_high_recovery', novice)
        self.assertIn('qt_prep_magic_very_high_recovery', _result('magic_preparation', mana='very_high'))

    def test_range_touch_sight_and_long_distance_boundaries(self):
        result = _result('magic_range', yards='5', mode='area', see=False)
        self.assertEqual(result['qt_prep_spell_range_result'], {'mod': -10, 'range': -5, 'unseen': -5})
        self.assertIn('qt_prep_spell_range_guide_area', result)
        self.assertEqual(_result('magic_range', yards='5', see=False, touch=True)['qt_prep_spell_range_result']['mod'], 0)
        for yards, penalty in (('200', 0), ('200.01', -1), ('880', -1), ('881', -2),
                               ('1760000', -8), ('1760001', -9), ('17600000', -10)):
            with self.subTest(yards=yards):
                self.assertEqual(_result('magic_range', mode='long_distance', yards=yards, see=False, touch=True)
                                 ['qt_prep_spell_range_long'], {'mod': penalty})

    def test_references_backfire_without_executing_or_revealing_an_effect(self):
        base = _result('magic_check', effective_skill='22', roll='17')
        self.assertEqual(base['qt_prep_spell_check_outcome']['outcome'], Localized('gm_dice_check_failure'))
        self.assertNotIn('qt_prep_spell_backfire_reference', base)
        changed = _result('magic_check', effective_skill='22', roll='17', mana='very_high')
        self.assertEqual(changed['qt_prep_spell_check_outcome']['outcome'], Localized('gm_dice_check_critical_failure'))
        self.assertIn('qt_prep_spell_backfire_reference', changed)
        self.assertIsNone(_CARDS['magic_check'].resolve({'roll': '18'}).expression)
        self.assertIn('qt_prep_spell_minimum_skill', _result('magic_check', effective_skill='2', roll='3'))

    def test_wealth_status_and_encounter_slots_use_book_ranges_only(self):
        settled = _result('wealth_and_status', tl='3', wealth='struggling', status='-1')
        self.assertEqual(settled['qt_prep_wealth_result'], {'base': 1000, 'starting': 500})
        self.assertEqual(settled['qt_prep_wealth_split'], {'movable': 100, 'settled': 400})
        self.assertEqual(settled['qt_prep_status_result'], {'monthly': 300})
        high = _result('wealth_and_status', tl='15', wealth='filthy_rich', multimillionaire='1', settled=False)
        self.assertEqual(high['qt_prep_wealth_split'], {'movable': 100_000_000, 'settled': 0})
        self.assertEqual(_result('encounter_slot', roll='6')['qt_prep_encounter_slot'], {'slot': 6})
        self.assertNotIn('qt_prep_encounter_slot', _result('encounter_slot'))

    def test_validation_and_bilingual_fields(self):
        for card, field, value in (('object_hp', 'weight', '0'), ('vehicle_hit', 'roll', '19'),
                                   ('encounter_slot', 'roll', '7'), ('wealth_and_status', 'status', '-3'),
                                   ('magic_preparation', 'mage', 'yes'), ('magic_range', 'yards', 'nan')):
            with self.subTest(card=card, field=field), self.assertRaisesRegex(ValueError, '^qt_reference_'):
                _result(card, **{field: value})
        locales = Path(__file__).resolve().parents[1] / 'i18n'
        english, portuguese = (json.loads((locales / f'{language}.json').read_text(encoding='utf-8'))
                               for language in ('en_US', 'pt_BR'))
        keys = lambda entries: {key for key in entries if key.startswith('qt_prep_')}
        self.assertEqual(keys(english), keys(portuguese))
        placeholders = lambda text: sorted((field, format_spec) for _, field, format_spec, _ in Formatter().parse(text)
                                           if field is not None)
        for key in keys(english):
            self.assertEqual(placeholders(english[key]), placeholders(portuguese[key]), key)
        for card in CARDS:
            needed = [card.title, *(field.title for field in card.fields),
                      *(option[1] for field in card.fields for option in field.options), *_result(card.key)]
            self.assertTrue(set(needed) <= english.keys(), card.key)
