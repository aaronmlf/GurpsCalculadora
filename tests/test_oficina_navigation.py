"""The Oficina shell preserves tool IDs and works with or without the sidebar."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.tk_support import requires_tk


@requires_tk
class OficinaNavigationTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        paths = patch('main.application_data_dir', return_value=Path(self.directory.name))
        paths.start()
        self.addCleanup(paths.stop)
        self.app = GURPSCalculator()
        self.callback_errors = []
        self.app.root.report_callback_exception = lambda *error: self.callback_errors.append(error[1])
        self.addCleanup(self.destroy_app)
        self.addCleanup(lambda: self.assertEqual(self.callback_errors, []))
        self.app.root.update()

    def destroy_app(self):
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()

    def test_dice_is_a_root_shortcut_and_selected_domain_opens(self):
        app = self.app
        self.assertEqual(app.navigation_tree.parent('15'), '')
        self.assertFalse(app.navigation_tree.item('ui_combat', 'open'))
        app.choose_tool(8)
        self.assertEqual(app.navigation_tree.selection(), ('8',))
        self.assertTrue(app.navigation_tree.item('ui_combat', 'open'))
        self.assertFalse(app.navigation_tree.item('ui_powers', 'open'))
        app._change_language('en_US')
        self.assertEqual(app.navigation_tree.selection(), ('8',))
        self.assertTrue(app.navigation_tree.item('ui_combat', 'open'))
        self.assertEqual(app.navigation_tree.parent('15'), '')
        app.choose_tool(15)
        self.assertEqual(app.notebook.index(app.notebook.select()), 15)
        self.assertFalse(app.navigation_tree.item('ui_combat', 'open'))

    def test_search_matches_both_languages_and_does_not_need_catalogs(self):
        app = self.app
        with patch.object(app.weapon_catalog, 'search', side_effect=AssertionError('searched weapons')):
            chooser = app.open_tool_chooser()
            self.assertIs(app.open_tool_chooser(), chooser)
            chooser.query.set('FORCA')
            self.assertEqual([index for index, _ in chooser.filtered], [9])
            chooser.query.set('mass combat')
            self.assertEqual([index for index, _ in chooser.filtered], [14])
            chooser.query.set('sem resultados')
            self.assertFalse(chooser.filtered)
            self.assertTrue(chooser.open_button.instate(['disabled']))
            chooser.query.set('DICE')
            chooser.confirm()
        self.assertEqual(app.notebook.index(app.notebook.select()), 15)

    def test_hidden_sidebar_retains_search_and_navigation(self):
        from utils.i18n import t

        app = self.app
        app.ui_preferences['sidebar_hidden'] = True
        app._rebuild_ui()
        app.root.update()
        self.assertFalse(app.navigation_tree.winfo_ismapped())
        self.assertTrue(app.workspace_topbar.winfo_ismapped())
        app.ui_preferences['recent'] = [11]
        view = app.root.nametowidget(app.menubar.entrycget('end', 'menu'))
        for index in range(view.index('end') + 1):
            if view.entrycget(index, 'label') == t('ui_tool_search'):
                view.invoke(index)
                break
        chooser = app._tool_chooser
        chooser.query.set('magia')
        chooser.confirm()
        self.assertEqual(app.notebook.index(app.notebook.select()), 10)
        self.assertTrue(app.navigation_tree.item('ui_powers', 'open'))

    def test_rebuild_dismisses_open_search_and_keeps_one_root_shortcut(self):
        app = self.app
        binding = app.root.bind('<Control-k>')
        first = app.open_tool_chooser()
        app._change_language('en_US')
        self.assertFalse(first.winfo_exists())
        self.assertIsNone(app._tool_chooser)
        self.assertEqual(app.root.bind('<Control-k>'), binding)
        chooser = app.open_tool_chooser()
        self.assertEqual(chooser.title(), 'Find tools')
        chooser.query.set('veiculos')
        chooser.confirm()
        self.assertEqual(app.notebook.index(app.notebook.select()), 12)

    def test_topbar_fits_minimum_window_at_maximum_font_size(self):
        app = self.app
        app.root.geometry('800x600')
        app.ui_preferences['font_size'] = 18
        app._rebuild_ui()
        app.root.update()
        bar = app.workspace_topbar
        right = bar.winfo_rootx() + bar.winfo_width()
        for frame in bar.winfo_children():
            for control in frame.winfo_children():
                self.assertTrue(control.winfo_ismapped())
                self.assertLessEqual(control.winfo_rootx() + control.winfo_width(), right)

    def test_dashboard_shortcuts_open_existing_tools_and_refresh_personal_items(self):
        from tkinter import ttk

        from utils.gui_form_state import descendants
        from utils.i18n import t

        app = self.app
        app.root.geometry('1280x840')
        app.root.update()
        cards = app.home_shortcuts.copy()
        self.assertEqual(set(cards), {6, 7, 8, 15})
        self.assertEqual({button.master.grid_info()['column'] for button in cards.values()}, {0, 1})
        for index, button in cards.items():
            button.invoke()
            self.assertEqual(app.notebook.index(app.notebook.select()), index)
            app.choose_tool('home')
            self.assertIs(app.home_shortcuts[index], button)
        app.choose_tool(9)
        app.toggle_tool_favorite()
        app.choose_tool('home')
        labels = [widget['text'] for widget in descendants(app.home_frame)
                  if isinstance(widget, ttk.Button) and widget.winfo_manager()]
        self.assertGreaterEqual(labels.count(t('tab_strength')), 2)
        self.assertIn(t('ui_home_open_session'), labels)
        self.assertIn(t('ui_home_all_tools'), labels)

    def test_dashboard_cards_reflow_and_keep_controls_within_narrow_window(self):
        app = self.app
        app.root.geometry('800x600')
        app.ui_preferences['font_size'] = 18
        for language in ('pt_BR', 'en_US'):
            with self.subTest(language=language):
                app._change_language(language)
                app.root.update()
                left = app.home_frame.winfo_rootx()
                right = left + app.home_frame.winfo_width()
                for button in app.home_shortcuts.values():
                    self.assertGreaterEqual(button.winfo_rootx(), left)
                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), right)
                    button.focus_force()
                    app.root.update()
                    x = button.winfo_rootx() + button.winfo_width() // 2
                    y = button.winfo_rooty() + button.winfo_height() // 2
                    self.assertIs(app.root.winfo_containing(x, y), button)
                app.home_shortcuts[15].invoke()
                self.assertEqual(app.notebook.index(app.notebook.select()), 15)
                app.choose_tool('home')


if __name__ == '__main__':
    unittest.main()
