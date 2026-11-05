"""Master controls: narrow geometry, validated alignment, and snapped dragging."""

import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.ui_preferences import BATTLE_MAP_TOOL


@requires_tk
class BattleMapControlTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = self.enterContext(TemporaryDirectory())
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
