"""Run with xvfb-run when no desktop display is available."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("DISPLAY"), "requires a graphical display")
class UnitGuiTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator
        self.temp = TemporaryDirectory()
        self.paths = patch("main.application_data_dir", return_value=Path(self.temp.name))
        self.paths.start()
        self.app = GURPSCalculator()

    def tearDown(self):
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()
        self.paths.stop()
        self.temp.cleanup()

    def binding(self, variable):
        return next(b for b in self.app._unit_bindings if b.canonical is variable)

    def test_battle_classes_editor_is_explicit_and_persisted_on_apply(self):
        from utils.battle_ui import BattleClassEditor
        app = self.app
        before = app.campaign_session.to_dict()
        dialog = BattleClassEditor(app)
        dialog.values['F'][0].set('5')
        dialog.apply_parameters()
        self.assertEqual(app.campaign_session.to_dict(), before)
        with patch('calculators.campaign.roll_3d6', return_value=(10, [3,3,4])):
            app._run_mass_combat()
        with patch('main.messagebox.askyesno', return_value=True): app._apply_mass_round()
        self.assertEqual(app.campaign_session.battle_class_strengths['gui.mass.attacker']['F'], [5,0])
        self.assertGreater(int(app.mass_attacker_position.get()), 0)
        app._mass_classes = {}
        app._sync_mass_fields()
        self.assertEqual(app._mass_classes['attacker']['F'], [5,0])

    def test_mass_strategy_events_in_both_languages(self):
        app = self.app
        snapshot = app.campaign_session.to_dict()
        for lang in ('pt_BR', 'en_US'):
            app._change_language(lang)
            for a, d, event in [('parley', 'parley', 'parley'), ('full_retreat', 'defense', 'no_battle')]:
                app.mass_attacker_choice.set(a)
                app.mass_defender_choice.set(d)
                with patch('calculators.campaign.roll_3d6', side_effect=AssertionError('rolled')):
                    app._run_mass_combat(False)
                    self.assertIsNone(app._pending_mass_round)
                    app._run_mass_combat()
                self.assertEqual(app._last_mass_result.outcome, event)
                self.assertIsNone(app._pending_mass_round)
                self.assertNotIn('mass_event_', app.mass_result_text.get('1.0', 'end'))
        self.assertEqual(app.campaign_session.to_dict(), snapshot)

    def test_mass_strategy_change_invalidates_pending_result(self):
        app = self.app
        with patch('calculators.campaign.roll_3d6', return_value=(10, [3,3,4])):
            app._run_mass_combat()
        snapshot = app.campaign_session.to_dict()
        app.mass_attacker_choice.set('parley')
        with patch('main.messagebox.askyesno') as confirm:
            app._apply_mass_round()
        confirm.assert_not_called()
        self.assertEqual(app.campaign_session.to_dict(), snapshot)

    def test_aftermath_dialog_calculate_confirm_and_undo(self):
        from utils.battle_ui import BattleAftermathEditor
        app = self.app
        with patch('calculators.campaign.roll_3d6', return_value=(10, [])):
            app._run_mass_combat()
        with patch('main.messagebox.askyesno', return_value=True):
            app._apply_mass_round()
        snapshot = app.campaign_session.to_dict()
        for lang in ('pt_BR', 'en_US'):
            app._change_language(lang)
            dialog = BattleAftermathEditor(app)
            dialog.retreat.set(True)
            with patch('calculators.battle_aftermath.roll_3d6', side_effect=AssertionError):
                dialog.run(False)
            self.assertIsNone(dialog.pending)
            dialog.rolls['leadership'].set('8')
            dialog.run(False)
            self.assertIsNotNone(dialog.pending)
            self.assertNotIn('mass_aftermath_',dialog.output.cget('text'))
            with patch('utils.battle_ui.messagebox.askyesno', return_value=False):
                dialog.apply_result()
            self.assertEqual(app.campaign_session.to_dict(),snapshot)

            with patch('utils.battle_ui.messagebox.askyesno', return_value=True):
                dialog.apply_result()
            self.assertFalse(app.campaign_session.battle_casualties)
            app.campaign_session.undo()
            self.assertEqual(app.campaign_session.to_dict(),snapshot)

    def test_logistics_editor_save_pay_and_undo_bilingual(self):
        from utils.logistics_ui import LogisticsEditor
        app=self.app
        for lang in ('pt_BR','en_US'):
            app._change_language(lang)
            before=app.campaign_session.to_dict()
            dialog=LogisticsEditor(app)
            dialog.values['monthly_cost'].set('100000')
            dialog.values['funds'].set('1000000')
            dialog.values['ls_land'].set('100')
            dialog.values['readiness'].set('low')
            with patch('utils.logistics_ui.messagebox.askyesno',return_value=False):dialog.save_configuration()
            self.assertEqual(app.campaign_session.to_dict(),before)
            with patch('utils.logistics_ui.messagebox.askyesno',return_value=True):dialog.save_configuration()
            configured=app.campaign_session.to_dict()
            with patch('calculators.logistics.roll_3d6',side_effect=AssertionError):dialog.run(False)
            self.assertIsNone(dialog.pending)
            dialog.values['administration_roll'].set('10')
            dialog.run(False)
            self.assertNotIn('log_ui_',dialog.output.cget('text'))
            with patch('utils.logistics_ui.messagebox.askyesno',return_value=False):dialog.apply_month()
            self.assertEqual(app.campaign_session.to_dict(),configured)
            with patch('utils.logistics_ui.messagebox.askyesno',return_value=True):dialog.apply_month()
            force=app.campaign_session.forces['gui.mass.attacker']
            self.assertEqual(force.resources,900000)
            self.assertEqual(force.readiness_multiplier,.5)
            reopened=LogisticsEditor(app)
            self.assertEqual(reopened.values['monthly_cost'].get(),'100000.0')
            self.assertEqual(reopened.values['funds'].get(),'900000.0')
            reopened.destroy()
            app.campaign_session.undo()
            app.campaign_session.undo()
            self.assertEqual(app.campaign_session.to_dict(),before)

    def test_logistics_changed_inputs_cannot_apply(self):
        from utils.logistics_ui import LogisticsEditor
        dialog=LogisticsEditor(self.app,'defender')
        dialog.values['administration_roll'].set('10')
        dialog.run(False)
        dialog.values['monthly_cost'].set('1')
        with patch('utils.logistics_ui.messagebox.askyesno') as confirm:
            with self.assertRaises(ValueError):dialog.apply_month()
        confirm.assert_not_called()
        dialog.destroy()

    def test_replacement_dialog_bilingual_confirmation(self):
        from utils.replacements_ui import ReplacementEditor
        from calculators.campaign import ForceRecord, ElementRecord
        app=self.app
        key='gui.mass.attacker'
        app.campaign_session.forces[key]=ForceRecord(key,'A',[ElementRecord('e','E',90,['Inf'])],resources=1000)
        for lang in ('pt_BR','en_US'):
            app._change_language(lang)
            before=app.campaign_session.to_dict()
            dialog=ReplacementEditor(app,'attacker')
            for k,v in {'full_strength':'100','full_cost':'1000','full_days':'120','percent':'10'}.items():dialog.values[k].set(v)
            dialog.preview()
            self.assertNotIn('replacement_',dialog.output.cget('text'))
            with patch('utils.replacements_ui.messagebox.askyesno',return_value=False):dialog.start()
            self.assertEqual(app.campaign_session.to_dict(),before)
            with patch('utils.replacements_ui.messagebox.askyesno',return_value=True):dialog.start()
            self.assertEqual(app.campaign_session.forces[key].troop_strength,90)
            dialog.destroy()
            dialog=ReplacementEditor(app,'attacker')
            dialog.values['days'].set('12')
            with patch('utils.replacements_ui.messagebox.askyesno',return_value=True):dialog.advance()
            self.assertEqual(app.campaign_session.forces[key].troop_strength,100)
            dialog.destroy()
            app.campaign_session.undo()
            app.campaign_session.undo()
            self.assertEqual(app.campaign_session.to_dict(),before)

    def test_mass_round_confirmation_finish_and_undo(self):
        app = self.app
        before = app.campaign_session.to_dict()
        with patch('calculators.campaign.roll_3d6', return_value=(10, [3,3,4])):
            app._run_mass_combat()
        with patch('main.messagebox.askyesno', return_value=False): app._apply_mass_round()
        self.assertEqual(app.campaign_session.to_dict(), before)
        with patch('main.messagebox.askyesno', return_value=True): app._apply_mass_round()
        self.assertEqual(app.campaign_session.forces['gui.mass.attacker'].troop_strength, 100)
        accumulated = app.campaign_session.to_dict()
        with patch('main.messagebox.askyesno', return_value=True): app._apply_mass_round()
        self.assertEqual(app.campaign_session.to_dict(), accumulated)
        with patch('main.simpledialog.askfloat', side_effect=[5, None]): app._finish_mass_battle()
        self.assertEqual(app.campaign_session.to_dict(), accumulated)
        with patch('main.simpledialog.askfloat', side_effect=[5, 20]), patch('main.messagebox.askyesno', return_value=True):
            app._finish_mass_battle()
        self.assertEqual(app.campaign_session.forces['gui.mass.attacker'].troop_strength, 95)
        self.assertFalse(app.campaign_session.battle_casualties)
        with patch('main.messagebox.askyesno', return_value=True): app._undo_mass_campaign()
        self.assertEqual(app.campaign_session.to_dict(), accumulated)

    def test_changed_mass_inputs_invalidate_apply(self):
        app = self.app
        before = app.campaign_session.to_dict()
        with patch('calculators.campaign.roll_3d6', return_value=(10, [3,3,4])): app._run_mass_combat()
        app.mass_attacker_ts.set('200')
        with patch('main.messagebox.askyesno', side_effect=AssertionError('stale confirmation')):
            app._apply_mass_round()
        self.assertEqual(app.campaign_session.to_dict(), before)

    def test_mass_combat_calculate_never_rolls_or_changes_campaign(self):
        app = self.app
        before = app.campaign_session.to_dict()
        app.mass_attacker_casualties.set('15')
        app.mass_defender_casualties.set('10')
        with patch('calculators.campaign.roll_3d6', side_effect=AssertionError('rolled')):
            app._run_mass_combat(False)
        self.assertIsNone(app._last_mass_result)
        self.assertEqual(app.campaign_session.to_dict(), before)
        self.assertIn('9', app.mass_result_text.get('1.0', 'end'))

    def test_campaign_editor_confirms_before_saving(self):
        from utils.gui_editors import CampaignEditor
        dialog = CampaignEditor(self.app)
        dialog.variables['name'].set('Guild')
        dialog.variables['resources'].set('10')
        with patch('utils.gui_editors.messagebox.askyesno', return_value=False):
            dialog.save_record()
        self.assertFalse(self.app.campaign_session.organizations)
        with patch('utils.gui_editors.messagebox.askyesno', return_value=True):
            dialog.save_record()
        self.assertEqual(len(self.app.campaign_session.organizations), 1)
        with patch('utils.gui_editors.messagebox.askyesno', return_value=True):
            dialog.undo()
        self.assertFalse(self.app.campaign_session.organizations)
        dialog.destroy()

    def test_ceremonial_editor_and_resistance_are_non_mutating(self):
        from utils.gui_editors import CeremonialEditor
        before = self.app.combat_session.to_dict()
        editor = CeremonialEditor(self.app)
        editor.energy.set('3')
        editor.add()
        editor.apply_parameters()
        self.assertEqual(self.app.magic_system.get(), 'ceremonial')
        self.assertEqual(self.app._magic_ceremony.assistants[0].energy, 3)
        self.app.magic_resisted.set(True)
        self.app.magic_resistance.set('18')
        self.assertEqual(self.app._resistance_input('magic').target, 18)
        self.assertEqual(self.app.combat_session.to_dict(), before)

    def test_vehicle_movement_requires_confirmation_and_can_undo(self):
        from calculators.vehicles import VehicleRecord
        app = self.app
        app._vehicle_map['Test'] = VehicleRecord('v', 'V', 'Custom', '-')
        app.vehicle_selected.set('Test')
        before = app.vehicle_session.snapshot()
        app._run_vehicle()
        self.assertEqual(app.vehicle_session.snapshot(), before)
        with patch('main.messagebox.askyesno', return_value=False):
            app._apply_vehicle_movement()
        self.assertEqual(app.vehicle_session.snapshot(), before)
        with patch('main.messagebox.askyesno', return_value=True):
            app._apply_vehicle_movement()
        self.assertIn('v', app.vehicle_session.vehicles)
        app._undo_vehicle_movement()
        self.assertEqual(app.vehicle_session.snapshot(), before)

    def test_custom_power_modifier_is_explicit_and_marks_preview_stale(self):
        from utils.gui_editors import AbilityEditor
        from utils.editor_records import ability_document, load_ability_document
        app = self.app
        editor = AbilityEditor(app)
        editor.calculate()
        editor.modifier_name.set('GM option')
        editor.modifier_percent.set('-20')
        editor.add_modifier()
        self.assertEqual(editor.build().modifiers[-1].source, 'Custom')
        self.assertTrue(editor.error.cget('text'))
        name, build = load_ability_document(ability_document('Test', editor.build()))
        self.assertEqual(build.modifiers[-1].percent, -20)
        editor.destroy()

    def test_casting_assistant_changes_inputs_only(self):
        from utils.gui_editors import CastingAssistant
        app = self.app
        before = app.combat_session.to_dict()
        dialog = CastingAssistant(app)
        dialog.cost.set('3')
        dialog.time.set('2')
        dialog.apply_parameters()
        self.assertEqual(app.magic_cost_override.get(), '3')
        self.assertEqual(app.magic_time_override.get(), '2')
        self.assertEqual(app.combat_session.to_dict(), before)
        dialog = CastingAssistant(app)
        app.magic_spell.set('changed')
        with self.assertRaises(ValueError):
            dialog.apply_parameters()
        dialog.destroy()

    def test_vehicle_editor_converts_units_without_changing_original(self):
        from calculators.vehicles import VehicleRecord
        from utils.gui_editors import VehicleEditor
        app = self.app
        template = VehicleRecord('basic.test', 'Test', 'Basic Set', '1', move_top_speed=10, range_miles=100)
        app._vehicle_map['Test'] = template
        app.vehicle_selected.set('Test')
        editor = VehicleEditor(app)
        self.assertAlmostEqual(float(editor.variables['move_top_speed'].get()), 9.144)
        self.assertAlmostEqual(editor.record().range_miles, 100)
        editor.variables['move_top_speed'].set('18,288')
        self.assertAlmostEqual(editor.record().move_top_speed, 20)
        self.assertEqual(template.move_top_speed, 10)
        from utils.editor_records import read_document, load_vehicle_document
        output = Path(self.temp.name) / 'vehicle-export.json'
        with patch('utils.gui_editors.filedialog.asksaveasfilename', return_value=str(output)):
            editor.export_record()
        exported = load_vehicle_document(read_document(output))
        self.assertEqual(exported.source, 'Custom')
        self.assertEqual(exported.move_top_speed, 20)
        self.assertIn('Basic Set', exported.original['based_on'])
        editor.destroy()

    def test_ability_editor_preview_is_non_mutating(self):
        from utils.gui_editors import AbilityEditor
        app = self.app
        before = app.combat_session.to_dict()
        editor = AbilityEditor(app)
        editor.calculate()
        self.assertTrue(editor.output.get('1.0', 'end-1c'))
        self.assertEqual(app.combat_session.to_dict(), before)
        editor.destroy()

    def test_numeric_presets_use_canonical_units_and_reject_unknown_fields(self):
        from utils.gui_presets import fields_for, validate_preset, SCHEMA
        app = self.app
        app.ranged_distance.set('91.44')
        app.result_units.set('imperial')
        app._change_units()
        fields = fields_for(app, 8)
        self.assertAlmostEqual(float(fields['ranged_distance'][0].get()), 91.44)
        document = {'schema': SCHEMA, 'tool': 8, 'values': {'ranged_distance': '91.44'}}
        self.assertEqual(validate_preset(document, 8, fields), document['values'])
        with self.assertRaises(ValueError):
            validate_preset(document, 9, fields)
        document['values']['combat_session'] = '0'
        with self.assertRaises(ValueError):
            validate_preset(document, 8, fields)

    def test_catalog_favorites_are_saved_without_changing_selected_spell(self):
        from utils.gui_workspace import CatalogDialog
        from utils.ui_preferences import load_ui_preferences
        app = self.app
        combo = next(widget for widget in app._form_states[10].widgets
                     if hasattr(widget, 'catalog_records'))
        original = app.magic_spell.get()
        dialog = CatalogDialog(combo)
        dialog.list.selection_set(0)
        dialog.toggle_favorite()
        self.assertTrue(load_ui_preferences(app.ui_preferences_path)['catalog_favorites'])
        self.assertEqual(app.magic_spell.get(), original)
        dialog.only_favorites.set(True)
        dialog.refresh()
        self.assertEqual(len(dialog.filtered), 1)
        dialog.destroy()

    def test_home_favorites_and_appearance_keep_results(self):
        from utils.ui_preferences import load_ui_preferences
        app = self.app
        app.root.update()
        app.choose_tool(9)
        app.toggle_tool_favorite()
        self.assertIn(9, load_ui_preferences(app.ui_preferences_path)['favorites'])
        app._run_strength()
        app.root.update()
        text = app.strength_result_text.get('1.0', 'end-1c')
        app.ui_preferences.update(theme='light', font_size=14)
        app._setup_theme()
        app._rebuild_ui()
        app.root.update()
        self.assertEqual(app.strength_result_text.get('1.0', 'end-1c'), text)
        self.assertEqual(app.colors['bg'], '#f2f4f7')
        app.choose_tool('home')
        app.root.update()
        self.assertTrue(app.home_frame.winfo_ismapped())
        app.choose_tool(10)
        app.root.update()
        self.assertTrue(app.notebook.winfo_ismapped())

    def test_session_preview_cancel_and_stale_never_mutate(self):
        from calculators.injury import StateDelta
        from utils.gui_hub import remember_session, confirm_session, session_window
        app = self.app
        app.root.update()
        remember_session(app, 'injury')
        before = app.combat_session.to_dict()
        with patch('utils.gui_hub.messagebox.askyesno', return_value=False) as confirm:
            self.assertFalse(confirm_session(app, 'injury', StateDelta(hp_change=-3)))
            self.assertIn('10 → 7', confirm.call_args.args[1])
        self.assertEqual(app.combat_session.to_dict(), before)
        app.combat_session.combatants[app.session_target_key].current_hp = 8
        with patch('utils.gui_hub.messagebox.showwarning') as warning:
            self.assertFalse(confirm_session(app, 'injury', StateDelta(hp_change=-3)))
            warning.assert_called_once()
        session_window(app)
        app.root.update()

    def test_history_is_bounded_and_survives_rebuild(self):
        app = self.app
        app.root.update()
        for number in range(25):
            app._show_result(app.strength_result_text, [f'ST: {number}'])
            app.root.update()
        self.assertEqual(len(app.strength_result_text.comparison.history), 20)
        app._rebuild_ui()
        app.root.update()
        self.assertEqual(len(app.strength_result_text.comparison.history), 20)
        app.strength_result_text.comparison.show_history()
        app.root.update()

    def test_legacy_forms_reject_invalid_numbers_before_calculation(self):
        from tkinter import ttk
        from utils.i18n import t
        cases = [(0, 'knockback_calculate'), (1, 'slam_calculate'), (2, 'falls_calculate'),
                 (3, 'collisions_calculate'), (4, 'explosions_calculate'), (5, 'falling_objects_calculate')]
        self.app.root.update()
        for index, key in cases:
            form = self.app._form_states[index]
            field, variable, spec = form.fields[0]
            original = variable.get()
            button = next(w for w in form.widgets if isinstance(w, ttk.Button) and w.cget('text') == t(key))
            with self.subTest(tool=key), patch('main.messagebox.showerror') as dialog:
                for bad in ('abc', 'nan', 'inf', ''):
                    variable.set(bad)
                    self.assertFalse(form.validate())
                    self.assertTrue(field.instate(['invalid']))
                    button.invoke()
                    dialog.assert_not_called()
                variable.set(original)
                self.assertTrue(form.validate())
                button.invoke()
                self.app.root.update()
                dialog.assert_not_called()
                self.assertTrue(form.boxes[0].get('1.0', 'end-1c'))

    def test_legacy_fractional_metric_input_and_radio_values(self):
        app = self.app
        app.kb_damage_type.set('cutting')
        app._rebuild_ui()
        self.assertEqual(app.kb_damage_type.get(), 'cutting')
        self.binding(app.falls_distance).display.set('0,5')
        self.assertTrue(app._form_states[2].validate())
        self.assertAlmostEqual(app.falls_distance.get(), 0.5)
        app.root.update()
        app._calculate_falls()
        app.root.update()
        app.falls_distance.set(2)
        self.assertTrue(app.falls_result_text.stale)

    def test_results_comparison_and_staleness_survive_rebuild(self):
        app = self.app
        app.root.update()
        app._run_strength()
        app.root.update()
        original = app.strength_result_text.get('1.0', 'end-1c')
        app.strength_result_text.comparison.keep()
        app.strength_st.set('15')
        self.assertTrue(app.strength_result_text.stale)
        app._change_language('en_US')
        app.root.update()
        self.assertEqual(app.strength_result_text.get('1.0', 'end-1c'), original)
        self.assertEqual(app.strength_result_text.comparison.saved, original)
        self.assertTrue(app.strength_result_text.stale)
        self.assertIn('original', app.strength_result_text.status_label.cget('text'))
        app.result_units.set('imperial')
        app._change_units()
        app.root.update()
        self.assertEqual(app.strength_result_text.get('1.0', 'end-1c'), original)
        app._run_strength()
        app.root.update()
        self.assertFalse(app.strength_result_text.stale)

    def test_inline_validation_blocks_bad_input(self):
        from tkinter import ttk
        from utils.i18n import t
        app = self.app
        form = app._form_states[9]
        app.strength_st.set('oops')
        self.assertFalse(form.validate())
        field = next(iter(form.errors))
        self.assertTrue(field.instate(['invalid']))
        button = next(w for w in form.widgets if isinstance(w, ttk.Button) and w.cget('text') == t('common_calculate'))
        button.invoke()
        self.assertEqual(app.strength_result_text.get('1.0', 'end-1c'), '')
        app.strength_st.set('12')
        self.assertTrue(form.validate())
        button.invoke()
        app.root.update()
        self.assertTrue(app.strength_result_text.get('1.0', 'end-1c'))

    def test_sidebar_selection_survives_language_change(self):
        app = self.app
        app.navigation_tree.selection_set('10')
        app.root.update()
        self.assertEqual(app.notebook.index(app.notebook.select()), 10)
        app._change_language('en_US')
        app.root.update()
        self.assertEqual(app.notebook.index(app.notebook.select()), 10)
        self.assertEqual(len(app.notebook.tabs()), 15)

    def test_ranged_filter_preserves_current_overrides(self):
        app = self.app
        selected = app.ranged_weapon.get()
        app.ranged_half_damage.set('321')
        app._populate_ranged_weapon_box([])
        self.assertEqual(app.ranged_weapon.get(), selected)
        self.assertEqual(app.ranged_half_damage.get(), '321')

    def test_workspace_layout_and_result(self):
        app = self.app
        app.root.geometry('1024x768')
        app.navigation_tree.selection_set('10')
        app.root.update()
        self.assertLess(app.navigation_tree.winfo_rootx(), app.notebook.winfo_rootx())
        app._run_strength()
        app.root.update()
        self.assertTrue(app.strength_result_text.get('1.0', 'end').strip())
        self.assertTrue(app.strength_result_text.tag_ranges('heading'))
        if os.environ.get('GURPS_GUI_SCREENSHOT'):
            import subprocess
            subprocess.run(['import', '-window', str(app.root.winfo_id()),
                            os.environ['GURPS_GUI_SCREENSHOT']], check=True)

    def test_units_change_presentation_not_stored_values(self):
        app = self.app
        app.ranged_distance.set("91.44")
        app.result_units.set("imperial")
        app._change_units()
        self.assertAlmostEqual(float(self.binding(app.ranged_distance).display.get()), 100)
        self.assertAlmostEqual(float(app.ranged_distance.get()), 91.44)
        self.binding(app.ranged_distance).display.set("200")
        self.assertAlmostEqual(float(app.ranged_distance.get()), 182.88)
        app.result_units.set("metric")
        app._change_units()
        self.assertAlmostEqual(float(self.binding(app.ranged_distance).display.get()), 182.88)

    def test_fractional_input_and_catalog_updates(self):
        app = self.app
        app.result_units.set("imperial")
        app._change_units()
        self.binding(app.falls_distance).display.set("1.5")
        self.assertAlmostEqual(app.falls_distance.get(), 1.3716)
        app.ranged_half_damage.set("500")
        self.assertEqual(float(self.binding(app.ranged_half_damage).display.get()), 500)
        app.ranged_half_damage.set("")
        self.assertEqual(self.binding(app.ranged_half_damage).display.get(), "")

    def test_languages_and_preferences(self):
        from utils.preferences import load_preferences
        app = self.app
        app.result_units.set("imperial")
        app._change_units()
        app._change_language("en_US")
        app._run_strength()
        self.assertIn("Capacity:", app.strength_result_text.get("1.0", "end"))
        self.assertIn("lb", app.strength_result_text.get("1.0", "end"))
        app._change_language("pt_BR")
        app._run_strength()
        self.assertIn("Capacidade:", app.strength_result_text.get("1.0", "end"))
        self.assertEqual(load_preferences(app.preferences_path), {"language": "pt_BR", "units": "imperial"})

    def test_rebuild_does_not_accumulate_traces(self):
        app = self.app
        baseline = len(app.ranged_distance.trace_info())
        for _ in range(3):
            app._rebuild_ui()
        self.assertEqual(len(app.ranged_distance.trace_info()), baseline)
