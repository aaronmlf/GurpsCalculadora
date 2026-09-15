from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from utils.ui_preferences import clean_preferences, load_ui_preferences, save_ui_preferences


class UIPreferencesTests(unittest.TestCase):
    def test_validation_and_roundtrip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'ui.json'
            value = clean_preferences({'favorites': [1, 1, 2, -1, '3'], 'font_size': 14, 'theme': 'light'})
            self.assertEqual(value['favorites'], [1, 2])
            save_ui_preferences(path, value)
            self.assertEqual(load_ui_preferences(path), value)

    def test_corruption_is_preserved_and_defaults_are_safe(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'ui.json'
            path.write_text('broken')
            self.assertEqual(load_ui_preferences(path)['theme'], 'dark')
            self.assertEqual(path.read_text(), 'broken')
        self.assertEqual(clean_preferences({'font_size': 1000, 'window': '1x2'})['window'], '1024x768')
