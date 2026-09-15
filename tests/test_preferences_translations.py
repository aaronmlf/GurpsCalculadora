import json
import ast
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory
import unittest
from utils.preferences import load_preferences, save_preferences


class PreferenceTranslationTests(unittest.TestCase):
    def test_new_engine_error_codes_have_specific_translations(self):
        root = Path(__file__).resolve().parents[1]
        codes = set()
        for module in ("strength", "magic", "powers", "vehicles", "campaign"):
            tree = ast.parse((root / "calculators" / f"{module}.py").read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                function = node.func
                error = (isinstance(function, ast.Name) and function.id == "ValueError") or (
                    isinstance(function, ast.Attribute) and function.attr == "append" and
                    isinstance(function.value, ast.Name) and function.value.id == "errors")
                if error and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    codes.add(node.args[0].value)
        for language in ("pt_BR", "en_US"):
            catalog = json.loads((root / "i18n" / f"{language}.json").read_text(encoding='utf-8'))
            missing = {code for code in codes if "engine_error_" + code not in catalog}
            self.assertFalse(missing, f"{language}: {sorted(missing)}")

    def test_saved_preferences_and_corruption_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            save_preferences(path, "en_US", "imperial")
            self.assertEqual(load_preferences(path), {"language": "en_US", "units": "imperial"})
            path.write_text("broken", encoding="utf-8")
            self.assertEqual(load_preferences(path), {})
            self.assertEqual(path.read_text(), "broken")

    def test_keys_placeholders_and_duplicates(self):
        root = Path(__file__).resolve().parents[1] / "i18n"
        def unique(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result, f"Duplicate translation: {key}")
                result[key] = value
            return result
        pt, en = [json.loads((root / f"{language}.json").read_text(encoding='utf-8'), object_pairs_hook=unique)
                  for language in ("pt_BR", "en_US")]
        self.assertEqual(set(pt), set(en))
        formatter = Formatter()
        for key in pt:
            fields = lambda text: sorted((field, spec, conversion or '')
                for _, field, spec, conversion in formatter.parse(text) if field is not None)
            self.assertEqual(fields(pt[key]), fields(en[key]), key)
