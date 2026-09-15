import os
import tkinter as tk
from tkinter import ttk
import unittest
from types import SimpleNamespace

from utils.gui_workspace import CatalogDialog, search_values, ResultComparison, record_details
from utils.i18n import t


class SearchTests(unittest.TestCase):
    def test_accent_case_and_multiple_words(self):
        self.assertEqual(search_values(['Água — Magic p.20', 'Fire — Magic p.10'], 'AGUA magic'),
                         ['Água — Magic p.20'])
        self.assertEqual(search_values(['Fire'], 'ice'), [])


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires display')
class CatalogTests(unittest.TestCase):
    def test_combined_filters_and_details(self):
        root = tk.Tk()
        try:
            records = {'Fire': SimpleNamespace(source='Magic', college='Fire', base_cost=2),
                       'Water': SimpleNamespace(source='Basic Set', college='Water', base_cost=1)}
            combo = ttk.Combobox(root, values=list(records))
            combo.set('Water')
            combo.catalog_records = lambda: records
            dialog = CatalogDialog(combo)
            dialog.filters['source'].set('Magic')
            root.update()
            self.assertLessEqual(dialog.use.winfo_y() + dialog.use.winfo_height(), dialog.winfo_height())
            self.assertEqual(dialog.filtered, ['Fire'])
            dialog.list.selection_set(0)
            dialog.select()
            self.assertIn(t('ui_field_base_cost') + ': 2', dialog.detail.get('1.0', 'end'))
            dialog.filters['college'].set('Water')
            self.assertEqual(dialog.filtered, [])
            self.assertEqual(str(dialog.use['state']), 'disabled')
            self.assertEqual(combo.get(), 'Water')
        finally:
            root.destroy()

    def test_comparison_snapshot_is_explicit_and_immutable(self):
        root = tk.Tk()
        try:
            box = tk.Text(root)
            comparison = ResultComparison(box)
            comparison.keep()
            self.assertEqual(comparison.saved, '')
            box.insert('1.0', 'Damage: 10')
            comparison.keep()
            box.delete('1.0', 'end')
            box.insert('1.0', 'Damage: 20')
            comparison.show()
            self.assertEqual(comparison.saved, 'Damage: 10')
            self.assertEqual(box.get('1.0', 'end-1c'), 'Damage: 20')
        finally:
            root.destroy()

    def test_search_cancel_and_confirm(self):
        root = tk.Tk()
        try:
            combo = ttk.Combobox(root, values=['Fire', 'Water'])
            combo.set('Fire')
            dialog = CatalogDialog(combo)
            dialog.query.set('water')
            self.assertEqual(combo.get(), 'Fire')
            dialog.destroy()
            self.assertEqual(combo.get(), 'Fire')
            dialog = CatalogDialog(combo)
            dialog.query.set('water')
            dialog.list.selection_set(0)
            dialog.confirm()
            self.assertEqual(combo.get(), 'Water')
        finally:
            root.destroy()
