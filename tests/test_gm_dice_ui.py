"""Detailed GM rolls stay usable and independent of campaign/combat state."""
from itertools import repeat
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

from tests.tk_support import assert_workbench_reflow, requires_tk
from utils.gm_dice import DiceRollError, roll_dice
from utils.gm_dice_preferences import DiceExpressions
from utils.ui_preferences import load_ui_preferences


@requires_tk
class GMDiceGuiTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator
        self.directory = TemporaryDirectory()
        self.paths = patch('main.application_data_dir', return_value=Path(self.directory.name))
        self.paths.start()
        self.app = GURPSCalculator()
        self.app.choose_tool(15)
        self.app.root.update()

    def tearDown(self):
        if self.app._gm_dice_job:
            self.app.gm_dice_panel.cancel()
            self.wait_for_job()
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()
        self.paths.stop()
        self.directory.cleanup()

    def wait_for_job(self):
        deadline = time.monotonic() + 10
        while self.app._gm_dice_job and time.monotonic() < deadline:
            self.app.root.update()
            time.sleep(.01)
        self.assertIsNone(self.app._gm_dice_job, 'background job did not finish')
        self.app.root.update()

    def test_104_dice_show_all_pages_subtotal_and_modifier_in_both_languages(self):
        app = self.app
        before = (app.combat_session.to_dict(), app.campaign_session.to_dict())
        values = tuple(index % 6 + 1 for index in range(104))
        result = roll_dice('104d6+20', values=values)
        for language in ('pt_BR', 'en_US'):
            app._change_language(language)
            panel = app.gm_dice_panel
            app.gm_dice_expression.set('104d6+20')
            with patch('utils.gm_dice_ui.roll_dice', return_value=result):
                panel.roll_button.invoke()
            first = panel.output.get('1.0', 'end-1c')
            self.assertIn('#1=1', first)
            self.assertIn('#100=4', first)
            self.assertNotIn('#101=', first)
            panel.next.invoke()
            last = panel.output.get('1.0', 'end-1c')
            self.assertIn('#101=5', last)
            self.assertIn('#104=2', last)
            self.assertIn(f'{sum(values)} +20 = {sum(values) + 20}', last)
            panel.copy_result()
            self.assertEqual(app.root.clipboard_get(), last)
            self.assertEqual(str(panel.output['state']), 'disabled')
        self.assertEqual((app.combat_session.to_dict(), app.campaign_session.to_dict()), before)

    def test_roll_controls_and_results_reflow_without_horizontal_clipping(self):
        app = self.app
        app.ui_preferences['font_size'] = 18
        for language in ('pt_BR', 'en_US'):
            with self.subTest(language=language):
                app._change_language(language)
                panel = app.gm_dice_panel
                app.root.geometry('800x600')
                app.root.update()
                assert_workbench_reflow(self, panel, wide=False)
                self.assertFalse(panel.work.winfo_ismapped())
                app.gm_dice_expression.set('104d1+20')
                panel.roll_button.invoke()
                app.root.update()
                self.assertEqual(panel.total['text'], '124')
                self.assertIn('#100=1', panel.output.get('1.0', 'end-1c'))
                for button in (panel.roll_button, *panel.quick_buttons, panel.copy_button,
                               panel.export_button, panel.clear_button, panel.previous,
                               panel.next, panel.page_entry, panel.go):
                    self.assertTrue(button.winfo_ismapped())
                    self.assertGreaterEqual(button.winfo_rootx(), panel.canvas.winfo_rootx())
                    self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                         panel.canvas.winfo_rootx() + panel.canvas.winfo_width())
                app.root.geometry('1500x900')
                app.root.update()
                assert_workbench_reflow(self, panel)
                self.assertEqual(panel.total['text'], '124')
                panel.next.invoke()
                self.assertIn('#104=1', panel.output.get('1.0', 'end-1c'))

    def test_action_rows_do_not_oscillate_on_a_one_pixel_resize(self):
        from tkinter import ttk

        from utils.ranged_layout import flow_buttons

        root = self.app.root
        toolbar = ttk.Frame(root, width=200, height=100)
        toolbar.pack_propagate(False)
        toolbar.place(x=0, y=0)
        first = ttk.Button(toolbar, text='Copy total')
        second = ttk.Button(toolbar, text='Export all')
        flow_buttons(toolbar, [first, second])
        root.update()
        required = first.winfo_reqwidth() + second.winfo_reqwidth() + 16
        toolbar.configure(width=required - 1)
        root.update()
        self.assertLess(first.winfo_rooty(), second.winfo_rooty())
        for width in (required, required - 1) * 3:
            toolbar.configure(width=width)
            root.update()
            self.assertLess(first.winfo_rooty(), second.winfo_rooty())
        toolbar.configure(width=required + 20)
        root.update()
        self.assertEqual(first.winfo_rooty(), second.winfo_rooty())
        toolbar.destroy()

    def test_language_change_preserves_roll_and_dice_navigation_preferences(self):
        app = self.app
        result = roll_dice('1d6-20', values=[1])
        app.gm_dice_expression.set('1d6-20')
        with patch('utils.gm_dice_ui.roll_dice', return_value=result) as roller:
            app.gm_dice_panel.roll()
            app._change_language('en_US')
            app.root.update()
            self.assertIn('Final total: -19', app.gm_dice_panel.output.get('1.0', 'end'))
            app._change_language('pt_BR')
            self.assertIn('Soma final: -19', app.gm_dice_panel.output.get('1.0', 'end'))
            self.assertEqual(roller.call_count, 1)
        self.assertEqual(app.notebook.index(app.notebook.select()), 15)
        app.toggle_tool_favorite()
        saved = load_ui_preferences(app.ui_preferences_path)
        self.assertEqual(saved['last_tool'], 15)
        self.assertIn(15, saved['favorites'])

    def test_favorite_and_recent_expressions_reopen_without_rolling_and_copy_only_total(self):
        app = self.app
        panel = app.gm_dice_panel
        app.gm_dice_expression.set('1 D 1 - 20')
        panel.favorite_button.invoke()
        panel.roll_button.invoke()
        panel.copy_total_button.invoke()
        self.assertEqual(app.root.clipboard_get(), '-19')
        state = DiceExpressions.load(Path(self.directory.name) / 'dice_expressions.json')
        self.assertEqual((state.favorites, state.recent), (('1d1-20',), ('1d1-20',)))
        result = app.gm_dice_last_result
        app._change_language('en_US')
        panel = app.gm_dice_panel
        with patch('utils.gm_dice_ui.roll_dice') as roller:
            app.gm_dice_expression.set('104d6+20')
            panel.recent_menu.invoke(0)
            self.assertEqual(app.gm_dice_expression.get(), '1d1-20')
            app.gm_dice_expression.set('3d6')
            panel.favorite_menu.invoke(0)
            self.assertEqual(app.gm_dice_expression.get(), '1d1-20')
            roller.assert_not_called()
        self.assertIs(app.gm_dice_last_result, result)
        panel.favorite_button.invoke()
        self.assertEqual(DiceExpressions.load(Path(self.directory.name) / 'dice_expressions.json').favorites, ())

    def test_3d6_check_reuses_critical_rules_and_survives_language_rebuild(self):
        app = self.app
        session = app.combat_session.to_dict()
        dialog = app.gm_dice_panel.open_check()
        dialog.targets[0].set('16')
        with patch('utils.gm_dice_ui.roll_3d6', return_value=(6, [2, 2, 2])) as roller:
            dialog.roll_button.invoke()
            self.assertIn('Sucesso crítico', dialog.output['text'])
            self.assertIn('+10', dialog.output['text'])
            app._change_language('en_US')
            self.assertFalse(dialog.winfo_exists())
            dialog = app.gm_dice_panel.open_check()
            self.assertIn('Critical success', dialog.output['text'])
            self.assertIn('2, 2, 2 = 6', dialog.output['text'])
            roller.assert_called_once_with()
        self.assertEqual(app.combat_session.to_dict(), session)
        self.assertIsNone(app.gm_dice_last_result)

    def test_quick_contest_resolves_margin_and_ties_and_rejects_bad_target(self):
        app = self.app
        dialog = app.gm_dice_panel.open_check(True)
        dialog.targets[0].set('13')
        dialog.targets[1].set('0')
        with patch('utils.gm_dice_ui.roll_3d6') as roller:
            dialog.roll_button.invoke()
            roller.assert_not_called()
        self.assertIn('1 e 999', dialog.error['text'])
        self.assertTrue(dialog.entries[1].instate(['invalid']))
        dialog.targets[1].set('12')
        with patch('utils.gm_dice_ui.roll_3d6', side_effect=[(10, [3, 3, 4]), (9, [3, 3, 3]),
                                                         (9, [3, 3, 3]), (11, [3, 4, 4]),
                                                         (16, [6, 5, 5]), (13, [5, 4, 4])]):
            dialog.roll_button.invoke()
            self.assertIn('Empate', dialog.output['text'])
            dialog.roll_button.invoke()
            self.assertIn('Vencedor: Participante A (margem 3)', dialog.output['text'])
            self.assertNotIn('invalid', dialog.entries[1].state())
            dialog.roll_button.invoke()
            self.assertIn('Vencedor: Participante B (margem 2)', dialog.output['text'])
            self.assertIn('margem: -3', dialog.output['text'])

    def test_save_error_keeps_completed_roll_and_can_retry_same_expression(self):
        app = self.app
        panel = app.gm_dice_panel
        app.gm_dice_expression.set('3d1+10')
        with patch.object(DiceExpressions, 'save', side_effect=OSError('read-only')):
            panel.roll_button.invoke()
        self.assertEqual(app.gm_dice_last_result.total, 13)
        self.assertIn('read-only', panel.saved_feedback['text'])
        self.assertEqual(app.gm_dice_expressions.recent, ('3d1+10',))
        panel.roll_button.invoke()
        self.assertFalse(app.gm_dice_save_error)
        self.assertEqual(DiceExpressions.load(Path(self.directory.name) / 'dice_expressions.json').recent,
                         ('3d1+10',))

    def test_million_dice_are_paged_without_a_million_line_widget(self):
        app = self.app
        app.gm_dice_expression.set('1000000d6+20')
        def deterministic(expression, **kwargs):
            return roll_dice(expression, values=repeat(6, 1_000_000), **kwargs)
        with patch('utils.gm_dice_ui.roll_dice', side_effect=deterministic):
            app.gm_dice_panel.roll()
            self.assertIsNotNone(app._gm_dice_job)
            heartbeat = []
            app.root.after(1, lambda: heartbeat.append(True))
            self.wait_for_job()
        self.assertEqual(heartbeat, [True])
        self.assertEqual(app.gm_dice_last_result.total, 6_000_020)
        self.assertEqual(app.gm_dice_last_result.rolls.nbytes, 4_000_000)
        history_path = Path(self.directory.name) / 'dice_expressions.json'
        self.assertLess(history_path.stat().st_size, 300)
        self.assertEqual(DiceExpressions.load(history_path).recent, ('1000000d6+20',))
        self.assertEqual(dict(DiceExpressions.load(history_path).recent_totals), {'1000000d6+20': 6_000_020})
        self.assertEqual(app.gm_dice_panel.recent_menu.entrycget(0, 'label'), '1000000d6+20 = 6000020')
        self.assertLess(len(app.gm_dice_panel.output.get('1.0', 'end')), 2500)
        app.gm_dice_page.set('10000')
        app.gm_dice_panel.go_to_page()
        self.assertIn('#1000000=6', app.gm_dice_panel.output.get('1.0', 'end'))
        app.gm_dice_page.set('10001')
        app.gm_dice_panel.go_to_page()
        self.assertEqual(app.gm_dice_page.get(), '10000')

    def test_cancellation_and_language_rebuild_keep_last_completed_result(self):
        app = self.app
        result = roll_dice('3d6', values=[1, 2, 3])
        app.gm_dice_last_result = result
        app.gm_dice_expression.set('1000000d6')
        entered = Event()
        def slow_roll(expression, **kwargs):
            entered.set()
            while not kwargs['should_cancel']():
                time.sleep(.01)
            raise DiceRollError('cancelled')
        with patch('utils.gm_dice_ui.roll_dice', side_effect=slow_roll):
            app.gm_dice_panel.roll()
            self.assertTrue(entered.wait(1))
            app.root.update()
            self.assertTrue(app.gm_dice_panel.work.winfo_ismapped())
            app._change_language('en_US')
            self.assertEqual(str(app.gm_dice_panel.roll_button['state']), 'disabled')
            app.gm_dice_panel.cancel_button.invoke()
            self.wait_for_job()
        self.assertIs(app.gm_dice_last_result, result)
        self.assertEqual(app.gm_dice_expressions.recent, ())
        self.assertIn('Operation cancelled', app.gm_dice_panel.error['text'])
        self.assertFalse(app.gm_dice_panel.work.winfo_ismapped())

    def test_export_contains_every_die_and_cancelled_export_preserves_destination(self):
        app = self.app
        app.gm_dice_last_result = roll_dice('104d6+20', values=repeat(6, 104))
        destination = Path(self.directory.name) / 'roll.txt'
        with patch('utils.gm_dice_ui.filedialog.asksaveasfilename', return_value=str(destination)):
            app.gm_dice_panel.export_result()
            self.wait_for_job()
            contents = destination.read_text(encoding='utf-8')
            self.assertEqual(len([line for line in contents.splitlines() if line.startswith('#')]), 104)
            self.assertIn('#104=6', contents)
            self.assertIn('644', contents)
            def cancelled(kind, count, operation):
                cancelled_event = Event()
                cancelled_event.set()
                operation({'cancel': cancelled_event})
            with patch.object(app.gm_dice_panel, 'start_job', side_effect=cancelled):
                with self.assertRaises(DiceRollError):
                    app.gm_dice_panel.export_result()
            self.assertEqual(destination.read_text(encoding='utf-8'), contents)

    def test_invalid_input_is_localized_and_does_not_roll(self):
        for language in ('pt_BR', 'en_US'):
            self.app._change_language(language)
            self.app.gm_dice_expression.set('0d6')
            with patch('utils.gm_dice_ui.roll_dice') as roller:
                self.app.gm_dice_panel.roll()
            roller.assert_not_called()
            self.assertNotIn('gm_dice_error_', self.app.gm_dice_panel.error['text'])
            self.assertIsNone(self.app.gm_dice_last_result)
        self.app.gm_dice_expression.set('10001d1')
        self.app.gm_dice_panel.roll()
        self.wait_for_job()
        self.assertNotIn('invalid', self.app.gm_dice_panel.entry.state())
