"""Read-only rules previews in the desktop workbench; no session writes."""

import math
import tkinter as tk
from tkinter import ttk

from utils.i18n import t
from utils.quick_tables import ILLUMINATION_PRESETS, calculate_illumination, calculate_speed_range
from utils.ranged_layout import Disclosure, FieldGrid, RangedWorkbench, checkbutton, flow_buttons, wrap_label
from utils.unit_binding import UnitBinding
from utils.units import UnitSystem


_AMBIENT = {entry.key: entry for entry in ILLUMINATION_PRESETS if entry.kind == 'ambient'}
_POINT = {entry.key: entry for entry in ILLUMINATION_PRESETS if entry.kind == 'point'}
_DEFAULTS = {'ambient': 'daylight', 'point': '', 'point_distance': '1', 'heavy_cloud': False,
             'polar_moonlight': False, 'flicker': '0', 'dimming': '0', 'adaptation': '0',
             'range_mode': 'attack', 'range_distance': '7', 'range_speed': '', 'consider_speed': False}


def _number(text, *, blank=None):
    text = text.strip().replace(',', '.')
    if not text and blank is not None:
        return blank
    try:
        if len(text) > 64:
            raise ValueError
        number = float(text)
        if not math.isfinite(number) or number < 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError('quick_tables_invalid_number') from exc
    return number


def _display_error(error):
    return t(str(error)) if str(error) else t('quick_tables_invalid_option')


class QuickTablesPanel(RangedWorkbench):
    """Combat previews and a lazily opened library of read-only rule cards."""

    def __init__(self, parent, app, *, map_distance=None, send_to_ranged=None, send_lighting=None, state=None):
        state = state or {}
        self.WIDE = max(780, 49 * app.ui_preferences['font_size'])
        super().__init__(parent, app.colors['bg'])
        self.frame = self  # The workbench itself lives inside its packed canvas.
        self.units = UnitSystem(app.result_units.get())
        self._map_distance = map_distance
        self._send_to_ranged = send_to_ranged
        self._send_lighting = send_lighting
        self._app = app
        self._reference_state = state.get('reference')
        self.reference = None
        self.page = tk.StringVar(self, value='combat')
        self._map_snapshot = state.get('map_snapshot')
        self._copying_map = False
        self._muting_light = False
        self._unit_fields = []
        self._traces = []
        self.values = {key: (tk.BooleanVar if isinstance(value, bool) else tk.StringVar)(
            self, value=state.get(key, value)) for key, value in _DEFAULTS.items()}
        self.ambient_var = self.values['ambient']
        self.distance_var = self.values['range_distance']
        self.speed_var = self.values['range_speed']
        self.consider_speed_var = self.values['consider_speed']
        self.range_mode_var = self.values['range_mode']
        self.illumination_result = self.range_result = None

        wrap_label(ttk.Label(self.header, text=t('quick_tables_title'), style='PageTitle.TLabel')).pack(fill='x')
        wrap_label(ttk.Label(self.header, text=t('quick_tables_intro'), style='Muted.TLabel')).pack(fill='x')
        views = ttk.Frame(self.header)
        views.pack(fill='x', pady=(6, 0))
        flow_buttons(views, [
            ttk.Radiobutton(views, text=t('qt_reference_view_' + key), variable=self.page, value=key,
                            command=lambda key=key: self.show_page(key))
            for key in ('combat', 'reference')
        ])
        self._build_lighting()
        self._build_range()
        self.light_options.show(state.get('light_options', False))
        for key, variable in self.values.items():
            callback = (self._range_distance_changed if key == 'range_distance' else self.refresh_map
                        if key.startswith('range_') or key == 'consider_speed' else self._refresh_lighting)
            self._traces.append((variable, variable.trace_add('write', callback)))
        self._refresh_lighting()
        self.refresh_map()
        self.bind_scrolling()
        if state.get('page') == 'reference':
            self.show_page('reference')

    def show_page(self, page):
        self.page.set(page)
        if page == 'reference':
            self.body.pack_forget()
            if self.reference is None:
                from utils.quick_tables_cards_ui import ReferenceCardsPanel
                self.reference = ReferenceCardsPanel(
                    self, units=self.units, open_tool=self._app.choose_tool, open_dice=self._open_dice,
                    state=self._reference_state, attach_scroll=self.bind_scrolling,
                    enabled_packages=self._app.ui_preferences['quick_tables_packs'],
                    save_packages=self._save_packages)
                self.bind_scrolling(self.reference)
            self.reference.pack(fill='both', expand=True)
        else:
            if self.reference is not None:
                self.reference.pack_forget()
            self.body.pack(fill='both', expand=True)
        self.canvas.yview_moveto(0)

    def _open_dice(self, expression):
        self._app.choose_tool(15)
        self._app.gm_dice_panel.select_expression(expression)

    def _save_packages(self, packages):
        from utils.gui_hub import save_ui

        self._app.ui_preferences['quick_tables_packs'] = list(packages)
        save_ui(self._app)

    def _place(self, wide):
        changed = wide != self.wide
        super()._place(wide)
        if changed and wide:
            self.body.columnconfigure(0, weight=1)
            self.body.columnconfigure(1, weight=1)

    def destroy(self):
        for variable, identifier in self._traces:
            variable.trace_remove('write', identifier)
        for binding in self._unit_fields:
            binding.close()
        super().destroy()

    def snapshot(self):
        """Keep canonical yard strings and the map token across GUI rebuilds only."""
        return {**{key: variable.get() for key, variable in self.values.items()},
                'map_snapshot': self._map_snapshot, 'light_options': self.light_options.expanded,
                'page': self.page.get(),
                'reference': self.reference.snapshot() if self.reference else self._reference_state}

    @staticmethod
    def _card(parent, title):
        card = ttk.Frame(parent, padding=(8, 6))
        card.pack(fill='x')
        wrap_label(ttk.Label(card, text=t(title), style='Subtitle.TLabel')).pack(fill='x', pady=(0, 4))
        body = ttk.LabelFrame(card, padding=8)
        body.pack(fill='x')
        return body

    @staticmethod
    def _row(parent, key, **fields):
        cell = ttk.Frame(parent)
        wrap_label(ttk.Label(cell, text=t(key, **fields), width=1)).pack(fill='x', pady=(0, 2))
        if isinstance(parent, FieldGrid):
            parent.add(cell)
        else:
            cell.pack(fill='x', pady=(0, 5))
        return cell

    def _choice(self, parent, field, label, options):
        keys = tuple(options)
        canonical = self.values[field]
        display = tuple(options.values())
        box = ttk.Combobox(self._row(parent, label), values=display, state='readonly', width=1)
        box.pack(fill='x')

        def sync(*_):
            index = keys.index(canonical.get()) if canonical.get() in keys else 0
            if box.current() != index:
                box.current(index)

        def select(_event):
            index = box.current()
            if index >= 0:
                canonical.set(keys[index])

        sync()
        self._traces.append((canonical, canonical.trace_add('write', sync)))
        box.bind('<<ComboboxSelected>>', select)
        return box

    def _entry(self, parent, field, label, quantity=None):
        variable = self.values[field]
        if quantity:
            # UnitSystem defines the conversion; UnitBinding keeps only the
            # presentation in metric and preserves unrounded input for rules.
            sample = self.units.display(1, quantity)
            symbol = sample.rsplit(' ', 1)[-1]
            cell = self._row(parent, label, unit=symbol)
        else:
            cell = self._row(parent, label)
        entry = ttk.Entry(cell, textvariable=variable, width=1)
        entry.pack(fill='x')
        if quantity:
            self._unit_fields.append(UnitBinding(entry, variable, 1 / self.units.to_rules(1, quantity), symbol))
        return entry

    @staticmethod
    def _preview(parent):
        metric = wrap_label(ttk.Label(parent, width=1, style='Metric.TLabel'))
        metric.pack(fill='x', pady=(6, 3))
        details = wrap_label(ttk.Label(parent, width=1, justify='left'))
        details.pack(fill='x')
        status = wrap_label(ttk.Label(parent, width=1, justify='left', style='Warning.TLabel'))
        status.pack(fill='x', pady=(3, 0))
        return metric, details, status

    @staticmethod
    def _preset_label(preset):
        return t('quick_tables_preset', name=t('quick_tables_light_' + preset.key),
                 modifier=f'{preset.modifier:+d}')

    def _build_lighting(self):
        body = self._card(self.inputs, 'quick_tables_lighting')
        self._choice(body, 'ambient', 'quick_tables_ambient',
                     {key: self._preset_label(preset) for key, preset in _AMBIENT.items()})

        point = FieldGrid(body, columns=2)
        point.pack(fill='x')
        self._choice(point, 'point', 'quick_tables_point',
                     {'': t('common_none'), **{key: self._preset_label(preset) for key, preset in _POINT.items()}})
        self.point_distance_entry = self._entry(point, 'point_distance', 'quick_tables_point_distance', 'yards')

        self.light_options = Disclosure(body, t('quick_tables_light_options'),
                                        lambda: self.light_options.show(not self.light_options.expanded))
        self.light_options.pack(fill='x', pady=(4, 0))
        advanced = self.light_options.section
        self.cloud_button = checkbutton(advanced, t('quick_tables_heavy_cloud'), self.values['heavy_cloud'])
        self.cloud_button.pack(fill='x')
        self.polar_button = checkbutton(advanced, t('quick_tables_polar_moonlight'), self.values['polar_moonlight'])
        self.polar_button.pack(fill='x')
        extra = FieldGrid(advanced, columns=2)
        extra.pack(fill='x')
        self._choice(extra, 'flicker', 'quick_tables_flicker', {str(n): str(n) for n in range(4)})
        self._choice(extra, 'dimming', 'quick_tables_dimming', {str(n): str(n) for n in range(11)})
        self.adaptation_entry = self._entry(advanced, 'adaptation', 'quick_tables_adaptation')

        self.light_metric, self.light_details, self.light_status = self._preview(body)
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        self.send_light_button = ttk.Button(actions, text=t('quick_tables_send_light'),
                                            command=self.send_current_lighting)
        flow_buttons(actions, [self.send_light_button])

    @staticmethod
    def _enable(widget, value):
        widget.state(['!disabled' if value else 'disabled'])

    def _refresh_lighting(self, *_):
        if self._muting_light:
            return
        values = self.values
        ambient = _AMBIENT.get(values['ambient'].get())
        point = _POINT.get(values['point'].get())
        heavy = bool(ambient and ambient.cloud_sensitive)
        polar = bool(ambient and ambient.high_latitude_sensitive)
        self._muting_light = True
        try:
            for field, enabled, button in (('heavy_cloud', heavy, self.cloud_button),
                                           ('polar_moonlight', polar, self.polar_button)):
                self._enable(button, enabled)
                if not enabled and values[field].get():
                    values[field].set(False)
        finally:
            self._muting_light = False
        self._enable(self.point_distance_entry, point is not None)
        dimming = values['dimming'].get() != '0'
        self._enable(self.adaptation_entry, bool(dimming))
        self.light_status.configure(text='')
        try:
            result = calculate_illumination(
                values['ambient'].get(), point.key if point else None,
                _number(values['point_distance'].get()) if point else 1.0,
                heavy_cloud=values['heavy_cloud'].get(), polar_moonlight=values['polar_moonlight'].get(),
                flicker=int(values['flicker'].get()), sudden_dimming_steps=int(values['dimming'].get()),
                adaptation_elapsed_minutes=_number(values['adaptation'].get(), blank=0.0) if dimming else 0.0,
            )
        except ValueError as exc:
            self.illumination_result = None
            self.light_metric.configure(text='—')
            self.light_details.configure(text='')
            self.light_status.configure(text=_display_error(exc))
        else:
            self.illumination_result = result
            rows = [t('quick_tables_ambient_detail', modifier=f'{result.ambient_modifier:+d}')]
            if values['heavy_cloud'].get():
                rows.append(t('quick_tables_cloud_detail', modifier=f'{result.cloud_modifier:+d}'))
            if values['polar_moonlight'].get():
                rows.append(t('quick_tables_polar_detail', modifier=f'{result.polar_modifier:+d}'))
            if result.point_modifier is not None:
                rows.append(t('quick_tables_point_detail', base=f'{point.modifier:+d}',
                              adjustment=f'{result.point_distance_modifier:+d}', final=f'{result.point_modifier:+d}'))
            rows.append(t('quick_tables_chosen_light',
                          source=t('quick_tables_point' if result.point_used else 'quick_tables_ambient'),
                          modifier=f'{result.chosen_modifier:+d}'))
            if values['flicker'].get() != '0':
                rows.append(t('quick_tables_flicker_detail', modifier=f'{result.flicker_modifier:+d}'))
            if dimming:
                rows.append(t('quick_tables_adaptation_detail', modifier=f'{result.adaptation_modifier:+d}',
                              minutes=result.adaptation_required_minutes))
            rows.append(t('quick_tables_reference', page=result.page))
            self.light_metric.configure(text=t('quick_tables_modifier', modifier=f'{result.modifier:+d}'))
            self.light_details.configure(text='\n'.join(rows))
            if result.total_darkness:
                self.light_status.configure(text=t('quick_tables_total_darkness_notice', setting=t('ranged_cannot_see')))
        self._enable(self.send_light_button, self._send_lighting is not None and self.illumination_result is not None)

    def send_current_lighting(self):
        if self._send_lighting is not None and self.illumination_result is not None:
            try:
                self._send_lighting(self.illumination_result)
            except ValueError as exc:
                self.light_status.configure(text=_display_error(exc))

    def _build_range(self):
        body = self._card(self.result, 'quick_tables_range')
        self._choice(body, 'range_mode', 'quick_tables_range_mode',
                     {key: t('quick_tables_range_' + key) for key in ('attack', 'sense')})
        distances = FieldGrid(body, columns=2)
        distances.pack(fill='x')
        self.range_distance_entry = self._entry(distances, 'range_distance', 'quick_tables_distance', 'yards')
        self.range_speed_entry = self._entry(distances, 'range_speed', 'quick_tables_speed', 'yards_per_second')
        checkbutton(body, t('quick_tables_consider_speed'), self.values['consider_speed']).pack(fill='x')
        self.range_metric, self.range_details, self.range_status = self._preview(body)
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        self.map_button = ttk.Button(actions, text=t('quick_tables_pull_map'), command=self.pull_map_distance)
        self.send_range_button = ttk.Button(actions, text=t('map_send_distance'), command=self.send_range)
        flow_buttons(actions, [self.map_button, self.send_range_button])

    def _range_distance_changed(self, *_):
        if not self._copying_map:
            self._map_snapshot = None
        self.refresh_map()

    def refresh_map(self, *_):
        """Refresh availability/provenance after the master moves or changes the pair."""
        latest = self._map_distance() if self._map_distance is not None else None
        stale = self._map_snapshot is not None and self._map_snapshot != latest
        self._enable(self.map_button, latest is not None)
        self._enable(self.range_speed_entry, self.values['consider_speed'].get())
        self._refresh_range_result(stale=stale)

    def _refresh_range_result(self, *, stale):
        values = self.values
        include_speed = values['consider_speed'].get()
        try:
            distance = (self._map_snapshot.distance_yards if self._map_snapshot is not None
                        else _number(values['range_distance'].get()))
            speed = _number(values['range_speed'].get(), blank=0.0) if include_speed else 0.0
            result = calculate_speed_range(distance, speed, mode=values['range_mode'].get(), consider_speed=include_speed)
        except ValueError as exc:
            self.range_result = None
            self.range_metric.configure(text='—')
            self.range_details.configure(text='')
            status = _display_error(exc)
        else:
            self.range_result = result
            self.range_metric.configure(text=t('quick_tables_modifier', modifier=f'{result.modifier:+d}'))
            rows = [t('quick_tables_distance_detail', distance=self.units.display(result.distance_yards, 'yards', precision=15))]
            if include_speed:
                rows.append(t('quick_tables_speed_detail', sign='−' if result.mode == 'sense' else '+',
                              speed=self.units.display(result.speed_yps, 'yards_per_second', precision=15)))
            rows += [t('quick_tables_lookup_detail', effective=self.units.display(result.effective_yards, 'yards', precision=15),
                       lookup=result.lookup_yards), t('quick_tables_band_detail', limit=self._band_limit(result.band_limit_yards)),
                     t('quick_tables_reference', page=result.page)]
            self.range_details.configure(text='\n'.join(rows))
            status = (t('quick_tables_map_stale') if stale else t('quick_tables_map_used')
                      if self._map_snapshot is not None else t('quick_tables_sense_no_send')
                      if result.mode == 'sense' else '')
        self.range_status.configure(text=status)
        self._enable(self.send_range_button, self._send_to_ranged is not None and self.range_result is not None
                     and self.range_result.mode == 'attack' and not stale)

    def _band_limit(self, yards):
        original = f'{yards} yd'
        if self.units.name == 'metric':
            try:
                return f'{self.units.display(yards, "yards", precision=15)} ({original})'
            except (OverflowError, ValueError):
                pass  # Extremely large integer bands may exceed floating-point range.
        return original

    def pull_map_distance(self):
        measurement = self._map_distance() if self._map_distance is not None else None
        if measurement is None:
            self.refresh_map()
            self.range_status.configure(text=t('map_need_pair'))
            return
        self._map_snapshot = measurement
        self._copying_map = True
        try:
            self.values['range_distance'].set(repr(measurement.distance_yards))
        finally:
            self._copying_map = False
        self.refresh_map()

    def send_range(self):
        self.refresh_map()
        result = self.range_result
        if result is None or self.send_range_button.instate(['disabled']):
            return
        try:
            self._send_to_ranged(result.distance_yards, result.speed_yps, map_snapshot=self._map_snapshot,
                                 consider_speed=result.consider_speed)
        except ValueError as exc:
            self.range_status.configure(text=_display_error(exc))
