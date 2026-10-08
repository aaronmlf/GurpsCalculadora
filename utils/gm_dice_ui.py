"""Independent, detailed dice rolls for the game master."""
import os
from pathlib import Path
from queue import Empty, Queue
import tempfile
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, ttk

from utils.gm_dice import DiceRollError, parse_dice, roll_dice
from utils.i18n import t


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


class GMDicePanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=16)
        self.app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(8, weight=1)
        ttk.Label(self, text=t('gm_dice_title'), style='Title.TLabel').grid(
            row=0, column=0, sticky='w', pady=(0, 8))
        ttk.Label(self, text=t('gm_dice_help'), wraplength=580).grid(
            row=1, column=0, sticky='w', pady=(0, 12))
        form = ttk.Frame(self)
        form.grid(row=2, column=0, sticky='ew')
        form.columnconfigure(0, weight=1)
        ttk.Label(form, text=t('gm_dice_expression')).grid(row=0, column=0, sticky='w', pady=(0, 4))
        self.entry = ttk.Entry(form, textvariable=app.gm_dice_expression, width=26)
        self.entry.grid(row=1, column=0, sticky='ew', padx=(0, 8))
        self.roll_button = ttk.Button(form, text=t('gm_dice_roll'), command=self.roll)
        self.roll_button.grid(row=1, column=1)
        self.entry.bind('<Return>', self.roll)
        self.quick_buttons = []
        quick = ttk.Frame(self)
        quick.grid(row=3, column=0, sticky='w', pady=8)
        ttk.Label(quick, text=t('gm_dice_quick')).pack(side='left', padx=(0, 6))
        for expression in ('1d6', '2d6', '3d6'):
            button = ttk.Button(quick, text=expression,
                                command=lambda expression=expression: self.quick_roll(expression))
            button.pack(side='left', padx=3)
            self.quick_buttons.append(button)
        error_color = '#b42318' if app.ui_preferences['theme'] == 'light' else '#ff8585'
        self.error = ttk.Label(self, foreground=error_color, wraplength=580)
        self.error.grid(row=4, column=0, sticky='w', pady=(0, 6))
        work = ttk.Frame(self)
        work.grid(row=5, column=0, sticky='ew')
        work.columnconfigure(0, weight=1)
        self.progress_text = ttk.Label(work)
        self.progress_text.grid(row=0, column=0, sticky='w')
        self.progress = ttk.Progressbar(work, mode='determinate')
        self.progress.grid(row=1, column=0, sticky='ew', pady=4)
        self.cancel_button = ttk.Button(work, text=t('gm_dice_cancel'), command=self.cancel)
        self.cancel_button.grid(row=1, column=1, padx=(8, 0))
        self.total = ttk.Label(self, style='Title.TLabel')
        self.total.grid(row=6, column=0, sticky='w', pady=8)
        pages = ttk.Frame(self)
        pages.grid(row=7, column=0, sticky='ew', pady=(0, 8))
        self.previous = ttk.Button(pages, text=t('gm_dice_previous'), command=lambda: self.change_page(-1))
        self.previous.pack(side='left')
        self.next = ttk.Button(pages, text=t('gm_dice_next'), command=lambda: self.change_page(1))
        self.next.pack(side='left', padx=4)
        ttk.Label(pages, text=t('gm_dice_page')).pack(side='left', padx=(6, 4))
        self.page_entry = ttk.Entry(pages, textvariable=app.gm_dice_page, width=7)
        self.page_entry.pack(side='left')
        self.page_entry.bind('<Return>', self.go_to_page)
        self.go = ttk.Button(pages, text=t('gm_dice_go'), command=self.go_to_page)
        self.go.pack(side='left', padx=4)
        self.pages_label = ttk.Label(pages)
        self.pages_label.pack(side='left')
        details = ttk.Frame(self)
        details.grid(row=8, column=0, sticky='nsew')
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.output = tk.Text(details, height=12, width=40, wrap='word', state='disabled',
                              bg=app.colors['panel'], fg=app.colors['fg'],
                              selectbackground=app.colors['accent'], font=('Consolas', 10),
                              padx=10, pady=10)
        self.output.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(details, command=self.output.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.output.configure(yscrollcommand=scroll.set)
        actions = ttk.Frame(self)
        actions.grid(row=9, column=0, sticky='w', pady=(10, 0))
        self.copy_button = ttk.Button(actions, text=t('gm_dice_copy_page'), command=self.copy_result)
        self.copy_button.pack(side='left', padx=(0, 8))
        self.export_button = ttk.Button(actions, text=t('gm_dice_export'), command=self.export_result)
        self.export_button.pack(side='left', padx=(0, 8))
        self.clear_button = ttk.Button(actions, text=t('gm_dice_clear'), command=self.clear_result)
        self.clear_button.pack(side='left')
        self.render()

    def render(self):
        result = self.app.gm_dice_last_result
        job = self.app._gm_dice_job
        busy = job is not None
        pages = (result.count + PAGE_SIZE - 1) // PAGE_SIZE if result else 1
        page = self.app._gm_dice_current_page
        self.pages_label.configure(text=t('gm_dice_pages', pages=pages))
        self.total.configure(text=t('gm_dice_total', total=result.total) if result else t('gm_dice_empty'))
        self.error.configure(text=t('gm_dice_error_' + self.app.gm_dice_error_code)
                             if self.app.gm_dice_error_code else '')
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        if result:
            self.output.insert('1.0', format_roll(result, page))
        self.output.configure(state='disabled')
        self.copy_button.configure(state='normal' if result else 'disabled')
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
        self.cancel_button.configure(state='normal' if busy else 'disabled')
        self.progress.configure(maximum=job['count'] if busy else 1, value=job['done'] if busy else 0)
        self.progress_text.configure(text=t('gm_dice_progress_' + job['kind'], done=job['done'], count=job['count'])
                                     if busy else '')

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
            self.app.gm_dice_last_result = result
            self.app._gm_dice_current_page = 1
            self.app.gm_dice_page.set('1')
            self.app.gm_dice_error_code = None
            self.entry.state(['!invalid'])
        self.render()
        return 'break' if event is not None else None

    def start_job(self, kind, count, operation):
        job = {'kind': kind, 'count': count, 'done': 0, 'queue': Queue(), 'cancel': Event()}
        self.app._gm_dice_job = job
        self.app.gm_dice_error_code = None
        self.render()
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
                        self.app.gm_dice_last_result = value
                        self.app._gm_dice_current_page = 1
                        self.app.gm_dice_page.set('1')
                self.app._gm_dice_job = None
        panel = self.app.gm_dice_panel
        panel.render()
        if not completed:
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

    def clear_result(self):
        self.app.gm_dice_last_result = None
        self.app._gm_dice_current_page = 1
        self.app.gm_dice_page.set('1')
        self.app.gm_dice_error_code = None
        self.entry.state(['!invalid'])
        self.render()
