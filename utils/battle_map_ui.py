"""Encounter map controls. Only the master can change the saved map."""

from dataclasses import replace
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from zlib import crc32

from utils.battle_map_assets import BattleMapAssetError, BattleMapAssetStore
from utils.i18n import t
from utils.ranged_layout import FieldGrid, flow_buttons, wrap_label
from utils.units import UnitSystem


_GROUP_COLORS = ('#4982e7', '#cf6775', '#599d76', '#c28c49', '#9d75db', '#499ea6')


def _number(variable):
    text = variable.get().strip()
    if len(text) > 40:
        raise ValueError('map_bad_input')
    try:
        return float(text.replace(',', '.'))
    except ValueError as exc:
        raise ValueError('map_bad_input') from exc


class GridSettingsDialog(tk.Toplevel):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.session = panel.app.combat_session
        self.base = self.session.battle_map
        self.title(t('map_grid_settings').rstrip('…'))
        self.transient(panel.winfo_toplevel())
        self.geometry('480x440')
        self.minsize(380, 360)
        self.bind('<Escape>', lambda _event: self.destroy())
        body = ttk.Frame(self, padding=12)
        body.pack(fill='both', expand=True)

        self.kinds = {t('map_grid_' + key): key for key in ('hex', 'hex_flat', 'square')}
        self.kind = tk.StringVar(self, value=next(label for label, key in self.kinds.items() if key == self.base.grid))
        wrap_label(ttk.Label(body, text=t('map_grid_kind'))).pack(fill='x')
        ttk.Combobox(body, textvariable=self.kind, state='readonly', values=tuple(self.kinds), width=1).pack(
            fill='x', pady=(3, 8))
        fields = FieldGrid(body, columns=2)
        fields.pack(fill='x')
        self.values = {}
        for name in ('cell_size', 'origin_x', 'origin_y', 'yards_per_cell'):
            cell = ttk.Frame(fields)
            wrap_label(ttk.Label(cell, text=t('map_' + name))).pack(fill='x')
            variable = tk.StringVar(self, value=f'{getattr(self.base, name):g}')
            self.values[name] = variable
            ttk.Entry(cell, textvariable=variable, width=1).pack(fill='x', pady=(2, 5))
            fields.add(cell)
        self.show_grid = tk.BooleanVar(self, value=self.base.show_grid)
        ttk.Checkbutton(body, text=t('map_show_grid'), variable=self.show_grid).pack(anchor='w', pady=(6, 0))
        self.error = wrap_label(ttk.Label(body, style='Error.TLabel', wraplength=345))
        self.error.pack(fill='x', pady=4)
        actions = ttk.Frame(body)
        actions.pack(side='bottom', fill='x')
        flow_buttons(actions, [ttk.Button(actions, text=t('map_apply_grid'), command=self.apply,
                                          style='Primary.TButton'),
                               ttk.Button(actions, text=t('ui_cancel'), command=self.destroy)])
        self.grab_set()

    def apply(self):
        if self.panel.app.combat_session is not self.session or self.session.battle_map != self.base:
            self.error.configure(text=t('map_settings_stale'))
            return False
        try:
            settings = {key: _number(variable) for key, variable in self.values.items()}
            candidate = replace(self.base, grid=self.kinds[self.kind.get()], show_grid=self.show_grid.get(),
                                **settings)
            self.panel.commit(candidate)
        except (OSError, ValueError, KeyError) as exc:
            self.error.configure(text=self.panel.error_text(exc))
            return False
        self.destroy()
        return True


class BattleMapPanel(ttk.Frame):
    """A lightweight map workbench bound to the active encounter."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=(8, 6))
        from utils.battle_map_view import MapCanvas

        self.app = app
        self.asset_store = getattr(app, '_battle_map_assets', None)
        if self.asset_store is None:
            self.asset_store = app._battle_map_assets = BattleMapAssetStore(app.ui_preferences_path.parent)
        self._fit_next = True
        self._placing_id = None
        self._session = None
        self._last_image = None
        self._selected_id = getattr(app, '_battle_map_selected_id', None)
        self._grid_dialog = None
        self._roster_keys = {}
        self._labels = {}
        self._colors = {}
        self._scene = None
        self.show_grid = tk.BooleanVar(self)
        self.visible_to_players = tk.BooleanVar(self)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x')
        options = ttk.Menubutton(toolbar, text=t('tab_battle_map'))
        self.map_menu = tk.Menu(options, tearoff=False)
        options.configure(menu=self.map_menu)
        self.map_menu.add_command(label=t('map_import_png'), command=lambda: self._guard(self.choose_background))
        self.map_menu.add_command(label=t('map_clear_background'), command=lambda: self._guard(self.clear_background))
        self._clear_entry = self.map_menu.index('end')
        self.map_menu.add_command(label=t('map_grid_settings'), command=self.open_grid_settings)
        self.map_menu.add_checkbutton(label=t('map_show_grid'), variable=self.show_grid,
                                      command=lambda: self._guard(self._toggle_grid))
        self.map_menu.add_separator()
        self.map_menu.add_command(label=t('session_undo'), command=self.app._undo_session)
        self.map_menu.add_command(label=t('ui_help'), command=lambda: messagebox.showinfo(
            t('map_title'), t('map_help'), parent=self.winfo_toplevel()))
        self.player_button = ttk.Button(toolbar, text=t('map_players'), command=self.open_player_view)
        flow_buttons(toolbar, [
            options,
            ttk.Button(toolbar, text='−', command=lambda: self.canvas.zoom_out()),
            ttk.Button(toolbar, text='+', command=lambda: self.canvas.zoom_in()),
            ttk.Button(toolbar, text=t('map_fit'), command=lambda: self.canvas.fit()),
            self.player_button,
        ])

        picker = ttk.Frame(self)
        picker.pack(fill='x', pady=(3, 5))
        picker.columnconfigure(0, weight=1)
        self.roster_selection = tk.StringVar(self)
        self.roster = ttk.Combobox(picker, textvariable=self.roster_selection, state='readonly', width=1)
        self.roster.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.roster.bind('<<ComboboxSelected>>', self._pick_roster)
        self.place_button = ttk.Button(picker, text=t('map_place'), command=lambda: self._guard(self.arm_placement))
        self.place_button.grid(row=0, column=1, padx=(0, 5))
        token_options = ttk.Menubutton(picker, text=t('map_token_actions'))
        token_options.grid(row=0, column=2)
        self.token_menu = tk.Menu(token_options, tearoff=False)
        token_options.configure(menu=self.token_menu)
        self.token_menu.add_command(label=t('encounter_use_actor'), command=lambda: self._guard(
            lambda: self.set_role('actor')))
        self.token_menu.add_command(label=t('encounter_use_target'), command=lambda: self._guard(
            lambda: self.set_role('target')))
        self.token_menu.add_checkbutton(label=t('map_player_visibility'), variable=self.visible_to_players,
                                        command=lambda: self._guard(self._toggle_visibility))
        self._visibility_entry = self.token_menu.index('end')
        self.token_menu.add_command(label=t('map_remove_token'), command=lambda: self._guard(self.remove_token))
        self._remove_entry = self.token_menu.index('end')

        footer = ttk.Frame(self)
        footer.pack(side='bottom', fill='x', pady=(4, 0))
        footer.columnconfigure(0, weight=1)
        self.distance_label = wrap_label(ttk.Label(footer, width=1, wraplength=230))
        self.distance_label.grid(row=0, column=0, sticky='ew')
        self.send_button = ttk.Button(footer, text=t('map_send_distance'), command=lambda: self._guard(self.send_distance),
                                      style='Primary.TButton')
        self.send_button.grid(row=0, column=1, padx=(5, 0))
        self.status = wrap_label(ttk.Label(self, width=1, wraplength=230, style='Warning.TLabel'))
        self.canvas = MapCanvas(self, asset_store=self.asset_store, on_select=self._canvas_select,
                                on_move=self._canvas_move, on_click=self._canvas_click,
                                background=app.colors['panel'], highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Escape>', self.cancel_placement, add='+')
        self.refresh_from_session()

    @property
    def state(self):
        return self.app.combat_session.battle_map

    @staticmethod
    def error_text(exc):
        if isinstance(exc, BattleMapAssetError):
            key = exc.code
        elif isinstance(exc, OSError):
            return t('local_data_save_error', error=exc)
        else:
            key = str(exc)
        return t(key) if t(key) != key else t('map_bad_input')

    def _message(self, text=''):
        self.status.configure(text=text)
        if text:
            if not self.status.winfo_manager():
                self.status.pack(side='bottom', fill='x', pady=(2, 0), before=self.canvas)
        else:
            self.status.pack_forget()

    def _guard(self, operation):
        try:
            return operation()
        except (BattleMapAssetError, OSError, ValueError, KeyError) as exc:
            self.refresh_from_session()
            self._message(self.error_text(exc))

    def commit(self, candidate, *, fit=False):
        self.app.combat_session.set_battle_map(candidate)
        self._fit_next = self._fit_next or fit
        self.app._battle_map_changed()

    def choose_background(self):
        filename = filedialog.askopenfilename(parent=self.winfo_toplevel(), title=t('map_import_png'),
                                              filetypes=[('PNG', '*.png')])
        if filename:
            return self.import_background(filename)

    def import_background(self, path):
        identifier = self.asset_store.import_png(path)
        self.commit(replace(self.state, image_id=identifier), fit=True)
        return identifier

    def clear_background(self):
        # Keep the PNG in local assets: Undo and named scenarios may reference it.
        self.commit(replace(self.state, image_id=None), fit=True)

    def open_grid_settings(self):
        if self._grid_dialog is not None and self._grid_dialog.winfo_exists():
            self._grid_dialog.lift()
        else:
            self._grid_dialog = GridSettingsDialog(self)
        return self._grid_dialog

    def _toggle_grid(self):
        self.commit(replace(self.state, show_grid=self.show_grid.get()))

    def _pick_roster(self, _event=None):
        self.cancel_placement()
        self.select_token(self._roster_keys.get(self.roster_selection.get()))

    def select_token(self, identifier):
        if identifier not in self.app.combat_session.combatants:
            return
        self._selected_id = self.app._battle_map_selected_id = identifier
        self.roster_selection.set(self._labels[identifier])
        self.canvas.render(self._scene, selected_id=identifier)
        self._refresh_controls()

    def _canvas_select(self, identifier):
        self.cancel_placement()
        self.select_token(identifier)

    def _selected(self):
        if self._selected_id not in self.app.combat_session.combatants:
            raise ValueError('encounter_select_one')
        return self._selected_id

    def arm_placement(self):
        identifier = self._selected()
        self._placing_id = identifier
        self._message(t('map_place_click', name=self.app.combat_session.combatants[identifier].name))
        self.canvas.focus_set()

    def cancel_placement(self, event=None):
        if self._placing_id is not None:
            self._placing_id = None
            self._message()
            return 'break' if event is not None else None

    def _canvas_click(self, x, y):
        identifier = self._placing_id
        if identifier is not None:
            self.cancel_placement()
            self._guard(lambda: self.place_token(identifier, x, y))

    def place_token(self, identifier, x, y):
        if identifier not in self.app.combat_session.combatants:
            raise ValueError('encounter_select_one')
        q, r = self.state.cell_at(x, y)
        self._selected_id = self.app._battle_map_selected_id = identifier
        self.commit(self.state.with_token(identifier, q, r))

    def _canvas_move(self, identifier, x, y):
        self.cancel_placement()
        # Do not recreate a token removed from the encounter during a drag.
        if identifier in self.state.tokens:
            self._guard(lambda: self.place_token(identifier, x, y))

    def _toggle_visibility(self):
        identifier = self._selected()
        if identifier in self.state.tokens:
            self.commit(self.state.with_token_visibility(identifier, self.visible_to_players.get()))

    def remove_token(self):
        identifier = self._selected()
        if identifier in self.state.tokens:
            self.cancel_placement()
            self.commit(self.state.without_token(identifier))

    def set_role(self, role):
        self.app._select_encounter_role(role, self._selected())

    def pair_distance(self):
        actor_id, target_id = self.app.session_actor_key, self.app.session_target_key
        actor, target = self.state.tokens.get(actor_id), self.state.tokens.get(target_id)
        if actor is None or target is None or actor_id == target_id:
            return None
        return self.state.distance_yards(actor.q, actor.r, target.q, target.r)

    def send_distance(self):
        distance = self.pair_distance()
        if distance is not None:
            self.app._send_map_distance_to_ranged(self.app.session_actor_key, self.app.session_target_key, distance)

    def _refresh_controls(self):
        token = self.state.tokens.get(self._selected_id)
        self.show_grid.set(self.state.show_grid)
        self.visible_to_players.set(bool(token and token.visible))
        self.map_menu.entryconfigure(self._clear_entry, state='normal' if self.state.image_id else 'disabled')
        for index in (self._visibility_entry, self._remove_entry):
            self.token_menu.entryconfigure(index, state='normal' if token else 'disabled')
        distance = self.pair_distance()
        units = UnitSystem(self.app.result_units.get())
        self.distance_label.configure(text=t('map_need_pair') if distance is None else
                                      t('map_pair_distance', distance=units.display(distance, 'yards')))
        self.send_button.configure(state='disabled' if distance is None else 'normal')

    def refresh_from_session(self):
        from utils.battle_map_view import MapScene

        session = self.app.combat_session
        state = session.battle_map
        if self._session is not session:
            self._session = session
            self.cancel_placement()
            self._fit_next = True
        if self._last_image != state.image_id:
            self._last_image = state.image_id
            self._fit_next = True
        self._labels = {key: f'{index}. {session.combatants[key].name}'
                        for index, key in enumerate(session.combatant_order, 1)}
        self._colors = {}
        for key, participant in session.combatants.items():
            group = participant.group or participant.team
            if group:
                self._colors[key] = _GROUP_COLORS[crc32(group.casefold().encode('utf-8')) % len(_GROUP_COLORS)]
            else:
                self._colors[key] = self.app.colors['accent']
        self._roster_keys = {label: key for key, label in self._labels.items()}
        self.roster['values'] = tuple(self._roster_keys)
        if self._selected_id not in self._labels:
            self._selected_id = self.app.session_actor_key
        self.app._battle_map_selected_id = self._selected_id
        self.roster_selection.set(self._labels.get(self._selected_id, ''))
        if self._placing_id not in self._labels:
            self.cancel_placement()
        fit = self._fit_next
        self._fit_next = False
        self._scene = MapScene.from_map(state, self._labels, self._colors)
        self.canvas.render(self._scene, selected_id=self._selected_id, fit=fit)
        self.canvas.set_ruler_ids(self.app.session_actor_key, self.app.session_target_key)
        self._refresh_controls()
        if self.canvas.background_unavailable and self._placing_id is None:
            self._message(t('map_background_missing'))
        elif self._placing_id is None:
            self._message()
        self._refresh_player(fit=fit)

    def _refresh_player(self, *, fit=False):
        from utils.battle_map_view import MapScene

        player = getattr(self.app, '_battle_map_player', None)
        if player is not None and player.winfo_exists():
            player.title(t('map_players'))
            player.canvas.configure(background=self.app.colors['panel'])
            # Rebuild the public projection from the current session, not from
            # an earlier player window or any token data kept by the renderer.
            # Avoid the master's roster numbers: gaps could disclose hidden entries.
            labels = {key: self.app.combat_session.combatants[key].name for key in self.state.public_tokens()}
            scene = MapScene.from_map(self.state, labels, self._colors, player=True)
            player.render(scene, fit=fit)

    def open_player_view(self):
        from utils.battle_map_view import PlayerMapWindow

        player = getattr(self.app, '_battle_map_player', None)
        opened = player is None or not player.winfo_exists()
        if opened:
            player = self.app._battle_map_player = PlayerMapWindow(
                self.app.root, asset_store=self.asset_store, title=t('map_players'),
                background=self.app.colors['panel'], highlightthickness=0)
        else:
            player.lift()
        self._refresh_player(fit=opened)
        return player
