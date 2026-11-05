"""Interaction checks for the GM's encounter window."""
import os
from tempfile import TemporaryDirectory
from tkinter import ttk
import unittest
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.gui_form_state import descendants
from utils.gui_hub import session_window
from utils.i18n import t


@requires_tk
class CombatPrepLayoutTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'GURPS_CALCULADORA_DATA_DIR': directory}))
        self.app = GURPSCalculator()
        self.addCleanup(self.app.root.destroy)
        self.app.root.update()

    def _control(self, parent, key):
        return next(widget for widget in descendants(parent) if isinstance(widget, ttk.Button)
                    and widget.cget('text') == t(key))

    def _assert_keyboard_reveals(self, widget):
        root = self.app.root
        widget.focus_force()
        root.update()
        x = widget.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() + widget.winfo_height() // 2
        self.assertIs(root.winfo_containing(x, y), widget)

    def test_large_font_actions_remain_reachable_in_both_languages(self):
        app = self.app
        app.root.geometry('800x600')
        app.ui_preferences['font_size'] = 18
        for language in ('pt_BR', 'en_US'):
            with self.subTest(language=language):
                app._change_language(language)
                window = session_window(app)
                window.geometry('560x430+20+20')
                for page, keys in (
                    (window.roster_page, ('encounter_use_actor', 'encounter_sort_speed', 'encounter_resources')),
                    (window.sheets_page, ('encounter_import_files', 'encounter_add')),
                    (window.scenarios_page, ('combat_prep_save_session', 'session_undo')),
                ):
                    window.pages.select(page)
                    app.root.update()
                    for key in keys:
                        self._assert_keyboard_reveals(self._control(page, key))
                window.destroy()

    def test_resource_editor_rejects_newer_session_state_then_accepts_fresh_edit(self):
        app = self.app
        window = session_window(app)
        identifier = app.session_actor_key
        dialog = window.edit_resources(identifier)
        dialog.current_hp.set('3')
        app.combat_session.edit_combatant_state(identifier, current_hp=7)
        self.assertFalse(dialog.apply_changes())
        self.assertEqual(dialog.status.get(), t('ui_session_stale'))
        self.assertEqual(app.combat_session.combatants[identifier].current_hp, 7)
        dialog.destroy()

        dialog = window.edit_resources(identifier)
        dialog.current_fp.set('6')
        pool = dialog.add_pool('Reserva', 8, 5)
        self.assertTrue(dialog.apply_changes())
        state = app.combat_session.combatants[identifier]
        self.assertEqual((state.current_hp, state.current_fp, state.max_fp), (7, 6, 10))
        self.assertEqual(state.resource_pools[pool], {'label': 'Reserva', 'maximum': 8, 'current': 5})
        self.assertTrue(app.combat_session.undo())
        self.assertNotIn(pool, app.combat_session.combatants[identifier].resource_pools)
