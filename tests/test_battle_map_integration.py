"""Integration checks for the Mapa → Cenários / Tiro workflow."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from calculators.combat_session import CombatSession
from calculators.injury import CombatantState
from tests.tk_support import requires_tk
from utils.dice_roller import get_range_modifier
from utils.i18n import t
from utils.ui_preferences import BATTLE_MAP_TOOL, clean_preferences


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
        self.assertEqual(app._current_ranged_input().distance_in_yards, 7)
        with self.assertRaisesRegex(ValueError, "map_settings_stale"):
            app._send_map_distance_to_ranged(actor, target, 7)
        app.ranged_distance.set("1.8288")
        self.assertEqual(app.ranged_map_hint.get(), "")
        self.assertIsNone(app._current_ranged_input().map_distance_yards)

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
