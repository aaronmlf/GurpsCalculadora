import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from dataclasses import replace
from calculators.vehicles import VehicleRecord, SpacecraftRecord, VehicleState, VehicleSession, VehicleEngine, VehicleMovementInput


class VehicleSessionTests(unittest.TestCase):
    def test_apply_save_reload_and_undo_history(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            state = VehicleState(SpacecraftRecord('ship', 'Ship', 'Custom', '-', acceleration_g=1, delta_v_mps=100))
            session = VehicleSession({}, autosave_path=path)
            initial = session.snapshot()
            result = VehicleEngine().calculate_movement(VehicleMovementInput(state, environment='space'))
            session.apply_movement('ship', result, state, initial)
            loaded = VehicleSession.load_or_new(path)
            self.assertEqual(session.snapshot(), loaded.snapshot())
            self.assertIsInstance(loaded.vehicles['ship'].record, SpacecraftRecord)
            self.assertTrue(session.undo())
            self.assertEqual(session.snapshot(), initial)
            self.assertEqual(VehicleSession.load_or_new(path).snapshot(), initial)

    def test_save_failure_preserves_memory_and_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            state = VehicleState(VehicleRecord('v', 'V', 'Custom', '-'))
            session = VehicleSession({'v': state}, autosave_path=path)
            session.save()
            before, disk = session.snapshot(), path.read_bytes()
            result = VehicleEngine().calculate_movement(VehicleMovementInput(state))
            with patch('utils.editor_records.os.replace', side_effect=OSError('disk')):
                with self.assertRaises(OSError): session.apply_movement('v', result)
            self.assertEqual(session.snapshot(), before)
            self.assertEqual(path.read_bytes(), disk)
            self.assertFalse(session.undo())

    def test_stale_and_invalid_results_are_rejected(self):
        state = VehicleState(VehicleRecord('v', 'V', 'Custom', '-'))
        session = VehicleSession({'v': state})
        result = VehicleEngine().calculate_movement(VehicleMovementInput(state))
        before = session.snapshot()
        for invalid in (replace(result, final_speed=float('nan')), replace(result, fuel_used=1)):
            with self.assertRaises(ValueError): session.apply_movement('v', invalid)
        self.assertEqual(session.snapshot(), before)
        session.apply_movement('v', result)
        with self.assertRaises(ValueError): session.apply_movement('v', result, expected_snapshot=before)

    def test_corruption_is_preserved(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'session.json'
            path.write_text('{broken', encoding='utf-8')
            session = VehicleSession.load_or_new(path)
            self.assertEqual(session.vehicles, {})
            self.assertEqual(session.recovered_file.read_text(encoding='utf-8'), '{broken')

    def test_fractional_seconds_are_not_discarded(self):
        state = VehicleState(VehicleRecord('v', 'V', 'Custom', '-'))
        session = VehicleSession({'v': state})
        result = VehicleEngine().calculate_movement(VehicleMovementInput(state, duration_seconds=.5))
        session.apply_movement('v', result)
        self.assertEqual(session.elapsed_seconds, .5)
