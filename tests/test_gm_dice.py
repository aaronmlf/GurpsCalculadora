"""Tests for a GM's independent dice sum, rather than a damage calculator."""

from dataclasses import FrozenInstanceError
import random
import unittest
from unittest.mock import Mock

from utils.gm_dice import (
    DiceRollError,
    MAX_DICE,
    MAX_MODIFIER,
    MAX_SIDES,
    parse_dice,
    roll_dice,
)


class GMDiceTests(unittest.TestCase):
    def test_104_dice_preserve_each_detail_and_sum(self):
        values = tuple(index % 6 + 1 for index in range(104))
        result = roll_dice("104d6+20", values=values)
        self.assertEqual(result.expression, "104d6+20")
        self.assertEqual((result.count, result.sides, result.modifier), (104, 6, 20))
        self.assertEqual(result.rolls, values)
        self.assertEqual(result.subtotal, sum(values))
        self.assertEqual(result.total, sum(values) + 20)
        with self.assertRaises(FrozenInstanceError):
            result.total = 0

    def test_gurps_shorthand_whitespace_and_case(self):
        result = roll_dice(" 3 D - 2 ", values=[1, 3, 6])
        self.assertEqual(result.expression, "3d6-2")
        self.assertEqual(result.total, 8)
        self.assertEqual(parse_dice("3d").sides, 6)

    def test_general_sum_retains_negative_and_zero_totals(self):
        self.assertEqual(roll_dice("1d6-20", values=[1]).total, -19)
        self.assertEqual(roll_dice("1d6-1", values=[1]).total, 0)

    def test_other_die_sizes_and_injected_randomness(self):
        first = roll_dice("8d20+3", rng=random.Random(17))
        second = roll_dice("8d20+3", rng=random.Random(17))
        self.assertEqual(first, second)
        self.assertEqual(len(first.rolls), 8)
        self.assertTrue(all(1 <= value <= 20 for value in first.rolls))
        self.assertEqual(first.total, sum(first.rolls) + 3)

    def test_each_random_roll_receives_the_requested_size(self):
        source = Mock()
        source.randint.side_effect = [2, 8, 12]
        result = roll_dice("3d12", rng=source)
        self.assertEqual(result.rolls, (2, 8, 12))
        self.assertEqual(source.randint.call_count, 3)
        source.randint.assert_called_with(1, 12)

    def test_invalid_expressions_never_consume_randomness(self):
        source = Mock()
        invalid = (
            "", "d6", "1 0d6", "3d6+", "3d6+-2", "3d6+2d6", "3d6*2",
            "3d6/2", "(3d6)", "__import__('os').system('x')", "3d6; print(1)",
            "٣d6", "1d6\n2d6", "9" * 129, None,
        )
        for expression in invalid:
            with self.subTest(expression=expression):
                with self.assertRaises(DiceRollError) as caught:
                    roll_dice(expression, rng=source)
                self.assertEqual(caught.exception.code, "invalid_expression")
        source.randint.assert_not_called()

    def test_numeric_bounds_and_long_fields(self):
        invalid = {
            "0d6": "dice_count",
            f"{MAX_DICE + 1}d6": "dice_count",
            "000000000d6": "dice_count",
            "1d0": "dice_sides",
            f"1d{MAX_SIDES + 1}": "dice_sides",
            "1d99999999999999999999": "dice_sides",
            f"1d6+{MAX_MODIFIER + 1}": "dice_modifier",
            f"1d6-{MAX_MODIFIER + 1}": "dice_modifier",
            "1d6+00000000000": "dice_modifier",
        }
        source = Mock()
        for expression, code in invalid.items():
            with self.subTest(expression=expression):
                with self.assertRaises(DiceRollError) as caught:
                    roll_dice(expression, rng=source)
                self.assertEqual(caught.exception.code, code)
        source.randint.assert_not_called()

    def test_exact_upper_bounds_are_allowed(self):
        parsed = parse_dice(f"{MAX_DICE}d{MAX_SIDES}-{MAX_MODIFIER}")
        self.assertEqual((parsed.count, parsed.sides, parsed.modifier),
                         (MAX_DICE, MAX_SIDES, -MAX_MODIFIER))
        self.assertEqual(parse_dice(f"{MAX_DICE}d1").count, MAX_DICE)

    def test_explicit_values_validate_before_randomness(self):
        source = Mock()
        for values in ([1], [1, 2, 3], [0, 1], [1, 7], [True, 1], [1.0, 1], 4):
            with self.subTest(values=values):
                with self.assertRaises(DiceRollError) as caught:
                    roll_dice("2d6", values=values, rng=source)
                self.assertEqual(caught.exception.code, "explicit_rolls")
        self.assertEqual(roll_dice("2d6", values=[3, 6], rng=source).total, 9)
        source.randint.assert_not_called()

    def test_explicit_infinite_values_are_consumed_only_to_limit(self):
        from itertools import repeat
        with self.assertRaises(DiceRollError):
            roll_dice("2d6", values=repeat(1))

    def test_large_rolls_retain_details_in_compact_readonly_storage(self):
        count = 100_001
        values = (index % 6 + 1 for index in range(count))
        result = roll_dice(f"{count}d6+20", values=values)
        self.assertIsInstance(result.rolls, memoryview)
        self.assertTrue(result.rolls.readonly)
        self.assertEqual(result.rolls.nbytes, count * 4)
        self.assertEqual(len(result.rolls), count)
        self.assertEqual(tuple(result.rolls[:8]), (1, 2, 3, 4, 5, 6, 1, 2))
        self.assertEqual(result.rolls[-1], count % 6 or 6)
        self.assertEqual(result.subtotal, (count // 6) * 21 + sum(range(1, count % 6 + 1)))
        self.assertEqual(result.total, result.subtotal + 20)
        with self.assertRaises(TypeError):
            result.rolls[0] = 6

    def test_progress_fires_per_chunk_and_at_completion(self):
        from itertools import repeat
        updates = []
        result = roll_dice("25001d1", values=repeat(1, 25001),
                           progress=lambda done, total: updates.append((done, total)))
        self.assertEqual(result.total, 25001)
        self.assertEqual(updates, [(10000, 25001), (20000, 25001), (25001, 25001)])

    def test_cancellation_stops_before_remaining_randomness(self):
        from threading import Event
        cancelled = Event()
        source = Mock()
        source.randint.return_value = 1
        updates = []
        def progressed(done, total):
            updates.append((done, total))
            cancelled.set()
        with self.assertRaises(DiceRollError) as caught:
            roll_dice("100000d6", rng=source, progress=progressed,
                      should_cancel=cancelled.is_set)
        self.assertEqual(caught.exception.code, "cancelled")
        self.assertEqual(source.randint.call_count, 10000)
        self.assertEqual(updates, [(10000, 100000)])

    def test_cancelled_start_does_not_consume_randomness_and_validation_still_first(self):
        source = Mock()
        with self.assertRaises(DiceRollError) as caught:
            roll_dice("100000d6", rng=source, should_cancel=lambda: True)
        self.assertEqual(caught.exception.code, "cancelled")
        with self.assertRaises(DiceRollError) as caught:
            roll_dice("broken", rng=source, should_cancel=lambda: True)
        self.assertEqual(caught.exception.code, "invalid_expression")
        source.randint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
