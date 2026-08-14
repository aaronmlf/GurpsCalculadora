import ast
import json
import string
import unittest
from pathlib import Path
from unittest.mock import patch

from calculators.collisions import CollisionsCalculator
from calculators.combat import CombatCalculator
from calculators.explosions import ExplosionsCalculator
from calculators.falling_objects import FallingObjectsCalculator
from calculators.falls import FallsCalculator
from calculators.knockback import KnockbackCalculator
from calculators.slam import SlamCalculator
from utils.dice_roller import (
    calculate_collision_damage,
    evaluate_success_roll,
    get_damage_dice,
    get_falling_velocity,
    get_range_modifier,
    roll_dice,
)


class DamageTableTests(unittest.TestCase):
    def test_printed_damage_table_entries(self):
        self.assertEqual(get_damage_dice(10), ("1d-2", "1d"))
        self.assertEqual(get_damage_dice(20), ("2d-1", "3d+2"))
        self.assertEqual(get_damage_dice(26), ("2d+2", "5d"))
        self.assertEqual(get_damage_dice(40), ("4d+1", "7d-1"))
        self.assertEqual(get_damage_dice(100), ("11d", "13d"))

    def test_high_st_adds_one_die_per_full_ten_points(self):
        self.assertEqual(get_damage_dice(109), ("11d", "13d"))
        self.assertEqual(get_damage_dice(110), ("12d", "14d"))
        self.assertEqual(get_damage_dice(125), ("13d", "15d"))

    def test_damage_roll_never_becomes_negative(self):
        with patch("utils.dice_roller.random.randint", return_value=1):
            self.assertEqual(roll_dice("1d-6")[0], 0)

    def test_dice_parser_rejects_trailing_garbage(self):
        with self.assertRaises(ValueError):
            roll_dice("1d+1 garbage")


class SuccessRollTests(unittest.TestCase):
    def test_complete_critical_success_rules(self):
        self.assertTrue(evaluate_success_roll(15, 5)["critical_success"])
        self.assertFalse(evaluate_success_roll(14, 5)["critical_success"])
        self.assertTrue(evaluate_success_roll(16, 6)["critical_success"])

    def test_complete_critical_failure_rules(self):
        self.assertTrue(evaluate_success_roll(15, 17)["critical_failure"])
        self.assertFalse(evaluate_success_roll(16, 17)["critical_failure"])
        self.assertTrue(evaluate_success_roll(5, 15)["critical_failure"])


class CollisionAndFallTests(unittest.TestCase):
    def test_collision_fraction_breakpoints(self):
        self.assertEqual(calculate_collision_damage(10, 2)[1], "1d-3")
        self.assertEqual(calculate_collision_damage(10, 5)[1], "1d-2")
        self.assertEqual(calculate_collision_damage(10, 6)[1], "1d-1")

    def test_revised_falling_velocity_table(self):
        self.assertEqual(get_falling_velocity(17), 19)
        self.assertEqual(get_falling_velocity(61), 36)
        self.assertEqual(get_falling_velocity(100), 47)
        self.assertEqual(get_falling_velocity(112), 49)

    def test_long_fall_uses_revised_formula_and_rounding(self):
        self.assertEqual(get_falling_velocity(200), 65)

    @patch("calculators.falls.roll_dice", return_value=(12, [4, 4, 4]))
    def test_fall_rolls_damage_and_applies_blunt_trauma_only_when_stopped(self, _):
        calculator = FallsCalculator()
        penetrating = calculator.calculate_fall(10, 10, "hard", armor_dr=10)
        stopped = calculator.calculate_fall(10, 10, "hard", armor_dr=20)
        self.assertEqual(penetrating["damage_dice"], "3d")
        self.assertEqual(penetrating["damage_total"], 12)
        self.assertEqual(penetrating["penetrating_damage"], 2)
        self.assertEqual(penetrating["blunt_trauma"], 0)
        self.assertEqual(stopped["blunt_trauma"], 2)
        self.assertEqual(stopped["total_injury"], 2)

    def test_acrobatics_can_reduce_a_short_fall_to_zero(self):
        result = FallsCalculator().calculate_fall(5, 10, acrobatics_success=True)
        self.assertEqual(result["distance_yards"], 0)
        self.assertEqual(result["total_injury"], 0)

    @patch("calculators.collisions.roll_dice", side_effect=[(7, []), (14, [])])
    def test_hard_immovable_object_uses_twice_moving_hp(self, _):
        result = CollisionsCalculator().calculate_collision(
            10, 20, 1000, 0, "side_on", "hard", True
        )
        self.assertEqual(result["object1_damage_dice"], "2d")
        self.assertEqual(result["object2_damage_dice"], "4d")

    @patch("calculators.collisions.roll_dice", side_effect=[(30, []), (10, [])])
    def test_breakable_obstacle_caps_damage_at_hp_plus_dr(self, _):
        result = CollisionsCalculator().calculate_collision(
            100, 30, 5, 0, "side_on", "hard", True,
            object2_dr=2, obstacle_breakable=True
        )
        self.assertEqual(result["damage_cap"], 7)
        self.assertEqual(result["object1_damage_total"], 7)
        self.assertEqual(result["object2_damage_total"], 7)

    @patch("calculators.collisions.roll_dice", side_effect=[(9, []), (8, [])])
    def test_slower_head_on_object_cannot_inflict_more_dice(self, _):
        result = CollisionsCalculator().calculate_collision(100, 10, 10, 20)
        self.assertEqual(result["object1_damage_dice"], "3d")
        self.assertEqual(result["object2_damage_dice"], "3d")


class CombatAndKnockbackTests(unittest.TestCase):
    def test_st_three_knockback_is_one_yard_per_damage(self):
        result = KnockbackCalculator().calculate_knockback(
            "crushing", 8, 3, target_hp=10
        )
        self.assertEqual(result["yards_back"], 8)

    def test_hp_replaces_st_only_for_target_without_st(self):
        result = KnockbackCalculator().calculate_knockback(
            "crushing", 16, None, target_hp=10
        )
        self.assertEqual(result["yards_back"], 2)

    def test_injury_rounds_down_but_has_minimum_one(self):
        calculator = CombatCalculator()
        self.assertEqual(calculator.calculate_injury(5, "cutting"), 7)
        self.assertEqual(calculator.calculate_injury(1, "small_piercing"), 1)
        self.assertEqual(calculator.calculate_injury(0, "impaling"), 0)

    def test_shield_db_applies_to_block(self):
        self.assertEqual(CombatCalculator().calculate_block(11, 2)["block"], 10)

    def test_fencing_retreat_bonus_only_applies_when_retreating(self):
        calculator = CombatCalculator()
        self.assertEqual(calculator.calculate_parry(14, is_fencing=True)["parry"], 10)
        self.assertEqual(
            calculator.calculate_parry(14, is_fencing=True, retreat=True)["parry"], 13
        )

    @patch("calculators.slam.roll_dice", side_effect=[(10, []), (6, [])])
    def test_slam_requires_defender_dx_roll_without_false_attacker_roll(self, _):
        result = SlamCalculator().calculate_slam(10, 10, 10, 0, "side_on")
        self.assertTrue(result["defender_dx_roll_required"])
        self.assertFalse(result["attacker_dx_roll_required"])
        self.assertFalse(result["attacker_fall"])

    @patch("calculators.slam.roll_dice", side_effect=[(6, []), (10, [])])
    def test_slam_defender_winning_by_less_than_double_causes_no_fall(self, _):
        result = SlamCalculator().calculate_slam(10, 10, 10, 0, "side_on")
        self.assertEqual(result["outcome"], "no_knockdown")


class ExplosionAndDroppingTests(unittest.TestCase):
    @patch("calculators.explosions.roll_dice", side_effect=[(18, []), (8, [])])
    @patch("calculators.explosions.roll_3d6", return_value=(9, [3, 3, 3]))
    def test_fragmentation_is_damage_per_hit_with_separate_dr(self, _, __):
        result = ExplosionsCalculator().calculate_explosion(
            6, 2, 10, target_dr=2, fragment_attack_roll=9
        )
        self.assertEqual(result["fragment_attack_skill"], 11)
        self.assertEqual(result["fragment_hits"], 1)
        self.assertEqual(result["fragment_damage_dice"], "2d")
        self.assertEqual(result["fragment_injury_total"], 9)

    @patch("calculators.explosions.roll_dice", return_value=(21, []))
    def test_direct_hit_takes_full_blast_damage(self, _):
        result = ExplosionsCalculator().calculate_explosion(
            6, 0, 0, target_dr=5, direct_hit=True
        )
        self.assertEqual(result["collateral_damage_total"], 21)
        self.assertEqual(result["blast_injury"], 16)

    def test_explosive_damage_keeps_fractional_multiplier(self):
        result = ExplosionsCalculator().calculate_explosive_damage(0.0625, "tnt")
        self.assertEqual(result["damage_expression"], "6d×0.5")

    def test_demolition_example_uses_ref(self):
        result = ExplosionsCalculator().calculate_demolition_charge(48, "dynamite")
        self.assertEqual(result["weight_actual_lbs"], 20)

    @patch("calculators.falling_objects.roll_dice", return_value=(9, []))
    def test_dropping_requires_attack_and_allows_aware_target_to_dodge(self, _):
        result = FallingObjectsCalculator().calculate_falling_object(
            10, 10, 10, target_aware=True, dropping_skill=15,
            target_dodge=10, attack_roll=8, dodge_roll=9
        )
        self.assertTrue(result["attack_success"])
        self.assertTrue(result["dodge_success"])
        self.assertFalse(result["hit"])
        self.assertEqual(result["damage_total"], 0)

    def test_size_and_speed_range_modifier(self):
        self.assertEqual(get_range_modifier(2), 0)
        self.assertEqual(get_range_modifier(10), -4)
        self.assertEqual(get_range_modifier(100), -10)


class TranslationTests(unittest.TestCase):
    def test_languages_have_identical_keys_and_placeholders(self):
        root = Path(__file__).resolve().parents[1]
        pt = json.loads((root / "i18n" / "pt_BR.json").read_text(encoding="utf-8"))
        en = json.loads((root / "i18n" / "en_US.json").read_text(encoding="utf-8"))
        self.assertEqual(set(pt), set(en))
        formatter = string.Formatter()
        for key in pt:
            pt_fields = {name for _, name, _, _ in formatter.parse(pt[key]) if name}
            en_fields = {name for _, name, _, _ in formatter.parse(en[key]) if name}
            self.assertEqual(pt_fields, en_fields, key)

    def test_english_uses_basic_set_terms(self):
        root = Path(__file__).resolve().parents[1]
        en = json.loads((root / "i18n" / "en_US.json").read_text(encoding="utf-8"))
        self.assertEqual(en["tab_slam"], "Slam")
        self.assertIn("Active Defense", en["combat_defense"])
        self.assertIn("Size Modifier (SM)", en["explosions_target_sm"])

    def test_every_literal_ui_translation_key_exists(self):
        root = Path(__file__).resolve().parents[1]
        en = json.loads((root / "i18n" / "en_US.json").read_text(encoding="utf-8"))
        tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
        keys = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "t"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        self.assertEqual(keys - set(en), set())


if __name__ == "__main__":
    unittest.main()
