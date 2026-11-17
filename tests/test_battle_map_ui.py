"""Master controls: narrow geometry, validated alignment, and snapped dragging."""

from dataclasses import replace
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import patch

from calculators.combat_session import CombatSession
from calculators.injury import CombatantState
from tests.test_battle_map_view import png
from tests.tk_support import requires_tk
from utils.battle_map_assets import BattleMapAssetError
from utils.ui_preferences import BATTLE_MAP_TOOL


@requires_tk
class BattleMapControlTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = self.enterContext(TemporaryDirectory())
        self.directory = Path(directory)
        self.enterContext(patch.dict(os.environ, {'GURPS_CALCULADORA_DATA_DIR': directory}))
        self.app = GURPSCalculator()
        self.addCleanup(self.app.root.destroy)
        self.app.choose_tool(BATTLE_MAP_TOOL)
        self.app.root.update()

    def test_narrow_workspace_and_grid_validation_at_maximum_font(self):
        app = self.app
        app.root.geometry('800x600')
        app.ui_preferences['font_size'] = 18
        for language in ('pt_BR', 'en_US'):
            with self.subTest(language=language):
                app._change_language(language)
                app.root.update()
                panel = app.battle_map_panel
                self.assertGreater(panel.canvas.winfo_height(), 120)
                right = panel.winfo_rootx() + panel.winfo_width()
                for widget in (panel.place_button, panel.player_button, panel.send_button):
                    self.assertTrue(widget.winfo_ismapped())
                    self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right)
                dialog = panel.open_grid_settings()
                for geometry in ('480x440', '380x360'):
                    dialog.geometry(geometry)
                    app.root.update()
                    bottom = dialog.winfo_rooty() + dialog.winfo_height()
                    for button in (dialog.apply_button, dialog.cancel_button):
                        self.assertTrue(button.winfo_ismapped())
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)
                canvas = dialog.form_canvas
                self.assertLess(canvas.yview()[1], 1)
                dialog.entries['cell_size'].event_generate('<Button-5>', x=3, y=3)
                app.root.update()
                self.assertGreater(canvas.yview()[0], 0)
                canvas.yview_moveto(1)
                app.root.update()
                field = dialog.entries['yards_per_cell']
                self.assertGreaterEqual(field.winfo_rooty(), canvas.winfo_rooty())
                self.assertLessEqual(field.winfo_rooty() + field.winfo_height(), canvas.winfo_rooty() + canvas.winfo_height())
                original = app.combat_session.battle_map
                dialog.values['cell_size'].set('0')
                self.assertFalse(dialog.apply())
                self.assertEqual(app.combat_session.battle_map, original)
                dialog.kind.set(next(label for label, key in dialog.kinds.items() if key == 'hex_flat'))
                dialog.values['cell_size'].set('48')
                dialog.values['origin_x'].set('-12,5')
                dialog.values['yards_per_cell'].set('2.5')
                self.assertTrue(dialog.apply())
                updated = app.combat_session.battle_map
                self.assertEqual((updated.grid, updated.cell_size, updated.origin_x, updated.yards_per_cell),
                                 ('hex_flat', 48, -12.5, 2.5))

    def test_opening_grid_settings_keeps_exact_values_and_ruler_precision(self):
        app = self.app
        app.result_units.set('imperial')
        app._change_units()
        app.root.update()
        panel = app.battle_map_panel
        actor, target = app.combat_session.selected_pair()
        precise = replace(panel.state, cell_size=63.123456789, origin_x=4.123456789,
                          origin_y=-67.123456789, yards_per_cell=0.14000002)
        precise = precise.with_token(actor, 0, 0).with_token(target, 50, 0)
        panel.commit(precise)
        before = app.combat_session.to_dict()
        self.assertIn('7.000001 yd', panel.distance_label.cget('text'))

        dialog = panel.open_grid_settings()
        self.assertTrue(dialog.apply())
        self.assertEqual(app.combat_session.to_dict(), before)

        dialog = panel.open_grid_settings()
        dialog.show_grid.set(False)
        self.assertTrue(dialog.apply())
        self.assertEqual(panel.state, replace(precise, show_grid=False))
        self.assertIn('7.000001 yd', panel.distance_label.cget('text'))

        dialog = panel.open_grid_settings()
        dialog.values['yards_per_cell'].set('0,14')
        self.assertTrue(dialog.apply())
        self.assertIn('7 yd', panel.distance_label.cget('text'))

    def test_preference_rebuild_keeps_both_cameras_but_new_png_and_scenario_fit(self):
        app = self.app
        panel = app.battle_map_panel
        player = panel.open_player_view()
        app.root.update()

        def adjust_cameras():
            for i, canvas in enumerate((app.battle_map_panel.canvas, player.canvas), 1):
                canvas.zoom_in()
                canvas.zoom_in()
                canvas._set_center(42.5 * i, -18.25 * i)
            app.root.update()
            return app.battle_map_panel.canvas.snapshot_camera(), player.canvas.snapshot_camera()

        before = adjust_cameras()
        app.result_units.set('imperial')
        app._change_units()
        app.root.update()
        self.assertIs(app._battle_map_player, player)
        self.assertEqual((app.battle_map_panel.canvas.snapshot_camera(), player.canvas.snapshot_camera()), before)

        app.choose_tool(8)
        app.root.update()
        app._change_language('en_US')
        app.root.update()
        self.assertEqual(app._current_tool, 8)
        app.choose_tool(BATTLE_MAP_TOOL)
        app.root.update()
        self.assertEqual((app.battle_map_panel.canvas.snapshot_camera(), player.canvas.snapshot_camera()), before)

        app.ui_preferences['theme'] = 'light'
        app._setup_theme()
        app._rebuild_ui()
        app.root.update()
        self.assertEqual((app.battle_map_panel.canvas.snapshot_camera(), player.canvas.snapshot_camera()), before)
        self.assertEqual(player.canvas.cget('background'), app.colors['panel'])

        source = self.directory / 'camera.png'
        source.write_bytes(png())
        app.battle_map_panel.import_background(source)
        app.root.update()
        for canvas in (app.battle_map_panel.canvas, player.canvas):
            for value, expected in zip(canvas.snapshot_camera()[0], (48.0, 36.0)):
                self.assertAlmostEqual(value, expected)

        adjust_cameras()
        app._replace_active_session(CombatSession.new(app.combat_session.autosave_path))
        app.root.update()
        self.assertEqual(app.battle_map_panel.canvas.snapshot_camera()[0], (0.0, 0.0))
        self.assertEqual(player.canvas.snapshot_camera()[0], (0.0, 0.0))

    def test_camera_is_preserved_when_map_is_rebuilt_lazily(self):
        app = self.app
        canvas = app.battle_map_panel.canvas
        canvas.zoom_in()
        canvas._set_center(-34.5, 15.25)
        camera = canvas.snapshot_camera()
        app.choose_tool(8)
        app.root.update()
        app._change_language('en_US')
        app.root.update()
        self.assertIsNone(app.battle_map_panel)
        app.choose_tool(BATTLE_MAP_TOOL)
        app.root.update()
        self.assertEqual(app.battle_map_panel.canvas.snapshot_camera(), camera)

    def test_mouse_drag_snaps_and_commits_one_undo_step(self):
        app = self.app
        panel = app.battle_map_panel
        actor = app.session_actor_key
        before = panel.state
        panel.place_token(actor, *before.cell_center(0, 0))
        app.root.update()
        initial = panel.state
        events = len(app.combat_session.events)
        x, y = map(round, panel.canvas.canvas_coords(*initial.cell_center(0, 0)))
        end_x, end_y = map(round, panel.canvas.canvas_coords(*initial.cell_center(1, 0)))
        panel.canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        panel.canvas.event_generate('<B1-Motion>', x=end_x + 2, y=end_y - 2)
        self.assertEqual(panel.state, initial)
        panel.canvas.event_generate('<ButtonRelease-1>', x=end_x + 2, y=end_y - 2)
        app.root.update()
        token = panel.state.tokens[actor]
        self.assertEqual((token.q, token.r), (1, 0))
        self.assertEqual(len(app.combat_session.events), events + 1)
        app._undo_session()
        self.assertEqual(panel.state, initial)

    def _click_cell(self, q, r):
        panel = self.app.battle_map_panel
        x, y = map(round, panel.canvas.canvas_coords(*panel.state.cell_center(q, r)))
        panel.canvas.event_generate('<ButtonPress-1>', x=x, y=y)
        panel.canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
        self.app.root.update()
        return x, y

    def test_new_token_is_hidden_before_first_frame_and_can_opt_in_to_visibility(self):
        app = self.app
        panel = app.battle_map_panel
        actor, target = app.session_actor_key, app.session_target_key
        app.combat_session.edit_combatant_state(actor, name='Reforço secreto')
        app.combat_session.edit_combatant_state(target, name='Vigia')
        app._battle_map_changed()
        player = panel.open_player_view()
        app.root.update()
        panel.select_token(actor)
        self.assertFalse(panel.visible_to_players.get())
        self.assertEqual(panel.token_menu.entrycget(panel._visibility_entry, 'state'), 'normal')
        panel.place_button.invoke()
        self._click_cell(0, 0)
        self.assertFalse(panel.state.tokens[actor].visible)
        self.assertEqual(player.canvas.scene.tokens, ())
        self.assertEqual(player.canvas.find_withtag('map-token'), ())

        panel.select_token(target)
        panel.token_menu.invoke(panel._visibility_entry)
        self.assertTrue(panel.visible_to_players.get())
        self.assertNotIn(target, panel.state.tokens)
        panel.place_button.invoke()
        self._click_cell(1, 0)
        self.assertTrue(panel.state.tokens[target].visible)
        self.assertEqual([token.label for token in player.canvas.scene.tokens], ['Vigia'])
        self.assertNotIn('Reforço secreto', repr(player.canvas.scene))

    def test_placement_into_occupied_cell_keeps_the_armed_token(self):
        app = self.app
        panel = app.battle_map_panel
        actor, target = app.session_actor_key, app.session_target_key
        panel.place_token(actor, *panel.state.cell_center(0, 0))
        app.root.update()
        panel.select_token(target)
        panel.place_button.invoke()
        x, y = self._click_cell(0, 0)
        self.assertEqual(set(panel.state.tokens), {actor, target})
        self.assertEqual({(token.q, token.r) for token in panel.state.tokens.values()}, {(0, 0)})
        self.assertIsNone(panel._placing_id)
        self.assertEqual(panel._selected_id, target)
        self.assertEqual(panel.canvas.token_at(x, y), target)
        panel.roster_selection.set(panel._labels[actor])
        panel.roster.event_generate('<<ComboboxSelected>>')
        app.root.update()
        self.assertEqual(panel.canvas.token_at(x, y), actor)

    def test_player_view_shows_one_stack_with_all_public_names_and_no_group_colors(self):
        app = self.app
        panel = app.battle_map_panel
        actor, target = app.combat_session.selected_pair()
        app.combat_session.edit_combatant_state(actor, name='Batedor', group='A')
        app.combat_session.edit_combatant_state(target, name='Vigia', team='B')
        secret = app.combat_session.add_combatant(CombatantState(identifier='reserva', name='Reserva secreta'))
        scene = panel.state.with_token(actor, 0, 0, True).with_token(target, 0, 0, True)
        panel.commit(scene.with_token(secret, 0, 0, False))
        player = panel.open_player_view()
        app.root.update()
        public = player.canvas
        self.assertEqual([token.label for token in public.scene.tokens], ['Batedor', 'Vigia'])
        self.assertNotEqual(panel._colors[actor], panel._colors[target])
        self.assertEqual(len({token.color for token in public.scene.tokens}), 1)

        def marker_items():
            return [item for item in public.find_withtag('map-token') if public.type(item) == 'oval']

        marker, = marker_items()
        color = public.itemcget(marker, 'fill')
        x1, y1, x2, y2 = public.coords(marker)
        self.assertEqual(((x1 + x2) / 2, (y1 + y2) / 2), public.canvas_coords(*scene.cell_center(0, 0)))
        count, = public.find_withtag('map-token-count')
        self.assertEqual(public.itemcget(count, 'text'), '2')
        labels = [public.itemcget(item, 'text') for item in public.find_withtag('map-token')
                  if public.type(item) == 'text']
        self.assertEqual(labels, ['Batedor\nVigia'])

        master_color = panel._colors[actor]
        app.combat_session.edit_combatant_state(actor, group='D')
        panel.commit(panel.state.with_token(target, 1, 0))
        app.root.update()
        self.assertNotEqual(panel._colors[actor], master_color)
        self.assertEqual(len(marker_items()), 2)
        self.assertEqual({public.itemcget(item, 'fill') for item in marker_items()}, {color})
        self.assertEqual(public.find_withtag('map-token-count'), ())

    def test_background_is_not_replaced_if_png_is_malformed_or_tk_rejects_it(self):
        panel = self.app.battle_map_panel
        original, invalid, unsupported = (self.directory / (name + '.png') for name in (
            'original', 'invalid', 'unsupported',
        ))
        original.write_bytes(png())
        invalid.write_bytes(png(1, 1, scanlines=b'\x05\x00\x00\x00'))
        unsupported.write_bytes(png(1, 1))
        identifier = panel.import_background(original)
        player = panel.open_player_view()
        self.app.root.update()
        before = self.app.combat_session.to_dict()
        with self.assertRaisesRegex(BattleMapAssetError, 'battle_map_image_invalid'):
            panel.import_background(invalid)
        with (patch('utils.battle_map_view.tk.PhotoImage', side_effect=tk.TclError('cannot decode')),
              self.assertRaisesRegex(BattleMapAssetError, 'battle_map_image_invalid')):
            panel.import_background(unsupported)
        self.app.root.update()
        self.assertEqual(self.app.combat_session.to_dict(), before)
        self.assertEqual(player.canvas.scene.geometry.image_id, identifier)
        self.assertFalse(panel.canvas.background_unavailable)
        self.assertTrue(panel.canvas.find_withtag('map-image'))
        self.assertEqual([path.stem for path in panel.asset_store.directory.iterdir()], [identifier])
