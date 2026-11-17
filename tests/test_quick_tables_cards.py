"""Validate the reusable lookup registry and its desktop wiring."""
import math
import tempfile
import unittest
from string import Formatter
from unittest.mock import patch

from tests.tk_support import requires_tk
from utils.gm_dice import parse_dice
from utils.i18n import get_i18n, t
from utils.quick_tables_cards import Field, Localized, Quantity, SECTIONS, reference_cards
from utils.quick_tables_packages import PACKAGE_IDS
from utils.ui_preferences import QUICK_TABLES_TOOL, clean_preferences, load_ui_preferences
from utils.units import UnitSystem


class ReferenceCardsTests(unittest.TestCase):
    def test_number_parsing(self):
        self.assertEqual(Field('x', 'x').parse('1,25'), 1.25)
        self.assertIsNone(Field('x', 'x', 'integer', '').parse(''))
        for raw in ('NaN', 'Infinity', '0x10', '1e9999'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                Field('x', 'x').parse(raw)
        with self.assertRaisesRegex(ValueError, 'qt_reference_out_of_range'):
            Field('x', 'x', 'integer', '0', minimum=0, maximum=12).parse('13')

    def test_registry_defaults_and_locale_fields(self):
        basic = reference_cards()
        self.assertTrue(basic)
        self.assertTrue(all(card.package == 'basic' and card.source == 'Basic Set Revised' for card in basic))
        self.assertEqual({card.section for card in basic}, set(SECTIONS))
        cards = reference_cards(PACKAGE_IDS)
        self.assertEqual(cards[:len(basic)], basic)
        self.assertEqual({card.package for card in cards[len(basic):]}, set(PACKAGE_IDS))
        translations = list(get_i18n().translations.values())
        self.assertEqual(len({card.key for card in cards}), len(cards))
        for card in cards:
            with self.subTest(card=card.key):
                self.assertIsInstance(card.pages, str)
                self.assertRegex(card.pages, r'^\d')
                keys = {card.title}
                if card.package != 'basic':
                    self.assertNotEqual(card.source, 'Basic Set Revised')
                    self.assertIsNotNone(card.requirement)
                    keys.add(card.requirement)
                self.assertEqual(len({field.key for field in card.fields}), len(card.fields))
                for field in card.fields:
                    keys.add(field.title)
                    keys.update(key for _, key in field.options)
                    if field.unit is not None:
                        UnitSystem().display(1, field.unit)
                result = card.resolve({})
                self.assertTrue(result.lines)
                for row in result.lines:
                    keys.add(row.key)
                    for argument in row.arguments.values():
                        if isinstance(argument, Localized):
                            keys.add(argument.key)
                        elif isinstance(argument, Quantity):
                            self.assertTrue(math.isfinite(argument.value))
                            UnitSystem().display(argument.value, argument.unit)
                    for table in translations:
                        expected = set(name for _, name, _, _ in Formatter().parse(table[row.key])
                                       if name is not None)
                        self.assertEqual(expected, set(row.arguments), (card.key, row.key))
                if card.roll is not None:
                    field_key, count, sides = card.roll
                    self.assertIn(field_key, {field.key for field in card.fields})
                    parse_dice(f'{count}d{sides}')
                if result.expression is not None:
                    parse_dice(result.expression)
                for table in translations:
                    self.assertFalse(keys.difference(table), keys.difference(table))

    def test_pack_preference_validates_known_ids_only_and_preserves_baseline(self):
        self.assertEqual(clean_preferences({})['quick_tables_packs'], [])
        self.assertEqual(clean_preferences({'quick_tables_packs': 'treasure'})['quick_tables_packs'], [])
        self.assertEqual(clean_preferences({'quick_tables_packs': [
            'treasure', [], 'unknown', 'wilderness', 'treasure', 42]})['quick_tables_packs'],
            ['wilderness', 'treasure'])
        basic = reference_cards()
        self.assertEqual(reference_cards(['unknown']), basic)
        selected = reference_cards(['treasure'])
        self.assertEqual(selected[:len(basic)], basic)
        self.assertEqual({card.package for card in selected[len(basic):]}, {'treasure'})


@requires_tk
class ReferenceCardsGuiTests(unittest.TestCase):
    def test_roll_is_disabled_for_invalid_or_inapplicable_checks(self):
        from main import GURPSCalculator
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict('os.environ', {'GURPS_CALCULADORA_DATA_DIR': directory}))
        app = GURPSCalculator()
        self.addCleanup(app.root.destroy)
        app.choose_tool(QUICK_TABLES_TOOL)
        app.quick_tables_panel.show_page('reference')
        reference = app.quick_tables_panel.reference
        reference.set_enabled_packages(('social', 'horror'))
        with patch('utils.quick_tables_cards_ui.roll_dice', return_value=(8, [2, 3, 3])) as roll:
            reference.query.set('scamp_rank')
            self.assertTrue(reference.roll_button.instate(['!disabled']))
            for value in ('invalid', '-10'):
                reference.inputs['modifier'].set(value)
                self.assertTrue(reference.roll_button.instate(['disabled']))
                reference.roll_button.invoke()
                reference.roll()
            roll.assert_not_called()
            self.assertEqual(reference.inputs['roll'].get(), '')
            reference.inputs['modifier'].set('0')
            reference.roll_button.invoke()
            roll.assert_called_once_with('3d6')
            self.assertEqual(reference.inputs['roll'].get(), '8')

            reference.query.set('scamp_fright')
            reference.inputs['fright_method'].set('ad_hoc')
            self.assertEqual(reference.result.expression, '1d6')
            self.assertTrue(reference.roll_button.instate(['disabled']))
            reference.roll_button.invoke()
            roll.assert_called_once()

    def test_search_switch_units_explicit_roll_and_no_session_writes(self):
        from main import GURPSCalculator
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict('os.environ', {'GURPS_CALCULADORA_DATA_DIR': directory}))
        app = GURPSCalculator()

        def close():
            for form in app._form_states:
                form.close()
            for binding in app._unit_bindings:
                binding.close()
            app.root.destroy()

        self.addCleanup(close)
        callback_errors = []
        app.root.report_callback_exception = lambda *args: callback_errors.append(args[1])
        app.root.geometry('800x600')
        app.choose_tool(QUICK_TABLES_TOOL)
        panel = app.quick_tables_panel
        self.assertIsNone(panel.reference)
        before = app.combat_session.to_dict()
        panel.show_page('reference')
        reference = panel.reference
        reference.query.set('hearing')
        self.assertEqual(reference.current.key, 'hearing')
        reference.inputs['hearing_distance'].set('8')
        self.assertIn(' m', reference.readout.cget('text'))
        self.assertEqual(reference.enabled_packages, ())
        reference.query.set('sup_df_treasure_cost')
        self.assertIsNone(reference.current)
        reference.package_menu.invoke(PACKAGE_IDS.index('treasure'))
        self.assertEqual(reference.current.key, 'sup_df_treasure_cost')
        self.assertEqual(load_ui_preferences(app.ui_preferences_path)['quick_tables_packs'], ['treasure'])
        self.assertEqual(reference.current.source, 'GURPS Dungeon Fantasy 8: Treasure Tables')
        self.assertIn(t('qt_sfant_cost_total_result', value='100.00'), reference.readout.cget('text'))
        reference.sources.current(reference.source_keys.index('basic'))
        reference.sources.event_generate('<<ComboboxSelected>>')
        app.root.update()
        self.assertIsNone(reference.current)
        reference.sources.current(reference.source_keys.index('treasure'))
        reference.sources.event_generate('<<ComboboxSelected>>')
        app.root.update()
        self.assertEqual(reference.current.key, 'sup_df_treasure_cost')
        reference.set_enabled_packages(())
        self.assertIsNone(reference.current)
        self.assertEqual(load_ui_preferences(app.ui_preferences_path)['quick_tables_packs'], [])
        reference.query.set('zz-nothing-found-zz')
        self.assertIsNone(reference.current)
        self.assertTrue(reference.selector.instate(['disabled']))
        reference.query.set('hearing')
        self.assertEqual(reference.inputs['hearing_distance'].get(), '8')
        self.assertEqual(reference.result.lines[1].arguments['modifier'], -3)

        app.result_units.set('imperial')
        app._change_language('en_US')
        app.root.update()
        panel = app.quick_tables_panel
        reference = panel.reference
        self.assertEqual(panel.page.get(), 'reference')
        self.assertTrue(reference.readout.winfo_viewable())
        self.assertEqual(panel.canvas.xview(), (0.0, 1.0))
        self.assertIn(' yd', reference.readout.cget('text'))
        self.assertEqual(reference.inputs['hearing_distance'].get(), '8')

        with patch('utils.quick_tables_cards_ui.roll_dice', return_value=(4, [4])) as roll:
            reference.query.set('encounter_slot')
            self.assertEqual(reference.current.key, 'encounter_slot')
            self.assertEqual(reference.inputs['roll'].get(), '')
            roll.assert_not_called()
            reference.roll()
            roll.assert_called_once_with('1d6')
            self.assertEqual(reference.inputs['roll'].get(), '4')
        reference.query.set('terrain')
        spec = reference.result.expression
        self.assertIsNotNone(spec)
        reference._send_expression()
        self.assertEqual(app._current_tool, 15)
        self.assertEqual(app.gm_dice_expression.get(), spec)
        self.assertIsNone(app.gm_dice_last_result)
        self.assertEqual(app.combat_session.to_dict(), before)
        self.assertEqual(callback_errors, [])
