import json
from pathlib import Path
import unittest

from version import __version__


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_identification_and_json_packaging(self):
        self.assertEqual(__version__, "1.6.0")
        spec = (ROOT / "packaging" / "GurpsCalculadora.spec").read_text(encoding="utf-8")
        self.assertIn('for folder in ("i18n", "data")', spec)
        self.assertIn('rglob("*.json")', spec)
        self.assertIn('not path.is_symlink()', spec)
        for name in ("LEIA-ME_LINUX.txt", "LEIA-ME_WINDOWS.txt"):
            self.assertIn("v1.6.0", (ROOT / "packaging" / name).read_text(encoding="utf-8"))

    def test_canonical_glossary_is_versioned_unique_and_referenced(self):
        glossary = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
        self.assertEqual(glossary["schema"], "gurps-calculadora.glossary.v1")
        keys = [item["key"] for item in glossary["terms"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue({"injury", "major_wound", "hit_location", "accuracy", "recoil"} <= set(keys))
        self.assertTrue(all(item["english"] and item["portuguese"] for item in glossary["terms"]))
        self.assertTrue(all(item["source"] and item["page"] for item in glossary["terms"]))

    def test_git_and_packaging_exclude_local_books(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/GURPS 4th Edition/", ignored)
        self.assertIn("*.pdf", ignored)
        spec = (ROOT / "packaging" / "GurpsCalculadora.spec").read_text(encoding="utf-8")
        self.assertNotIn("GURPS 4th Edition", spec)
        self.assertNotIn(".pdf", spec.casefold())


if __name__ == "__main__":
    unittest.main()
