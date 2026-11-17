"""Small desktop renderer for rule cards; never writes a campaign or encounter."""
import tkinter as tk
from tkinter import ttk
import unicodedata

from utils.dice_roller import roll_dice
from utils.i18n import get_i18n, t
from utils.quick_tables_cards import Localized, Quantity, SECTIONS, SUPPLEMENT_SECTIONS, reference_cards
from utils.quick_tables_packages import PACKAGE_IDS, normalize_packages
from utils.ranged_layout import FieldGrid, checkbutton, flow_buttons, wrap_label
from utils.unit_binding import UnitBinding


def _fold(text):
    return ''.join(char for char in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(char))


class ReferenceCardsPanel(ttk.Frame):
    """Only the selected card has live widgets; drafts last until the app closes."""

    def __init__(self, parent, *, units, open_tool, open_dice, state=None, attach_scroll=None,
                 enabled_packages=(), save_packages=None):
        super().__init__(parent)
        state = state or {}
        self.units = units
        self.open_tool = open_tool
        self.open_dice = open_dice
        self.attach_scroll = attach_scroll or (lambda _widget: None)
        self.save_packages = save_packages
        self.enabled_packages = ()
        self.cards = ()
        self.by_key = {}
        self.drafts = dict(state.get('drafts', {}))
        self.section_keys = ('all', *SECTIONS)
        self.current = None
        self.result = None
        self.roll_button = None
        self.inputs = {}
        self.bindings = []
        self.traces = []
        self.available = []
        self.field_panel = None
        self._shown = False

        controls = ttk.Frame(self, padding=(4, 0, 4, 3))
        controls.pack(fill='x')
        self.package_control = ttk.Menubutton(controls)
        self.package_control.pack(anchor='w')
        self.package_menu = tk.Menu(self.package_control, tearoff=False)
        self.package_control.configure(menu=self.package_menu)
        self.package_choices = {}
        for key in PACKAGE_IDS:
            value = self.package_choices[key] = tk.BooleanVar(self, value=False)
            self.package_menu.add_checkbutton(label=t('qt_package_' + key), variable=value,
                                              command=self._apply_package_choices)
        self.package_menu.add_separator()
        self.package_menu.add_command(label=t('qt_packages_reset'), command=lambda: self.set_enabled_packages(()))

        index = FieldGrid(self, columns=4)
        index.pack(fill='x')
        self.sections = ttk.Combobox(self._column(index, 'qt_reference_section'), width=1, state='readonly',
                                     values=tuple(t('qt_reference_section_' + key) for key in self.section_keys))
        self.sections.pack(fill='x')
        self.sections.bind('<<ComboboxSelected>>', self._refresh_choices)
        self.sources = ttk.Combobox(self._column(index, 'qt_packages_filter'), width=1, state='disabled')
        self.sources.pack(fill='x')
        self.source_keys = ('basic',)
        self.sources.bind('<<ComboboxSelected>>', self._refresh_choices)
        self.query = tk.StringVar(self, value=state.get('query', ''))
        ttk.Entry(self._column(index, 'qt_reference_search'), width=1, textvariable=self.query).pack(fill='x')
        self.selector = ttk.Combobox(self._column(index, 'qt_reference_lookup'), width=1, state='readonly')
        self.selector.pack(fill='x')
        self.selector.bind('<<ComboboxSelected>>', self._choose_card)
        self._query_trace = self.query.trace_add('write', self._refresh_choices)
        self.content = ttk.Frame(self, padding=(4, 8))
        self.content.pack(fill='both', expand=True)
        self._configure_packages(normalize_packages(enabled_packages), state.get('section', 'all'),
                                 state.get('source', 'all'))
        self._refresh_choices(preferred=state.get('card'))

    @staticmethod
    def _column(parent, title, **kwargs):
        cell = ttk.Frame(parent)
        wrap_label(ttk.Label(cell, width=1, text=t(title, **kwargs))).pack(fill='x', pady=(0, 3))
        parent.add(cell)
        return cell

    def _section(self):
        return self.section_keys[max(self.sections.current(), 0)]

    def _source_filter(self):
        return self.source_keys[max(self.sources.current(), 0)]

    def _configure_packages(self, packages, section, source):
        cards = reference_cards(packages)
        self.cards = cards
        self.by_key = {card.key: card for card in cards}
        self.enabled_packages = packages
        for key, choice in self.package_choices.items():
            choice.set(key in packages)
        self.package_control.configure(text=t('qt_packages_toggle', count=len(packages)))
        self.section_keys = ('all', *SECTIONS,
                             *(key for key in SUPPLEMENT_SECTIONS if any(card.section == key for card in cards)))
        self.sections.configure(values=[t('qt_reference_section_' + key) for key in self.section_keys])
        self.sections.current(self.section_keys.index(section) if section in self.section_keys else 0)
        self.source_keys = ('all', 'basic', *packages) if packages else ('basic',)
        self.sources.configure(
            values=[t('qt_package_' + key) for key in self.source_keys],
            state='readonly' if packages else 'disabled')
        self.sources.current(self.source_keys.index(source) if source in self.source_keys else 0)

    def _apply_package_choices(self):
        self.set_enabled_packages(tuple(key for key, value in self.package_choices.items() if value.get()))

    def set_enabled_packages(self, packages):
        selected = normalize_packages(packages)
        if selected == self.enabled_packages:
            return
        # When the switch is first turned on, show the newly available sources.
        source = self._source_filter() if self.enabled_packages else 'all'
        self._configure_packages(selected, self._section(), source)
        self._refresh_choices()
        if self.save_packages is not None:
            self.save_packages(selected)

    def _refresh_choices(self, *_event, preferred=None):
        section = self._section()
        source = self._source_filter()
        words = _fold(self.query.get()).split()
        translations = get_i18n().translations.values()
        self.available = [
            card for card in self.cards
            if (section == 'all' or section == card.section)
            and (source == 'all' or source == card.package)
            and all(word in _fold(' '.join((card.pages, card.key, card.source,
                        *(language.get(key, '') for language in translations
                          for key in (card.title, 'qt_package_' + card.package))))) for word in words)
        ]
        wanted = preferred or (self.current.key if self.current is not None else None)
        keys = [card.key for card in self.available]
        self.selector.configure(values=[t(card.title) for card in self.available],
                                state='readonly' if keys else 'disabled')
        if keys:
            self.selector.current(keys.index(wanted) if wanted in keys else 0)
        else:
            self.selector.set('')
        self._choose_card()

    def _choose_card(self, *_event):
        index = self.selector.current()
        selected = self.available[index] if 0 <= index < len(self.available) else None
        if selected is not self.current or not self._shown:
            self._show(selected)

    def _remember(self):
        if self.current is not None:
            self.drafts[self.current.key] = {key: var.get() for key, var in self.inputs.items()}

    def snapshot(self):
        self._remember()
        return {'section': self._section(), 'source': self._source_filter(), 'query': self.query.get(),
                'card': self.current.key if self.current else None, 'drafts': self.drafts.copy()}

    def _close_fields(self):
        for variable, token in self.traces:
            variable.trace_remove('write', token)
        self.traces.clear()
        for binding in self.bindings:
            binding.close()
        self.bindings.clear()
        self.inputs.clear()

    def destroy(self):
        self.query.trace_remove('write', self._query_trace)
        self._close_fields()
        super().destroy()

    def _show(self, card):
        self._remember()
        self._close_fields()
        for child in self.content.winfo_children():
            child.destroy()
        self.current, self.result = card, None
        self.roll_button = None
        self.field_panel = None
        self._shown = True
        if card is None:
            wrap_label(ttk.Label(self.content, text=t('qt_reference_empty'), style='Muted.TLabel',
                                 width=1)).pack(fill='x')
            return

        wrap_label(ttk.Label(self.content, text=t(card.title), style='Subtitle.TLabel', width=1)).pack(fill='x')
        wrap_label(ttk.Label(self.content, text=t('qt_reference_source', book=card.source, pages=card.pages),
                             style='Muted.TLabel', width=1)).pack(fill='x', pady=(2, 6))
        if card.requirement:
            wrap_label(ttk.Label(self.content, text=t('qt_packages_context', detail=t(card.requirement)),
                                 style='Muted.TLabel', width=1)).pack(fill='x', pady=(0, 8))
        if card.fields:
            self.field_panel = FieldGrid(self.content, columns=3)
            self.field_panel.pack(fill='x', pady=(0, 6))
        draft = self.drafts.get(card.key, {})
        for field in card.fields:
            self._build_field(field, draft.get(field.key, field.default))
        results = ttk.LabelFrame(self.content, padding=(8, 6), text=t('qt_reference_readout'))
        results.pack(fill='x')
        self.readout = wrap_label(ttk.Label(results, width=1, justify='left'))
        self.readout.pack(fill='x', pady=(2, 2))

        actions = ttk.Frame(self.content)
        actions.pack(fill='x', pady=(4, 0))
        buttons = []
        if card.roll is not None:
            _, count, sides = card.roll
            self.roll_button = ttk.Button(actions, text=t('qt_reference_roll', dice=f'{count}d{sides}'),
                                          command=self.roll)
            buttons.append(self.roll_button)
        if card.tool is not None:
            buttons.append(ttk.Button(actions, text=t('qt_reference_open_tool'),
                                      command=lambda: self.open_tool(card.tool)))
        if buttons:
            flow_buttons(actions, buttons)
        else:
            actions.pack_forget()
        self.expression_actions = ttk.Frame(self.content)
        ttk.Button(self.expression_actions, text=t('qt_reference_open_dice'),
                   command=self._send_expression).pack(fill='x', padx=4)
        self._calculate()
        self.attach_scroll(self.content)

    def _build_field(self, field, raw):
        if field.kind == 'bool':
            cell = ttk.Frame(self.field_panel)
            self.field_panel.add(cell)
            variable = tk.BooleanVar(self, value=raw)
            checkbutton(cell, t(field.title), variable).pack(fill='x')
        elif field.kind == 'choice':
            cell = self._column(self.field_panel, field.title)
            variable = tk.StringVar(self, value=raw)
            options = [key for key, _ in field.options]
            combo = ttk.Combobox(cell, width=1, state='readonly',
                                 values=[t(title) for _, title in field.options])
            combo.pack(fill='x')
            combo.current(options.index(raw) if raw in options else 0)
            variable.set(options[combo.current()])
            combo.bind('<<ComboboxSelected>>', lambda _event: variable.set(options[combo.current()]))
        else:
            variable = tk.StringVar(self, value=raw)
            if field.unit is not None:
                symbol = self.units.display(1, field.unit).rsplit(' ', 1)[-1]
            else:
                symbol = ''
            cell = self._column(self.field_panel, field.title, unit=symbol)
            widget = ttk.Entry(cell, width=1, textvariable=variable)
            widget.pack(fill='x')
            if field.unit is not None:
                self.bindings.append(UnitBinding(widget, variable, 1 / self.units.to_rules(1, field.unit), symbol))
        self.inputs[field.key] = variable
        self.traces.append((variable, variable.trace_add('write', self._calculate)))

    def _format_argument(self, value):
        if isinstance(value, Localized):
            return t(value.key)
        if isinstance(value, Quantity):
            return self.units.display(value.value, value.unit, precision=10)
        return value

    def _calculate(self, *_ignored):
        self.result = None
        values = {}
        for field in self.current.fields:
            try:
                values[field.key] = field.parse(self.inputs[field.key].get())
            except ValueError as exc:
                text = t('qt_reference_field_error', field=t(field.title).replace(' ({unit})', ''),
                         error=t(str(exc)))
                self.readout.configure(text=text, style='Warning.TLabel')
                self._update_actions(False)
                return
        try:
            result = self.current.calculate(values)
            text = '\n'.join(t(row.key, **{name: self._format_argument(value)
                                           for name, value in row.arguments.items()}) for row in result.lines)
        except (ValueError, OverflowError) as exc:
            reason = str(exc)
            localized = t(reason)
            self.readout.configure(text=localized if reason != localized else t('qt_reference_invalid_number'),
                                   style='Warning.TLabel')
            self._update_actions(False)
            return
        self.result = result
        self.readout.configure(text=text, style='TLabel')
        self._update_actions(bool(result.expression))

    def _update_actions(self, has_expression):
        if self.roll_button is not None:
            enabled = self.result is not None and self.result.allows_roll
            self.roll_button.state(['!disabled' if enabled else 'disabled'])
        if has_expression and not self.expression_actions.winfo_manager():
            self.expression_actions.pack(fill='x', pady=(4, 0))
        elif not has_expression:
            self.expression_actions.pack_forget()

    def _send_expression(self):
        if self.result is not None and self.result.expression:
            self.open_dice(self.result.expression)

    def roll(self):
        if (self.current is not None and self.current.roll is not None and self.result is not None
                and self.result.allows_roll):
            field, count, sides = self.current.roll
            total, _ = roll_dice(f'{count}d{sides}')
            self.inputs[field].set(str(total))
