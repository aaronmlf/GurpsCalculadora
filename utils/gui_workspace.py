"""Shared desktop navigation, catalog selection and result presentation."""
import tkinter as tk
from tkinter import ttk, filedialog, font, messagebox
from pathlib import Path
from dataclasses import asdict, is_dataclass
import unicodedata

from utils.i18n import t
from utils.rules_catalog import catalog_status
from utils.ui_preferences import BATTLE_MAP_TOOL


_TOOL_KEYS = (
    'tab_knockback', 'tab_slam', 'tab_falls', 'tab_collisions', 'tab_explosions',
    'tab_falling_objects', 'tab_combat', 'tab_injury', 'tab_ranged', 'tab_strength',
    'tab_magic', 'tab_powers', 'tab_vehicles', 'tab_social', 'tab_mass_combat',
    'tab_gm_dice', 'tab_battle_map',
)
_WORKSPACE_GROUPS = (
    ('ui_combat', (BATTLE_MAP_TOOL, 6, 8, 7, 9)), ('ui_powers', (10, 11)),
    ('ui_impacts', (0, 1, 2, 3, 4, 5)), ('ui_vehicles', (12,)),
    ('ui_campaign', (13, 14)),
)
_TOOL_GROUPS = {index: group for group, indices in _WORKSPACE_GROUPS for index in indices}
_TOOL_GROUPS[15] = 'ui_game_master'
_DOMAIN_GLYPHS = {'ui_combat': '×', 'ui_powers': '✦', 'ui_impacts': '↘',
                  'ui_vehicles': '▰', 'ui_campaign': '▦'}


def _fold_text(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c))


def search_values(values, query):
    words = _fold_text(query).split()
    return [value for value in values if all(word in _fold_text(value) for word in words)]


class ToolChooser(tk.Toplevel):
    """A small, bilingual index of the workspace's tools, independent of catalogs."""

    def __init__(self, app):
        super().__init__(app.main_frame)
        self.app = app
        self.title(t('ui_tool_search'))
        self.transient(app.root)
        self.geometry('520x380')
        self.minsize(380, 285)

        favorites = app.ui_preferences['favorites']
        recent = app.ui_preferences['recent']
        count = len(app.notebook.tabs())
        order = dict.fromkeys((15, *favorites, *recent, *range(count)))
        translations = app.i18n.translations.values()
        self.entries = []
        for index in order:
            if not 0 <= index < min(count, len(_TOOL_KEYS)):
                continue
            key, group = _TOOL_KEYS[index], _TOOL_GROUPS[index]
            label = app.notebook.tab(index, 'text')
            domain = t(group)
            names = tuple(_fold_text(name) for name in (label, *(table.get(key, '') for table in translations)))
            name_text = ' '.join(names)
            domain_text = _fold_text(' '.join((domain, *(table.get(group, '') for table in translations))))
            display = label if label == domain else f'{label}  ·  {domain}'
            self.entries.append((index, display, names, name_text, f'{name_text} {domain_text}'))

        frame = ttk.Frame(self, padding=14)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=t('ui_tool_search_hint'), wraplength=350).pack(anchor='w', pady=(0, 6))
        self.query = tk.StringVar(self)
        self.entry = ttk.Entry(frame, textvariable=self.query)
        self.entry.pack(fill='x', pady=(0, 8))

        buttons = ttk.Frame(frame)
        buttons.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Button(buttons, text=t('ui_cancel'), command=self.destroy).pack(side='right')
        self.open_button = ttk.Button(buttons, text=t('ui_open_tool'), command=self.confirm)
        self.open_button.pack(side='right', padx=(0, 6))
        self.empty = ttk.Label(frame)
        self.empty.pack(side='bottom', anchor='w')

        result = ttk.Frame(frame)
        result.pack(fill='both', expand=True)
        colors = app.colors
        self.listbox = tk.Listbox(result, height=7, width=24, exportselection=False,
                                  bg=colors.get('surface', colors['panel']),
                                  fg=colors.get('panel_fg', colors['fg']),
                                  selectbackground=colors['accent'],
                                  selectforeground=colors.get('accent_fg', colors['bg']),
                                  highlightthickness=0, relief='flat')
        scroll = ttk.Scrollbar(result, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.listbox.pack(side='left', fill='both', expand=True)

        self.entry.bind('<Down>', lambda _event: self.move(1))
        self.entry.bind('<Up>', lambda _event: self.move(-1))
        self.listbox.bind('<Double-1>', self.confirm)
        self.bind('<Return>', self.confirm)
        self.bind('<Escape>', lambda _event: self.destroy())
        self.query.trace_add('write', self.refresh)
        self.refresh()
        self.entry.focus_set()

    def refresh(self, *_):
        words = _fold_text(self.query.get()).split()
        query = ' '.join(words)
        matches = []
        for index, label, names, name_text, terms in self.entries:
            if all(word in terms for word in words):
                rank = 0 if query in names else 1 if all(word in name_text for word in words) else 2
                matches.append((rank, index, label))
        if words:
            matches.sort(key=lambda item: item[0])
        self.filtered = [(index, label) for _, index, label in matches]
        self.listbox.delete(0, 'end')
        for _, label in self.filtered:
            self.listbox.insert('end', label)
        if self.filtered:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        self.open_button.configure(state='normal' if self.filtered else 'disabled')
        self.empty.configure(text='' if self.filtered else t('ui_tool_search_empty'))

    def move(self, offset):
        if self.filtered:
            selected = self.listbox.curselection()
            index = min(len(self.filtered) - 1, max(0, (selected[0] if selected else 0) + offset))
            self.listbox.selection_clear(0, 'end')
            self.listbox.selection_set(index)
            self.listbox.activate(index)
            self.listbox.see(index)
        return 'break'

    def confirm(self, event=None):
        selected = self.listbox.curselection()
        if selected:
            index = self.filtered[selected[0]][0]
            self.destroy()
            self.app.choose_tool(index)
        return 'break' if event is not None else None

    def destroy(self):
        if getattr(self.app, '_tool_chooser', None) is self:
            self.app._tool_chooser = None
        super().destroy()


def select_workspace_tool(tree, index):
    """Keep unrelated domains collapsed and reveal a programmatically chosen tool."""
    iid = str(index)
    if not tree.exists(iid):
        return
    parent = tree.parent(iid)
    for group, _ in _WORKSPACE_GROUPS:
        tree.item(group, open=(group == parent))
    if tree.selection() != (iid,):
        tree.selection_set(iid)
    tree.focus(iid)
    tree.see(iid)


def short_tool_title(app, index):
    return app.notebook.tab(index, 'text').split(' (', 1)[0]


def workspace_tool_label(app, index):
    prefixes = []
    if index == 15:
        prefixes.append('◇')
    if index in app.ui_preferences['favorites']:
        prefixes.append('★')
    return '  '.join((*prefixes, short_tool_title(app, index)))


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
        for field in ('catalog_status', 'source', 'college', 'spell_class', 'vehicle_type', 'tech_level', 'power', 'category', 'profile'):
            options = sorted({self._filter_value(record, field) for record in self.records.values()
                              if self._filter_value(record, field)})
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
            self._filter_value(self.records.get(label), field) == variable.get()
            for field, variable in self.filters.items())]
        if self.only_favorites.get():
            self.filtered = [label for label in self.filtered if self.favorite_key(label) in self.favorites]
        self.list.delete(0, 'end')
        for value in self.filtered:
            self.list.insert('end', ('★ ' if self.favorite_key(value) in self.favorites else '') + value)
        self.count.configure(text=t('ui_count', count=len(self.filtered)))
        self.set_detail('' if self.filtered else t('ui_no_matches'))
        self.use.configure(state='disabled')

    @staticmethod
    def _filter_value(record, field):
        if field == 'catalog_status':
            status = catalog_status(record)
            return t('catalog_status_' + status) if status else ''
        return str(getattr(record, field, '') or '')

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
    colors = app.colors
    sidebar_color = colors.get('sidebar', colors['panel'])
    sidebar_fg = colors.get('sidebar_fg', colors['fg'])
    style.configure('Oficina.Sidebar.TFrame', background=sidebar_color)
    style.configure('Oficina.Sidebar.TLabel', background=sidebar_color,
                    foreground=sidebar_fg)
    style.configure('Workspace.Treeview', background=sidebar_color,
                    fieldbackground=sidebar_color, foreground=sidebar_fg, rowheight=25,
                    borderwidth=0, bordercolor=sidebar_color,
                    lightcolor=sidebar_color, darkcolor=sidebar_color)
    style.map('Workspace.Treeview', background=[('selected', colors['accent'])],
              foreground=[('selected', colors.get('accent_fg', colors['bg']))])
    notebook.configure(style='Workspace.TNotebook')
    sidebar = ttk.Frame(app.main_frame, style='Oficina.Sidebar.TFrame', padding=(6, 8))
    sidebar.pack(side='left', fill='y', before=notebook, padx=(0, 10))
    sidebar_header = ttk.Frame(sidebar, style='Oficina.Sidebar.TFrame')
    app.workspace_sidebar_header = sidebar_header
    sidebar_header.pack(fill='x', padx=3, pady=(0, 6))
    ttk.Label(sidebar_header, text=t('ui_tools'), style='Oficina.Sidebar.TLabel').pack(side='left')
    tree = ttk.Treeview(sidebar, show='tree', selectmode='browse', height=10,
                        style='Workspace.Treeview')
    size = app.ui_preferences['font_size']
    domain_labels = {
        key: f'{_DOMAIN_GLYPHS[key]}  {t("ui_impacts_short" if key == "ui_impacts" else key)}'
        for key, _ in _WORKSPACE_GROUPS
    }
    domain_font = font.Font(root=app.root, family='Arial', size=size, weight='bold')
    widest_domain = max(domain_font.measure(label) for label in domain_labels.values())
    tree.column('#0', width=min(262, max(154, int(16.5 * size), widest_domain + 26)), stretch=True)
    tree.tag_configure('domain', font=('Arial', size, 'bold'))
    scroll = ttk.Scrollbar(sidebar, command=tree.yview)
    def update_scroll(first, last):
        scroll.set(first, last)
        needed = float(first) > 0 or float(last) < 1
        if needed and not scroll.winfo_manager():
            scroll.pack(side='right', fill='y', before=tree)
        elif not needed and scroll.winfo_manager():
            scroll.pack_forget()
    tree.configure(yscrollcommand=update_scroll)
    tree.pack(fill='both', expand=True)
    tree.insert('', 'end', iid='15', text=workspace_tool_label(app, 15), tags=('domain',))
    for key, indices in _WORKSPACE_GROUPS:
        tree.insert('', 'end', iid=key, text=domain_labels[key], open=False, tags=('domain',))
        for index in indices:
            tree.insert(key, 'end', iid=str(index), text=workspace_tool_label(app, index))

    def toggle_domain(iid):
        if iid and tree.get_children(iid):
            tree.item(iid, open=not tree.item(iid, 'open'))
            return 'break'

    def click_domain(event):
        if 'indicator' not in tree.identify_element(event.x, event.y):
            return toggle_domain(tree.identify_row(event.y))

    tree.bind('<ButtonRelease-1>', click_domain, add='+')
    tree.bind('<Return>', lambda _event: toggle_domain(tree.focus()), add='+')
    select_workspace_tool(tree, active)
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
    card = getattr(box, 'oficina_card', False)
    responsive = card or getattr(box, 'responsive_toolbar', False)
    toolbar = ttk.Frame(box.master)
    toolbar.pack(fill='x', before=box, padx=8, pady=4)
    summary = ttk.Label(toolbar, text=t('ui_result_empty'), wraplength=180 if responsive else 500,
                        style='ResultSummary.TLabel' if card else 'TLabel')
    summary.pack(anchor='w', fill='x')
    box.summary_label = summary
    box.status_label = ttk.Label(toolbar, text='', style='Warning.TLabel',
                                 wraplength=180 if responsive else 650)
    box.status_label.pack(anchor='w', fill='x')
    def copy():
        box.clipboard_clear()
        box.clipboard_append(box.get('1.0', 'end-1c'))
    actions = ttk.Frame(toolbar)
    actions.pack(fill='x', pady=4)
    copy_button = ttk.Button(actions, text=t('ui_copy_short' if responsive else 'ui_copy'), command=copy)
    comparison = ResultComparison(box)
    comparison.button = ttk.Button(actions, text=t('ui_compare'), command=comparison.show, state='disabled')
    def export():
        path = filedialog.asksaveasfilename(parent=box.winfo_toplevel(), defaultextension='.txt',
                                          filetypes=[(t('ui_text_file'), '*.txt')])
        if path:
            try:
                Path(path).write_text(box.get('1.0', 'end-1c'), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror(t('common_error_title'), str(exc))
    if card:
        more = ttk.Menubutton(actions, text=t('ui_result_actions'))
        menu = tk.Menu(more, tearoff=0)
        menu.add_command(label=t('ui_keep_result'), command=comparison.keep)
        menu.add_command(label=t('ui_result_history'), command=comparison.show_history)
        menu.add_command(label=t('ui_export_result'), command=export)
        more.configure(menu=menu)
        buttons = (copy_button, comparison.button, more)
    else:
        keep_button = ttk.Button(actions, text=t('ui_keep_result'), command=comparison.keep)
        history_button = ttk.Button(actions, text=t('ui_result_history'), command=comparison.show_history)
        export_button = ttk.Button(actions, text=t('ui_export_result'), command=export)
        buttons = (copy_button, keep_button, comparison.button, history_button, export_button)
    columns = 0

    def layout_actions(count):
        nonlocal columns
        if columns == count:
            return
        columns = count
        for column in range(3):
            actions.columnconfigure(column, weight=int(column < columns))
        for index, button in enumerate(buttons):
            row, column = divmod(index, columns)
            button.grid(row=row, column=column, sticky='ew', padx=2, pady=(4, 0) if row else 0)

    layout_actions(1 if responsive else 3)
    if responsive:
        def fit_actions(event):
            width = max(button.winfo_reqwidth() + 4 for button in buttons)
            layout_actions(min(3, max(1, event.width // width)))

        def fit_labels(event):
            width = max(140, event.width - 6)
            summary.configure(wraplength=width)
            box.status_label.configure(wraplength=width)

        actions.bind('<Configure>', fit_actions)
        toolbar.bind('<Configure>', fit_labels)
    box.comparison = comparison
    if card:
        scrollbar = getattr(box, 'oficina_scrollbar', None)

        def show_details(visible):
            box.oficina_details = visible
            details.configure(text=t('ui_result_hide_details' if visible else 'ui_result_show_details'))
            if visible:
                if scrollbar is not None:
                    scrollbar.pack(side='right', fill='y')
                box.pack(fill='both', expand=True, pady=(0, 4))
            else:
                box.pack_forget()
                if scrollbar is not None:
                    scrollbar.pack_forget()

        details = ttk.Button(toolbar, command=lambda: show_details(not box.oficina_details))
        details.pack(fill='x', pady=(0, 4))
        box.show_oficina_details = show_details
        show_details(False)
    else:
        ttk.Label(toolbar, text=t('ui_breakdown')).pack(side='left')

    def present(text):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        separator = '\n' if card else '  |  '
        highlights = [line for line in getattr(box, 'oficina_highlights', ()) if line in lines] if card else []
        summary.configure(text=separator.join((highlights or lines)[:2]) if lines else t('ui_result_empty'))
        if card:
            details.configure(state='normal' if lines else 'disabled')
            copy_button.configure(state='normal' if lines else 'disabled')

    box.present_result = present
    present(box.get('1.0', 'end-1c'))
    box.configure(wrap='word', spacing1=3, spacing3=3)
    box.tag_configure('heading', font=('Arial', 11, 'bold'))
    def changed(*_):
        if not box.edit_modified():
            return
        text = box.get('1.0', 'end-1c')
        present(text)
        box.tag_remove('heading', '1.0', 'end')
        box.tag_add('heading', '1.0', '1.end')
        if hasattr(box, 'form_state'):
            box.form_state.result_changed(box)
        box.edit_modified(False)
        layout = getattr(box, 'oficina_layout', None)
        if layout is not None and not layout.wide and text.strip() and toolbar.winfo_ismapped():
            layout.after_idle(lambda: layout.reveal(toolbar, align_top=True))
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
