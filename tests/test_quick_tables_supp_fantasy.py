from decimal import Decimal
import unittest

from utils.quick_tables_supp_fantasy import PACKS


CARDS = {card.key: card for cards in PACKS.values() for card in cards}


class FantasyReferenceTests(unittest.TestCase):
    def run_card(self, key, **fields):
        rows = CARDS[key].resolve(fields)
        return {row.key.removeprefix('qt_sfant_'): row.arguments for row in rows.lines}, rows.expression

    def test_travel_pace_and_backtracking(self):
        values, _ = self.run_card('sup_df_overland')
        self.assertEqual(values['travel_distance']['distance'].value, 30)
        values, _ = self.run_card('sup_df_overland', pace='pace_sleepless_survival',
                                  conditions_percent='-105', low_hp_or_fp=True)
        self.assertAlmostEqual(values['travel_distance']['distance'].value, -1.1875)
        self.assertIn('travel_negative', values)
        with self.assertRaisesRegex(ValueError, 'qt_sfant_stops_beyond_hours'):
            self.run_card('sup_df_overland', time_stopped='13')

    def test_foraging_time_methods_and_failures(self):
        values, _ = self.run_card('sup_df_foraging', forage_skill='14', forage_method='forage_hunt',
                                  forage_time='forage_two_hours', weapon_acc='3', forage_terrain='-1', roll='4')
        self.assertEqual(values['forage_target']['skill'], 13)
        self.assertEqual(values['forage_meals']['count'], 2)
        self.assertEqual(values['forage_meals']['weight'].value, 1)
        values, expression = self.run_card('sup_df_foraging', forage_method='forage_spear', roll='18')
        self.assertIn('forage_spear_harm', values)
        self.assertEqual(expression, '1d6')

    def test_treasure_cost_floor_and_published_example(self):
        values, _ = self.run_card('sup_df_treasure_cost', base_price='750', total_cf='11.5',
                                  flat_price='1125', enchantments='5000')
        self.assertEqual(Decimal(values['cost_total_result']['value']), 15500)
        values, _ = self.run_card('sup_df_treasure_cost', total_cf='-2', flat_price='4')
        self.assertEqual(Decimal(values['cost_total_result']['value']), 24)
        self.assertIn('cost_floor', values)

    def test_treasure_roll_retains_each_die_and_budget_is_separate(self):
        values, expression = self.run_card('sup_df_treasure_order', treasure_die_1='4',
                                           treasure_die_2='2', treasure_die_3='3')
        self.assertEqual(values['ordered_dice_key'], {'first': 4, 'second': 2, 'third': 3})
        self.assertEqual(expression, '3d6')
        values, _ = self.run_card('sup_df_treasure_budget', extra_expenses='35')
        self.assertEqual(Decimal(values['budget_total']['total']), 803)
