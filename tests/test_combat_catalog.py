import json
import tempfile
import unittest
from pathlib import Path

from calculators.injury import ArmorRecord
from calculators.melee_combat import MeleeDamageMode, MeleeWeaponRecord
from utils.combat_catalog import (
    ARMOR_CATALOG_SCHEMA,
    MELEE_CATALOG_SCHEMA,
    STYLE_CATALOG_SCHEMA,
    TECHNIQUE_CATALOG_SCHEMA,
    ArmorCatalog,
    MeleeWeaponCatalog,
    StyleCatalog,
    TechniqueCatalog,
)


class CombatCatalogTests(unittest.TestCase):
    def test_embedded_catalogs_are_broad_unique_and_referenced(self):
        melee = MeleeWeaponCatalog(load_user=False).weapons
        armor = ArmorCatalog(load_user=False).armor
        techniques = TechniqueCatalog(load_user=False).techniques
        styles = StyleCatalog(load_user=False).styles
        self.assertGreaterEqual(len(melee), 350)
        self.assertGreaterEqual(len(armor), 290)
        self.assertGreaterEqual(len(techniques), 110)
        self.assertGreaterEqual(len(styles), 100)
        self.assertEqual(len({item.identifier for item in melee}), len(melee))
        self.assertEqual(len({item.identifier for item in armor}), len(armor))
        self.assertEqual(len({item.identifier for item in techniques}), len(techniques))
        self.assertEqual(len({item.identifier for item in styles}), len(styles))
        self.assertEqual({item.source for item in melee}, {
            "Basic Set", "Martial Arts", "Low-Tech", "High-Tech", "Ultra-Tech"
        })
        self.assertEqual({item.source for item in armor}, {
            "Basic Set", "Martial Arts", "Low-Tech", "High-Tech", "Ultra-Tech"
        })
        for collection in (melee, armor, techniques, styles):
            self.assertTrue(all(item.page and item.source and item.name for item in collection))

    def test_searches_cover_public_filters_and_specialized_sources_sort_first(self):
        melee = MeleeWeaponCatalog(load_user=False)
        results = melee.search("Axe")
        self.assertTrue(results)
        same_name = [item for item in results if item.name == "Axe"]
        self.assertNotEqual(same_name[0].source, "Basic Set")
        self.assertTrue(melee.search(source="Ultra-Tech"))
        self.assertTrue(melee.search(skill="Broadsword"))
        armor = ArmorCatalog(load_user=False)
        self.assertTrue(armor.search(location="arm", armor_type="flexible"))
        techniques = TechniqueCatalog(load_user=False)
        self.assertTrue(techniques.search(prerequisite="Karate", profile="realistic"))
        self.assertFalse(any(item.silly for item in techniques.search(profile="cinematic")))
        styles = StyleCatalog(load_user=False)
        self.assertTrue(styles.search(skill="Judo"))
        self.assertTrue(styles.search(technique="Arm Lock"))
        self.assertEqual(styles.search(profile="basic"), [])

    def test_custom_presets_use_user_files_and_public_schemas(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            melee_path = root / "melee.json"
            melee = MeleeWeaponCatalog(user_path=melee_path, load_user=False)
            melee.save_custom(MeleeWeaponRecord(
                "temporary", "User", "-", "Test Blade", "3", "Sword", ["Broadsword"],
                [MeleeDamageMode("sw", "cut", ["1"])],
            ))
            self.assertTrue(melee_path.exists())
            self.assertEqual(json.loads(melee_path.read_text())["schema"], MELEE_CATALOG_SCHEMA)
            armor_path = root / "armor.json"
            armor = ArmorCatalog(user_path=armor_path, load_user=False)
            armor.save_custom(ArmorRecord("temporary", "User", "-", "Test Armor", dr=3))
            self.assertEqual(json.loads(armor_path.read_text())["schema"], ARMOR_CATALOG_SCHEMA)

    def test_invalid_json_and_each_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            path.write_text("{}", encoding="utf-8")
            for cls in (MeleeWeaponCatalog, ArmorCatalog, TechniqueCatalog, StyleCatalog):
                with self.subTest(cls=cls.__name__), self.assertRaises(ValueError):
                    cls(user_path=path)
        self.assertEqual(TECHNIQUE_CATALOG_SCHEMA, "gurps-calculadora.technique-catalog.v1")
        self.assertEqual(STYLE_CATALOG_SCHEMA, "gurps-calculadora.style-catalog.v1")


if __name__ == "__main__":
    unittest.main()
