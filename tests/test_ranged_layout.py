"""Interaction and reflow checks for the ranged combat workbench."""
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
import unittest
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.gui_form_state import descendants
from utils.i18n import t


@requires_tk
class RangedLayoutTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        temp = self.enterContext(TemporaryDirectory())
        self.enterContext(patch('main.application_data_dir', return_value=Path(temp)))
        self.show_error = self.enterContext(patch('main.messagebox.showerror'))
        self.app = GURPSCalculator()
        self.callback_errors = []
        self.app.root.report_callback_exception = lambda *error: self.callback_errors.append(error[1])
        self.addCleanup(self.app.root.destroy)
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, []))

    def button(self, key):
        return next(w for w in descendants(self.app.ranged_layout)
                    if isinstance(w, ttk.Button) and w.cget('text') == t(key))

    def resize(self, geometry):
        self.app.root.geometry(geometry)
        self.app.root.update()

    def assert_clickable(self, button):
        self.app.ranged_layout.reveal(button)
        self.app.root.update()
        x = button.winfo_rootx() + button.winfo_width() // 2
        y = button.winfo_rooty() + button.winfo_height() // 2
        self.assertIs(self.app.root.winfo_containing(x, y), button)

    def test_ranged_actions_and_adaptive_geometry_in_both_languages(self):
        app = self.app
        app.ui_preferences['font_size'] = 18
        for language in ('pt_BR', 'en_US'):
            with self.subTest(language=language):
                app._change_language(language)
                app.choose_tool(8)
                self.resize('1520x920')
                layout = app.ranged_layout
                self.assertTrue(layout.wide)
                self.assertEqual(layout.inputs.grid_info()['row'], layout.result.grid_info()['row'])

                app.ranged_search.set('Auto Pistol, 9mm')
                self.button('ranged_search_button').invoke()
                app.ranged_weapon_box.current(0)
                app.ranged_weapon_box.event_generate('<<ComboboxSelected>>')
                self.assertEqual(app.ranged_weapon_name.get(), 'Auto Pistol, 9mm')
                app.ranged_skill.set('16')
                app.ranged_aim_seconds.set('1')
                app.ranged_distance.set('18.288')
                expected = app.ranged_calc.calculate(app._current_ranged_input())
                self.assertTrue(expected.range_valid)
                for action in ('ranged_calculate', 'ranged_roll_attack', 'ranged_resolve'):
                    self.assert_clickable(self.button(action))
                self.button('ranged_calculate').invoke()
                app.root.update()
                text = app.ranged_result_text
                calculated = text.get('1.0', 'end-1c')
                self.assertIn(t('ranged_effective_skill', value=expected.effective_skill,
                                probability=expected.probability), calculated)

                self.resize('800x600')
                self.assertFalse(layout.wide)
                self.assertGreater(layout.result.grid_info()['row'], layout.inputs.grid_info()['row'])
                self.assertEqual(layout.winfo_width(), layout.canvas.winfo_width())
                self.assertEqual(layout.canvas.xview(), (0.0, 1.0))
                self.assertIs(text, app.ranged_result_text)
                self.assertEqual(text.get('1.0', 'end-1c'), calculated)
                self.assertEqual(app.ranged_distance.get(), '18.288')
                for action in ('ranged_calculate', 'ranged_roll_attack', 'ranged_resolve'):
                    self.assert_clickable(self.button(action))

                app._ranged_advanced_disclosure.toggle.invoke()
                app.root.update()
                self.assertTrue(app.ranged_advanced_frame.winfo_ismapped())
                self.assertFalse(text.stale)
                app._ranged_advanced_disclosure.toggle.invoke()
                self.assertFalse(app.ranged_advanced_frame.winfo_ismapped())

                with patch('calculators.ranged_combat.roll_3d6', return_value=(8, [2, 3, 3])):
                    self.button('ranged_roll_attack').invoke()
                    app.root.update()
                    self.assertIn(t('ranged_attack_roll', roll=8,
                                    outcome=t('combat_outcome_hit', margin=expected.effective_skill - 8)),
                                  text.get('1.0', 'end'))
                    self.button('ranged_resolve').invoke()
                    app.root.update()
                    self.assertIn(t('ranged_hits_after_defense', value=0), text.get('1.0', 'end'))
                self.show_error.assert_not_called()
                self.resize('1520x920')
                self.assertTrue(layout.wide)
                self.assertIs(text, app.ranged_result_text)

    def test_invalid_hidden_field_reveals_its_disclosure(self):
        app = self.app
        app.choose_tool(8)
        self.resize('800x600')
        self.assertFalse(app.ranged_advanced_frame.winfo_ismapped())
        app.ranged_scope.set('invalid')
        app.root.update()
        self.assertTrue(app.ranged_advanced_frame.winfo_ismapped())
        scope = next(w for w in descendants(app.ranged_advanced_frame)
                     if isinstance(w, ttk.Entry) and w.cget('textvariable') == str(app.ranged_scope))
        self.assertTrue(scope.instate(['invalid']))
        self.assertTrue(scope.validation_label.label.winfo_ismapped())
