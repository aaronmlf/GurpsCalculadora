from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.ui_preferences import load_ui_preferences, save_ui_preferences
from utils.ui_theme import contrast, make_palette


class OficinaPaletteTests(unittest.TestCase):
    def test_saved_overrides_are_validated_per_theme(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'appearance.json'
            save_ui_preferences(path, {'theme': 'light', 'theme_colors': {
                'light': {'bg': '#6E6E6E', 'accent': '#ABA', 'panel': ['#ffffff']},
                'dark': {'panel': '#f0F0f0', 'text': '#123456'},
                'unknown': {'accent': '#ffffff'},
            }})
            self.assertEqual(load_ui_preferences(path)['theme_colors'], {
                'light': {'bg': '#6e6e6e'}, 'dark': {'panel': '#f0f0f0'},
            })

    def test_text_is_readable_even_when_custom_surfaces_flip_brightness(self):
        combinations = [None, {'dark': {'bg': '#f3e9d1', 'panel': '#41414a', 'accent': '#eeeeee'}},
                        {'dark': {'bg': '#767676', 'panel': '#ffffff', 'accent': '#121212'}}]
        for overrides in combinations:
            palette = make_palette('dark', overrides)
            for surface, text in [('bg', 'fg'), ('panel', 'panel_fg'), ('sidebar', 'sidebar_fg'),
                                  ('accent', 'accent_fg'), ('bg', 'accent_text'), ('bg', 'error')]:
                self.assertGreaterEqual(contrast(palette[surface], palette[text]), 4.5)


@requires_tk
class OficinaAppearanceTests(unittest.TestCase):
    def test_preview_cancel_apply_and_restore_keep_inputs_and_dice(self):
        from tkinter import ttk

        from main import GURPSCalculator
        from utils.gm_dice import roll_dice
        from utils.gui_form_state import descendants
        from utils.gui_hub import settings
        from utils.i18n import t

        with TemporaryDirectory() as directory, patch('main.application_data_dir', return_value=Path(directory)):
            app = GURPSCalculator()
            try:
                app.choose_tool(15)
                app.ranged_distance.set('91.44')
                result = roll_dice('3d6+2', values=[1, 2, 3])
                app.gm_dice_last_result = result
                app.gm_dice_panel.render()
                app.root.update()
                original = dict(app.colors)

                def button(window, key):
                    return next(widget for widget in descendants(window) if isinstance(widget, ttk.Button)
                                and widget['text'] == t(key))

                def pick_background(window):
                    with patch('utils.gui_hub.colorchooser.askcolor', return_value=((230, 220, 202), '#e6dcca')):
                        button(window, 'ui_color_pick').invoke()

                window = settings(app)
                pick_background(window)
                self.assertEqual(app.colors, original)
                button(window, 'ui_cancel').invoke()
                self.assertEqual(app.ui_preferences['theme_colors'], {})

                window = settings(app)
                pick_background(window)
                with patch('utils.gm_dice_ui.roll_dice', side_effect=AssertionError('unexpected reroll')):
                    button(window, 'ui_settings_apply').invoke()
                app.root.update()
                self.assertEqual(app.root['background'], '#e6dcca')
                self.assertEqual(app._current_tool, 15)
                self.assertIs(app.gm_dice_last_result, result)
                self.assertEqual(app.ranged_distance.get(), '91.44')
                self.assertEqual(load_ui_preferences(app.ui_preferences_path)['theme_colors'],
                                 {'dark': {'bg': '#e6dcca'}})

                window = settings(app)
                button(window, 'ui_color_restore').invoke()
                button(window, 'ui_settings_apply').invoke()
                app.root.update()
                self.assertEqual(app.colors, original)
                self.assertEqual(load_ui_preferences(app.ui_preferences_path)['theme_colors'], {})
            finally:
                for form in app._form_states:
                    form.close()
                for binding in app._unit_bindings:
                    binding.close()
                app.root.destroy()
