import unittest
from utils.units import UnitSystem


class UnitTests(unittest.TestCase):
    def test_exact_boundaries(self):
        metric = UnitSystem("metric")
        self.assertEqual(metric.display(1, "yards"), "0.9144 m")
        self.assertEqual(metric.to_rules(0.45359237, "pounds"), 1)
        self.assertEqual(UnitSystem("imperial").display(20, "pounds"), "20 lb")

    def test_round_trip_without_display_rounding(self):
        for name, factor in (("yards", 0.9144), ("pounds", 0.45359237), ("miles", 1.609344)):
            self.assertAlmostEqual(UnitSystem().to_rules(123.456 * factor, name), 123.456)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            UnitSystem("unknown")
        with self.assertRaises(ValueError):
            UnitSystem().display(float("nan"), "yards")
