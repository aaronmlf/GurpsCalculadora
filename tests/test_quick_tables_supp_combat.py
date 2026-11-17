"""Optional tactical, martial arts, and Action numeric references."""

import json
import math
from pathlib import Path
import unittest

from utils.quick_tables_cards import Localized, Quantity
from utils.quick_tables_packages import enabled_cards
from utils.quick_tables_supp_combat import PACKS
from utils.units import UnitSystem


_PREFIX = 'qt_scombat_'
_CARDS = {card.key: card for cards in PACKS.values() for card in cards}


def _resolve(key, **values):
    return {line.key.removeprefix(_PREFIX): line.arguments for line in _CARDS[key].resolve(values).lines}


class SupplementCombatCardsTests(unittest.TestCase):
    def test_registry_is_opt_in_and_has_source_and_context_per_card(self):
        self.assertEqual(tuple(PACKS), ('tactical', 'martial_arts', 'action'))
        self.assertEqual(sum(map(len, PACKS.values())), len(_CARDS))
        self.assertFalse(enabled_cards())
        sources = {
            'tactical': {'GURPS Tactical Shooting', 'GURPS Tactical Shooting: Extreme Conditions'},
            'martial_arts': {'GURPS Martial Arts'}, 'action': {'GURPS Action 2: Exploits'},
        }
        for package, cards in PACKS.items():
            with self.subTest(package=package):
                loaded = enabled_cards([package])
                self.assertEqual(tuple(card.key for card in loaded), tuple(card.key for card in cards))
                self.assertTrue(all(card.package == package for card in loaded))
                self.assertEqual({card.source for card in loaded}, sources[package])
                self.assertTrue(all(card.pages and card.requirement.startswith(_PREFIX) for card in loaded))

    def test_sight_modes_and_mask_modifiers_are_not_interchangeable(self):
        options = dict(distance='10', perception='10', darkness='-2', sight_gear='mask')
        near = _resolve('ts_sights', **options)['sights_modifiers']
        self.assertEqual(near, dict(modifier=-2, darkness=-2, relief=1, gear=-1))
        options['distance'] = '10.01'
        self.assertEqual(_resolve('ts_sights', **options)['sights_modifiers']['modifier'], -3)
        options['distance'] = repr(math.nextafter(10., math.inf))
        self.assertEqual(_resolve('ts_sights', **options)['sights_modifiers']['modifier'], -2)
        self.assertEqual(_resolve('ts_sights', shooting_method='sighted', **options)['sights_modifiers']['modifier'], -6)
        self.assertIn('sights_no_sighted', _resolve('ts_sights', shooting_method='aimed', sight_gear='goggles'))
        self.assertIn('sights_no_weapon_night_sight', _resolve('ts_sights', sight_gear='weapon_night_sight'))
        self.assertIn('sights_no_visibility', _resolve('ts_sights', target_not_visible=True))

    def test_bracing_and_range_cards_are_explicit(self):
        for grade, incoming, outgoing in (('very_light', -1, 0), ('light', -2, 0), ('medium', -3, -2), ('heavy', -4, -4)):
            with self.subTest(cover=grade):
                self.assertEqual(_resolve('ts_cover', cover_grade=grade)['cover_pair'], dict(incoming=incoming, outgoing=outgoing))
                self.assertEqual(_resolve('ts_cover', cover_grade=grade, braced_and_aimed=True)['cover_pair'],
                                 dict(incoming=incoming, outgoing=0))
        self.assertIn('rangefinding_set_sights', _resolve('ts_rangefinding', range_source='measured'))
        self.assertEqual(_resolve('ts_rangefinding', range_source='landmark', sights_set=True)['rangefinding_acc']['modifier'], 3)
        self.assertEqual(_resolve('ts_rangefinding', range_source='near_landmark')['rangefinding_acc']['modifier'], 1)
        self.assertEqual(_resolve('ts_rangefinding', range_source='unknown', sights_set=True)['rangefinding_acc']['modifier'], 0)

    def test_precipitation_and_vegetation_use_selected_increment_and_scope(self):
        suggested = _resolve('ts_obscuration', obscuration='dense')
        self.assertEqual(suggested['increment_interval'], dict(low=Quantity(2, 'yards'), high=Quantity(4, 'yards')))
        self.assertNotIn('increment_result', suggested)
        jungle = _resolve('ts_obscuration', obscuration='dense', affected_distance='10', chosen_increment='2', beneath_vegetation=True)
        self.assertEqual(jungle['increment_result'], dict(modifier=-5, effective=Quantity(2, 'yards')))
        self.assertNotIn('increment_shelter', jungle)
        fog = _resolve('ts_obscuration', obscuration='fog', affected_distance='330', chosen_increment='80', beneath_vegetation=True)
        self.assertEqual(fog['increment_result'], dict(modifier=-2, effective=Quantity(160, 'yards')))
        self.assertIn('increment_shelter', fog)
        with self.assertRaisesRegex(ValueError, 'qt_scombat_invalid_increment'):
            _resolve('ts_obscuration', obscuration='blizzard', chosen_increment='9')

    def test_wind_example_and_precision_aiming_correction(self):
        self.assertEqual(_resolve('ts_crosswind', distance='300', crosswind='strong')['crosswind_result']['modifier'], 0)
        self.assertEqual(_resolve('ts_crosswind', distance='1000')['crosswind_result']['modifier'], -3)
        strong = _resolve('ts_crosswind', distance='1000', crosswind='strong', aiming_successes='2')['crosswind_result']
        self.assertEqual(strong, dict(modifier=-2, steps=3, threshold=Quantity(300, 'yards'), wind=-6, correction=4))
        self.assertEqual(_resolve('ts_crosswind', distance='1000', aiming_successes='8')['crosswind_result']['modifier'], 0)

    def test_martial_arts_melee_attack_modes_do_not_stack(self):
        self.assertEqual(_resolve('ma_maneuvers', second_step=True)['maneuver_committed'], dict(hit=0, damage=0, steps=2))
        strong = _resolve('ma_maneuvers', martial_maneuver='strong', second_step=True,
                          damage_dice='7', scale_strong=True)['maneuver_committed']
        self.assertEqual(strong, dict(hit=-2, damage=3, steps=2))
        nonst = _resolve('ma_maneuvers', martial_maneuver='strong', st_based=False)['maneuver_committed']
        self.assertEqual(nonst['damage'], 0)
        defensive = _resolve('ma_maneuvers', martial_maneuver='defensive', damage_dice='5')
        self.assertEqual(defensive['maneuver_defensive']['damage'], -5)
        self.assertIn('maneuver_telegraphic_limits', _resolve('ma_maneuvers', martial_maneuver='telegraphic'))
        self.assertIn('maneuver_not_ready', _resolve('ma_maneuvers', ready_melee=False))

    def test_defensive_and_reversed_grips_are_distinct_from_base_modifiers(self):
        self.assertEqual(_resolve('ma_grips')['grip_result'], dict(attack=-2, damage=1, parry=1))
        two_handed = _resolve('ma_grips', martial_grip='defensive_two', swing=True, side_attack=True, damage_dice='4')
        self.assertEqual(two_handed['grip_result'], dict(attack=0, damage=-4, parry=-1))
        reversed_grip = _resolve('ma_grips', martial_grip='reversed', swing=False, side_attack=True)
        self.assertEqual(reversed_grip['grip_result'], dict(attack=0, damage=1, parry=-2))

    def test_slip_uses_different_movement_and_stop_thrust_modifiers(self):
        self.assertEqual(_resolve('ma_defensive_step')['slip_result']['modifier'], 0)
        self.assertEqual(_resolve('ma_defensive_step', mobile_defense=True, stop_thrust=True)['slip_result']['modifier'], 2)
        slip = _resolve('ma_defensive_step', defensive_step='slip', stop_thrust=True)
        self.assertEqual(slip['slip_result']['modifier'], -2)
        self.assertIn('slip_unavailable', _resolve('ma_defensive_step', standing_and_space=False))

    def test_severe_bleeding_per_location_damage_and_interval(self):
        for wound, kind, modifier, seconds in (
            ('neck', 'cut', -4, 30), ('neck', 'other', -2, 60), ('skull_eye', 'tight_beam', -2, 30),
            ('artery', 'cut', -6, 30), ('artery', 'imp', -5, 30), ('vitals', 'piercing', -6, 30),
            ('limb', 'cut', -6, 30), ('extremity', 'imp', -4, 60), ('superficial', 'cut', -3, 60),
        ):
            with self.subTest(wound=wound, kind=kind):
                result = _resolve('ma_severe_bleeding', bleeding_wound=wound, wound_damage=kind)['bleed_result']
                self.assertEqual((result['modifier'], result['seconds']), (modifier, seconds))
        self.assertIn('bleed_artery_ineligible', _resolve('ma_severe_bleeding', bleeding_wound='artery', wound_damage='other'))
        self.assertIn('bleed_no_injury', _resolve('ma_severe_bleeding', bleeding_injury='0'))

    def test_bad_replaces_detailed_modifiers_but_does_not_penalize_combat_or_chases(self):
        result = _resolve('action_bad', bad_method='enemy', enemy_value='15', task_skill='13', personal_adjustments='2')
        self.assertEqual(result['bad_selected']['bad'], -3)
        self.assertEqual(result['bad_effective']['target'], 12)
        for scene in ('detailed', 'combat', 'chase'):
            with self.subTest(scene=scene):
                result = _resolve('action_bad', bad_context=scene, bad_npc_alternative=True)
                self.assertNotIn('bad_effective', result)
                self.assertEqual(result['bad_npc_skill']['skill'], 15)
        alternative = _resolve('action_bad', bad_npc_alternative=True)
        self.assertNotIn('bad_effective', alternative)

    def test_chases_use_initial_bands_and_abstract_contest_shifts(self):
        for distance, band, modifier in ((5, 'close', 0), (6, 'short', -3), (20, 'short', -3),
                                          (21, 'medium', -7), (100, 'medium', -7), (101, 'long', -11),
                                          (500, 'long', -11), (501, 'extreme', -15)):
            with self.subTest(distance=distance):
                self.assertEqual(_resolve('action_chases', distance=str(distance))['chase_result'],
                                 dict(band=Localized(_PREFIX + 'chase_band_' + band), modifier=modifier))
        for margin, shifts in ((4, 0), (5, 1), (9, 1), (10, 2)):
            self.assertEqual(_resolve('action_chases', victory_margin=str(margin))['chase_steps']['steps'], shifts)
        self.assertIn('chase_both_static', _resolve('action_chases', static_parties='both', victory_margin='15'))
        self.assertIn('chase_one_static', _resolve('action_chases', static_parties='one', victory_margin='15'))

    def test_every_card_default_and_requirement_renders_in_pt_en(self):
        root = Path(__file__).resolve().parents[1]
        for lang, units in (('pt_BR', 'metric'), ('en_US', 'imperial')):
            table = json.loads((root / 'i18n' / (lang + '.json')).read_text(encoding='utf-8'))
            for card in _CARDS.values():
                with self.subTest(language=lang, key=card.key):
                    self.assertTrue(table[card.title] and table[card.requirement])
                    for field in card.fields:
                        self.assertTrue(table[field.title])
                        for _, key in field.options:
                            self.assertTrue(table[key])
                    for rendered in card.resolve({}).lines:
                        args = {k: (UnitSystem(units).display(v.value, v.unit) if isinstance(v, Quantity)
                                    else table[v.key] if isinstance(v, Localized) else v)
                                for k, v in rendered.arguments.items()}
                        self.assertTrue(table[rendered.key].format(**args))


if __name__ == '__main__':
    unittest.main()
