from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from calculators.powers import AdvantageRecord, ModifierRecord, PowerRecord, AbilityBuildInput, AbilityEngine
from calculators.vehicles import VehicleRecord, VehicleCatalog
from utils.editor_records import (vehicle_document, load_vehicle_document, ability_document,
                                  load_ability_document, write_document, read_document, number)


class EditorRecordTests(unittest.TestCase):
    def test_vehicle_roundtrip_and_invalid_numbers(self):
        record = VehicleRecord('custom.vehicle.test', 'Test', 'Custom', '-', move_top_speed=12.5)
        self.assertEqual(load_vehicle_document(vehicle_document(record)), record)
        for invalid in ('nan', 'inf', True, 'abc'):
            with self.assertRaises(ValueError):
                number(invalid, float)
        with self.assertRaises(ValueError):
            number('1.5', int)
        self.assertEqual(number('1,5', float), 1.5)

    def test_ability_roundtrip_preserves_modifier_values(self):
        build = AbilityBuildInput(AdvantageRecord('a', 'A', 'Basic Set', '1', 20, 10),
                                  [ModifierRecord('m', 'M', 'Powers', '1', 50)],
                                  PowerRecord('p', 'P', 'Powers', '1', -10), 3)
        name, loaded = load_ability_document(ability_document('Example', build))
        self.assertEqual(name, 'Example')
        self.assertEqual(loaded, build)
        self.assertEqual(AbilityEngine().calculate(loaded).modified_cost, 56)
        loaded.modifiers.append(deepcopy(loaded.modifiers[0]))
        with self.assertRaises(ValueError):
            ability_document(name, loaded)

    def test_invalid_json_is_not_changed(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            for text in ('{"x": 1, "x": 2}', '{"x": NaN}', 'bad'):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_document(path)
                self.assertEqual(path.read_text(encoding='utf-8'), text)

    def test_atomic_vehicle_save_failure_keeps_memory_and_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'vehicles.json'
            catalog = VehicleCatalog(Path(__file__).resolve().parents[1] / 'data' / 'vehicles.json', path)
            before = list(catalog.custom)
            with patch('calculators.vehicles.os.replace', side_effect=OSError('test')):
                with self.assertRaises(OSError):
                    catalog.save_custom(VehicleRecord('custom.test', 'Test', 'Custom', '-'))
            self.assertEqual(catalog.custom, before)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_document_atomic_roundtrip(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'document.json'
            write_document(path, {'schema': 'test', 'name': 'Água'})
            self.assertEqual(read_document(path)['name'], 'Água')
