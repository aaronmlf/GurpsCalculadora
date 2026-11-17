"""Integration checks for the Mapa → Cenários / Tiro workflow."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculators.combat_session import CombatSession
from calculators.injury import CombatantState
from tests.tk_support import requires_tk
from utils.dice_roller import get_range_modifier
from utils.i18n import t
from utils.ui_preferences import BATTLE_MAP_TOOL, QUICK_TABLES_TOOL, clean_preferences


class BattleMapPreferencesTests(unittest.TestCase):
    def test_map_tool_can_be_restored_without_changing_old_tool_indices(self):
        preferences = clean_preferences({
            "last_tool": BATTLE_MAP_TOOL,
            "favorites": [8, 15, BATTLE_MAP_TOOL, 2000],
        })
        self.assertEqual(preferences["last_tool"], BATTLE_MAP_TOOL)
        self.assertEqual(preferences["favorites"], [8, 15, BATTLE_MAP_TOOL])


@requires_tk
class BattleMapIntegrationTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict("os.environ", {"GURPS_CALCULADORA_DATA_DIR": directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = GURPSCalculator()
        self.addCleanup(self._close)
        self.app.root.update()

    def _close(self):
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()

    def _place_pair(self):
        app = self.app
        actor, target = app.combat_session.selected_pair()
        model = app.combat_session.battle_map
        model = model.with_token(actor, 0, 0, visible=True).with_token(target, 7, 0, visible=False)
        app.combat_session.set_battle_map(model)
        app._battle_map_changed()
        return actor, target, model

    def test_map_loads_only_when_used_and_transfer_keeps_seven_yards_exact(self):
        app = self.app
        self.assertIsNone(app.battle_map_panel)
        app.choose_tool(BATTLE_MAP_TOOL)
        app.root.update()
        self.assertEqual(app.notebook.tab(BATTLE_MAP_TOOL, "text"), t("tab_battle_map"))
        self.assertIsNotNone(app.battle_map_panel)
        self.assertTrue(app.battle_map_panel.canvas.winfo_ismapped())
        self.assertTrue(app.navigation_tree.exists(str(BATTLE_MAP_TOOL)))
        actor, target, _ = self._place_pair()
        app.ranged_skill.set("16")
        app.ranged_speed.set("0")
        app.ranged_cover.set("-1")
        app.ranged_half_damage.set("7")
        app.ranged_max_range.set("7")
        app._send_map_distance_to_ranged(actor, target, 7)
        app.root.update()
        self.assertEqual(app._current_tool, 8)
        self.assertEqual((app.session_actor_key, app.session_target_key), (actor, target))
        data = app._current_ranged_input()
        self.assertEqual(data.distance_in_yards, 7)
        self.assertAlmostEqual(data.distance_m, 6.4008)
        self.assertEqual((data.skill, data.cover_modifier), (16, -1))
        outcome = app.ranged_calc.calculate(data)
        self.assertTrue(outcome.range_valid)
        self.assertFalse(outcome.beyond_half_damage)
        modifier = next(item for item in outcome.modifiers if item["key"] == "range_and_speed")
        self.assertEqual(modifier["value"], get_range_modifier(7))
        self.assertIn("6.4008 m", app.ranged_map_hint.get())
        app.result_units.set("imperial")
        app._change_units()
        app._change_language("en_US")
        self.assertIn("7 yd", app.ranged_map_hint.get())
        self.assertEqual(app._current_ranged_input().distance_in_yards, 7)

    def test_changed_positions_mark_copy_stale_and_manual_edit_unlinks(self):
        app = self.app
        actor, target, model = self._place_pair()
        app._send_map_distance_to_ranged(actor, target, 7)
        app.combat_session.set_battle_map(model.with_token(target, 8, 0))
        app._battle_map_changed()
        self.assertIn(t("ranged_map_distance_stale"), app.ranged_map_hint.get())
        with self.assertRaises(ValueError) as error:
            app._current_ranged_input()
        self.assertEqual(str(error.exception), t("ranged_map_distance_stale"))
        with self.assertRaisesRegex(ValueError, "map_settings_stale"):
            app._send_map_distance_to_ranged(actor, target, 7)
        app.ranged_distance.set("1.8288")
        self.assertEqual(app.ranged_map_hint.get(), "")
        self.assertIsNone(app._current_ranged_input().map_distance_yards)

    def test_transfers_reveal_the_new_distance_at_narrow_width(self):
        app = self.app
        app.root.geometry('800x600')
        app.ui_preferences['font_size'] = 18
        app._change_language('pt_BR')
        app.choose_tool(8)
        app.root.update()
        ranged = app.ranged_layout
        ranged.canvas.yview_moveto(1)
        app.root.update()

        def assert_within_view(widget, canvas):
            self.assertTrue(widget.winfo_ismapped())
            y = widget.winfo_rooty() - canvas.winfo_rooty()
            self.assertGreaterEqual(y, -1)
            self.assertLessEqual(y + widget.winfo_height(), canvas.winfo_height())

        self.assertLess(app._ranged_distance_field.winfo_rooty(), ranged.canvas.winfo_rooty())
        app.choose_tool(BATTLE_MAP_TOOL)
        self._place_pair()
        app.battle_map_panel.send_button.invoke()
        app.root.update()
        self.assertEqual(app._current_tool, 8)
        assert_within_view(app._ranged_distance_field, ranged.canvas)
        assert_within_view(app.ranged_map_hint_label, ranged.canvas)

        ranged.canvas.yview_moveto(1)
        app.choose_tool(BATTLE_MAP_TOOL)
        app.open_quick_tables(from_map=True)
        app.root.update()
        self.assertEqual(app._current_tool, QUICK_TABLES_TOOL)
        tables = app.quick_tables_panel
        self.assertEqual(float(tables.distance_var.get()), 7)
        assert_within_view(tables.range_distance_entry, tables.canvas)
        tables.send_range_button.invoke()
        app.root.update()
        self.assertEqual(app._current_tool, 8)
        assert_within_view(app._ranged_distance_field, ranged.canvas)
        self.assertEqual(app._current_ranged_input().distance_in_yards, 7)

    def test_stale_measurement_blocks_all_shot_actions_for_a_new_target(self):
        app = self.app
        actor, target, model = self._place_pair()
        third = app.combat_session.add_combatant(CombatantState(identifier="vigia", name="Vigia"))
        app.combat_session.set_battle_map(model.with_token(third, 120, 0))
        app.ranged_max_range.set("7")
        app.ranged_skill.set("16")
        app._send_map_distance_to_ranged(actor, target, 7)
        app._select_encounter_role("target", third)
        with (patch("main.messagebox.showerror") as error,
              patch.object(app.ranged_calc, "calculate") as calculate,
              patch.object(app.ranged_calc, "resolve") as resolve):
            for action in ("calculate", "attack", "resolve"):
                app._run_ranged(action)
            calculate.assert_not_called()
            resolve.assert_not_called()
            self.assertEqual(error.call_count, 3)
            self.assertEqual(error.call_args.args[1], t("ranged_map_distance_stale"))
        self.assertEqual(app._ranged_drafts, {})
        self.assertEqual(app.combat_session.combatants[third].current_hp, 10)
        app._send_map_distance_to_ranged(actor, third, 120)
        data = app._current_ranged_input()
        self.assertEqual(data.distance_in_yards, 120)
        self.assertFalse(app.ranged_calc.calculate(data).range_valid)

    def test_visual_grid_changes_do_not_invalidate_a_ranged_result(self):
        app = self.app
        actor, target, model = self._place_pair()
        app._send_map_distance_to_ranged(actor, target, 7)
        app._run_ranged("calculate")
        app.root.update()
        self.assertFalse(app.ranged_result_text.stale)
        hint = app.ranged_map_hint.get()
        app.combat_session.set_battle_map(replace(model, show_grid=False, cell_size=96, origin_x=5))
        app._battle_map_changed()
        app.root.update()
        self.assertEqual(app.ranged_map_hint.get(), hint)
        self.assertFalse(app.ranged_result_text.stale)
        self.assertEqual(app._current_ranged_input().distance_in_yards, 7)

    def test_ranged_result_displays_distances_just_outside_the_limit(self):
        app = self.app
        actor, target, model = self._place_pair()
        model = replace(model.with_token(target, 50, 0), yards_per_cell=0.14000002)
        app.combat_session.set_battle_map(model)
        app.ranged_max_range.set("7")
        app.result_units.set("imperial")
        app._send_map_distance_to_ranged(actor, target, model.distance_yards(0, 0, 50, 0))
        app._run_ranged("calculate")
        self.assertIn("7.000001 yd", app.ranged_map_hint.get())
        result = app.ranged_result_text.get("1.0", "end")
        self.assertIn(t("ranged_range_result", meters="6.4008009144", yards="7.000001",
                        valid=t("common_no")), result)

    def test_named_scenario_restores_map_and_resets_transfer_context(self):
        app = self.app
        actor, target, original = self._place_pair()
        app.combat_library.save_session("Ponte", app.combat_session)
        app.combat_session.set_battle_map(original.with_token(target, 9, 0, visible=True))
        app.ranged_distance.set("3.25")
        app._send_map_distance_to_ranged(actor, target, 9)
        app.combat_session.set_battle_map(original.with_token(target, 10, 0))
        app._send_map_distance_to_ranged(actor, target, 10)
        copy = app.combat_library.open_session("Ponte", app.combat_session.autosave_path)
        app._replace_active_session(copy)
        self.assertEqual(app.combat_session.battle_map, original)
        self.assertFalse(app.combat_session.battle_map.tokens[target].visible)
        self.assertIsNone(app._current_ranged_input().map_distance_yards)
        self.assertEqual(app.ranged_distance.get(), "3.25")
        self.assertEqual(app.ranged_map_hint.get(), "")
        self.assertTrue(Path(app.combat_session.autosave_path).is_file())

    def test_named_scenario_preserves_active_pair_and_its_map_distance(self):
        app = self.app
        app.choose_tool(BATTLE_MAP_TOOL)
        actor, target = app.combat_session.selected_pair()
        third = app.combat_session.add_combatant(CombatantState(identifier="reserve", name="Reserva"))
        panel = app.battle_map_panel
        panel.commit(panel.state.with_token(actor, 0, 0).with_token(target, 2, 0).with_token(third, 9, 0))
        app._select_encounter_role("target", third)
        self.assertEqual(panel.pair_distance(), 9)
        app.combat_library.save_session("Ponte", app.combat_session)
        app._select_encounter_role("target", target)
        self.assertEqual(panel.pair_distance(), 2)
        app._replace_active_session(app.combat_library.open_session("Ponte", app.combat_session.autosave_path))
        self.assertEqual((app.session_actor_key, app.session_target_key), (actor, third))
        self.assertEqual(panel.pair_distance(), 9)
        self.assertEqual(CombatSession.load_or_new(app.combat_session.autosave_path).selected_pair(), (actor, third))

    def test_player_window_tracks_current_scenario_without_private_data(self):
        app = self.app
        app.choose_tool(BATTLE_MAP_TOOL)
        actor, target = app.combat_session.selected_pair()
        app.combat_session.edit_combatant_state(actor, name="Batedor", current_hp=-7)
        app.combat_session.edit_combatant_state(target, name="Reserva secreta", current_fp=2)
        panel = app.battle_map_panel
        panel.place_token(actor, *app.combat_session.battle_map.cell_center(0, 0))
        panel.place_token(target, *app.combat_session.battle_map.cell_center(7, 0))
        panel.commit(panel.state.with_token_visibility(actor, True).with_token_visibility(target, False))
        player = panel.open_player_view()
        app.root.update()
        self.assertTrue(player.winfo_ismapped())
        self.assertEqual([token.label for token in player.canvas.scene.tokens], ["Batedor"])
        self.assertEqual(player.canvas.scene.geometry.tokens, {})
        self.assertNotIn("Reserva secreta", repr(player.canvas.scene))
        self.assertNotIn(actor, repr(player.canvas.scene))
        app._change_language("en_US")
        app.root.update()
        self.assertIs(app._battle_map_player, player)
        self.assertEqual(player.title(), t("map_players"))
        self.assertEqual([token.label for token in player.canvas.scene.tokens], ["Batedor"])
        app._replace_active_session(CombatSession.new(app.combat_session.autosave_path))
        app.root.update()
        self.assertEqual(player.canvas.scene.tokens, ())
