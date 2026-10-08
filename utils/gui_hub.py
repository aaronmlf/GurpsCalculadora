"""Home, appearance and session access for the existing offline application."""
import tkinter as tk
from tkinter import ttk, messagebox, font
from utils.i18n import t
from utils.ui_preferences import save_ui_preferences
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
    for key, after in preview.combatants.items():
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
    style.configure('Subtitle.TLabel', font=('Arial', size))
    style.configure('Workspace.Treeview', rowheight=size * 2 + 6, font=('Arial', size))
    def visit(parent):
        for child in parent.winfo_children():
            if isinstance(child, tk.Text):
                child.configure(font=('Consolas', size))
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
    ttk.Label(form, text=t('ui_theme')).grid(row=0, column=0, sticky='w')
    for row, key in enumerate(('dark', 'light'), 1):
        ttk.Radiobutton(form, text=t('ui_theme_' + key), variable=theme, value=key).grid(row=row, column=0, sticky='w')
    ttk.Label(form, text=t('ui_font_size')).grid(row=3, column=0, sticky='w', pady=8)
    ttk.Combobox(form, textvariable=size, values=list(range(9, 19)), state='readonly', width=8).grid(row=3, column=1)
    def commit():
        app.ui_preferences.update(theme=theme.get(), font_size=size.get())
        save_ui(app)
        window.destroy()
        app._setup_theme()
        app._rebuild_ui()
    ttk.Button(form, text=t('ui_settings_apply'), command=commit).grid(row=4, column=0, columnspan=2, pady=8)


def session_window(app):
    window = tk.Toplevel(app.root)
    window.title(t('session_title'))
    window.geometry('760x500')
    summary = ttk.Label(window, wraplength=720)
    summary.pack(fill='x', padx=12, pady=12)
    history = tk.Text(window, wrap='word', height=12)
    history.pack(fill='both', expand=True, padx=12)
    def refresh():
        lines = []
        for state in app.combat_session.combatants.values():
            lines.append(f'{state.name}: HP {state.current_hp} / {state.max_hp}; FP {state.current_fp} / {state.max_fp}')
            lines.append(t('ui_conditions') + ': ' + (', '.join(state.conditions) or '—'))
        summary.configure(text='\n'.join(lines))
        history.configure(state='normal')
        history.delete('1.0', 'end')
        for event in app.combat_session.events[-100:]:
            history.insert('end', f'{event.applied_at}  {event.label}\n')
        history.configure(state='disabled')
    def undo():
        app._undo_session()
        refresh()
    buttons = ttk.Frame(window, padding=12)
    buttons.pack(fill='x')
    ttk.Button(buttons, text=t('session_undo'), command=undo).pack(side='left')
    ttk.Button(buttons, text=t('ui_refresh'), command=refresh).pack(side='left', padx=8)
    refresh()


def install_hub(app):
    tree = app.navigation_tree
    sidebar = tree.master
    tree.insert('', 0, iid='home', text=t('ui_home'))
    home = ttk.Frame(app.main_frame, padding=20)
    app.home_frame = home
    selected = getattr(app, '_current_tool', app.ui_preferences['last_tool'])

    def render_home():
        for child in home.winfo_children():
            child.destroy()
        ttk.Label(home, text=t('ui_home_title'), style='Title.TLabel').pack(anchor='w', pady=10)
        ttk.Label(home, text=t('ui_home_help'), wraplength=600).pack(anchor='w', pady=10)
        for key in ('favorites', 'recent'):
            section = ttk.LabelFrame(home, text=t('ui_' + key), padding=8)
            section.pack(fill='x', pady=8)
            items = app.ui_preferences[key][:3]
            if not items:
                ttk.Label(section, text=t('ui_empty_tools')).pack(anchor='w')
            for index in items:
                ttk.Button(section, text=app.notebook.tab(index, 'text'),
                           command=lambda index=index: choose(index)).pack(fill='x', pady=2)
        ttk.Button(home, text=t('session_title'), command=lambda: session_window(app)).pack(anchor='w', pady=10)

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
            app.notebook.select(index)
            recent = app.ui_preferences['recent']
            app.ui_preferences['recent'] = [index] + [item for item in recent if item != index]
        if tree.selection() != (str(index),):
            tree.selection_set(str(index))
        favorite.configure(text=t('ui_unfavorite' if index in app.ui_preferences['favorites'] else 'ui_favorite'),
                           state='disabled' if index == 'home' else 'normal')
        for tool in range(len(app.notebook.tabs())):
            tree.item(str(tool), text=('★ ' if tool in app.ui_preferences['favorites'] else '') + app.notebook.tab(tool, 'text'))

    def navigate(*_):
        selection = tree.selection()
        if selection and (selection[0] == 'home' or selection[0].isdigit()):
            choose('home' if selection[0] == 'home' else int(selection[0]))

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

    favorite = ttk.Button(sidebar, text=t('ui_favorite'), command=toggle_favorite)
    favorite.pack(fill='x', before=tree, pady=4)
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
    view.add_command(label=t('ui_toggle_sidebar'), command=toggle_sidebar)
    view.add_command(label=t('ui_settings'), command=lambda: settings(app))
    view.add_command(label=t('ui_preset_save'), command=lambda: input_preset(app))
    view.add_command(label=t('ui_preset_load'), command=lambda: input_preset(app, True))
    view.add_command(label=t('session_title'), command=lambda: session_window(app))
    view.add_command(label=t('ui_help'), command=lambda: messagebox.showinfo(t('ui_help'), t('ui_help_text')))
    app.root.bind('<Control-h>', lambda event: choose('home'))
    def close():
        job = getattr(app, '_gm_dice_job', None)
        if job:
            job['cancel'].set()
            job['thread'].join(timeout=.5)
        save_ui(app)
        app.root.destroy()
    app.root.protocol('WM_DELETE_WINDOW', close)
    # File > Exit follows the same persistence path as the window close button.
    app.root.nametowidget(app.menubar.entrycget(0, 'menu')).entryconfigure(0, command=close)
    choose(selected)
    if app.ui_preferences['sidebar_hidden']:
        sidebar.pack_forget()
    apply_fonts(app)
