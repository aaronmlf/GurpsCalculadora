import math
import sys
import unittest

from calculators.ranged_combat import RangedAttackInput, RangedCombatCalculator
from tests.test_ranged_combat import weapon
from utils.dice_roller import get_range_band, get_range_modifier
from utils.quick_tables import ILLUMINATION_PRESETS, calculate_illumination, calculate_speed_range


class QuickIlluminationTests(unittest.TestCase):
    def test_stable_presets_cover_the_reference_levels(self):
        presets = {preset.key: preset for preset in ILLUMINATION_PRESETS}
        self.assertEqual(len(presets), len(ILLUMINATION_PRESETS))
        self.assertEqual({preset.modifier for preset in presets.values() if preset.kind == 'ambient'},
                         set(range(-10, 1)))
        self.assertEqual({preset.key for preset in presets.values() if preset.high_latitude_sensitive},
                         {'quarter_moon', 'half_moon', 'full_moon'})
        for key, preset in presets.items():
            with self.subTest(preset=key):
                if preset.kind == 'ambient':
                    self.assertEqual(calculate_illumination(key).modifier, preset.modifier)
                else:
                    self.assertEqual(calculate_illumination('total_darkness', key).modifier, preset.modifier)

    def test_revised_candle_example_and_boundaries(self):
        for distance, expected in ((0, -3), (1, -3), (math.nextafter(1.0, math.inf), -3),
                                   (1.001, -4), (2, -4), (2.001, -5), (5, -5),
                                   (5.001, -6), (7, -6), (10, -6), (10.001, -7), (1e100, -10)):
            with self.subTest(distance=distance):
                result = calculate_illumination('total_darkness', 'candle', distance)
                self.assertEqual(result.modifier, expected)
                self.assertEqual(result.page, 574)
                self.assertEqual(result.total_darkness, expected == -10)

    def test_point_light_never_makes_ambient_darker(self):
        result = calculate_illumination('twilight', 'candle', 100)
        self.assertEqual((result.ambient_modifier, result.point_modifier, result.point_distance_modifier),
                         (-2, -9, -6))
        self.assertEqual((result.chosen_modifier, result.modifier, result.point_used), (-2, -2, False))
        result = calculate_illumination('quarter_moon', 'quality_flashlight', 2)
        self.assertEqual((result.chosen_modifier, result.point_distance_modifier, result.point_used), (-1, -1, True))

    def test_cloud_and_polar_dimming_do_not_apply_to_unmarked_presets(self):
        result = calculate_illumination('full_moon', heavy_cloud=True, polar_moonlight=True)
        self.assertEqual((result.ambient_modifier, result.cloud_modifier, result.polar_modifier, result.modifier),
                         (-4, -1, -1, -6))
        result = calculate_illumination('twilight', heavy_cloud=True, polar_moonlight=True)
        self.assertEqual((result.cloud_modifier, result.polar_modifier, result.modifier), (-1, 0, -3))
        for key in ('clouded_starlight', 'overcast_moonless', 'daylight', 'main_street_lights'):
            with self.subTest(preset=key):
                result = calculate_illumination(key, heavy_cloud=True, polar_moonlight=True)
                self.assertEqual((result.cloud_modifier, result.polar_modifier), (0, 0))

    def test_environment_penalties_stop_at_minus_ten_and_adaptation_expires(self):
        before = calculate_illumination('starlight', flicker=3, sudden_dimming_steps=2,
                                        adaptation_elapsed_minutes=3.99)
        self.assertEqual((before.modifier, before.flicker_modifier, before.adaptation_modifier), (-10, -3, -2))
        self.assertEqual(before.adaptation_required_minutes, 4)
        self.assertFalse(before.total_darkness)  # Numeric cap is distinct from no light.
        after = calculate_illumination('starlight', flicker=1, sudden_dimming_steps=2,
                                       adaptation_elapsed_minutes=4)
        self.assertEqual((after.modifier, after.adaptation_modifier), (-8, 0))

    def test_rejects_wrong_preset_kind_and_invalid_inputs(self):
        for ambient, point in (('bad', None), ('candle', None), ('daylight', 'daylight'), ([], 'candle')):
            with self.subTest(ambient=ambient, point=point), self.assertRaisesRegex(ValueError, 'invalid_option'):
                calculate_illumination(ambient, point)
        for key, invalid in (('flicker', 4), ('flicker', -1), ('flicker', 1.0), ('heavy_cloud', 1),
                             ('polar_moonlight', 'true'), ('sudden_dimming_steps', 11), ('sudden_dimming_steps', True)):
            with self.subTest(parameter=key, invalid=invalid), self.assertRaisesRegex(ValueError, 'invalid_option'):
                calculate_illumination('daylight', **{key: invalid})
        for invalid in (-1, '2', True, math.inf, math.nan, 10**500):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'invalid_number'):
                calculate_illumination('daylight', 'candle', invalid)
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'invalid_number'):
                calculate_illumination('daylight', adaptation_elapsed_minutes=invalid)


class QuickSpeedRangeTests(unittest.TestCase):
    def test_attack_adds_optional_speed_and_sense_subtracts_it(self):
        base = calculate_speed_range(40, 30)
        self.assertEqual((base.page, base.modifier, base.speed_adjustment, base.lookup_yards), (550, -8, 0, 40))
        self.assertEqual((base.distance_yards, base.speed_yps, base.consider_speed), (40, 30, False))
        fast = calculate_speed_range(40, 30, consider_speed=True)
        self.assertEqual((fast.page, fast.modifier, fast.speed_adjustment, fast.lookup_yards), (550, -9, 30, 70))
        sense = calculate_speed_range(40, 30, mode='sense', consider_speed=True)
        self.assertEqual((sense.page, sense.modifier, sense.speed_adjustment, sense.lookup_yards), (551, -4, -30, 10))
        sense = calculate_speed_range(10, 40, mode='sense', consider_speed=True)
        self.assertEqual((sense.effective_yards, sense.lookup_yards, sense.modifier), (0, 0, 0))
        sense = calculate_speed_range(40, 80, mode='sense')
        self.assertEqual((sense.effective_yards, sense.lookup_yards, sense.modifier), (40, 40, -8))

    def test_revised_examples_and_extended_progression(self):
        self.assertEqual(calculate_speed_range(8).modifier, -4)
        self.assertEqual(calculate_speed_range(5, 1000, consider_speed=True).modifier, -17)
        self.assertEqual(calculate_speed_range(200000).modifier, -30)
        self.assertEqual(calculate_speed_range(300000).modifier, -31)
        self.assertEqual(calculate_speed_range(2000000).modifier, -36)
        self.assertEqual(calculate_speed_range(20000000).modifier, -42)

    def test_gets_real_band_upper_limit_instead_of_the_rounded_probe(self):
        for distance, probe, modifier, band_limit in ((0, 0, 0, 2), (2.01, 3, -1, 3), (7.1, 8, -4, 10),
                                                       (8, 8, -4, 10), (40, 40, -8, 50),
                                                       (200001, 200001, -31, 300000)):
            with self.subTest(distance=distance):
                result = calculate_speed_range(distance)
                self.assertEqual((result.lookup_yards, result.modifier, result.band_limit_yards),
                                 (probe, modifier, band_limit))
                self.assertEqual(get_range_band(probe), (modifier, band_limit))
                self.assertEqual(get_range_modifier(probe), modifier)

    def test_extreme_finite_distance_uses_an_integer_band_limit(self):
        for distance in (1e308, sys.float_info.max):
            with self.subTest(distance=distance):
                result = calculate_speed_range(distance)
                self.assertEqual(result.distance_yards, distance)
                self.assertLess(result.modifier, -1000)
                self.assertIs(type(result.band_limit_yards), int)
                self.assertGreaterEqual(result.band_limit_yards, result.lookup_yards)
                self.assertEqual(get_range_band(result.band_limit_yards), (result.modifier, result.band_limit_yards))
        self.assertEqual(calculate_speed_range(sys.float_info.max).band_limit_yards, 2 * 10**308)
        for invalid in (math.inf, -math.inf, math.nan):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                get_range_band(invalid)

    def test_boundaries_match_ranged_calculator_after_metric_conversion(self):
        engine = RangedCombatCalculator()
        reference_weapon = weapon()
        for distance, skill_modifier in ((0, 0), (2, 0), (2.00001, -1), (3, -1), (5, -2),
                                         (0.14 * 50, -3), (7.000001, -4), (10, -4), (15, -5), (20, -6)):
            with self.subTest(distance=distance):
                quick = calculate_speed_range(distance).modifier
                ranged = engine.calculate(RangedAttackInput(weapon=reference_weapon, skill=16,
                                                             distance_m=distance * 0.9144))
                actual = next(part['value'] for part in ranged.modifiers if part['key'] == 'range_and_speed')
                self.assertEqual(quick, skill_modifier)
                self.assertEqual(actual, skill_modifier)

    def test_rejects_negative_nonfinite_and_overflowing_values(self):
        for invalid in (-0.000001, True, '2', math.inf, math.nan, 10**500):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'invalid_number'):
                calculate_speed_range(invalid)
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'invalid_number'):
                calculate_speed_range(0, invalid, consider_speed=True)
        with self.assertRaisesRegex(ValueError, 'invalid_number'):
            calculate_speed_range(1e308, 1e308, consider_speed=True)
        with self.assertRaisesRegex(ValueError, 'invalid_option'):
            calculate_speed_range(1, mode='magic')
        with self.assertRaisesRegex(ValueError, 'invalid_option'):
            calculate_speed_range(1, consider_speed=1)


if __name__ == '__main__':
    unittest.main()
