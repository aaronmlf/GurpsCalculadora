import unittest

from utils.quick_tables_packages import enabled_cards
from utils.quick_tables_supp_campaign import PACKS


CARDS = {card.key.removeprefix('scamp_'): card for group in PACKS.values() for card in group}


def line_args(result, key):
    return next(row.arguments for row in result.lines if row.key == 'qt_scamp_' + key)


def resolve(key, **values):
    return CARDS[key].resolve(values)


class CampaignSupplementTests(unittest.TestCase):
    def test_opt_in_metadata_and_defaults_are_deterministic(self):
        self.assertEqual(set(PACKS), {'social', 'mass_combat', 'horror'})
        self.assertEqual(len(CARDS), 12)
        self.assertFalse(enabled_cards())
        for package, cards in PACKS.items():
            self.assertEqual([c.key for c in enabled_cards((package,))], [c.key for c in cards])
            for card in cards:
                self.assertTrue(card.requirement)
                self.assertTrue(card.source.startswith('GURPS '))
                self.assertEqual(card.resolve({}), card.resolve({}))
                if card.roll:
                    self.assertEqual(card.roll, ('roll', 3, 6))
                    self.assertIsNone(card.resolve({}).expression)

    def test_reaction_contexts_and_bands_are_separate(self):
        for total, band in ((-1, 'disastrous'), (0, 'disastrous'), (1, 'very_bad'),
                            (3, 'very_bad'), (4, 'bad'), (6, 'bad'), (7, 'poor'),
                            (9, 'poor'), (10, 'neutral'), (12, 'neutral'), (13, 'good'),
                            (15, 'good'), (16, 'very_good'), (18, 'very_good'), (19, 'excellent')):
            with self.subTest(total=total):
                result = resolve('reaction', context='loyalty', roll='10', modifier=str(total - 10))
                self.assertEqual(line_args(result, 'reaction_result')['band'].key,
                                 'qt_scamp_band_' + band)
                self.assertEqual(line_args(result, 'reaction_reference')['page'], 76)
        for context, page in (('authority', 74), ('admission', 75), ('commerce', 75), ('seduction', 76)):
            self.assertEqual(line_args(resolve('reaction', context=context), 'reaction_reference')['page'], page)

    def test_rank_published_examples_repeat_and_natural_17(self):
        self.assertEqual(line_args(resolve('rank'), 'rank_target')['target'], 9)
        result = resolve('rank', rank='2', patron='20', rank_cost='5', previous='1')
        self.assertEqual(line_args(result, 'rank_target')['base'], 5)
        self.assertEqual(line_args(result, 'rank_target')['target'], 4)
        result = resolve('rank', rank='0', patron='10', rank_cost='2', roll='3')
        self.assertIn('qt_scamp_rank_blocked', {row.key for row in result.lines})
        result = resolve('rank', modifier='15', roll='17')
        self.assertIn('qt_scamp_rank_no_aid', {row.key for row in result.lines})

    def test_mass_relative_ts_and_classes_match_drakes_cross(self):
        self.assertEqual(line_args(resolve('strength'), 'strength_result')['b'], 2)
        self.assertEqual(line_args(resolve('strength', ts_a='150', ts_b='100'), 'strength_result')['a'], 2)
        self.assertEqual(line_args(resolve('strength', ts_a='149.99', ts_b='100'), 'strength_result')['a'], 0)
        self.assertEqual(line_args(resolve('class'), 'class_result')['a'], 1)
        self.assertEqual(line_args(resolve('class', neutral_b='100'), 'class_totals'), {'a': '9.0', 'b': '9.0'})
        result = resolve('class', **{'class': 'air'}, class_a='5', class_b='0', opposing_ts='500', encounter=True)
        self.assertEqual(line_args(result, 'class_result')['a'], 2)
        result = resolve('class', class_a='5', class_b='0', opposing_ts='501')
        self.assertIn('qt_scamp_class_insignificant', {row.key for row in result.lines})
        result = resolve('class', **{'class': 'recon'})
        self.assertEqual(line_args(result, 'class_recon_result')['a'], 1)

    def test_battle_round_boundaries_and_desperate_threshold(self):
        for count, minutes in ((1, 15), (9, 15), (10, 30), (99, 30), (100, 60),
                               (999, 60), (1000, 120), (9999, 120), (10000, 240)):
            result = resolve('length', elements_a='50000', elements_b=str(count))
            self.assertEqual(line_args(result, 'length_result')['minutes'], minutes)
        result = resolve('strategy', strategy='all_out_attack', strategy_extra='desperate', casualty_gap='25')
        self.assertEqual(line_args(result, 'strategy_desperate_result')['total'], '+6')
        result = resolve('strategy', strategy_extra='desperate', casualty_gap='24')
        self.assertEqual(line_args(result, 'strategy_desperate_minimum')['gap'], 24)
        result = resolve('strategy', strategy='skirmish', strategy_extra='desperate', casualty_gap='50')
        self.assertIn('qt_scamp_strategy_desperate_invalid', {row.key for row in result.lines})

    def test_base_round_result_and_aftermath(self):
        self.assertEqual(line_args(resolve('battle', margin='0'), 'battle_tie')['percent'], 10)
        self.assertEqual(line_args(resolve('battle', margin='5'), 'battle_result'), {'winner': 10, 'loser': 20})
        self.assertEqual(line_args(resolve('battle', margin='20', winner_action='raid'), 'battle_raid')['shift'], 4)
        self.assertEqual(line_args(resolve('after'), 'after_final'), {'winner': 15, 'loser': 15})
        result = resolve('after', retreated=True, aftermath='pursue', air_edge=True, cavalry_edge=True)
        self.assertEqual(line_args(result, 'after_final'), {'winner': 15, 'loser': 30})
        result = resolve('after', retreated=True, aftermath='hold', winner_loss='25')
        self.assertEqual(line_args(result, 'after_final')['winner'], 10)
        self.assertEqual(line_args(resolve('after', winner_loss='100', loser_loss='100'), 'after_final'),
                         {'winner': 50, 'loser': 50})
        self.assertIn('qt_scamp_after_not_retreat', {row.key for row in resolve('after', aftermath='hold').lines})

    def test_individual_risk_examples_and_unlisted_round_loss(self):
        heroism = resolve('risk', risk_kind='heroism', risk='3', useful=True, unit_leader=True, roll='9')
        self.assertEqual(line_args(heroism, 'risk_target')['target'], 10)
        self.assertEqual(line_args(heroism, 'risk_heroism_result')['bonus'], '+1')
        misfortune = resolve('risk', round_loss='10', risk='3', roll='8')
        self.assertEqual(line_args(misfortune, 'risk_target')['target'], 9)
        self.assertEqual(misfortune.expression, '2d6-1')
        self.assertEqual(resolve('risk', round_loss='40', roll='4').expression, '6d6')
        self.assertEqual(line_args(resolve('risk', round_loss='0'), 'risk_unlisted')['loss'], 0)

    def test_horror_rule_of_14_and_explicit_alternatives(self):
        result = resolve('fright', will='18', intrinsic='-1', size='large', appearance='disgusting', roll='14')
        self.assertEqual(line_args(result, 'fright_modifiers'),
                         {'size': '-1', 'appearance': '-1', 'target': 15})
        self.assertEqual(line_args(result, 'fright_limit')['target'], 13)
        self.assertEqual(result.expression, '3d6+1')
        self.assertEqual(resolve('fright', fright_method='ad_hoc', roll='18').expression, '1d6')
        result = resolve('fright', fright_method='alternatives', roll='18')
        self.assertEqual(len(result.lines), 1)
        self.assertIsNone(result.expression)

    def test_cumulative_fear_and_stress_are_distinct(self):
        self.assertEqual(line_args(resolve('fear', fear_load='2', fear_event='success'),
                                   'fear_cumulative_result'), {'current': -2, 'next': -1})
        self.assertEqual(line_args(resolve('fear', fear_load='0', fear_event='success'),
                                   'fear_cumulative_result')['next'], 0)
        result = resolve('stress', will='10', stress='9', deranged='9', stress_event='critical_failure')
        self.assertEqual(line_args(result, 'stress_result'), {'stress': -10, 'deranged': -10,
                                                            'penalty': -10, 'permanent': 1})
        result = resolve('stress', stress='3', deranged='2', blast=True, stress_event='failure', stress_only=True)
        self.assertEqual(line_args(result, 'stress_result'), {'stress': -3, 'deranged': -3,
                                                            'penalty': -5, 'permanent': 0})
