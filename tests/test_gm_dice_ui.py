"""Detailed GM rolls stay usable and independent of campaign/combat state."""
from itertools import repeat
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

from utils.gm_dice import DiceRollError, roll_dice
from utils.ui_preferences import load_ui_preferences


@unittest.skipUnless(os.environ.get('DISPLAY'), 'requires a graphical display')
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
            app._change_language('en_US')
            self.assertEqual(str(app.gm_dice_panel.roll_button['state']), 'disabled')
            app.gm_dice_panel.cancel_button.invoke()
            self.wait_for_job()
        self.assertIs(app.gm_dice_last_result, result)
        self.assertIn('Operation cancelled', app.gm_dice_panel.error['text'])

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
