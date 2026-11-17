"""Regression tests for the two supernatural workbenches and their editors."""
import os
import tempfile
import unittest
from tkinter import ttk
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.gui_editors import CeremonialEditor
from utils.gui_form_state import descendants
from utils.gui_workspace import CatalogDialog
from utils.i18n import t


@requires_tk
class MagicPowersWorkbenchTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator

        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'GURPS_CALCULADORA_DATA_DIR': directory}))
        self.app = GURPSCalculator()
        self.errors = []
        self.app.root.report_callback_exception = lambda *args: self.errors.append(args[1])
        self.addCleanup(self.close)
        self.app.root.geometry('800x600')
        self.app.ui_preferences['font_size'] = 18
        self.app._rebuild_ui()
        self.app.root.update()

    def close(self):
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()
        self.assertFalse(self.errors)

    def select(self, index):
        self.app.choose_tool(index)
        self.app.root.update()

    def button(self, index, key):
        parent = self.app.root.nametowidget(self.app.notebook.tabs()[index])
        return next(widget for widget in descendants(parent)
                    if isinstance(widget, ttk.Button) and widget.cget('text') == t(key))

    def test_ceremony_updates_visible_system_and_footer_fits_desktop(self):
        app = self.app
        self.select(10)
        editor = CeremonialEditor(app)
        app.root.update()
        button = next(widget for widget in editor.actions.winfo_children()
                      if widget.cget('text') == t('ui_apply_parameters'))
        button_bottom = button.winfo_rooty() + button.winfo_height()
        self.assertTrue(button.winfo_viewable())
        self.assertLessEqual(button_bottom, app.root.winfo_screenheight())
        self.assertLessEqual(button_bottom, editor.winfo_rooty() + editor.winfo_height())
        editor.caster.set('3')
        button.invoke()
        app.root.update()
        self.assertEqual(app.magic_system.get(), 'ceremonial')
        self.assertTrue(app.magic_system_picker.get().startswith(t('value_ceremonial')))
        self.assertEqual(app._magic_ceremony.caster_energy, 3)
        app._change_language('en_US')
        app.root.update()
        self.assertTrue(app.magic_system_picker.get().startswith(t('value_ceremonial')))

    def test_catalog_filters_independent_persistent_and_empty_is_explicit(self):
        app = self.app
        self.select(10)
        picker = app.magic_spell_picker
        previous = app._magic_map[app.magic_spell.get()].identifier
        app._run_magic(False)
        app.root.update()
        picker.catalog_filter.set('unmatched_spell_marker')
        self.assertEqual(str(picker.cget('state')), 'disabled')
        self.assertIn(t('ui_no_matches'), picker.catalog_filter_status.cget('text'))
        self.assertIn(t('ui_catalog_selection_unchanged'), picker.catalog_filter_status.cget('text'))
        self.assertEqual(app._magic_map[app.magic_spell.get()].identifier, previous)
        self.assertFalse(app.magic_result_text.stale)
        picker.catalog_filter.set('fireball')
        self.assertTrue(0 < len(picker.cget('values')) < len(picker.catalog_values))
        dialog = CatalogDialog(picker)
        dialog.query.set('light')
        dialog.filters['college'].set('Light and Darkness')
        self.assertTrue(dialog.filtered)
        self.assertEqual(len(dialog.values), len(app._magic_map))
        self.assertNotIn(dialog.filtered[0], picker.cget('values'))
        app._change_language('en_US')
        app.root.update()
        self.assertFalse(dialog.winfo_exists())
        picker = app.magic_spell_picker
        self.assertEqual(picker.catalog_filter.get(), 'fireball')
        self.assertEqual(app._magic_map[app.magic_spell.get()].identifier, previous)
        dialog = CatalogDialog(picker)
        self.assertEqual(dialog.query.get(), 'light')
        self.assertEqual(dialog.filters['college'].get(), 'Light and Darkness')
        self.assertTrue(dialog.filtered)
        dialog.list.selection_set(0)
        choice = dialog.filtered[0]
        dialog.select()
        dialog.use.invoke()
        self.assertEqual(app.magic_spell.get(), choice)
        self.assertEqual(picker.catalog_filter.get(), 'fireball')
        self.assertIn(choice, picker.catalog_active.cget('text'))

        self.select(11)
        psi_picker = app.power_psi_picker
        psi_picker.catalog_filter.set('emotion')
        before = psi_picker.cget('values')
        self.assertTrue(0 < len(before) < len(psi_picker.catalog_values))
        app.result_units.set('imperial')
        app._change_units()
        self.assertEqual(app.power_psi_picker.catalog_filter.get(), 'emotion')
        self.assertEqual(app.power_psi_picker.cget('values'), before)

    def test_advantage_and_psi_actions_validate_only_their_own_fields(self):
        app = self.app
        self.select(11)
        app.power_skill.set('')
        app.root.update()
        with patch.object(app.ability_calc, 'calculate', wraps=app.ability_calc.calculate) as calculate:
            self.button(11, 'powers_build').invoke()
        calculate.assert_called_once()
        self.assertIn(t('summary_final_cost'), app.powers_result_text.get('1.0', 'end-1c'))

        app.power_skill.set('12')
        app.power_levels.set('')
        app.power_disadvantage_points.set('not used')
        app.power_use_session.set(True)
        app.power_fp.set('not used')
        self.assertNotEqual(app._psi_map[app.power_psi.get()].operational_model, 'mental_surgery')
        with patch.object(app.psi_calc, 'calculate', wraps=app.psi_calc.calculate) as calculate:
            self.button(11, 'common_calculate').invoke()
        calculate.assert_called_once()
        self.assertEqual(calculate.call_args.args[0].changed_disadvantage_points, 0)
        app.power_skill.set('')
        with patch.object(app.psi_calc, 'calculate') as calculate:
            self.button(11, 'common_calculate').invoke()
            app.root.update()
        calculate.assert_not_called()

    def test_narrow_error_stays_under_field_without_collapsing_its_width(self):
        app = self.app
        self.select(11)
        app.power_skill.set('')
        self.button(11, 'common_calculate').invoke()
        app.root.update()
        state = app.powers_result_text.form_state
        skill = next(widget for widget, variable, _ in state.fields if str(variable) == str(app.power_skill))
        error = skill.validation_label.label
        self.assertTrue(error.winfo_ismapped())
        self.assertGreaterEqual(skill.winfo_width(), 92)
        self.assertGreaterEqual(int(error.cget('wraplength')), 80)
        self.assertGreaterEqual(error.winfo_rooty(), skill.winfo_rooty() + skill.winfo_height())
        self.assertEqual(app.powers_result_text.oficina_layout.canvas.xview(), (0.0, 1.0))
