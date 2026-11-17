"""Rendering regressions for the combat forms and the reported Strength layout."""
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
import unittest
from unittest.mock import patch

from tests.tk_support import assert_workbench_reflow, requires_tk
from utils.gui_form_state import descendants
from utils.i18n import t


@requires_tk
class CombatStrengthGeometryTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch('main.application_data_dir', return_value=Path(directory)))
        self.app = GURPSCalculator()
        self.addCleanup(self.app.root.destroy)
        self.errors = []
        self.app.root.report_callback_exception = lambda _, error, __: self.errors.append(error)
        self.addCleanup(lambda: self.assertEqual(self.errors, []))

    def button(self, pane, key):
        return next(w for w in descendants(pane)
                    if isinstance(w, ttk.Button) and w.cget('text') == t(key))

    def assert_accessible(self, layout, button):
        layout.reveal(button)
        self.app.root.update()
        x = button.winfo_rootx() + button.winfo_width() // 2
        y = button.winfo_rooty() + button.winfo_height() // 2
        self.assertIs(self.app.root.winfo_containing(x, y), button)
        self.assertLessEqual(button.winfo_reqwidth(), button.winfo_width())

    def test_melee_and_injury_have_reachable_actions_and_wheel_scrolling(self):
        app = self.app
        app.ui_preferences['font_size'] = 18
        for language in ('pt_BR', 'en_US'):
            app._change_language(language)
            for index, box, actions in (
                (6, app.melee_result_text, ('common_search', 'melee_resolve', 'grapple_resolve')),
                (7, app.injury_result_text, ('common_search', 'injury_equip_armor', 'injury_resolve_checks')),
            ):
                with self.subTest(language=language, tab=index):
                    app.choose_tool(index)
                    app.root.geometry('800x600')
                    app.root.update()
                    layout = box.oficina_layout
                    assert_workbench_reflow(self, layout, wide=False)
                    if index == 6:
                        toggle = next(w for w in descendants(layout.inputs) if isinstance(w, ttk.Button)
                                      and t('grapple_section') in ' '.join(w.cget('text').split()))
                        self.assert_accessible(layout, toggle)
                        if toggle.cget('text').startswith('▸'):
                            toggle.invoke()
                        app.root.update()
                    layout.canvas.yview_moveto(0)
                    label = next(w for w in descendants(layout.header) if isinstance(w, ttk.Label))
                    label.event_generate('<MouseWheel>', delta=-120)
                    app.root.update()
                    self.assertGreater(layout.canvas.yview()[0], 0)
                    for key in actions:
                        self.assert_accessible(layout, self.button(layout.inputs, key))

    def test_strength_labels_keep_width_after_resize_and_attack_summary_shows_damage(self):
        app = self.app
        for language, size in (('pt_BR', 10), ('en_US', 18), ('pt_BR', 18)):
            with self.subTest(language=language, font=size):
                app.ui_preferences['font_size'] = size
                app._change_language(language)
                app.choose_tool(9)
                layout = app.strength_result_text.oficina_layout
                for geometry in ('1520x920', '800x600', '1520x920'):
                    app.root.geometry(geometry)
                    app.root.update()
                    label = next(w for w in descendants(layout.inputs)
                                 if isinstance(w, ttk.Label) and w.cget('text') == t('strength_lifting_st'))
                    self.assertGreaterEqual(label.winfo_width(), 100)
                    self.assertGreaterEqual(int(label.cget('wraplength')), 100)
                    self.assert_accessible(layout, self.button(layout.inputs, 'common_calculate'))
                app.strength_task.set('striking')
                app.strength_st.set('27')
                app.strength_all_out.set(True)
                self.button(layout.inputs, 'common_calculate').invoke()
                app.root.update()
                self.assertIn(t('strength_damage_result', original='5d+1', final='5d+6'),
                              app.strength_result_text.oficina_highlights)
