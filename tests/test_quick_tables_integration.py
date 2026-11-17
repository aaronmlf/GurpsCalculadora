"""Integration coverage for Quick Tables, Mapa and Tiro."""

from dataclasses import replace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from calculators.injury import CombatantState
from tests.tk_support import assert_workbench_reflow, requires_tk
from utils.i18n import t
from utils.ui_preferences import BATTLE_MAP_TOOL, QUICK_TABLES_TOOL, clean_preferences


class QuickTablesPreferencesTests(unittest.TestCase):
    def test_navigation_ids_are_stable(self):
        self.assertEqual((BATTLE_MAP_TOOL, QUICK_TABLES_TOOL), (16, 17))
        preferences = clean_preferences({
            "last_tool": QUICK_TABLES_TOOL,
            "favorites": [8, 15, BATTLE_MAP_TOOL, QUICK_TABLES_TOOL, 18],
        })
        self.assertEqual(preferences["last_tool"], QUICK_TABLES_TOOL)
        self.assertEqual(preferences["favorites"], [8, 15, 16, 17])


@requires_tk
class QuickTablesIntegrationTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator
        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"GURPS_CALCULADORA_DATA_DIR": directory}))
        self.app = GURPSCalculator()
        self.addCleanup(self.close_app)
        self.app.root.update()

    def close_app(self):
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()

    def place_pair(self, yards=7):
        app = self.app
        actor, target = app.combat_session.selected_pair()
        model = app.combat_session.battle_map.with_token(actor, 0, 0).with_token(target, yards, 0)
        app.combat_session.set_battle_map(model)
        app._battle_map_changed()
        return actor, target

    def test_read_map_lazily_and_send_raw_inputs_without_touching_session(self):
        app = self.app
        self.assertIsNone(app.quick_tables_panel)
        self.assertIsNone(app.battle_map_panel)
        self.assertIsNone(app._quick_table_map_distance())
        self.place_pair(40)
        before = app.combat_session.to_dict()
        app.ranged_speed.set("99")
        app.ranged_custom_modifier.set("2")
        app.open_quick_tables(from_map=True)
        app.root.update()
        panel = app.quick_tables_panel
        self.assertEqual(app.navigation_tree.parent(str(QUICK_TABLES_TOOL)), 'ui_game_master')
        self.assertIsNone(app.battle_map_panel)
        self.assertEqual(panel.range_result.distance_yards, 40.0)
        panel.consider_speed_var.set(True)
        panel.speed_var.set("30")
        self.assertEqual(panel.range_result.modifier, -9)
        panel.send_range()
        data = app._current_ranged_input()
        self.assertEqual(data.distance_in_yards, 40)
        self.assertAlmostEqual(data.target_speed_mps, 27.432)
        self.assertEqual(data.custom_modifier, 2)
        result = app.ranged_calc.calculate(data)
        self.assertEqual([mod["value"] for mod in result.modifiers if mod["key"] == "range_and_speed"], [-9])
        self.assertEqual(app._current_tool, 8)
        self.assertEqual(app.combat_session.to_dict(), before)

    def test_map_token_uses_pair_geometry_and_scenario_not_just_distance(self):
        app = self.app
        actor, target = self.place_pair()
        snapshot = app._quick_table_map_distance()
        model = app.combat_session.battle_map
        other = app.combat_session.add_combatant(CombatantState(identifier="other", name="Other"))
        app.combat_session.set_battle_map(model.with_token(other, 7, 0))
        app._select_encounter_role("target", other)
        self.assertEqual(app._quick_table_map_distance().distance_yards, snapshot.distance_yards)
        with self.assertRaisesRegex(ValueError, t("ranged_map_distance_stale")):
            app._send_quick_range_to_ranged(7, 0, map_snapshot=snapshot)
        app._select_encounter_role("target", target)
        app.combat_session.set_battle_map(replace(app.combat_session.battle_map, show_grid=False, cell_size=96))
        self.assertEqual(app._quick_table_map_distance(), snapshot)
        app.open_quick_tables(from_map=True)
        panel = app.quick_tables_panel
        app.combat_session.set_battle_map(model.with_token(target, 8, 0))
        app._battle_map_changed()
        self.assertTrue(panel.send_range_button.instate(["disabled"]))
        panel.pull_map_distance()
        panel.send_range()
        self.assertEqual(app._current_ranged_input().map_distance_yards, 8)
        app.combat_session.set_battle_map(model.with_token(target, 9, 0))
        app._battle_map_changed()
        with self.assertRaises(ValueError):
            app._current_ranged_input()
        app._send_quick_range_to_ranged(8, 11, consider_speed=False)
        data = app._current_ranged_input()
        self.assertIsNone(data.map_distance_yards)
        self.assertAlmostEqual(data.distance_in_yards, 8)
        self.assertEqual(data.target_speed_mps, 0)

    def test_metric_imperial_and_bilingual_rebuild_preserve_entries(self):
        app = self.app
        app.root.geometry("800x600")
        self.place_pair()
        app.open_quick_tables(from_map=True)
        app.root.update()
        panel = app.quick_tables_panel
        assert_workbench_reflow(self, panel, wide=False)
        self.assertAlmostEqual(float(panel.range_distance_entry.get()), 6.4008)
        panel.ambient_var.set("full_moon")
        panel.range_mode_var.set("sense")
        panel.consider_speed_var.set(True)
        panel.speed_var.set("4")
        self.assertEqual(panel.range_result.modifier, -1)
        self.assertTrue(panel.send_range_button.instate(["disabled"]))
        app._change_language("en_US")
        app.result_units.set("imperial")
        app._change_units()
        app.root.update()
        panel = app.quick_tables_panel
        self.assertEqual(panel.range_distance_entry.get(), "7")
        self.assertEqual(panel.range_speed_entry.get(), "4")
        self.assertEqual(panel.ambient_var.get(), "full_moon")
        self.assertEqual(panel.range_result.mode, "sense")
        self.assertEqual(panel.illumination_result.modifier, -4)
        self.assertEqual(panel.snapshot()["map_snapshot"], app._quick_table_map_distance())
        self.assertEqual(app.notebook.tab(QUICK_TABLES_TOOL, "text"), "Quick Tables")

    def test_light_provenance_and_visibility_floor_in_ranged(self):
        app = self.app
        app.open_quick_tables()
        panel = app.quick_tables_panel
        panel.ambient_var.set("full_moon")
        before = app.combat_session.to_dict()
        app.ranged_skill.set("25")
        app.ranged_distance.set("0")
        app.ranged_visibility.set("-8")
        panel.send_current_lighting()
        data = app._current_ranged_input()
        result = app.ranged_calc.calculate(data)
        modifiers = {entry["key"]: (entry["value"], entry["page"]) for entry in result.modifiers}
        self.assertEqual(modifiers["illumination"], (-4, "574"))
        self.assertEqual(modifiers["visibility"][0], -8)
        self.assertEqual(modifiers["visibility_floor"][0], +2)
        self.assertEqual(result.effective_skill, 15)
        panel.ambient_var.set("total_darkness")
        panel.send_current_lighting()
        self.assertEqual(app.ranged_calc.calculate(app._current_ranged_input()).effective_skill, 9)
        app._change_language("en_US")
        self.assertIn(t("ranged_illumination_blind"), app.ranged_illumination_note.get())
        app._ranged_clear_illumination.invoke()
        data = app._current_ranged_input()
        self.assertIsNone(data.illumination_modifier)
        self.assertFalse(data.illumination_total_darkness)
        self.assertEqual(app.ranged_visibility.get(), "-8")
        self.assertEqual(app.combat_session.to_dict(), before)
