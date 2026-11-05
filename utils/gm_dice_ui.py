"""Independent, detailed dice rolls for the game master."""
import os
from pathlib import Path
from queue import Empty, Queue
import tempfile
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, ttk

from calculators.contests import quick_contest
from utils.dice_roller import evaluate_success_roll, roll_3d6
from utils.gm_dice import DiceRollError, parse_dice, roll_dice
from utils.gm_dice_preferences import DiceExpressions
from utils.i18n import t
from utils.ranged_layout import Disclosure, RangedWorkbench, flow_buttons, wrap_label


PAGE_SIZE = 100


def format_roll(result, page=1):
    """Render existing rolls in the current language without rolling again."""
    first = (page - 1) * PAGE_SIZE
    last = min(first + PAGE_SIZE, result.count)
    lines = [t('gm_dice_total', total=result.total),
             t('gm_dice_expression_result', expression=result.expression), '',
             t('gm_dice_count', count=result.count, sides=result.sides),
             t('gm_dice_details'),
             t('gm_dice_range', first=first + 1, last=last, count=result.count)]
    for start in range(first, last, 10):
        lines.append('  '.join(f'#{index + 1}={value}'
                               for index, value in enumerate(result.rolls[start:min(start + 10, last)], start)))
    lines.extend(['', t('gm_dice_subtotal', subtotal=result.subtotal),
                  t('gm_dice_modifier', modifier=f'{result.modifier:+d}'),
                  t('gm_dice_equation', subtotal=result.subtotal,
                    modifier=f'{result.modifier:+d}', total=result.total)])
    return '\n'.join(lines)


class DiceCheckDialog(tk.Toplevel):
    """Ordinary GURPS checks and Quick Contests, with no session changes."""

    def __init__(self, panel, contest):
        super().__init__(panel)
        self.app = panel.app
        self.contest = contest
        self.title(t('gm_dice_contest' if contest else 'gm_dice_check'))
        self.transient(panel.app.root)
        self.geometry('470x390' if contest else '470x300')
        self.minsize(360, 390 if contest else 300)
        body = ttk.Frame(self, padding=14)
        body.pack(fill='both', expand=True)
        self.targets = []
        self.entries = []
        labels = ('gm_dice_side_a', 'gm_dice_side_b') if contest else ('gm_dice_target',)
        for index, label in enumerate(labels):
            wrap_label(ttk.Label(body, text=t(label))).pack(fill='x')
            target = tk.StringVar(self, value=panel.app.gm_dice_check_targets[index])
            entry = ttk.Entry(body, textvariable=target, width=10)
            entry.pack(anchor='w', pady=(2, 8))
            self.targets.append(target)
            self.entries.append(entry)

        actions = ttk.Frame(body)
        actions.pack(side='bottom', fill='x', pady=(8, 0))
        self.roll_button = ttk.Button(actions, text=t('gm_dice_roll'), command=self.run,
                                      style='Primary.TButton')
        self.roll_button.pack(side='left')
        ttk.Button(actions, text=t('ui_cancel'), command=self.destroy).pack(side='right')
        self.output = wrap_label(ttk.Label(body, justify='left', wraplength=390))
        self.output.pack(fill='x', pady=(3, 0))
        self.error = wrap_label(ttk.Label(body, style='Error.TLabel', wraplength=390))
        self.error.pack(fill='x')
        if contest in self.app.gm_dice_last_checks:
            self.present(*self.app.gm_dice_last_checks[contest])
        self.bind('<Return>', self.run)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.entries[0].focus_set()

    @staticmethod
    def _roll_line(target, roll, dice, margin):
        return t('gm_dice_check_roll', target=target, roll=roll,
                 dice=', '.join(str(die) for die in dice), margin=f'{margin:+d}')

    def run(self, event=None):
        values = []
        for entry, target in zip(self.entries, self.targets):
            raw = target.get().strip()
            value = int(raw) if len(raw) <= 3 and raw.isascii() and raw.isdecimal() else 0
            entry.state(['!invalid' if value else 'invalid'])
            if value:
                values.append(value)
        if len(values) != len(self.targets):
            self.error.configure(text=t('gm_dice_check_bad_target'))
            return 'break' if event is not None else None
        self.error.configure(text='')
        for index, value in enumerate(values):
            self.app.gm_dice_check_targets[index] = str(value)
        rolls = tuple((total, tuple(dice)) for total, dice in (roll_3d6() for _ in values))
        snapshot = (tuple(values), rolls)
        self.app.gm_dice_last_checks[self.contest] = snapshot
        self.present(*snapshot)
        return 'break' if event is not None else None

    def present(self, values, rolls):
        first, dice_a = rolls[0]
        if self.contest:
            second, dice_b = rolls[1]
            result = quick_contest(*values, first, second)
            lines = [t('gm_dice_side_a'), self._roll_line(values[0], first, dice_a, result.attacker_margin),
                     t('gm_dice_side_b'), self._roll_line(values[1], second, dice_b, result.defender_margin)]
            if result.winner == 'tie':
                lines.append(t('gm_dice_contest_tie'))
            else:
                winner = t('gm_dice_side_a' if result.winner == 'attacker' else 'gm_dice_side_b')
                lines.append(t('gm_dice_contest_winner', winner=winner, margin=result.margin_of_victory))
        else:
            result = evaluate_success_roll(values[0], first)
            outcome = ('critical_success' if result['critical_success'] else
                       'critical_failure' if result['critical_failure'] else
                       'success' if result['success'] else 'failure')
            lines = [self._roll_line(values[0], first, dice_a, values[0] - first),
                     t('gm_dice_check_' + outcome)]
        self.output.configure(text='\n'.join(lines))


class GMDicePanel(RangedWorkbench):
    def __init__(self, parent, app):
        self.app = app
        self.WIDE = 720 + max(0, app.ui_preferences['font_size'] - 10) * 20
        super().__init__(parent, app.colors['bg'])
        self._displayed = None
        self._reveal_after = None
        self._check_dialog = None
        self._menu_snapshot = None
        self._expressions_path = app.ui_preferences_path.with_name('dice_expressions.json')
        if not hasattr(app, 'gm_dice_expressions'):
            app.gm_dice_expressions = DiceExpressions.load(self._expressions_path)
            app.gm_dice_check_targets = ['12', '12']
            app.gm_dice_last_checks = {}
            app.gm_dice_save_error = ''
        wrap_label(ttk.Label(self.header, text=t('gm_dice_title'), style='PageTitle.TLabel')).pack(fill='x')
        wrap_label(ttk.Label(self.header, text=t('gm_dice_workbench_hint'), style='Subtitle.TLabel')).pack(
            fill='x', pady=(3, 0))

        controls = ttk.LabelFrame(self.inputs, text=t('gm_dice_new_roll'), padding=10)
        controls.pack(fill='x')
        wrap_label(ttk.Label(controls, text=t('gm_dice_expression'))).pack(fill='x')
        self.entry = ttk.Entry(controls, textvariable=app.gm_dice_expression, width=1)
        self.entry.pack(fill='x', pady=(4, 8))
        self.entry.bind('<Return>', self.roll)
        self.roll_button = ttk.Button(controls, text=t('gm_dice_roll'), command=self.roll,
                                      style='Primary.TButton')
        self.roll_button.pack(fill='x')
        self.error = wrap_label(ttk.Label(controls, style='Error.TLabel', wraplength=180))
        self.error.pack(fill='x', pady=(6, 0))

        quick = ttk.Frame(controls)
        quick.pack(fill='x', pady=(10, 0))
        wrap_label(ttk.Label(quick, text=t('gm_dice_quick'), style='Subtitle.TLabel')).pack(fill='x')
        quick_actions = ttk.Frame(quick)
        quick_actions.pack(fill='x')
        self.quick_buttons = []
        for expression in ('1d6', '2d6', '3d6'):
            self.quick_buttons.append(ttk.Button(
                quick_actions, text=expression, command=lambda expression=expression: self.quick_roll(expression)))
        flow_buttons(quick_actions, self.quick_buttons)

        expressions = ttk.Frame(controls)
        expressions.pack(fill='x', pady=(6, 0))
        self.favorite_menu_button = ttk.Menubutton(expressions, text=t('gm_dice_favorites'))
        self.favorite_menu = tk.Menu(self.favorite_menu_button, tearoff=False)
        self.favorite_menu_button.configure(menu=self.favorite_menu)
        self.recent_menu_button = ttk.Menubutton(expressions, text=t('gm_dice_recent'))
        self.recent_menu = tk.Menu(self.recent_menu_button, tearoff=False)
        self.recent_menu_button.configure(menu=self.recent_menu)
        self.favorite_button = ttk.Button(expressions, text=t('gm_dice_star'), command=self.toggle_favorite)
        self._fit_expression_actions = flow_buttons(
            expressions, [self.favorite_menu_button, self.recent_menu_button, self.favorite_button])
        self.saved_feedback = wrap_label(ttk.Label(controls, style='Warning.TLabel', wraplength=180))

        checks = ttk.Frame(self.inputs)
        checks.pack(fill='x', pady=(6, 0))
        self.check_button = ttk.Button(checks, text=t('gm_dice_check'), command=self.open_check)
        self.contest_button = ttk.Button(checks, text=t('gm_dice_contest'), command=lambda: self.open_check(True))
        flow_buttons(checks, [self.check_button, self.contest_button])
        help_section = Disclosure(self.inputs, t('gm_dice_help_title'),
                                  lambda: help_section.show(not help_section.expanded))
        help_section.pack(fill='x', pady=(8, 0))
        wrap_label(ttk.Label(help_section.section, text=t('gm_dice_help'),
                             style='Muted.TLabel', wraplength=180)).pack(fill='x')

        self.result_card = ttk.LabelFrame(self.result, text=t('gm_dice_result_title'),
                                         padding=10, style='Result.TLabelframe')
        self.result_card.pack(fill='x')
        self.result_card.columnconfigure(0, weight=1)
        wrap_label(ttk.Label(self.result_card, text=t('gm_dice_total_label'), style='Subtitle.TLabel')).grid(
            row=0, column=0, sticky='ew')
        self.total = wrap_label(ttk.Label(self.result_card, style='Metric.TLabel'))
        self.total.grid(row=1, column=0, sticky='ew')
        self.meta = wrap_label(ttk.Label(self.result_card, style='Muted.TLabel', wraplength=180))
        self.meta.grid(row=2, column=0, sticky='ew', pady=(3, 4))

        self.work = ttk.Frame(self.result_card)
        self.work.grid(row=3, column=0, sticky='ew', pady=(4, 8))
        self.work.columnconfigure(0, weight=1)
        self.progress_text = wrap_label(ttk.Label(self.work, wraplength=180))
        self.progress_text.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.progress = ttk.Progressbar(self.work, mode='determinate', length=1)
        self.progress.grid(row=1, column=0, sticky='ew')
        self.cancel_button = ttk.Button(self.work, text=t('gm_dice_cancel'), command=self.cancel)
        self.cancel_button.grid(row=1, column=1, padx=(8, 0))

        self.result_details = ttk.Frame(self.result_card)
        self.result_details.grid(row=4, column=0, sticky='ew')
        actions = ttk.Frame(self.result_details)
        actions.pack(fill='x', pady=(2, 4))
        self.copy_total_button = ttk.Button(actions, text=t('gm_dice_copy_total'), command=self.copy_total)
        self.copy_button = ttk.Button(actions, text=t('gm_dice_copy_page'), command=self.copy_result)
        self.export_button = ttk.Button(actions, text=t('gm_dice_export'), command=self.export_result)
        self.clear_button = ttk.Button(actions, text=t('gm_dice_clear'), command=self.clear_result)
        flow_buttons(actions, [self.copy_total_button, self.copy_button, self.export_button, self.clear_button])
        ttk.Separator(self.result_details).pack(fill='x', pady=(5, 8))
        wrap_label(ttk.Label(self.result_details, text=t('gm_dice_details'), wraplength=180)).pack(fill='x')

        pages = ttk.Frame(self.result_details)
        pages.pack(fill='x', pady=(3, 4))
        self.previous = ttk.Button(pages, text=t('gm_dice_previous'), command=lambda: self.change_page(-1))
        self.next = ttk.Button(pages, text=t('gm_dice_next'), command=lambda: self.change_page(1))
        flow_buttons(pages, [self.previous, self.next])
        jump = ttk.Frame(self.result_details)
        jump.pack(fill='x', pady=(0, 8))
        jump.columnconfigure(4, weight=1)
        ttk.Label(jump, text=t('gm_dice_page')).grid(row=0, column=0, sticky='w')
        self.page_entry = ttk.Entry(jump, textvariable=app.gm_dice_page, width=7)
        self.page_entry.grid(row=0, column=1, sticky='ew', padx=5)
        self.page_entry.bind('<Return>', self.go_to_page)
        self.go = ttk.Button(jump, text=t('gm_dice_go'), command=self.go_to_page)
        self.go.grid(row=0, column=3, padx=(5, 0))
        self.pages_label = ttk.Label(jump)
        self.pages_label.grid(row=0, column=2)

        details = ttk.Frame(self.result_details)
        details.pack(fill='both', expand=True)
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.output = tk.Text(details, height=10, width=1, wrap='word', state='disabled',
                              bg=app.colors['panel'], fg=app.colors['panel_fg'],
                              selectbackground=app.colors['accent'], selectforeground=app.colors['accent_fg'],
                              font=('Consolas', app.ui_preferences['font_size']), padx=8, pady=8)
        self.output.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(details, command=self.output.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.output.configure(yscrollcommand=scroll.set)
        self._expression_trace = app.gm_dice_expression.trace_add('write', self.refresh_expression_actions)
        self.bind_scrolling()
        self.render()

    def _place(self, wide):
        if self.wide == wide:
            return
        super()._place(wide)
        if wide:
            self.body.columnconfigure(0, weight=2)
            self.body.columnconfigure(1, weight=3)

    def _show_roll(self):
        if not self.wide:
            self._schedule_reveal(self.result_card, align_top=True)

    def _schedule_reveal(self, widget, *, align_top=False):
        if self._reveal_after is not None:
            self.after_cancel(self._reveal_after)

        def reveal():
            self._reveal_after = None
            self.reveal(widget, align_top=align_top)

        self._reveal_after = self.after_idle(reveal)

    def destroy(self):
        if self._reveal_after is not None:
            self.after_cancel(self._reveal_after)
        self.app.gm_dice_expression.trace_remove('write', self._expression_trace)
        super().destroy()

    def refresh_expression_actions(self, *_):
        saved = self.app.gm_dice_expressions
        busy = self.app._gm_dice_job is not None
        if saved != self._menu_snapshot:
            self._menu_snapshot = saved
            recent_totals = dict(saved.recent_totals)
            for menu, values in ((self.favorite_menu, saved.favorites), (self.recent_menu, saved.recent)):
                menu.delete(0, 'end')
                for expression in values:
                    label = (f'{expression} = {recent_totals[expression]}'
                             if menu is self.recent_menu and expression in recent_totals else expression)
                    menu.add_command(label=label,
                                     command=lambda expression=expression: self.select_expression(expression))
        self.favorite_menu_button.configure(state='normal' if saved.favorites and not busy else 'disabled')
        self.recent_menu_button.configure(state='normal' if saved.recent and not busy else 'disabled')
        try:
            expression = parse_dice(self.app.gm_dice_expression.get()).expression
        except DiceRollError:
            expression = ''
        label = t('gm_dice_unstar' if expression in saved.favorites else 'gm_dice_star')
        changed = self.favorite_button.cget('text') != label
        self.favorite_button.configure(text=label, state='disabled' if busy else 'normal')
        if changed:
            self._fit_expression_actions()

    def select_expression(self, expression):
        if self.app._gm_dice_job is None:
            self.app.gm_dice_expression.set(expression)
            self.app.gm_dice_error_code = None
            self.entry.focus_set()
            self.render()

    def _save_expressions(self, updated):
        if updated == self.app.gm_dice_expressions and not self.app.gm_dice_save_error:
            return
        self.app.gm_dice_expressions = updated
        try:
            updated.save(self._expressions_path)
        except OSError as error:
            self.app.gm_dice_save_error = str(error)
        else:
            self.app.gm_dice_save_error = ''

    def toggle_favorite(self):
        if self.app._gm_dice_job is not None:
            return
        try:
            updated = self.app.gm_dice_expressions.toggle_favorite(self.app.gm_dice_expression.get())
        except DiceRollError as error:
            self.app.gm_dice_error_code = error.code
        else:
            self.app.gm_dice_error_code = None
            self._save_expressions(updated)
        self.render()

    def open_check(self, contest=False):
        dialog = self._check_dialog
        if dialog is not None and dialog.winfo_exists():
            if dialog.contest == contest:
                dialog.lift()
                dialog.entries[0].focus_set()
                return dialog
            dialog.destroy()
        self._check_dialog = DiceCheckDialog(self, contest)
        return self._check_dialog

    def _accept_roll(self, result):
        self.app.gm_dice_last_result = result
        self.app._gm_dice_current_page = 1
        self.app.gm_dice_page.set('1')
        self.app.gm_dice_error_code = None
        self._save_expressions(self.app.gm_dice_expressions.remember(result.expression, result.total))

    def render(self):
        result = self.app.gm_dice_last_result
        job = self.app._gm_dice_job
        busy = job is not None
        pages = (result.count + PAGE_SIZE - 1) // PAGE_SIZE if result else 1
        page = self.app._gm_dice_current_page
        self.pages_label.configure(text=t('gm_dice_pages', pages=pages))
        self.total.configure(text=str(result.total) if result else '—')
        if result:
            self.meta.configure(text='\n'.join((
                t('gm_dice_expression_result', expression=result.expression),
                t('gm_dice_subtotal', subtotal=result.subtotal) + '  ·  ' +
                t('gm_dice_modifier', modifier=f'{result.modifier:+d}'),
            )))
            self.result_details.grid()
        else:
            self.meta.configure(text=t('gm_dice_empty'))
            self.result_details.grid_remove()
        if self.app.gm_dice_error_code:
            self.error.configure(text=t('gm_dice_error_' + self.app.gm_dice_error_code))
            if not self.error.winfo_manager():
                self.error.pack(fill='x', pady=(6, 0), after=self.roll_button)
        else:
            self.error.configure(text='')
            self.error.pack_forget()
        # Progress polling and exports need not rebuild a page of unchanged dice.
        displayed = (id(result), page)
        if self._displayed != displayed:
            self._displayed = displayed
            self.output.configure(state='normal')
            self.output.delete('1.0', 'end')
            if result:
                self.output.insert('1.0', format_roll(result, page))
            self.output.configure(state='disabled')
        self.copy_button.configure(state='normal' if result else 'disabled')
        self.copy_total_button.configure(state='normal' if result else 'disabled')
        self.export_button.configure(state='normal' if result and not busy else 'disabled')
        self.clear_button.configure(state='normal' if result and not busy else 'disabled')
        self.previous.configure(state='normal' if result and page > 1 else 'disabled')
        self.next.configure(state='normal' if result and page < pages else 'disabled')
        self.go.configure(state='normal' if result else 'disabled')
        self.page_entry.configure(state='normal' if result else 'disabled')
        self.roll_button.configure(state='disabled' if busy else 'normal')
        self.entry.configure(state='disabled' if busy else 'normal')
        self.entry.state(['invalid' if self.app.gm_dice_error_code in
                          ('invalid_expression', 'dice_count', 'dice_sides', 'dice_modifier')
                          else '!invalid'])
        for button in self.quick_buttons:
            button.configure(state='disabled' if busy else 'normal')
        self.refresh_expression_actions()
        if self.app.gm_dice_save_error:
            self.saved_feedback.configure(text=t('preferences_save_error', error=self.app.gm_dice_save_error))
            if not self.saved_feedback.winfo_manager():
                self.saved_feedback.pack(fill='x', pady=(4, 0))
        else:
            self.saved_feedback.pack_forget()
        self.cancel_button.configure(state='normal' if busy else 'disabled')
        if busy:
            self.work.grid()
            self.progress.configure(maximum=job['count'], value=job['done'])
            self.progress_text.configure(text=t('gm_dice_progress_' + job['kind'], done=job['done'], count=job['count']))
        else:
            self.work.grid_remove()

    def roll(self, event=None):
        if self.app._gm_dice_job is not None:
            return 'break' if event is not None else None
        try:
            expression = parse_dice(self.app.gm_dice_expression.get())
            if expression.count > 10_000:
                self.start_job('roll', expression.count, lambda job: roll_dice(
                    expression.expression, progress=lambda done, count: job['queue'].put(('progress', done)),
                    should_cancel=job['cancel'].is_set))
                return 'break' if event is not None else None
            result = roll_dice(expression.expression)
        except DiceRollError as exc:
            self.app.gm_dice_error_code = exc.code
            self.entry.state(['invalid'])
        else:
            self._accept_roll(result)
            self.entry.state(['!invalid'])
        self.render()
        if self.app.gm_dice_error_code is None:
            self._show_roll()
        return 'break' if event is not None else None

    def start_job(self, kind, count, operation):
        job = {'kind': kind, 'count': count, 'done': 0, 'queue': Queue(), 'cancel': Event()}
        self.app._gm_dice_job = job
        self.app.gm_dice_error_code = None
        self.render()
        if kind == 'roll':
            self._show_roll()
        def work():
            try:
                value = operation(job)
            except DiceRollError as exc:
                job['queue'].put(('error', exc.code))
            except OSError:
                job['queue'].put(('error', 'export'))
            except Exception:
                job['queue'].put(('error', 'unexpected'))
            else:
                job['queue'].put(('result', value))
        thread = Thread(target=work, daemon=True)
        job['thread'] = thread
        thread.start()
        self.app.root.after(50, self.poll_job)

    def poll_job(self):
        job = self.app._gm_dice_job
        if job is None:
            return
        completed = False
        panel = self.app.gm_dice_panel
        while True:
            try:
                kind, value = job['queue'].get_nowait()
            except Empty:
                break
            if kind == 'progress':
                job['done'] = value
            else:
                completed = True
                if kind == 'error':
                    self.app.gm_dice_error_code = value
                elif job['kind'] == 'roll':
                    if job['cancel'].is_set():
                        self.app.gm_dice_error_code = 'cancelled'
                    else:
                        panel._accept_roll(value)
                self.app._gm_dice_job = None
        panel.render()
        if completed and self.app.gm_dice_error_code:
            panel._schedule_reveal(panel.error)
        elif completed and job['kind'] == 'roll':
            panel._show_roll()
        elif not completed:
            self.app.root.after(50, panel.poll_job)

    def cancel(self):
        if self.app._gm_dice_job:
            self.app._gm_dice_job['cancel'].set()

    def change_page(self, offset):
        self.app.gm_dice_page.set(str(self.app._gm_dice_current_page + offset))
        self.go_to_page()

    def go_to_page(self, event=None):
        result = self.app.gm_dice_last_result
        if result:
            try:
                page = int(self.app.gm_dice_page.get())
                if not 1 <= page <= (result.count + PAGE_SIZE - 1) // PAGE_SIZE:
                    raise ValueError
            except ValueError:
                self.app.gm_dice_page.set(str(self.app._gm_dice_current_page))
            else:
                self.app._gm_dice_current_page = page
        self.render()
        return 'break' if event is not None else None

    def export_result(self):
        result = self.app.gm_dice_last_result
        if result is None or self.app._gm_dice_job is not None:
            return
        path = filedialog.asksaveasfilename(parent=self.app.root, defaultextension='.txt',
                                          filetypes=[(t('ui_text_file'), '*.txt')])
        if not path:
            return
        # Capture translated headers now so changing the UI language during the
        # export cannot mix languages in the saved file.
        header = '\n'.join([t('gm_dice_expression_result', expression=result.expression),
                            t('gm_dice_total', total=result.total),
                            t('gm_dice_subtotal', subtotal=result.subtotal),
                            t('gm_dice_modifier', modifier=f'{result.modifier:+d}'),
                            t('gm_dice_details')]) + '\n'
        def export(job):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=Path(path).parent,
                                                 delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(header)
                    for start in range(0, result.count, 10_000):
                        if job['cancel'].is_set():
                            raise DiceRollError('cancelled')
                        last = min(start + 10_000, result.count)
                        handle.writelines(f'#{index + 1}={value}\n' for index, value in
                                          enumerate(result.rolls[start:last], start))
                        job['queue'].put(('progress', last))
                if job['cancel'].is_set():
                    raise DiceRollError('cancelled')
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        self.start_job('export', result.count, export)

    def quick_roll(self, expression):
        self.app.gm_dice_expression.set(expression)
        self.roll()

    def copy_result(self):
        if self.app.gm_dice_last_result:
            self.clipboard_clear()
            self.clipboard_append(self.output.get('1.0', 'end-1c'))

    def copy_total(self):
        result = self.app.gm_dice_last_result
        if result is not None:
            self.clipboard_clear()
            self.clipboard_append(str(result.total))

    def clear_result(self):
        self.app.gm_dice_last_result = None
        self.app._gm_dice_current_page = 1
        self.app.gm_dice_page.set('1')
        self.app.gm_dice_error_code = None
        self.entry.state(['!invalid'])
        self.render()
