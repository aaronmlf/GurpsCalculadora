import json
import tempfile
import unittest
from pathlib import Path

from calculators.ranged_combat import (
    DamageMode,
    RangedAttackInput,
    RangedCombatCalculator,
    WeaponRecord,
    muscle_powered_damage,
    rapid_fire_bonus,
    simplified_range_modifier,
    success_probability,
)
from utils.weapon_catalog import CATALOG_SCHEMA, WeaponCatalog


def weapon(**changes):
    values = dict(
        identifier="test.rifle",
        source="Basic Set",
        page="279",
        name="Test Rifle",
        tech_level="8",
        category="GUNS (RIFLE)",
        skills=["Guns (Rifle)"],
        damage_modes=[DamageMode("5d", "pi", half_damage_range=500, max_range=3500)],
        accuracy=5,
        rate_of_fire_modes=[12],
        shots_raw="30+1(3)",
        strength=9,
        bulk=-4,
        recoil=2,
    )
    values.update(changes)
    return WeaponRecord(**values)


class RangedCalculationTests(unittest.TestCase):
    def setUp(self):
        self.calculator = RangedCombatCalculator()

    def calculate(self, **changes):
        values = dict(weapon=weapon(), skill=14, distance_m=1, target_aware=False)
        values.update(changes)
        return self.calculator.calculate(RangedAttackInput(**values))

    def test_metric_distance_and_speed_are_combined_and_rounded_up(self):
        result = self.calculate(distance_m=9.144, target_speed_mps=9.144)
        self.assertEqual(result.distance_yards, 10)
        self.assertEqual(result.speed_yards_per_second, 10)
        self.assertEqual(result.modifiers[0]["value"], -6)

    def test_aim_timing_and_zero_second_rule(self):
        no_aim = self.calculate(aim_seconds=0)
        one = self.calculate(aim_seconds=1)
        two = self.calculate(aim_seconds=2)
        three = self.calculate(aim_seconds=3)
        self.assertNotIn("aim", [item["key"] for item in no_aim.modifiers])
        self.assertEqual(next(item["value"] for item in one.modifiers if item["key"] == "aim"), 5)
        self.assertEqual(next(item["value"] for item in two.modifiers if item["key"] == "aim"), 6)
        self.assertEqual(next(item["value"] for item in three.modifiers if item["key"] == "aim"), 7)

    def test_lost_aim_removes_acc_and_extra_time_bonus(self):
        result = self.calculate(aim_seconds=3, aim_lost=True, braced=True, scope_bonus=3)
        keys = [item["key"] for item in result.modifiers]
        self.assertIn("aim_lost", keys)
        self.assertNotIn("aim", keys)
        self.assertNotIn("braced", keys)
        self.assertNotIn("targeting_devices", keys)

    def test_bracing_and_devices_obey_double_acc_cap(self):
        result = self.calculate(aim_seconds=3, braced=True, scope_bonus=5, laser_bonus=1)
        aimed = sum(item["value"] for item in result.modifiers
                    if item["key"] in ("aim", "braced", "targeting_devices"))
        self.assertEqual(aimed, 10)

    def test_move_and_attack_uses_worse_of_minus_two_or_bulk(self):
        result = self.calculate(maneuver="move_and_attack")
        self.assertEqual(next(item["value"] for item in result.modifiers
                              if item["key"] == "move_and_attack"), -4)

    def test_cannot_see_target_caps_effective_skill_at_nine(self):
        result = self.calculate(skill=30, aim_seconds=3, cannot_see_target=True)
        self.assertEqual(result.effective_skill, 9)

    def test_range_boundaries_and_half_damage(self):
        mode = DamageMode("2d", "pi", minimum_range=5, half_damage_range=100, max_range=200)
        custom = weapon(damage_modes=[mode])
        self.assertFalse(self.calculate(weapon=custom, distance_m=4 * 0.9144).range_valid)
        self.assertFalse(self.calculate(weapon=custom, distance_m=201 * 0.9144).range_valid)
        self.assertFalse(self.calculate(weapon=custom, distance_m=100 * 0.9144).beyond_half_damage)
        self.assertTrue(self.calculate(weapon=custom, distance_m=101 * 0.9144).beyond_half_damage)

    def test_simplified_range_bands(self):
        self.assertEqual(simplified_range_modifier(5), (0, "close"))
        self.assertEqual(simplified_range_modifier(20), (-3, "short"))
        self.assertEqual(simplified_range_modifier(100), (-7, "medium"))
        self.assertEqual(simplified_range_modifier(500), (-11, "long"))
        self.assertEqual(simplified_range_modifier(501), (-15, "extreme"))

    def test_cinematic_range_does_not_leak_to_basic(self):
        basic = self.calculate(distance_m=50 * 0.9144)
        cinematic = self.calculate(profile="cinematic", distance_m=50 * 0.9144)
        self.assertEqual(basic.modifiers[0]["key"], "range_and_speed")
        self.assertEqual(cinematic.modifiers[0]["key"], "simplified_range")

    def test_profile_specific_modifiers_are_rejected_outside_profile(self):
        result = self.calculate(profile="basic", rangefinder_bonus=1, cinematic_modifier=1)
        self.assertFalse(result.valid)
        self.assertIn("realistic_rule_outside_profile", result.errors)
        self.assertIn("cinematic_rule_outside_profile", result.errors)

    def test_special_ammunition_and_moa_are_isolated_to_realistic_profile(self):
        result = self.calculate(profile="basic", ammunition="hollow_point", minute_of_angle=True)
        self.assertIn("ammunition_outside_realistic_profile", result.errors)
        self.assertIn("minute_of_angle_outside_realistic_profile", result.errors)

    def test_minute_of_angle_caps_skill_before_spatial_penalties(self):
        result = self.calculate(profile="realistic", skill=40, aim_seconds=3,
                                minute_of_angle=True)
        moa = next(item for item in result.modifiers if item["key"] == "minute_of_angle")
        self.assertEqual(moa["detail"], "32")
        self.assertEqual(result.effective_skill, 32)

    def test_match_ammunition_adds_one_to_acc_when_aiming(self):
        standard = self.calculate(profile="realistic", aim_seconds=1)
        match = self.calculate(profile="realistic", aim_seconds=1, ammunition="match")
        self.assertEqual(match.effective_skill, standard.effective_skill + 1)

    def test_success_probability_uses_all_216_outcomes(self):
        self.assertEqual(success_probability(10), 50.0)
        self.assertEqual(success_probability(3), 1.85)

    def test_all_rapid_fire_intervals(self):
        cases = {1: 0, 4: 0, 5: 1, 8: 1, 9: 2, 12: 2, 13: 3,
                 16: 3, 17: 4, 24: 4, 25: 5, 49: 5, 50: 6,
                 99: 6, 100: 7, 200: 8, 400: 9}
        for shots, expected in cases.items():
            with self.subTest(shots=shots):
                self.assertEqual(rapid_fire_bonus(shots), expected)

    def test_full_auto_only_enforces_quarter_rof_minimum(self):
        custom = weapon(full_auto_only=True, rate_of_fire_modes=[20])
        result = self.calculate(weapon=custom, shots_fired=4)
        self.assertIn("full_auto_minimum", result.errors)
        self.assertTrue(self.calculate(weapon=custom, shots_fired=5).valid)


class RangedResolutionTests(unittest.TestCase):
    def setUp(self):
        self.calculator = RangedCombatCalculator()

    def resolve(self, **changes):
        supplied_damage = changes.pop("supplied_damage", [7] * 20)
        values = dict(weapon=weapon(), skill=15, distance_m=1, shots_fired=4,
                      target_aware=False, target_dr=0)
        values.update(changes)
        return self.calculator.resolve(RangedAttackInput(**values), attack_roll=10,
                                       damage_rolls=supplied_damage)

    def test_hits_use_margin_divided_by_recoil(self):
        result = self.resolve()
        self.assertEqual(result.hits_before_defense, 3)

    def test_attack_only_resolution_does_not_roll_defense_or_damage(self):
        result = self.calculator.resolve(
            RangedAttackInput(weapon=weapon(), skill=15, distance_m=1,
                              target_aware=True, dodge=18),
            attack_roll=10,
            resolve_defense=False,
            resolve_damage=False,
        )
        self.assertIsNone(result.defense)
        self.assertEqual(result.damages, [])

    def test_dodge_margin_removes_hits_from_burst(self):
        result = self.resolve(target_aware=True, dodge=11, defense_roll=10)
        self.assertEqual(result.hits_before_defense, 3)
        self.assertEqual(result.defense["hits_avoided"], 2)
        self.assertEqual(result.hits_after_defense, 1)

    def test_critical_attack_allows_no_active_defense(self):
        result = self.calculator.resolve(
            RangedAttackInput(weapon=weapon(), skill=15, distance_m=1,
                              shots_fired=3, target_aware=True, dodge=18),
            attack_roll=4, damage_rolls=[6, 6, 6],
        )
        self.assertIsNone(result.defense)

    def test_malfunction_is_detected_from_attack_roll(self):
        custom = weapon(malfunction=16)
        result = self.calculator.resolve(
            RangedAttackInput(weapon=custom, skill=20, distance_m=1, target_aware=False),
            attack_roll=16,
        )
        self.assertTrue(result.malfunction)

    def test_half_damage_rounding_is_visible(self):
        result = self.resolve(skill=30, distance_m=501 * 0.9144, supplied_damage=[9, 9, 9])
        self.assertEqual(result.damages[0]["basic_damage"], 4)
        self.assertEqual(result.damages[0]["rounding"], "floor")

    def test_armor_divisor_and_wounding_multiplier(self):
        custom = weapon(damage_modes=[DamageMode("2d", "pi+", armor_divisor=2, max_range=1000)])
        result = self.resolve(weapon=custom, target_dr=5, supplied_damage=[9, 9, 9])
        first = result.damages[0]
        self.assertEqual(first["effective_dr"], 3)
        self.assertEqual(first["penetrating_damage"], 6)
        self.assertEqual(first["injury"], 9)

    def test_vitals_override_for_piercing_attack(self):
        result = self.resolve(hit_location="vitals", target_dr=2, supplied_damage=[8, 8, 8])
        self.assertEqual(result.damages[0]["wounding_modifier"], 3.0)
        self.assertEqual(result.damages[0]["injury"], 18)

    def test_close_shotgun_multiplies_damage_and_dr_per_shell(self):
        shotgun = weapon(
            damage_modes=[DamageMode("1d+1", "pi", half_damage_range=50, max_range=125)],
            projectiles_per_shot=9, recoil=1, rate_of_fire_modes=[2],
        )
        result = self.resolve(weapon=shotgun, distance_m=4 * 0.9144, shots_fired=1,
                              target_dr=2, supplied_damage=[8])
        first = result.damages[0]
        self.assertIn("close_shotgun", result.notes)
        self.assertEqual(result.rate_of_fire_bonus, 0)
        self.assertEqual(first["close_shotgun_multiplier"], 4)
        self.assertEqual(first["basic_damage"], 32)
        self.assertEqual(first["effective_dr"], 8)

    def test_shotgun_at_longer_range_uses_all_pellets_for_rof(self):
        shotgun = weapon(
            damage_modes=[DamageMode("1d", "pi", half_damage_range=50, max_range=125)],
            projectiles_per_shot=9, recoil=1, rate_of_fire_modes=[1],
        )
        result = self.calculator.calculate(RangedAttackInput(
            weapon=shotgun, skill=15, distance_m=10 * 0.9144, shots_fired=1,
        ))
        self.assertEqual(result.rate_of_fire_bonus, 2)

    def test_muscle_powered_damage_uses_shooter_st(self):
        bow = weapon(damage_modes=[DamageMode("thr+1", "imp", max_range=200)], strength=10)
        result = self.resolve(weapon=bow, shooter_strength=10, shots_fired=1, supplied_damage=[5])
        self.assertEqual(muscle_powered_damage(10, "thrust", 1), "1d-1")
        self.assertEqual(result.damages[0]["expression"], "1d-1")

    def test_affliction_uses_own_resistance_result(self):
        stun = weapon(damage_modes=[DamageMode("1d", "aff", resistance="HT-5(0.5) aff", max_range=20)])
        result = self.resolve(weapon=stun, shots_fired=1)
        self.assertEqual(result.damages[0]["effect_type"], "affliction")
        self.assertEqual(result.damages[0]["injury"], 0)

    def test_ultra_tech_area_and_cone_effects_use_geometry_resolver(self):
        area = weapon(damage_modes=[DamageMode(
            "2d", "burn", max_range=100, effect_shape="area", area_radius_yards=2
        )])
        outside = self.resolve(weapon=area, shots_fired=1, effect_distance_m=2,
                               supplied_damage=[10])
        cone = weapon(damage_modes=[DamageMode(
            "1d", "aff", max_range=20, resistance="HT-4 aff",
            effect_shape="cone", cone_width_yards=3
        )])
        cone_result = self.resolve(weapon=cone, shots_fired=1)
        self.assertFalse(outside.damages[0]["affected"])
        self.assertEqual(outside.damages[0]["injury"], 0)
        self.assertEqual(cone_result.damages[0]["effect_shape"], "cone")
        self.assertEqual(cone_result.damages[0]["resistance"], "HT-4 aff")

    def test_follow_up_bypasses_dr_only_when_carrier_penetrates(self):
        mode = DamageMode("2d", "pi", max_range=100,
                          follow_up=DamageMode("1d", "tox"))
        custom = weapon(damage_modes=[mode])
        penetrated = self.resolve(weapon=custom, shots_fired=1, target_dr=5,
                                  follow_up_damage_rolls=[4], supplied_damage=[8])
        stopped = self.resolve(weapon=custom, shots_fired=1, target_dr=9,
                               follow_up_damage_rolls=[4], supplied_damage=[8])
        self.assertEqual(penetrated.damages[0]["follow_up"]["effective_dr"], 0)
        self.assertEqual(penetrated.damages[0]["follow_up"]["injury"], 4)
        self.assertFalse(stopped.damages[0]["follow_up"]["applied"])

    def test_explosive_hit_uses_existing_explosion_resolver(self):
        explosive = weapon(damage_modes=[DamageMode("6d", "cr", max_range=100,
                                                     explosive=True)])
        result = self.resolve(weapon=explosive, shots_fired=1, target_dr=5,
                              supplied_damage=[21])
        explosion = result.damages[0]["explosion"]
        self.assertTrue(explosion["direct_hit"])
        self.assertEqual(explosion["collateral_damage_total"], 21)
        self.assertEqual(explosion["blast_injury"], 16)

    def test_hollow_point_changes_armor_and_piercing_class(self):
        result = self.resolve(profile="realistic", ammunition="hollow_point",
                              shots_fired=1, target_dr=2, supplied_damage=[10])
        damage = result.damages[0]
        self.assertEqual(damage["armor_divisor"], 0.5)
        self.assertEqual(damage["damage_type"], "pi+")
        self.assertEqual(damage["effective_dr"], 4)
        self.assertEqual(damage["injury"], 9)


class WeaponCatalogTests(unittest.TestCase):
    def test_embedded_catalog_has_all_four_sources_and_unique_ids(self):
        catalog = WeaponCatalog(load_user=False)
        self.assertGreaterEqual(len(catalog.weapons), 700)
        self.assertEqual({weapon.source for weapon in catalog.weapons},
                         {"Basic Set", "High-Tech", "Low-Tech", "Ultra-Tech"})
        identifiers = [weapon.identifier for weapon in catalog.weapons]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_catalog_preserves_original_notation_and_references(self):
        catalog = WeaponCatalog(load_user=False)
        self.assertTrue(all(weapon.page and weapon.source for weapon in catalog.weapons))
        self.assertTrue(all(weapon.original for weapon in catalog.weapons))
        self.assertTrue(any("+" in weapon.shots_raw for weapon in catalog.weapons))
        self.assertTrue(any(weapon.projectiles_per_shot > 1 for weapon in catalog.weapons))
        self.assertTrue(any(weapon.damage_modes[0].armor_divisor != 1 for weapon in catalog.weapons))

    def test_shots_notation_is_structured_without_losing_original(self):
        catalog = WeaponCatalog(load_user=False)
        shotgun = catalog.search("Pump Shotgun, 12G", source="Basic Set")[0]
        rifle = catalog.search("Assault Rifle, 5.56mm", source="Basic Set")[0]
        self.assertEqual((shotgun.shots_capacity, shotgun.chamber_capacity,
                          shotgun.reload_seconds, shotgun.reload_individual), (5, 0, 3, True))
        self.assertEqual((rifle.shots_capacity, rifle.chamber_capacity), (30, 1))
        self.assertEqual(rifle.shots_raw, "30+1(3)")

    def test_search_filters_by_name_source_tl_category_and_skill(self):
        catalog = WeaponCatalog(load_user=False)
        self.assertTrue(catalog.search("gauss", source="Ultra-Tech"))
        low_bows = catalog.search(tech_level="3", source="Low-Tech", skill="bow")
        self.assertTrue(low_bows)

    def test_custom_presets_are_saved_outside_builtin_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            user_path = Path(temp) / "user-weapons.json"
            catalog = WeaponCatalog(user_path=user_path, load_user=False)
            custom = weapon(identifier="temporary", name="My Test Weapon")
            catalog.save_custom(custom)
            self.assertTrue(user_path.exists())
            self.assertEqual(catalog.custom[0].identifier, "custom.my-test-weapon")
            self.assertNotEqual(user_path.resolve(), catalog.catalog_path.resolve())

    def test_invalid_json_and_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "invalid.json"
            invalid.write_text("not json", encoding="utf-8")
            catalog = WeaponCatalog(load_user=False)
            with self.assertRaises(ValueError):
                catalog.import_file(invalid)
            invalid.write_text(json.dumps({"schema": "wrong", "weapons": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                catalog.import_file(invalid)

    def test_exported_document_uses_public_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "export.json"
            catalog = WeaponCatalog(load_user=False)
            catalog.export_file(output, [catalog.weapons[0]])
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], CATALOG_SCHEMA)
            self.assertEqual(len(document["weapons"]), 1)


if __name__ == "__main__":
    unittest.main()
