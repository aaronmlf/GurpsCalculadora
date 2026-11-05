"""Only bounded, validated expressions are saved; individual dice stay in RAM."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from utils.gm_dice import DiceRollError
from utils.gm_dice_preferences import DiceExpressions, FAVORITES_LIMIT, RECENT_LIMIT


class DiceExpressionPreferencesTests(unittest.TestCase):
    def test_normalizes_deduplicates_and_discards_invalid_saved_values(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'dice_expressions.json'
            path.write_text(json.dumps({'schema': 1,
                                        'favorites': ['3 D + 2', '3d6+2', '0d6', None, '104d6+20'],
                                        'recent': ['1d6; 2', '2d20-1', '2D20 - 1']}), encoding='utf-8')
            saved = DiceExpressions.load(path)
            self.assertEqual(saved.favorites, ('3d6+2', '104d6+20'))
            self.assertEqual(saved.recent, ('2d20-1',))
            saved = saved.remember('10000000d6').toggle_favorite(' 3d+2 ')
            saved.save(path)
            self.assertEqual(DiceExpressions.load(path), saved)
            self.assertEqual(saved.favorites, ('104d6+20',))
            self.assertEqual(saved.recent[0], '10000000d6')
            self.assertLess(path.stat().st_size, 300)

    def test_recent_is_most_recent_first_and_favorites_are_not_silently_evicted(self):
        state = DiceExpressions()
        for index in range(RECENT_LIMIT + 4):
            state = state.remember(f'{index + 1}d6')
        last = state.recent[-1]
        state = state.remember(last)
        self.assertEqual(len(state.recent), RECENT_LIMIT)
        self.assertEqual(state.recent[0], last)
        self.assertEqual(state.recent.count(last), 1)
        for index in range(FAVORITES_LIMIT):
            state = state.toggle_favorite(f'{index + 1}d6')
        with self.assertRaises(DiceRollError) as error:
            state.toggle_favorite('10000000d6')
        self.assertEqual(error.exception.code, 'favorite_limit')
        self.assertIn('1d6', state.favorites)

    def test_corrupt_or_oversized_file_is_read_without_mutating_it(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'dice_expressions.json'
            for malformed in ('not json', ' ' * 20_000, '{"schema": 99}'):
                path.write_text(malformed, encoding='utf-8')
                self.assertEqual(DiceExpressions.load(path), DiceExpressions())
                self.assertEqual(path.read_text(encoding='utf-8'), malformed)
