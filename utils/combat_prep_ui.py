"""Encounter preparation from imported GCS sheets and local snapshots."""

from copy import deepcopy
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

from calculators.combat_library import clean_name, combatant_from_imported
from utils.i18n import t
from utils.ui_preferences import BATTLE_MAP_TOOL
from utils.ranged_layout import flow_buttons, wrap_label


def _integer(value):
    raw = str(value).strip()
    digits = raw[1:] if raw[:1] in ('+', '-') else raw
    if not 1 <= len(digits) <= 10 or not digits.isascii() or not digits.isdecimal():
        raise ValueError('encounter_bad_number')
    return int(raw)


def _scroll_body(parent, background):
    canvas = tk.Canvas(parent, background=background, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, command=canvas.yview)
    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    body = ttk.Frame(canvas, padding=10)
    window = canvas.create_window(0, 0, anchor='nw', window=body)
    body.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox(window)))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
    return body, canvas


def _scroll_children(parent, canvas):
    def wheel(event):
        direction = -1 if event.num == 4 else 1 if event.num == 5 else (-1 if event.delta > 0 else 1)
        canvas.yview_scroll(direction, 'units')
        return 'break'

    def focus(event):
        widget = event.widget
        top = widget.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        height = canvas.winfo_height()
        bounds = canvas.bbox('all')
        if bounds and bounds[3] > 0:
            if top < 0:
                canvas.yview_moveto(canvas.canvasy(top) / bounds[3])
            elif bottom > height:
                canvas.yview_moveto(canvas.canvasy(bottom - height) / bounds[3])

    def walk(widget):
        if not isinstance(widget, (ttk.Treeview, tk.Text, ttk.Scrollbar)):
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                widget.bind(sequence, wheel)
            if isinstance(widget, (ttk.Entry, ttk.Combobox, ttk.Button, ttk.Menubutton)):
                widget.bind('<FocusIn>', focus)
            for child in widget.winfo_children():
                walk(child)

    walk(parent)


def _tree(parent, headings, selectmode='browse'):
    container = ttk.Frame(parent)
    container.pack(fill='x', pady=(4, 6))
    tree = ttk.Treeview(container, show='tree headings', selectmode=selectmode, height=6,
                        columns=tuple(key for key, _, _ in headings), style='Workspace.Treeview')
    tree.heading('#0', text=t('combat_prep_name'), anchor='w')
    tree.column('#0', width=200, minwidth=70)
    for key, label, width in headings:
        tree.heading(key, text=label, anchor='w')
        tree.column(key, width=width, minwidth=min(40, width), stretch=(key == 'group'))
    scrollbar = ttk.Scrollbar(container, command=tree.yview)
    scrollbar.pack(side='right', fill='y')
    tree.pack(side='left', fill='both', expand=True)
    tree.configure(yscrollcommand=scrollbar.set)
    return tree


def _speed(value):
    return f'{value:g}' if value is not None else '—'


def _sheet_format(code):
    return {'gcs_native': 'GCS (.gcs)', 'gcs_fantasy_grounds_pc': 'Fantasy Grounds (.xml)'}.get(code, code)


def _error_text(exc, fallback='encounter_bad_number'):
    if isinstance(exc, OSError):
        return t('local_data_save_error', error=exc)
    key = str(exc)
    return t(key) if t(key) != key else t(fallback)


class ResourceEditor(tk.Toplevel):
    """Change current encounter values without editing an imported sheet."""

    def __init__(self, parent, identifier):
        super().__init__(parent)
        self.window = parent
        self.app = parent.app
        self.identifier = identifier
        self.session = self.app.combat_session
        participant = self.session.combatants[identifier]
        self.before = participant.to_dict()
        self.pools = deepcopy(participant.resource_pools)
        self.currents = {}
        self.title(t('encounter_resources_title', name=participant.name))
        self.transient(parent)
        self.geometry('510x440')
        self.minsize(370, 320)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.status = tk.StringVar(self)
        wrap_label(ttk.Label(self, textvariable=self.status, style='Error.TLabel', wraplength=350)).pack(
            side='bottom', fill='x', padx=10)
        actions = ttk.Frame(self)
        actions.pack(side='bottom', fill='x', padx=10, pady=8)
        flow_buttons(actions, [
            ttk.Button(actions, text=t('session_apply'), command=self.apply_changes, style='Primary.TButton'),
            ttk.Button(actions, text=t('ui_cancel'), command=self.destroy),
        ])
        area = ttk.Frame(self)
        area.pack(fill='both', expand=True)
        body, self.canvas = _scroll_body(area, self.app.colors['bg'])
        self.values = ttk.Frame(body)
        self.values.pack(fill='x')
        self.current_hp = self._value_row(self.values, 'HP', participant.max_hp, participant.current_hp)
        self.current_fp = self._value_row(self.values, 'FP', participant.max_fp, participant.current_fp)
        for key, pool in self.pools.items():
            self.currents[key] = self._value_row(self.values, pool['label'], pool['maximum'], pool['current'])

        ttk.Button(body, text=t('encounter_add_pool') + '…', command=self._show_pool_form).pack(anchor='w', pady=6)
        self.pool_form = ttk.LabelFrame(body, text=t('encounter_add_pool'), padding=6)
        self.pool_name = tk.StringVar(self)
        self.pool_maximum = tk.StringVar(self, value='1')
        self.pool_current = tk.StringVar(self, value='1')
        for key, value in (('encounter_pool_name', self.pool_name), ('encounter_pool_maximum', self.pool_maximum),
                           ('encounter_pool_current', self.pool_current)):
            wrap_label(ttk.Label(self.pool_form, text=t(key))).pack(fill='x')
            ttk.Entry(self.pool_form, textvariable=value).pack(fill='x', pady=(2, 5))
        ttk.Button(self.pool_form, text=t('encounter_add_pool'), command=self._append_pool).pack(anchor='w')
        _scroll_children(self.canvas, self.canvas)
        self.grab_set()

    def _value_row(self, parent, label, maximum, current):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(0, 6))
        wrap_label(ttk.Label(row, text=label + ' · ' + t('encounter_resource_maximum', value=maximum))).pack(fill='x')
        variable = tk.StringVar(self, value=str(current))
        ttk.Entry(row, textvariable=variable, width=10).pack(anchor='w')
        return variable

    def _show_pool_form(self):
        self.pool_form.pack(fill='x', pady=4)
        self.update_idletasks()
        self.canvas.yview_moveto(1)

    def add_pool(self, label, maximum, current):
        label = clean_name(label)
        maximum, current = _integer(maximum), _integer(current)
        if (len(self.pools) >= 32 or maximum < 0 or not 0 <= current <= maximum
                or any(pool['label'].casefold() == label.casefold() for pool in self.pools.values())):
            raise ValueError('encounter_invalid_resource')
        key = 'manual-' + uuid4().hex
        self.pools[key] = {'label': label, 'maximum': maximum, 'current': current}
        self.currents[key] = self._value_row(self.values, label, maximum, current)
        _scroll_children(self.values.winfo_children()[-1], self.canvas)
        return key

    def _append_pool(self):
        try:
            self.add_pool(self.pool_name.get(), self.pool_maximum.get(), self.pool_current.get())
        except ValueError as exc:
            self.status.set(_error_text(exc))
        else:
            self.pool_name.set('')
            self.pool_form.pack_forget()
            self.status.set('')

    def apply_changes(self):
        try:
            current = self.app.combat_session.combatants.get(self.identifier)
            if self.app.combat_session is not self.session or current is None or current.to_dict() != self.before:
                raise ValueError('ui_session_stale')
            pools = deepcopy(self.pools)
            for key, variable in self.currents.items():
                pools[key]['current'] = _integer(variable.get())
            updated = {'current_hp': _integer(self.current_hp.get()), 'current_fp': _integer(self.current_fp.get()),
                       'resource_pools': pools}
            changes = {key: value for key, value in updated.items() if value != getattr(current, key)}
            if changes:
                self.session.edit_combatant_state(self.identifier, **changes)
        except (OSError, ValueError, KeyError) as exc:
            self.status.set(_error_text(exc))
            return False
        self.destroy()
        self.app._session_changed()
        self.window.refresh_from_session()
        return True


class CombatPrepWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.library = app.combat_library
        self.title(t('combat_prep_title'))
        self.transient(app.root)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.geometry('810x610')
        self.minsize(540, 420)
        if self.library.warning:
            wrap_label(ttk.Label(self, text=t('local_data_warning', path=self.library.warning),
                                 style='Warning.TLabel', wraplength=530)).pack(fill='x', padx=10, pady=4)
        self.status = tk.StringVar(self)
        wrap_label(ttk.Label(self, textvariable=self.status, wraplength=530)).pack(
            side='bottom', fill='x', padx=10, pady=(4, 7))
        self.pages = ttk.Notebook(self)
        self.pages.pack(fill='both', expand=True, padx=8, pady=8)
        self.roster_page = self._page('encounter_roster', self._build_roster)
        self.sheets_page = self._page('encounter_sheets', self._build_sheets)
        self.scenarios_page = self._page('encounter_scenarios', self._build_scenarios)
        self.refresh_from_session()
        self._refresh_sheets()
        self.pages.select(self.sheets_page if not self._sheet_rows else self.roster_page)

    def _page(self, key, build):
        page = ttk.Frame(self.pages)
        self.pages.add(page, text=t(key))
        body, canvas = _scroll_body(page, self.app.colors['bg'])
        build(body)
        _scroll_children(canvas, canvas)
        return page

    def _guard(self, handler):
        try:
            return handler()
        except (OSError, ValueError, KeyError) as exc:
            self.status.set(_error_text(exc))

    def _buttons(self, parent, choices):
        row = ttk.Frame(parent)
        row.pack(fill='x')
        buttons = [ttk.Button(row, text=t(key), command=lambda handler=handler: self._guard(handler))
                   for key, handler in choices]
        flow_buttons(row, buttons)
        return row

    def _build_roster(self, parent):
        self.roster_count = ttk.Label(parent, style='Title.TLabel')
        self.roster_count.pack(anchor='w')
        wrap_label(ttk.Label(parent, textvariable=self.app.session_summary, wraplength=510)).pack(fill='x')
        self.roster_tree = _tree(parent, (('hp', 'HP', 65), ('fp', 'FP', 65), ('speed', 'BS', 58),
                                         ('group', t('encounter_group'), 105)))
        self.roster_tree.bind('<Double-1>', self._resource_event)
        self.roster_tree.bind('<Return>', self._resource_event)
        self._buttons(parent, (
            ('encounter_use_actor', lambda: self._set_role('actor')),
            ('encounter_use_target', lambda: self._set_role('target')),
            ('encounter_resources', self.edit_resources),
        ))
        self._buttons(parent, (
            ('encounter_move_up', lambda: self._move_selected(-1)),
            ('encounter_move_down', lambda: self._move_selected(1)),
            ('encounter_sort_speed', self._sort_speed),
        ))
        self._buttons(parent, (
            ('encounter_set_group', self._set_group_selected), ('encounter_remove', self._remove_selected),
            ('combat_prep_swap', self._swap), ('combat_prep_use_weapons', self.app._use_session_weapons),
        ))
        self._buttons(parent, (
            ('encounter_sheets', lambda: self.pages.select(self.sheets_page)), ('session_undo', self._undo),
            ('tab_battle_map', self._open_map),
        ))

    def _open_map(self):
        self.app.choose_tool(BATTLE_MAP_TOOL)
        self.destroy()

    def _build_sheets(self, parent):
        self._buttons(parent, (('encounter_import_files', self._pick_files),))
        self.sheets_tree = _tree(parent, (('source', t('encounter_sheets'), 155),), selectmode='extended')
        self.sheets_tree.bind('<<TreeviewSelect>>', lambda _event: self._describe_sheet())
        self.sheet_summary = wrap_label(ttk.Label(parent, justify='left', wraplength=510))
        self.sheet_summary.pack(fill='x', pady=4)
        self.copies = tk.StringVar(self, value='1')
        copies = ttk.Frame(parent)
        copies.pack(fill='x', pady=(4, 0))
        wrap_label(ttk.Label(copies, text=t('encounter_copies'))).pack(fill='x')
        ttk.Spinbox(copies, from_=1, to=100, textvariable=self.copies, width=5).pack(anchor='w')
        self._buttons(parent, (('encounter_add', self._add_selected),))

    def _build_scenarios(self, parent):
        self.session_name = tk.StringVar(self)
        self.sessions = ttk.Combobox(parent, textvariable=self.session_name)
        self.sessions.pack(fill='x', pady=(0, 5))
        self._buttons(parent, (
            ('combat_prep_save_session', self._save_session), ('combat_prep_open_session', self._open_session),
            ('session_new', self._new_session), ('session_undo', self._undo),
        ))
        wrap_label(ttk.Label(parent, text=t('combat_prep_snapshot_hint'), wraplength=500)).pack(fill='x', pady=5)
        history = ttk.Frame(parent)
        history.pack(fill='x', pady=4)
        self.history = tk.Text(history, height=8, width=1, wrap='word',
                               background=self.app.colors['panel'], foreground=self.app.colors['panel_fg'])
        scroll = ttk.Scrollbar(history, command=self.history.yview)
        scroll.pack(side='right', fill='y')
        self.history.pack(fill='both', expand=True)
        self.history.configure(yscrollcommand=scroll.set)

    def _pick_files(self):
        from utils.gcs_import import SUPPORTED_SUFFIXES

        paths = filedialog.askopenfilenames(
            parent=self, title=t('encounter_import_files'),
            filetypes=[(t('encounter_file_types'), ' '.join('*' + extension for extension in sorted(SUPPORTED_SUFFIXES))),
                       ('*', '*')],
        )
        if paths:
            return self.import_paths(paths)

    def import_paths(self, paths):
        """Import validated sheets to the library; never change the active roster."""
        from utils.gcs_import import GCSImportResult, read_gcs_files

        report, records = [], {}
        for item in read_gcs_files(paths):
            if item.character is not None:
                try:
                    state = combatant_from_imported(item.character)
                except (TypeError, ValueError) as exc:
                    item = GCSImportResult(item.path, error='gcs_invalid_stat', detail=t(str(exc)))
                else:
                    records[item.character.source_id] = state
            report.append(item)
        failures = [item for item in report if item.error]
        if records:
            self.library.save_imported_batch(records)
        self._refresh_sheets(records)
        summary = t('encounter_import_summary', imported=len(records), failed=len(failures))
        self.status.set(summary)
        if failures:
            lines = [f'{Path(item.path).name}: {t(item.error)}' +
                     (f' ({str(item.detail)[:120]})' if item.detail else '') for item in failures[:8]]
            if len(failures) > len(lines):
                lines.append(f'… (+{len(failures) - len(lines)})')
            messagebox.showwarning(t('encounter_import_report'), summary + '\n\n' + '\n'.join(lines), parent=self)
        return tuple(report)

    def _refresh_sheets(self, new_imports=()):
        selected = ({('imported', key) for key in new_imports} if new_imports else
                    {self._sheet_rows[row] for row in self.sheets_tree.selection()
                     if row in getattr(self, '_sheet_rows', {})})
        self.sheets_tree.delete(*self.sheets_tree.get_children())
        self._sheet_rows = {}
        items = [(state.name, _sheet_format(state.source_format) or 'GCS', 'imported', key)
                 for key, state in self.library.imported.items()]
        items.extend((profile.name, t('encounter_legacy'), 'legacy', key)
                     for key, profile in self.library.profiles.items())
        for index, (name, source, kind, key) in enumerate(sorted(items, key=lambda item: item[0].casefold())):
            row = f'sheet_{index}'
            self._sheet_rows[row] = (kind, key)
            self.sheets_tree.insert('', 'end', iid=row, text=name, values=(source,))
            if (kind, key) in selected:
                self.sheets_tree.selection_add(row)
        self._describe_sheet()

    def _sheet_state(self, row):
        kind, key = self._sheet_rows[row]
        state = (self.library.open_imported(key) if kind == 'imported'
                 else self.library.profiles[key].instantiate('combatant'))
        state.identifier = 'combatant'
        return state

    def _describe_sheet(self):
        selection = self.sheets_tree.selection()
        if not selection:
            self.sheet_summary.configure(text='' if self._sheet_rows else t('encounter_empty_sheets'))
            return
        state = self._sheet_state(selection[0])
        lines = [
            f'ST {state.st} · DX {state.dx} · IQ {state.iq} · HT {state.ht} · {t("encounter_speed")} {_speed(state.basic_speed)}',
            f'HP {state.current_hp}/{state.max_hp} · FP {state.current_fp}/{state.max_fp}',
        ]
        lines.append(' · '.join(f'{pool["label"]} {pool["current"]}/{pool["maximum"]}'
                                for pool in list(state.resource_pools.values())[:6]))
        if state.source_format:
            source = t('encounter_source', format=_sheet_format(state.source_format), version=state.source_version)
            lines.append(source + (f' · {state.source_name}' if state.source_name else ''))
        if state.unknown_defenses:
            lines.append(t('encounter_unknown_defenses', values=', '.join(
                t('melee_defense_' + key) for key in state.unknown_defenses)))
        self.sheet_summary.configure(text='\n'.join(filter(None, lines)))

    def _add_selected(self):
        selected = self.sheets_tree.selection()
        if not selected:
            raise ValueError('encounter_select_sheet')
        count = _integer(self.copies.get())
        if not 1 <= count <= 100:
            raise ValueError('encounter_bad_copies')
        if count * len(selected) > 100:
            raise ValueError('encounter_roster_limit')
        states = [self._sheet_state(row) for row in selected for _ in range(count)]
        identifiers = self.app.combat_session.add_combatants(states, replace_defaults=True)
        self.app._session_changed()
        self.refresh_from_session()
        self.pages.select(self.roster_page)
        self.roster_tree.selection_set(identifiers[0])
        self.roster_tree.see(identifiers[0])
        self.status.set(t('encounter_added', count=len(identifiers)))
        return identifiers

    def _selected_roster_id(self):
        selected = self.roster_tree.selection()
        if not selected:
            raise ValueError('encounter_select_one')
        return selected[0]

    def _set_role(self, role):
        self.app._select_encounter_role(role, self._selected_roster_id())
        self.refresh_from_session()

    def _swap(self):
        self.app._swap_encounter_roles()
        self.refresh_from_session()

    def _move_selected(self, delta):
        key = self._selected_roster_id()
        session = self.app.combat_session
        index = session.combatant_order.index(key)
        new_index = index + delta
        if 0 <= new_index < len(session.combatant_order):
            session.move_combatant(key, new_index)
            self.app._session_changed()
            self.refresh_from_session()

    def _sort_speed(self):
        self.app.combat_session.sort_combatants('basic_speed')
        self.app._session_changed()
        self.refresh_from_session()

    def _set_group_selected(self, group=None):
        key = self._selected_roster_id()
        if group is None:
            group = simpledialog.askstring(t('encounter_set_group'), t('encounter_group'),
                                           parent=self, initialvalue=self.app.combat_session.combatants[key].group)
        if group is not None:
            self.app.combat_session.edit_combatant_state(key, group=group.strip())
            self.app._session_changed()
            self.refresh_from_session()

    def _remove_selected(self):
        key = self._selected_roster_id()
        state = self.app.combat_session.combatants[key]
        if messagebox.askyesno(t('encounter_remove'), t('encounter_remove_confirm', name=state.name), parent=self):
            self.app.combat_session.remove_combatant(key)
            self.app._session_changed()
            self.refresh_from_session()

    def _resource_event(self, _event):
        if self.roster_tree.selection():
            self._guard(self.edit_resources)

    def edit_resources(self, participant_id=None):
        return ResourceEditor(self, participant_id or self._selected_roster_id())

    def refresh_from_session(self):
        """Refresh the roster, never touching an open resource editor's fields."""
        session = self.app.combat_session
        selection = self.roster_tree.selection()
        self.roster_tree.delete(*self.roster_tree.get_children())
        for index, key in enumerate(session.combatant_order, 1):
            state = session.combatants[key]
            role = '→ ' if key == self.app.session_actor_key else '◎ ' if key == self.app.session_target_key else ''
            self.roster_tree.insert('', 'end', iid=key, text=f'{role}{index}. {state.name}',
                                    values=(f'{state.current_hp}/{state.max_hp}', f'{state.current_fp}/{state.max_fp}',
                                            _speed(state.basic_speed), state.group))
        if selection and self.roster_tree.exists(selection[0]):
            self.roster_tree.selection_set(selection[0])
        self.roster_count.configure(text=t('encounter_roster_count', count=len(session.combatants)))
        self.sessions['values'] = sorted(self.library.sessions, key=str.casefold)
        self.history.configure(state='normal')
        self.history.delete('1.0', 'end')
        for event in reversed(session.events):
            self.history.insert('end', f'{event.applied_at}  {t(event.label)}\n')
        self.history.configure(state='disabled')

    def _save_session(self):
        name = clean_name(self.session_name.get())
        if name in self.library.sessions and not messagebox.askyesno(
                self.title(), t('combat_prep_overwrite'), parent=self):
            return
        self.library.save_session(name, self.app.combat_session)
        self.refresh_from_session()
        self.status.set(t('combat_prep_snapshot_saved'))

    def _open_session(self):
        name = self.session_name.get().strip()
        if name not in self.library.sessions:
            self.status.set(t('combat_prep_choose_session'))
            return
        if messagebox.askyesno(self.title(), t('combat_prep_open_confirm'), parent=self):
            candidate = self.library.open_session(name, self.app.combat_session.autosave_path)
            self.app._replace_active_session(candidate)
            self.refresh_from_session()
            self.status.set(t('combat_prep_session_loaded', name=name))

    def _new_session(self):
        self.app._new_session()
        self.refresh_from_session()

    def _undo(self):
        self.app._undo_session()
        self.refresh_from_session()
