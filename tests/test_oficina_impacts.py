"""Verify that the impact workbench keeps real inputs and actions usable."""
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
import unittest
from unittest.mock import patch

from tests.tk_support import assert_workbench_reflow, requires_tk
from utils.gui_form_state import descendants
from utils.i18n import t


@requires_tk
class ImpactWorkbenchTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = self.enterContext(TemporaryDirectory())
        self.enterContext(patch('main.application_data_dir', return_value=Path(directory)))
        self.show_error = self.enterContext(patch('main.messagebox.showerror'))
        self.app = GURPSCalculator()
        self.errors = []
        self.app.root.report_callback_exception = lambda _, error, __: self.errors.append(error)
        self.addCleanup(self.app.root.destroy)
        self.addCleanup(lambda: self.assertEqual(self.errors, []))

    def button(self, layout, key):
        return next(w for w in descendants(layout.inputs)
                    if isinstance(w, ttk.Button) and w.cget('text') == t(key))

    def check_target(self, layout, widget):
        layout.reveal(widget)
        self.app.root.update()
        point = (widget.winfo_rootx() + widget.winfo_width() // 2,
                 widget.winfo_rooty() + widget.winfo_height() // 2)
        self.assertIs(self.app.root.winfo_containing(*point), widget)

    def test_six_tools_reflow_and_keep_results_in_both_languages(self):
        app = self.app
        app.ui_preferences['font_size'] = 18
        tools = (
            ('knockback_calculate', 'kb_result_text'),
            ('slam_calculate', 'slam_result_text'),
            ('falls_calculate', 'falls_result_text'),
            ('collisions_calculate', 'coll_result_text'),
            ('explosions_calculate', 'exp_result_text'),
            ('falling_objects_calculate', 'fo_result_text'),
        )
        for language in ('pt_BR', 'en_US'):
            app._change_language(language)
            for index, (action, output) in enumerate(tools):
                with self.subTest(language=language, tool=action):
                    app.choose_tool(index)
                    app.root.geometry('1520x920')
                    app.root.update()
                    text = getattr(app, output)
                    layout = text.oficina_layout
                    assert_workbench_reflow(self, layout)
                    button = self.button(layout, action)
                    self.check_target(layout, button)
                    button.invoke()
                    app.root.update()
                    result = text.get('1.0', 'end-1c')
                    self.assertTrue(result.strip())

                    app.root.geometry('800x600')
                    app.root.update()
                    assert_workbench_reflow(self, layout, wide=False)
                    self.assertIs(text, getattr(app, output))
                    self.assertEqual(text.get('1.0', 'end-1c'), result)
                    self.check_target(layout, button)
                    button.invoke()
                    app.root.update()
                    self.assertLess(layout.result.winfo_rooty(),
                                    layout.canvas.winfo_rooty() + layout.canvas.winfo_height())
                    self.show_error.assert_not_called()

    def test_knockback_keeps_damage_choices_and_separate_balance_roll(self):
        app = self.app
        app.choose_tool(0)
        app.root.update()
        layout = app.kb_result_text.oficina_layout
        cutting = next(w for w in descendants(layout.inputs)
                       if isinstance(w, ttk.Radiobutton) and w.cget('value') == 'cutting')
        self.check_target(layout, cutting)
        cutting.invoke()
        self.assertEqual(app.kb_damage_type.get(), 'cutting')
        app.kb_basic_damage.set(60)
        app.kb_target_dr.set(60)
        with patch('main.roll_3d6', return_value=(8, [2, 3, 3])):
            roll = self.button(layout, 'knockback_roll_button')
            self.check_target(layout, roll)
            roll.invoke()
        self.assertEqual(app.kb_roll_result.get(), 8)
        verify = self.button(layout, 'knockback_check_button')
        self.check_target(layout, verify)
        verify.invoke()
        app.root.update()
        self.assertIn(t('knockback_roll_result', value=8), app.kb_result_text.get('1.0', 'end'))
        self.show_error.assert_not_called()
