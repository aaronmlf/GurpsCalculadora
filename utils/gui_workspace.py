"""Shared desktop navigation, catalog selection and result presentation."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from dataclasses import asdict, is_dataclass
import unicodedata

from utils.i18n import t


def search_values(values, query):
    def normalize(value):
        return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                       if not unicodedata.combining(c))
    words = normalize(query).split()
    return [value for value in values if all(word in normalize(value) for word in words)]


class CatalogDialog(tk.Toplevel):
    """Searching never changes the active item; only confirmation commits it."""
    def __init__(self, combo):
        super().__init__(combo.winfo_toplevel())
        self.combo = combo
        self.title(t('ui_catalog'))
        self.geometry('800x620')
        self.minsize(640, 560)
        self.configure(background=combo.winfo_toplevel().cget('background'))
        self.transient(combo.winfo_toplevel())
        self.values = list(combo.cget('values'))
        self.records = getattr(combo, 'catalog_records', lambda: {})()
        self.app = getattr(combo, 'catalog_app', None)
        self.favorites = self.app.ui_preferences['catalog_favorites'] if self.app else []
        self.only_favorites = tk.BooleanVar(self, value=False)
        self.query = tk.StringVar(self)
        ttk.Label(self, text=t('ui_search_hint')).pack(anchor='w', padx=12, pady=(12, 4))
        entry = ttk.Entry(self, textvariable=self.query)
        entry.pack(fill='x', padx=12)
        self.filters = {}
        filters = ttk.Frame(self)
        filters.pack(fill='x', padx=12, pady=6)
        for field in ('source', 'college', 'spell_class', 'vehicle_type', 'tech_level', 'power', 'category', 'profile'):
            options = sorted({str(getattr(record, field)) for record in self.records.values()
                              if getattr(record, field, '') not in ('', None)})
            if len(options) < 2:
                continue
            index = len(self.filters)
            ttk.Label(filters, text=t('ui_field_' + field)).grid(row=index // 3 * 2, column=index % 3, sticky='w')
            variable = tk.StringVar(self, value=t('ui_all'))
            selector = ttk.Combobox(filters, textvariable=variable,
                                    values=[t('ui_all')] + options, state='readonly', width=22)
            selector.grid(row=index // 3 * 2 + 1, column=index % 3, sticky='ew', padx=(0, 6))
            self.filters[field] = variable
            variable.trace_add('write', self.refresh)
        self.count = ttk.Label(self)
        self.count.pack(anchor='w', padx=12, pady=4)
        ttk.Checkbutton(self, text=t('ui_only_favorites'), variable=self.only_favorites,
                        command=self.refresh).pack(anchor='w', padx=12)
        footer = ttk.Frame(self, padding=8)
        footer.pack(side='bottom', fill='x')
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=12)
        self.list = tk.Listbox(frame, exportselection=False, height=7)
        scrollbar = ttk.Scrollbar(frame, command=self.list.yview)
        self.list.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.list.pack(fill='both', expand=True)
        details = ttk.Frame(self)
        details.pack(fill='x', padx=12, pady=8)
        self.detail = tk.Text(details, height=7, wrap='word', state='disabled')
        detail_scroll = ttk.Scrollbar(details, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side='right', fill='y')
        self.detail.pack(fill='x')
        self.use = ttk.Button(footer, text=t('ui_use'), command=self.confirm, state='disabled')
        self.use.grid(row=0, column=3, padx=4)
        ttk.Button(footer, text=t('ui_cancel'), command=self.destroy).grid(row=0, column=2, padx=4)
        ttk.Button(footer, text=t('ui_catalog_star'), command=self.toggle_favorite).grid(row=0, column=0, padx=4)
        ttk.Button(footer, text=t('ui_full_record'), command=self.full_record).grid(row=0, column=1, padx=4)
        self.list.bind('<<ListboxSelect>>', self.select)
        self.list.bind('<Double-1>', self.confirm)
        self.bind('<Escape>', lambda event: self.destroy())
        self.query.trace_add('write', self.refresh)
        self.refresh()
        entry.focus_set()

    def refresh(self, *_):
        self.filtered = [label for label in self.values if search_values(
            [label + ' ' + ' '.join(getattr(self.records.get(label), 'aliases', []) or [])], self.query.get())]
        self.filtered = [label for label in self.filtered if all(
            variable.get() == t('ui_all') or
            str(getattr(self.records.get(label), field, '')) == variable.get()
            for field, variable in self.filters.items())]
        if self.only_favorites.get():
            self.filtered = [label for label in self.filtered if self.favorite_key(label) in self.favorites]
        self.list.delete(0, 'end')
        for value in self.filtered:
            self.list.insert('end', ('★ ' if self.favorite_key(value) in self.favorites else '') + value)
        self.count.configure(text=t('ui_count', count=len(self.filtered)))
        self.set_detail('' if self.filtered else t('ui_no_matches'))
        self.use.configure(state='disabled')

    def select(self, *_):
        selected = self.list.curselection()
        if selected:
            label = self.filtered[selected[0]]
            self.set_detail(record_details(label, self.records.get(label)))
            self.use.configure(state='normal')

    def set_detail(self, text):
        self.detail.configure(state='normal')
        self.detail.delete('1.0', 'end')
        self.detail.insert('1.0', text)
        self.detail.configure(state='disabled')

    def favorite_key(self, label):
        return getattr(self.records.get(label), 'identifier', label)

    def toggle_favorite(self):
        selected = self.list.curselection()
        if not selected:
            return
        label = self.filtered[selected[0]]
        key = self.favorite_key(label)
        if key in self.favorites:
            self.favorites.remove(key)
        else:
            self.favorites.append(key)
        if self.app:
            from utils.gui_hub import save_ui
            save_ui(self.app)
        self.refresh()
        if label in self.filtered:
            self.list.selection_set(self.filtered.index(label))
            self.select()

    def full_record(self):
        selected = self.list.curselection()
        if not selected:
            return
        record = self.records.get(self.filtered[selected[0]])
        if not is_dataclass(record):
            return
        window = tk.Toplevel(self)
        window.title(t('ui_full_record'))
        window.geometry('760x500')
        ttk.Label(window, text=t('ui_record_audit_notice'), wraplength=720).pack(fill='x', padx=12, pady=8)
        tree = ttk.Treeview(window, columns=('value',), show='tree headings')
        tree.heading('#0', text=t('ui_record_field'))
        tree.heading('value', text=t('ui_record_value'))
        tree.column('#0', width=260)
        tree.column('value', width=400)
        scroll = ttk.Scrollbar(window, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        def insert(parent, mapping):
            pairs = mapping.items() if isinstance(mapping, dict) else enumerate(mapping)
            for key, value in pairs:
                label = t('ui_field_' + str(key))
                if label == 'ui_field_' + str(key):
                    label = str(key)
                nested = isinstance(value, (dict, list))
                node = tree.insert(parent, 'end', text=label, values=('' if nested else value,))
                if nested:
                    insert(node, value)
        insert('', asdict(record))

    def confirm(self, *_):
        selected = self.list.curselection()
        if selected:
            self.combo.set(self.filtered[selected[0]])
            self.combo.event_generate('<<ComboboxSelected>>')
            self.destroy()


def record_details(label, record):
    lines = [label]
    for field in ('college', 'spell_class', 'vehicle_type', 'tech_level', 'power', 'skill',
                  'base_cost', 'maintenance_cost', 'casting_time_seconds', 'duration_seconds',
                  'resist_attribute', 'prerequisites', 'st_hp', 'ht', 'dr', 'occupants',
                  'activation_cost', 'cost_per_level'):
        value = getattr(record, field, None)
        if value is not None and value != '' and value != []:
            if isinstance(value, list):
                value = ', '.join(map(str, value))
            lines.append(f'{t("ui_field_" + field)}: {value}')
    if getattr(record, 'reference_only', False):
        lines.append(t('ui_reference_only'))
    lines.append(t('ui_catalog_notice'))
    return '\n'.join(lines)


def catalog_records(app, combo):
    labels = set(combo.cget('values'))
    records = {}
    for name in ('_magic_map', '_advantage_map', '_psi_map', '_vehicle_map', '_melee_weapon_labels'):
        records.update({label: record for label, record in getattr(app, name, {}).items()
                        if label in labels})
    for label, identifier in getattr(app, '_ranged_weapon_map', {}).items():
        if label in labels:
            records[label] = app.weapon_catalog.get(identifier)
    return records


def install_workspace(app, active=0):
    notebook = app.notebook
    style = ttk.Style(app.root)
    style.layout('Workspace.TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
    style.layout('Workspace.TNotebook.Tab', [])
    style.configure('Workspace.Treeview', background=app.colors['panel'],
                    fieldbackground=app.colors['panel'], foreground=app.colors['fg'], rowheight=25)
    notebook.configure(style='Workspace.TNotebook')
    sidebar = ttk.Frame(app.main_frame, width=190)
    sidebar.pack(side='left', fill='y', before=notebook, padx=(0, 10))
    ttk.Label(sidebar, text=t('ui_tools'), style='Title.TLabel').pack(anchor='w', pady=(0, 8))
    tree = ttk.Treeview(sidebar, show='tree', selectmode='browse', height=20,
                        style='Workspace.Treeview')
    tree.column('#0', width=180, stretch=True)
    scroll = ttk.Scrollbar(sidebar, command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)
    groups = [('ui_combat', [6, 8, 7, 9]), ('ui_powers', [10, 11]),
              ('ui_impacts', [0, 1, 2, 3, 4, 5]), ('ui_vehicles', [12]), ('ui_campaign', [13, 14]),
              ('ui_game_master', [15])]
    for key, indices in groups:
        tree.insert('', 'end', iid=key, text=t(key), open=True)
        for index in indices:
            tree.insert(key, 'end', iid=str(index), text=notebook.tab(index, 'text'))
    def navigate(*_):
        selected = tree.selection()
        if selected and selected[0].isdigit():
            notebook.select(int(selected[0]))
    tree.bind('<<TreeviewSelect>>', navigate)
    tree.selection_set(str(active))
    tree.see(str(active))
    notebook.select(active)
    app.navigation_tree = tree

    search_columns = {}
    def visit(parent):
        for widget in list(parent.winfo_children()):
            if isinstance(widget, ttk.Combobox) and len(widget.cget('values')) >= 30:
                widget.catalog_records = lambda box=widget: catalog_records(app, box)
                widget.catalog_app = app
                widget.bind('<Control-f>', lambda event, box=widget: CatalogDialog(box))
                info = widget.grid_info()
                if info:
                    row = int(info['row'])
                    column = search_columns.setdefault(widget.master, widget.master.grid_size()[0])
                    ttk.Button(widget.master, text=t('ui_search'),
                               command=lambda box=widget: CatalogDialog(box)).grid(
                                   row=row, column=column, padx=4, sticky='e')
            elif isinstance(widget, tk.Text):
                organize_result(widget)
            visit(widget)
    visit(notebook)


def organize_result(box):
    """Keep the existing Text API so all legacy engine renderers still work."""
    if box.winfo_manager() != 'pack':
        return
    toolbar = ttk.Frame(box.master)
    toolbar.pack(fill='x', before=box, padx=8, pady=4)
    summary = ttk.Label(toolbar, text=t('ui_result_empty'), wraplength=500)
    summary.pack(anchor='w', fill='x')
    box.summary_label = summary
    warning_color = '#8a4b00' if box.winfo_toplevel().cget('background') == '#f2f4f7' else '#ffbd69'
    box.status_label = ttk.Label(toolbar, text='', foreground=warning_color, wraplength=650)
    box.status_label.pack(anchor='w', fill='x')
    def copy():
        box.clipboard_clear()
        box.clipboard_append(box.get('1.0', 'end-1c'))
    actions = ttk.Frame(toolbar)
    actions.pack(fill='x', pady=4)
    ttk.Button(actions, text=t('ui_copy'), command=copy).grid(row=0, column=0, sticky='ew', padx=2)
    comparison = ResultComparison(box)
    ttk.Button(actions, text=t('ui_keep_result'), command=comparison.keep).grid(row=0, column=1, sticky='ew', padx=2)
    comparison.button = ttk.Button(actions, text=t('ui_compare'), command=comparison.show, state='disabled')
    comparison.button.grid(row=0, column=2, sticky='ew', padx=2)
    ttk.Button(actions, text=t('ui_result_history'), command=comparison.show_history).grid(row=1, column=0, sticky='ew', padx=2, pady=4)
    def export():
        path = filedialog.asksaveasfilename(parent=box.winfo_toplevel(), defaultextension='.txt',
                                          filetypes=[(t('ui_text_file'), '*.txt')])
        if path:
            try:
                Path(path).write_text(box.get('1.0', 'end-1c'), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror(t('common_error_title'), str(exc))
    ttk.Button(actions, text=t('ui_export_result'), command=export).grid(row=1, column=1, sticky='ew', padx=2, pady=4)
    for index in range(3):
        actions.columnconfigure(index, weight=1)
    box.comparison = comparison
    ttk.Label(toolbar, text=t('ui_breakdown')).pack(side='left')
    box.configure(wrap='word', spacing1=3, spacing3=3)
    box.tag_configure('heading', font=('Arial', 11, 'bold'))
    def changed(*_):
        if not box.edit_modified():
            return
        lines = [line.strip() for line in box.get('1.0', 'end-1c').splitlines() if line.strip()]
        summary.configure(text='  |  '.join(lines[:2]) if lines else t('ui_result_empty'))
        box.tag_remove('heading', '1.0', 'end')
        box.tag_add('heading', '1.0', '1.end')
        if hasattr(box, 'form_state'):
            box.form_state.result_changed(box)
        box.edit_modified(False)
    box.bind('<<Modified>>', changed, add='+')
    # Users can select and copy, but cannot accidentally edit calculated output.
    box.bind('<Key>', lambda event: None if event.keysym in ('Left', 'Right', 'Up', 'Down', 'Home', 'End', 'Prior', 'Next') or (event.state & 4 and event.keysym.lower() in ('c', 'a')) else 'break')
    box.bind('<<Paste>>', lambda event: 'break')
    box.bind('<<Cut>>', lambda event: 'break')


class ResultComparison:
    """An explicit snapshot of displayed output, never a session mutation."""
    def __init__(self, box):
        self.box = box
        self.saved = ''
        self.history = []
        self.button = None

    def keep(self):
        text = self.box.get('1.0', 'end-1c').strip()
        if text:
            self.saved = text
            if self.button:
                self.button.configure(state='normal')

    def show(self):
        if not self.saved:
            return
        window = tk.Toplevel(self.box.winfo_toplevel())
        window.title(t('ui_compare'))
        window.geometry('850x500')
        ttk.Label(window, text=t('ui_compare_notice'), wraplength=800).pack(fill='x', padx=12, pady=8)
        panels = ttk.Panedwindow(window, orient='horizontal')
        panels.pack(fill='both', expand=True, padx=12, pady=8)
        for title, value in ((t('ui_saved_result'), self.saved),
                             (t('ui_current_result'), self.box.get('1.0', 'end-1c'))):
            frame = ttk.LabelFrame(panels, text=title)
            panels.add(frame, weight=1)
            text = tk.Text(frame, wrap='word', width=35)
            scrollbar = ttk.Scrollbar(frame, command=text.yview)
            text.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right', fill='y')
            text.pack(fill='both', expand=True)
            text.insert('1.0', value)
            text.configure(state='disabled')

    def show_history(self):
        window = tk.Toplevel(self.box.winfo_toplevel())
        window.title(t('ui_result_history'))
        window.geometry('760x500')
        ttk.Label(window, text=t('ui_history_notice'), wraplength=700).pack(fill='x', padx=12, pady=8)
        selected = tk.StringVar(window)
        picker = ttk.Combobox(window, textvariable=selected, state='readonly',
                              values=[f'{index + 1}. {context}' for index, (context, text) in enumerate(self.history)])
        picker.pack(fill='x', padx=12)
        frame = ttk.Frame(window)
        frame.pack(fill='both', expand=True, padx=12, pady=12)
        output = tk.Text(frame, wrap='word', state='disabled')
        scroll = ttk.Scrollbar(frame, command=output.yview)
        output.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        output.pack(fill='both', expand=True)
        def select(*_):
            index = picker.current()
            if index >= 0:
                output.configure(state='normal')
                output.delete('1.0', 'end')
                output.insert('1.0', self.history[index][1])
                output.configure(state='disabled')
        picker.bind('<<ComboboxSelected>>', select)
        if self.history:
            picker.current(len(self.history) - 1)
            select()
