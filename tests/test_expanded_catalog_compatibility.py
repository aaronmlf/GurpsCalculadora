from dataclasses import replace
from pathlib import Path
import unittest

from utils.rules_catalog import ExtendedRulesCatalog
from calculators.magic import SpellcastingEngine, CastingInput
from calculators.powers import PsionicEngine, PsiUseInput
from calculators.vehicles import VehicleEngine, VehicleCatalog, VehicleState, VehicleMovementInput


class ExpandedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = ExtendedRulesCatalog()

    def test_all_expanded_entries_can_be_evaluated_without_crashes(self):
        spells = self.catalog.records('spells')
        self.assertGreaterEqual(len(spells), 813)
        for spell in spells:
            with self.subTest(spell=spell.identifier):
                result = SpellcastingEngine().resolve(CastingInput(spell), cast_roll=10)
                if not result.valid:
                    self.assertEqual(result.state_delta.fp_change, 0)
        for ability in self.catalog.records('psi_abilities'):
            PsionicEngine().resolve(PsiUseInput(ability), roll=10)
        root = Path(__file__).resolve().parents[1]
        vehicles = VehicleCatalog(root / 'data/vehicles.json', root / 'unused.json', load_user=False)
        self.assertGreaterEqual(len(vehicles.vehicles), 126)
        for record in vehicles.vehicles:
            VehicleEngine().calculate_movement(VehicleMovementInput(VehicleState(record)))

    def test_table_columns_and_case_normalization(self):
        spells = {s.identifier: s for s in self.catalog.records('spells')}
        fire = spells['spell.create-fire']
        self.assertEqual((fire.spell_class, fire.base_cost, fire.maintenance_cost), ('area', 2, 1))
        mind = spells['spell.mind-reading']
        self.assertEqual((mind.base_cost, mind.maintenance_cost, mind.casting_time_seconds), (4, 2, 10))

    def test_variable_cost_is_not_guessed(self):
        spell = next(s for s in self.catalog.records('spells') if s.identifier == 'spell.fireball')
        result = SpellcastingEngine().resolve(CastingInput(spell), cast_roll=3)
        self.assertIn('spell_requires_parameters', result.errors)
        self.assertIsNone(result.roll)
        chosen = replace(spell, base_cost=1, casting_time_seconds=1)
        self.assertTrue(SpellcastingEngine().calculate(CastingInput(chosen)).valid)

    def test_psi_new_metadata_is_preserved_not_used_as_fp(self):
        ability = self.catalog.records('psi_abilities')[0]
        self.assertEqual(ability.cost, '30')
        self.assertIsNotNone(ability.notes)
        result = PsionicEngine().resolve(PsiUseInput(ability), roll=3)
        self.assertIn('catalog_reference_only', result.errors)
        self.assertEqual(result.state_delta.fp_change, 0)
        technique = self.catalog.records('psi_techniques')[0]
        self.assertEqual(technique.cost_fp, 2)
