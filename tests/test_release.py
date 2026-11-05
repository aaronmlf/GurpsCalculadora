import json
from pathlib import Path
import unittest

from tools.release_inputs import read_version, resource_paths, source_paths
from version import __version__


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_version_identification_and_json_packaging(self):
        self.assertEqual(read_version(ROOT), __version__)
        spec = (ROOT / "packaging" / "GurpsCalculadora.spec").read_text(encoding="utf-8")
        self.assertIn('resource_paths(project_root)', spec)
        resources = set(resource_paths(ROOT))
        self.assertEqual(resources, {
            "i18n/en_US.json", "i18n/pt_BR.json", "data/armor.json", "data/extended_rules.json",
            "data/glossary.json", "data/magic_table_stats.json", "data/melee_weapons.json",
            "data/styles.json", "data/techniques.json", "data/vehicles.json", "data/weapons.json",
        })
        source = set(source_paths(ROOT))
        self.assertTrue(resources <= source)
        for name in ("LEIA-ME_LINUX.txt", "LEIA-ME_WINDOWS.txt"):
            self.assertIn(f"packaging/{name}", source)

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
