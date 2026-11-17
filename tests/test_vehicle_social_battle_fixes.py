"""Regressions for the vehicle, Social, and Mass Combat interface audit."""

from dataclasses import replace
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
import unittest
from unittest.mock import patch

from calculators.vehicles import (SpacecraftRecord, VehicleEngine, VehicleMovementInput, VehicleRecord,
                                  VehicleSession, VehicleState)
from tests.tk_support import requires_tk
from utils.gui_form_state import descendants
from utils.i18n import t
from utils.vehicle_combat_ui import vehicle_choices


class VehicleDefinitionTests(unittest.TestCase):
    def test_rebinding_uses_latest_definition_without_replenishing_or_repairing(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'vehicles.json'
            original = SpacecraftRecord('ship', 'Ship', 'Custom', '-', st_hp=30, fuel_hours=5,
                                        acceleration_g=1, delta_v_mps=50)
            changed = replace(original, st_hp=40, fuel_hours=10, acceleration_g=2, delta_v_mps=100)
            state = VehicleState(original, current_hp=12, speed_yards_per_second=10, fuel_remaining=3,
                                 delta_v_remaining_mps=25, systems_disabled=['sensors'], conditions=['smoke'])
            session = VehicleSession({'ship': state}, elapsed_seconds=12, history=[{'kind': 'previous'}], autosave_path=path)
            before = session.snapshot()
            rebound = session.state_for(changed)
            self.assertEqual(rebound, replace(state, record=changed))
            self.assertIsNot(rebound.record, changed)
            self.assertEqual(session.snapshot(), before)
            self.assertFalse(path.exists())

            movement = VehicleEngine().calculate_movement(VehicleMovementInput(rebound, environment='space'))
            self.assertTrue(movement.valid)
            self.assertAlmostEqual(movement.final_speed, 31.46)
            forged_state = replace(rebound, current_hp=40)
            with self.assertRaisesRegex(ValueError, 'stale_vehicle_movement'):
                session.apply_movement('ship', movement, forged_state, before)
            self.assertEqual(session.snapshot(), before)
            session.apply_movement('ship', movement, rebound, before)
            self.assertEqual(state.record, changed)
            self.assertEqual((state.current_hp, state.systems_disabled, state.conditions), (12, ['sensors'], ['smoke']))
            self.assertLess(state.fuel_remaining, 3)
            self.assertLess(state.delta_v_remaining_mps, 25)
            self.assertEqual(session.history[0], {'kind': 'previous'})
            self.assertEqual(VehicleSession.load_or_new(path).snapshot(), session.snapshot())

            self.assertTrue(session.undo())
            self.assertEqual(session.snapshot(), before)
            self.assertEqual(session.state_for(changed), rebound)

    def test_choices_preserve_unique_labels_and_disambiguate_same_name_by_id(self):
        first = VehicleRecord('custom.car.a', 'Car', 'Custom', '-')
        second = replace(first, identifier='custom.car.b')
        other = replace(first, identifier='test.other', name='Truck')
        self.assertEqual(vehicle_choices((first, other))['Car — Custom p.-'], first)
        choices = vehicle_choices((first, second, other))
        self.assertEqual(len(choices), 3)
        self.assertEqual(choices['Car — Custom p.- [custom.car.a]'], first)
        self.assertEqual(choices['Car — Custom p.- [custom.car.b]'], second)


@requires_tk
class VehicleSocialBattleGuiTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'GURPS_CALCULADORA_DATA_DIR': folder}))
        self.app = GURPSCalculator()
        self.addCleanup(self._close)
        self.app.root.update()

    def _close(self):
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()

    def _button(self, tab_index, key, *, fields=None):
        tab = self.app.root.nametowidget(self.app.notebook.tabs()[tab_index])
        return next(widget for widget in descendants(tab) if isinstance(widget, ttk.Button)
                    and widget.cget('text') == t(key)
                    and (fields is None or getattr(widget, 'validation_fields', None) == fields))

    def test_social_actions_validate_and_use_only_their_own_inputs(self):
        app = self.app
        app.choose_tool(13)
        for language in ('pt_BR', 'en_US'):
            with self.subTest(language=language):
                app._change_language(language)
                app.social_target_will.set('')
                app.social_skill_level.set('')
                app.social_modifier.set('bad')
                app.social_reaction_modifier.set('3')
                with patch('calculators.campaign.roll_3d6', return_value=(10, (3, 3, 4))):
                    with patch.object(app.social_calc, 'resolve_reaction', wraps=app.social_calc.resolve_reaction) as reaction:
                        self._button(13, 'social_reaction').invoke()
                        self.assertEqual(reaction.call_args.args[0].situational_modifier, 3)
                    self.assertIn(f"{t('summary_reaction')}: {t('value_good')}",
                                  app.social_result_text.get('1.0', 'end-1c'))

                app.social_target_will.set('11')
                app.social_skill_level.set('13')
                app.social_modifier.set('-2')
                app.social_reaction_modifier.set('')
                with patch.object(app.social_calc, 'resolve_influence', wraps=app.social_calc.resolve_influence) as influence:
                    self._button(13, 'social_influence').invoke()
                    resolved = influence.call_args.args[0]
                    self.assertEqual((resolved.target.will, resolved.modifier), (11, -2))

    def test_fractional_duration_and_mass_battle_values_reach_engines_in_both_languages(self):
        app = self.app
        for language, separator in (('pt_BR', ','), ('en_US', '.')):
            with self.subTest(language=language):
                app._change_language(language)
                app.vehicle_duration.set('0' + separator + '5')
                with patch.object(app.vehicle_calc, 'calculate_movement', wraps=app.vehicle_calc.calculate_movement) as move:
                    self._button(12, 'common_calculate').invoke()
                    self.assertEqual(move.call_args.args[0].duration_seconds, .5)

                app.mass_attacker_ts.set('12' + separator + '5')
                app.mass_defender_ts.set('10' + separator + '5')
                app.mass_attacker_casualties.set('2' + separator + '5')
                app.mass_defender_casualties.set('1' + separator + '5')
                with patch.object(app.mass_combat_calc, 'calculate', wraps=app.mass_combat_calc.calculate) as calculate:
                    self._button(14, 'common_calculate').invoke()
                    battle = calculate.call_args.args[0]
                    self.assertEqual((battle.attacker.troop_strength, battle.defender.troop_strength,
                                      battle.attacker_casualties, battle.defender_casualties), (12.5, 10.5, 2.5, 1.5))

    def test_edit_and_same_name_copy_refresh_operations_and_preserve_target_identity(self):
        from utils.gui_editors import VehicleEditor

        app = self.app
        app.result_units.set('imperial')
        app.choose_tool(12)
        original = VehicleRecord('custom.audit.car', 'Audit car', 'Custom', '-', move_acceleration=1, move_top_speed=20, dr=2)
        app.vehicle_catalog.save_custom(original)
        app.vehicle_selected.set('Audit car — Custom p.-')
        app._rebuild_ui()
        app.root.update()
        app._run_vehicle()
        with patch('main.messagebox.askyesno', return_value=True):
            app._apply_vehicle_movement()
        app._run_vehicle()
        self.assertIsNotNone(app._pending_vehicle_movement)
        live_before = app.vehicle_session.snapshot()

        editor = VehicleEditor(app)
        editor.variables['move_acceleration'].set('5')
        editor.variables['dr'].set('8')
        with patch('utils.gui_editors.messagebox.askyesno', return_value=True):
            editor.save(True)
        self.assertIsNone(app._pending_vehicle_movement)
        self.assertEqual(app.vehicle_session.snapshot(), live_before)
        app._run_vehicle()
        _, result, _, _, _ = app._pending_vehicle_movement
        self.assertEqual((result.initial_speed, result.final_speed), (1, 6))
        first, _, _ = app.vehicle_combat_panel._states()
        self.assertEqual((first.record.dr, first.speed_yards_per_second), (8, 1))

        app.vehicle_combat_target.set(app.vehicle_selected.get())
        editor = VehicleEditor(app)
        editor.variables['move_acceleration'].set('9')
        editor.save(False)
        first, target, _ = app.vehicle_combat_panel._states()
        self.assertNotEqual(first.record.identifier, target.record.identifier)
        self.assertEqual(first.record.move_acceleration, 9)
        self.assertEqual((target.record.identifier, target.record.move_acceleration), (original.identifier, 5))
        app.vehicle_duration.set('bad')
        with patch.object(app.vehicle_calc, 'calculate_attack', wraps=app.vehicle_calc.calculate_attack) as attack:
            self._button(12, 'ranged_calculate', fields=()).invoke()
            self.assertEqual(attack.call_args.args[0].target, target)
        with patch.object(app.vehicle_calc, 'calculate_collision', wraps=app.vehicle_calc.calculate_collision) as collision:
            app.vehicle_combat_panel.collision()
            self.assertEqual(collision.call_args.args[0].second, target)
        self.assertEqual(app.vehicle_session.snapshot(), live_before)
