"""Master controls: narrow geometry, validated alignment, and snapped dragging."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
import unittest
from unittest.mock import patch

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
