"""Oficina result cards preserve the existing calculation and text history."""
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
import unittest
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.gui_form_state import descendants
from utils.i18n import t


@requires_tk
class OficinaResultsTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        preferences = patch('main.application_data_dir', return_value=Path(directory.name))
        preferences.start()
        self.addCleanup(preferences.stop)
        self.app = GURPSCalculator()
        self.callback_errors = []
        self.app.root.report_callback_exception = lambda _, error, __: self.callback_errors.append(error)
        self.addCleanup(self.app.root.destroy)
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, []))

    def button(self, parent, key):
        return next(w for w in descendants(parent) if isinstance(w, ttk.Button) and w['text'] == t(key))

    def test_fall_summary_and_details_survive_language_change(self):
        app = self.app
        app.choose_tool(2)
        app.root.geometry('1360x840')
        app.root.update()
        self.button(app.falls_result_text.oficina_layout.inputs, 'falls_calculate').invoke()
        app.root.update()
        box = app.falls_result_text
        result = box.get('1.0', 'end-1c')
        summary = box.summary_label['text']
        self.assertIn(summary, result)
        self.assertIn('Lesão total:', summary)
        self.assertFalse(box.winfo_ismapped())
        self.button(box.master, 'ui_result_show_details').invoke()
        app.root.update()
        self.assertTrue(box.winfo_ismapped())
        box.comparison.keep()

        app._change_language('en_US')
        app.root.update()
        box = app.falls_result_text
        self.assertTrue(box.winfo_ismapped())
        self.assertEqual(box.get('1.0', 'end-1c'), result)
        self.assertEqual(box.summary_label['text'], summary)
        self.assertEqual(box.comparison.saved, result.strip())
        self.assertEqual(len(box.comparison.history), 1)
        self.button(box.master, 'ui_result_hide_details').invoke()
        app.root.update()
        self.assertFalse(box.winfo_ismapped())
        self.assertEqual(box.get('1.0', 'end-1c'), result)

    def test_extended_tools_reflow_and_keep_primary_commands_in_view(self):
        app = self.app
        app.ui_preferences['font_size'] = 18
        outputs = ('strength', 'magic', 'powers', 'vehicles', 'social', 'mass')
        for language in ('pt_BR', 'en_US'):
            app._change_language(language)
            for index, prefix in enumerate(outputs, 9):
                with self.subTest(language=language, tool=prefix):
                    box = getattr(app, prefix + '_result_text')
                    layout = box.oficina_layout
                    app.choose_tool(index)
                    app.root.geometry('1520x920')
                    app.root.update()
                    self.assertTrue(layout.wide)
                    app.root.geometry('800x600')
                    app.root.update()
                    self.assertFalse(layout.wide)
                    action = 'social_reaction' if prefix == 'social' else 'common_calculate'
                    button = self.button(layout.inputs, action)
                    layout.reveal(button)
                    app.root.update()
                    self.assertIs(app.root.winfo_containing(button.winfo_rootx() + button.winfo_width() // 2,
                                                           button.winfo_rooty() + button.winfo_height() // 2), button)
