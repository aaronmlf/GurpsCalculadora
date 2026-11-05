"""Home, appearance and session access for the existing offline application."""
import tkinter as tk
from tkinter import ttk, messagebox, font, colorchooser
from utils.i18n import t
from utils.ui_preferences import BATTLE_MAP_TOOL, save_ui_preferences
from utils.ui_theme import THEME_FIELDS, clean_theme_colors, make_palette
from calculators.combat_session import CombatSession
from utils.gui_presets import input_preset


def remember_session(app, kind):
    if not hasattr(app, '_pending_session_context'):
        app._pending_session_context = {}
    app._pending_session_context[kind] = (app.session_actor_key, app.session_target_key,
                                         app.combat_session.to_dict())


def confirm_session(app, kind, target_delta, actor_delta=None):
    context = (app.session_actor_key, app.session_target_key, app.combat_session.to_dict())
    box = app.injury_result_text if kind == 'injury' else app.melee_result_text
    if getattr(app, '_pending_session_context', {}).get(kind) != context or getattr(box, 'stale', False):
        messagebox.showwarning(t('session_title'), t('ui_session_stale'))
        return False
    preview = CombatSession.from_dict(app.combat_session.to_dict())
    if kind == 'injury':
        preview.apply(app.session_actor_key, app.session_target_key, target_delta, advance_action=False)
    else:
        preview.apply_action(app.session_actor_key, app.session_target_key, target_delta, actor_delta)
    lines = [t('ui_session_preview')]
    for key in dict.fromkeys((app.session_actor_key, app.session_target_key)):
        after = preview.combatants[key]
        before = app.combat_session.combatants[key]
        lines.append(f'\n{after.name}')
        for field, label in (('current_hp', 'HP'), ('current_fp', 'FP'), ('shock', t('ui_shock')),
                             ('personal_seconds', t('ui_personal_time')), ('stunned', t('ui_stunned')),
                             ('unconscious', t('ui_unconscious')), ('dead', t('ui_dead')),
                             ('posture', t('ui_posture'))):
            left, right = getattr(before, field), getattr(after, field)
            if left != right:
                if isinstance(left, bool):
                    left, right = t('common_yes' if left else 'common_no'), t('common_yes' if right else 'common_no')
                lines.append(f'{label}: {left} → {right}')
        for field in ('conditions', 'crippled_locations', 'destroyed_locations'):
            if getattr(before, field) != getattr(after, field):
                lines.append(t('ui_state_' + field) + ': ' + (', '.join(getattr(after, field)) or '—'))
        for field in ('wounds', 'pending_checks', 'grapples'):
            if getattr(before, field) != getattr(after, field):
                lines.append(t('ui_state_' + field) + f': {len(getattr(before, field))} → {len(getattr(after, field))}')
        if before.armor != after.armor:
            lines.append(t('ui_armor_changed'))
    return messagebox.askyesno(t('session_title'), '\n'.join(lines))


def save_ui(app):
    app.ui_preferences['window'] = f'{app.root.winfo_width()}x{app.root.winfo_height()}'
    try:
        save_ui_preferences(app.ui_preferences_path, app.ui_preferences)
    except OSError as exc:
        messagebox.showwarning(t('common_error_title'), t('preferences_save_error', error=str(exc)))


def apply_fonts(app):
    size = app.ui_preferences['font_size']
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont'):
        font.nametofont(name, root=app.root).configure(size=size)
    style = ttk.Style(app.root)
    style.configure('Title.TLabel', font=('Arial', size + 4, 'bold'))
    style.configure('PageTitle.TLabel', font=('Arial', size + 12, 'bold'))
    style.configure('ResultSummary.TLabel', font=('Arial', size + 2, 'bold'))
    style.configure('Result.TLabelframe.Label', font=('Arial', size + 1, 'bold'))
    style.configure('Subtitle.TLabel', font=('Arial', size))
    style.configure('Metric.TLabel', font=('Arial', size + 10, 'bold'))
    style.configure('Brand.TLabel', font=('Arial', size + 1, 'bold'))
    style.configure('Workspace.Treeview', rowheight=size * 2 + 6, font=('Arial', size))
    def visit(parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Text):
                child.configure(font=('Consolas', size), background=app.colors['panel'],
                                foreground=app.colors['panel_fg'], insertbackground=app.colors['panel_fg'],
                                selectbackground=app.colors['accent'], selectforeground=app.colors['accent_fg'],
                                borderwidth=0, highlightthickness=1, highlightbackground=app.colors['border'],
                                highlightcolor=app.colors['accent_text'])
            visit(child)
    visit(app.main_frame)


def settings(app):
    window = tk.Toplevel(app.root)
    window.title(t('ui_settings'))
    window.transient(app.root)
    form = ttk.Frame(window, padding=18)
    form.pack(fill='both', expand=True)
    theme = tk.StringVar(window, value=app.ui_preferences['theme'])
    size = tk.IntVar(window, value=app.ui_preferences['font_size'])
    overrides = clean_theme_colors(app.ui_preferences.get('theme_colors'))
    form.columnconfigure(1, weight=1)
    ttk.Label(form, text=t('ui_theme')).grid(row=0, column=0, sticky='w', padx=(0, 12))
    modes = ttk.Frame(form)
    modes.grid(row=0, column=1, sticky='w')
    ttk.Label(form, text=t('ui_font_size')).grid(row=1, column=0, sticky='w', pady=8)
    ttk.Combobox(form, textvariable=size, values=tuple(range(9, 19)), state='readonly', width=6).grid(
        row=1, column=1, sticky='w')

    palette_form = ttk.LabelFrame(form, text=t('ui_theme_colors'), padding=10)
    palette_form.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(4, 10))
    palette_form.columnconfigure(0, weight=1)
    swatches = {}
    preview_frame = ttk.LabelFrame(form, text=t('ui_theme_preview'), padding=6)
    preview_frame.grid(row=3, column=0, columnspan=2, sticky='ew')
    preview = tk.Frame(preview_frame, padx=10, pady=8)
    preview.pack(fill='x')
    sample = tk.Label(preview, text=t('ui_theme_preview_text'), padx=12, pady=8)
    sample.pack(side='left', fill='x', expand=True)
    sample_action = tk.Label(preview, text=t('common_calculate'), padx=12, pady=8)
    sample_action.pack(side='right', padx=(8, 0))

    def refresh():
        palette = make_palette(theme.get(), overrides)
        for key, swatch in swatches.items():
            foreground = palette[{'bg': 'fg', 'panel': 'panel_fg', 'accent': 'accent_fg'}[key]]
            swatch.configure(text=palette[key], background=palette[key], foreground=foreground)
        preview.configure(background=palette['bg'])
        sample.configure(background=palette['panel'], foreground=palette['panel_fg'])
        sample_action.configure(background=palette['accent'], foreground=palette['accent_fg'])

    def choose_color(key):
        previous = make_palette(theme.get(), overrides)[key]
        _, value = colorchooser.askcolor(color=previous, title=t('ui_color_' + key), parent=window)
        if value:
            overrides.setdefault(theme.get(), {})[key] = value
            refresh()

    def restore_colors():
        overrides.pop(theme.get(), None)
        refresh()

    for key in ('dark', 'light'):
        ttk.Radiobutton(modes, text=t('ui_theme_' + key), variable=theme, value=key,
                        command=refresh).pack(side='left', padx=(0, 8))
    for row, key in enumerate(THEME_FIELDS):
        ttk.Label(palette_form, text=t('ui_color_' + key)).grid(row=row, column=0, sticky='w', pady=3)
        swatch = tk.Label(palette_form, width=9, padx=4, pady=4)
        swatch.grid(row=row, column=1, padx=6)
        swatches[key] = swatch
        ttk.Button(palette_form, text=t('ui_color_pick'), command=lambda key=key: choose_color(key)).grid(
            row=row, column=2, sticky='ew', pady=3)
    ttk.Button(palette_form, text=t('ui_color_restore'), command=restore_colors).grid(
        row=len(THEME_FIELDS), column=0, columnspan=3, sticky='w', pady=(8, 0))

    def commit():
        app.ui_preferences.update(theme=theme.get(), font_size=size.get(),
                                  theme_colors=clean_theme_colors(overrides))
        save_ui(app)
        window.destroy()
        app._setup_theme()
        app._rebuild_ui()

    actions = ttk.Frame(form)
    actions.grid(row=4, column=0, columnspan=2, sticky='e', pady=(10, 0))
    ttk.Button(actions, text=t('ui_cancel'), command=window.destroy).pack(side='left', padx=(0, 8))
    ttk.Button(actions, text=t('ui_settings_apply'), command=commit, style='Primary.TButton').pack(side='left')
    window.bind('<Escape>', lambda _event: window.destroy())
    refresh()
    return window


def session_window(app):
    from utils.combat_prep_ui import CombatPrepWindow
    window = getattr(app, "_combat_prep_window", None)
    if window is None or not window.winfo_exists():
        window = app._combat_prep_window = CombatPrepWindow(app)
    else:
        window.lift()
    return window


def install_hub(app):
    from utils.gui_workspace import (ToolChooser, select_workspace_tool, short_tool_title,
                                     workspace_tool_label)

    tree = app.navigation_tree
    sidebar = tree.master
    tree.insert('', 0, iid='home', text=f"⌂  {t('ui_home')}", tags=('domain',))
    home = ttk.Frame(app.main_frame)
    app.home_frame = home
    selected = getattr(app, '_current_tool', app.ui_preferences['last_tool'])

    def open_tool_chooser(event=None):
        chooser = getattr(app, '_tool_chooser', None)
        if chooser is None or not chooser.winfo_exists():
            chooser = app._tool_chooser = ToolChooser(app)
        else:
            chooser.lift()
            chooser.entry.focus_set()
        return 'break' if event is not None else chooser

    app.open_tool_chooser = open_tool_chooser

    colors = app.colors
    style = ttk.Style(app.root)
    surface = colors.get('surface', colors['panel'])
    panel_fg = colors.get('panel_fg', colors['fg'])
    size = app.ui_preferences['font_size']
    style.configure('Oficina.Topbar.TFrame', background=surface)
    style.configure('Oficina.Brand.TLabel', background=surface,
                    foreground=panel_fg, font=('Arial', size + 2, 'bold'))
    style.configure('Oficina.Compact.TButton', padding=(7, 4))
    style.configure('Oficina.Card.TFrame', background=surface)
    style.configure('Oficina.Card.TLabel', background=surface, foreground=panel_fg)
    style.configure('Oficina.CardTitle.TLabel', background=surface, foreground=panel_fg,
                    font=('Arial', size, 'bold'))
    style.configure('Oficina.Section.TLabel', font=('Arial', size, 'bold'))
    style.configure('Oficina.Tile.TButton', background=surface, foreground=panel_fg,
                    anchor='w', padding=(4, 3), borderwidth=0, bordercolor=surface,
                    lightcolor=surface, darkcolor=surface, font=('Arial', size + 1, 'bold'))
    topbar = ttk.Frame(app.main_frame, style='Oficina.Topbar.TFrame', padding=(7, 5))
    app.workspace_topbar = topbar
    topbar.pack(side='top', fill='x', before=sidebar, pady=(0, 8))
    topbar.columnconfigure(0, weight=1)

    primary = ttk.Frame(topbar, style='Oficina.Topbar.TFrame')
    primary.grid(row=0, column=0, sticky='w')
    ttk.Button(primary, text='☰', style='Oficina.Compact.TButton',
               command=lambda: toggle_sidebar()).pack(side='left', padx=(0, 8))
    ttk.Label(primary, text=t('app_title'), style='Oficina.Brand.TLabel').pack(side='left', padx=(0, 10))
    ttk.Button(primary, text=f"{t('ui_tool_search')} · Ctrl+K", style='Oficina.Compact.TButton',
               command=open_tool_chooser).pack(side='left')

    controls = ttk.Frame(topbar, style='Oficina.Topbar.TFrame')
    controls.grid(row=0, column=1, sticky='e')
    ttk.Button(controls, text=t('tab_gm_dice'), style='Oficina.Compact.TButton',
               command=lambda: choose(15)).pack(side='left', padx=(0, 4))
    language = ttk.Menubutton(controls, text=app.i18n.get_language().replace('_', '-').upper())
    language_menu = tk.Menu(language, tearoff=0)
    for key, label in (('pt_BR', 'menu_portuguese'), ('en_US', 'menu_english')):
        language_menu.add_command(label=t(label), command=lambda key=key: app._change_language(key))
    language.configure(menu=language_menu)
    language.pack(side='left', padx=(0, 4))
    units = ttk.Menubutton(controls, text=t('ui_unit_' + app.result_units.get() + '_short'))
    units_menu = tk.Menu(units, tearoff=0)
    for key in ('metric', 'imperial'):
        units_menu.add_radiobutton(label=t('units_' + key), variable=app.result_units,
                                   value=key, command=app._change_units)
    units.configure(menu=units_menu)
    units.pack(side='left', padx=(0, 4))
    ttk.Button(controls, text=t('ui_settings'), style='Oficina.Compact.TButton',
               command=lambda: settings(app)).pack(side='left')

    def fit_header(event):
        wide = event.width >= primary.winfo_reqwidth() + controls.winfo_reqwidth() + 24
        row = 0 if wide else 1
        if controls.grid_info()['row'] != row:
            controls.grid_configure(row=row, column=1 if wide else 0,
                                    columnspan=1 if wide else 2, pady=0 if wide else (4, 0))

    topbar.bind('<Configure>', fit_header)

    canvas = tk.Canvas(home, background=colors['bg'], highlightthickness=0, yscrollincrement=20)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar = ttk.Scrollbar(home, command=canvas.yview)
    dashboard = ttk.Frame(canvas, padding=(16, 12, 16, 18))
    dashboard_window = canvas.create_window((0, 0), window=dashboard, anchor='nw')

    def sync_home_scroll(first, last):
        scrollbar.set(first, last)
        needed = float(first) > 0 or float(last) < 1
        if needed and not scrollbar.winfo_manager():
            scrollbar.pack(side='right', fill='y', before=canvas)
        elif not needed and scrollbar.winfo_manager():
            scrollbar.pack_forget()

    canvas.configure(yscrollcommand=sync_home_scroll)
    dashboard.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda event: canvas.itemconfigure(dashboard_window, width=event.width))

    def scroll_home(event):
        direction = 1 if event.num == 4 else -1 if event.num == 5 else event.delta
        if direction:
            canvas.yview_scroll(-1 if direction > 0 else 1, 'units')
        return 'break'

    def reveal_home_control(event):
        bounds = canvas.bbox(dashboard_window)
        if not bounds or not bounds[3]:
            return
        widget = event.widget
        top = widget.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + widget.winfo_height()
        if top < 0:
            canvas.yview_moveto(canvas.canvasy(top) / bounds[3])
        elif bottom > canvas.winfo_height():
            canvas.yview_moveto(canvas.canvasy(bottom - canvas.winfo_height()) / bounds[3])

    def enable_home_scroll(widget):
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            widget.bind(sequence, scroll_home)
        if isinstance(widget, ttk.Button):
            widget.bind('<FocusIn>', reveal_home_control, add='+')
        for child in widget.winfo_children():
            enable_home_scroll(child)

    def wrapped_label(parent, text='', style_name='TLabel'):
        label = ttk.Label(parent, text=text, style=style_name, wraplength=180, justify='left')
        def fit(event):
            if event.width > 20 and int(label.cget('wraplength') or 0) != event.width:
                label.configure(wraplength=event.width)
        label.bind('<Configure>', fit)
        label.pack(fill='x')
        return label

    def make_card(parent):
        return tk.Frame(parent, background=surface, highlightthickness=1,
                        highlightbackground=colors['border'], padx=11, pady=9)

    def fit_tiles(container, tiles, minimum_width):
        columns = 0
        def layout(event=None):
            nonlocal columns
            count = 2 if event and event.width >= 2 * minimum_width() + 10 else 1
            if count == columns:
                return
            columns = count
            for column in range(2):
                container.columnconfigure(column, weight=int(column < columns),
                                          uniform='cards' if column < columns else '')
            for offset, tile in enumerate(tiles):
                row, column = divmod(offset, columns)
                tile.grid(row=row, column=column, sticky='nsew', pady=(0, 8),
                          padx=(0, 8) if columns == 2 and column == 0 else 0)
        container.bind('<Configure>', layout)
        layout()

    def arrange_chips(frame):
        available = frame.winfo_width()
        row = column = used = 0
        for chip in frame.winfo_children():
            width = chip.winfo_reqwidth() + 5
            if used and used + width > available:
                row, column, used = row + 1, 0, 0
            chip.grid(row=row, column=column, sticky='w', padx=(0, 5), pady=(3, 0))
            column += 1
            used += width

    app.home_shortcuts = {}
    personal_panels = {}
    personal_snapshots = {}
    session_stats = None

    def build_home():
        nonlocal session_stats
        wrapped_label(dashboard, t('ui_home_title'), 'Title.TLabel')
        wrapped_label(dashboard, t('ui_home_intro'), 'Muted.TLabel')
        ttk.Label(dashboard, text=t('ui_home_quick_actions'), style='Oficina.Section.TLabel').pack(
            anchor='w', pady=(15, 6))
        quick = ttk.Frame(dashboard)
        quick.pack(fill='x')
        tiles = []
        for index, glyph, key in ((15, '◇', 'dice'), (8, '◎', 'ranged'),
                                  (6, '×', 'melee'), (7, '+', 'injury')):
            tile = make_card(quick)
            title = f'{glyph}   {short_tool_title(app, index)}   →'
            action = ttk.Button(tile, text=title, style='Oficina.Tile.TButton',
                                command=lambda index=index: choose(index))
            action.pack(fill='x', pady=(0, 5))
            detail = wrapped_label(tile, t(f'ui_home_{key}_desc'), 'Oficina.Card.TLabel')
            for area in (tile, detail):
                area.configure(cursor='hand2')
                area.bind('<Button-1>', lambda _event, index=index: choose(index))
            app.home_shortcuts[index] = action
            tiles.append(tile)
        fit_tiles(quick, tiles, lambda: max(170, max(button.winfo_reqwidth() + 24
                                                    for button in app.home_shortcuts.values())))

        personalized = ttk.Frame(dashboard)
        personalized.pack(fill='x', pady=(3, 0))
        panels = []
        for key, prefix in (('favorites', '★'), ('recent', '↺')):
            panel = make_card(personalized)
            ttk.Label(panel, text=f"{prefix}  {t('ui_' + key)}", style='Oficina.CardTitle.TLabel').pack(anchor='w')
            empty_key = 'ui_home_favorites_empty' if key == 'favorites' else 'ui_empty_tools'
            empty = wrapped_label(panel, t(empty_key), 'Oficina.Card.TLabel')
            chips = ttk.Frame(panel, style='Oficina.Card.TFrame')
            chips.pack(fill='x')
            chips.bind('<Configure>', lambda _event, frame=chips: arrange_chips(frame))
            personal_panels[key] = (chips, empty)
            panels.append(panel)
        fit_tiles(personalized, panels, lambda: max(170, 13 * size))

        session = make_card(dashboard)
        session.pack(fill='x', pady=(3, 8))
        ttk.Label(session, text=t('ui_home_session'), style='Oficina.CardTitle.TLabel').pack(anchor='w')
        session_stats = wrapped_label(session, style_name='Oficina.Card.TLabel')
        ttk.Button(session, text=t('ui_home_open_session'), style='Oficina.Compact.TButton',
                   command=lambda: session_window(app)).pack(anchor='w', pady=(5, 0))
        ttk.Button(session, text=t('tab_battle_map'), style='Oficina.Compact.TButton',
                   command=lambda: choose(BATTLE_MAP_TOOL)).pack(anchor='w', pady=(3, 0))
        ttk.Button(dashboard, text=t('ui_home_all_tools'), style='Oficina.Compact.TButton',
                   command=open_tool_chooser).pack(anchor='w', pady=(2, 0))
        enable_home_scroll(canvas)

    def render_home():
        if session_stats is None:
            build_home()
        for key, (chips, empty) in personal_panels.items():
            items = tuple(app.ui_preferences[key][:3])
            if personal_snapshots.get(key) == items:
                continue
            personal_snapshots[key] = items
            for child in chips.winfo_children():
                child.destroy()
            if items:
                empty.pack_forget()
            else:
                empty.pack(fill='x', before=chips)
            for index in items:
                chip = ttk.Button(chips, text=short_tool_title(app, index), style='Oficina.Compact.TButton',
                                  command=lambda index=index: choose(index))
                enable_home_scroll(chip)
            arrange_chips(chips)
        refresh_home_session()

    def refresh_home_session():
        if session_stats is None:
            return
        session = app.combat_session
        keys = list(session.selected_pair(app.session_actor_key, app.session_target_key))
        lines = [f'{state.name}  ·  HP {state.current_hp}/{state.max_hp}  ·  FP {state.current_fp}/{state.max_fp}'
                 for state in (session.combatants[key] for key in keys)]
        if len(session.combatants) > len(keys):
            lines.append(t('encounter_home_more', count=len(session.combatants) - len(keys)))
        session_stats.configure(text='\n'.join(lines))

    app.refresh_home_session = refresh_home_session

    def choose(index):
        app._current_tool = index
        app.ui_preferences['last_tool'] = index
        if index == 'home':
            app.notebook.pack_forget()
            render_home()
            home.pack(fill='both', expand=True)
        else:
            home.pack_forget()
            app.notebook.pack(fill='both', expand=True)
            if index == BATTLE_MAP_TOOL:
                app._ensure_battle_map_panel()
            app.notebook.select(index)
            recent = app.ui_preferences['recent']
            app.ui_preferences['recent'] = [index] + [item for item in recent if item != index]
        select_workspace_tool(tree, index)
        label = t('ui_unfavorite' if index in app.ui_preferences['favorites'] else 'ui_favorite')
        state = 'disabled' if index == 'home' else 'normal'
        favorite.configure(text='★' if index in app.ui_preferences['favorites'] else '☆', state=state)
        view.entryconfigure(favorite_entry, label=label, state=state)
        for tool in range(len(app.notebook.tabs())):
            tree.item(str(tool), text=workspace_tool_label(app, tool))

    def navigate(*_):
        selection = tree.selection()
        if selection and (selection[0] == 'home' or selection[0].isdigit()):
            index = 'home' if selection[0] == 'home' else int(selection[0])
            if index != app._current_tool:
                choose(index)

    def toggle_favorite():
        index = app._current_tool
        if index == 'home':
            return
        favorites = app.ui_preferences['favorites']
        if index in favorites:
            favorites.remove(index)
        else:
            favorites.append(index)
        save_ui(app)
        choose(index)

    favorite = ttk.Button(app.workspace_sidebar_header, text='☆', style='Oficina.Compact.TButton',
                          command=toggle_favorite)
    favorite.pack(side='right')
    tree.bind('<<TreeviewSelect>>', navigate)
    app.choose_tool = choose
    app.toggle_tool_favorite = toggle_favorite
    def toggle_sidebar():
        if sidebar.winfo_manager():
            sidebar.pack_forget()
            app.ui_preferences['sidebar_hidden'] = True
        else:
            content = home if app._current_tool == 'home' else app.notebook
            sidebar.pack(side='left', fill='y', before=content, padx=(0, 10))
            app.ui_preferences['sidebar_hidden'] = False
        save_ui(app)
    view = tk.Menu(app.menubar, tearoff=0)
    app.menubar.add_cascade(label=t('ui_view'), menu=view)
    view.add_command(label=t('ui_home'), command=lambda: choose('home'), accelerator='Ctrl+H')
    view.add_command(label=t('ui_tool_search'), command=open_tool_chooser, accelerator='Ctrl+K')
    view.add_command(label=t('tab_gm_dice'), command=lambda: choose(15))
    view.add_command(label=t('tab_battle_map'), command=lambda: choose(BATTLE_MAP_TOOL))
    view.add_command(label=t('ui_favorite'), command=toggle_favorite)
    favorite_entry = view.index('end')
    view.add_command(label=t('ui_toggle_sidebar'), command=toggle_sidebar)
    view.add_command(label=t('ui_settings'), command=lambda: settings(app))
    view.add_command(label=t('ui_preset_save'), command=lambda: input_preset(app))
    view.add_command(label=t('ui_preset_load'), command=lambda: input_preset(app, True))
    view.add_command(label=t('combat_prep_title'), command=lambda: session_window(app))
    view.add_command(label=t('ui_help'), command=lambda: messagebox.showinfo(t('ui_help'), t('ui_help_text')))
    def close():
        job = getattr(app, '_gm_dice_job', None)
        if job:
            job['cancel'].set()
            job['thread'].join(timeout=.5)
        save_ui(app)
        app.root.destroy()

    if not getattr(app, '_workspace_root_installed', False):
        # Bind once; call the current UI's actions after any language/theme rebuild.
        def show_home(_event):
            app.choose_tool('home')
            return 'break'

        app.root.bind('<Control-k>', lambda event: app.open_tool_chooser(event))
        app.root.bind('<Control-h>', show_home)
        app.root.protocol('WM_DELETE_WINDOW', close)
        app._workspace_root_installed = True
    # File > Exit follows the same persistence path as the window close button.
    app.root.nametowidget(app.menubar.entrycget(0, 'menu')).entryconfigure(0, command=close)
    choose(selected)
    if app.ui_preferences['sidebar_hidden']:
        sidebar.pack_forget()
    apply_fonts(app)
