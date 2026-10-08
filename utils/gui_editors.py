"""Guided editors over existing vehicle and ability engines."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from uuid import uuid4
from calculators.powers import AbilityBuildInput, ModifierRecord
from calculators.vehicles import VehicleRecord
from calculators.magic import CeremonialAssistant, CeremonialCasting
from calculators.campaign import OrganizationRecord, RelationshipRecord
from utils.i18n import t
from utils.editor_records import (VEHICLE_FIELDS, number, validate_vehicle, vehicle_document,
                                  load_vehicle_document, ability_document, load_ability_document,
                                  read_document, write_document)


class EditorWindow(tk.Toplevel):
    def __init__(self, app, title):
        super().__init__(app.root)
        self.app = app
        self.title(t(title))
        self.geometry('850x680')
        self.minsize(600, 400)
        self.transient(app.root)
        self.footer = ttk.Frame(self, padding=8)
        self.footer.pack(side='bottom', fill='x')
        canvas = tk.Canvas(self, highlightthickness=0, background=app.colors['bg'])
        scroll = ttk.Scrollbar(self, command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        horizontal = ttk.Scrollbar(self, orient='horizontal', command=canvas.xview)
        horizontal.pack(side='bottom', fill='x', before=canvas)
        canvas.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        self.form = ttk.Frame(canvas, padding=12)
        window = canvas.create_window(0, 0, window=self.form, anchor='nw')
        self.form.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=max(event.width, self.form.winfo_reqwidth())))
        self.form.columnconfigure(1, weight=1)
        self.error = ttk.Label(self.footer, text='', wraplength=780, foreground='#b42318' if app.ui_preferences['theme'] == 'light' else '#ff8585')
        self.error.pack(fill='x')
        self.actions = ttk.Frame(self.footer)
        self.actions.pack(fill='x', pady=4)
        self._action_count = 0

    def action(self, key, callback):
        def guarded():
            try:
                self.error.configure(text='')
                callback()
            except (OSError, ValueError, TypeError, tk.TclError) as exc:
                translated = t(str(exc))
                self.error.configure(text=translated if translated != str(exc) else t('ui_editor_error', error=str(exc)))
        index = self._action_count
        self._action_count += 1
        ttk.Button(self.actions, text=t(key), command=guarded).grid(row=index // 3, column=index % 3, sticky='ew', padx=3, pady=3)
        self.actions.columnconfigure(index % 3, weight=1)

    def entry(self, row, label, variable):
        ttk.Label(self.form, text=label, wraplength=360).grid(row=row, column=0, sticky='w', pady=4)
        ttk.Entry(self.form, textvariable=variable).grid(row=row, column=1, sticky='ew', padx=8, pady=4)


class CeremonialEditor(EditorWindow):
    def __init__(self, app):
        super().__init__(app, 'ui_ceremony_title')
        current = deepcopy(getattr(app, '_magic_ceremony', None) or CeremonialCasting())
        self.assistants = current.assistants
        self.caster = tk.StringVar(self, value=str(current.caster_energy))
        self.supporters = tk.StringVar(self, value=str(current.supporters))
        self.opponents = tk.StringVar(self, value=str(current.opponents))
        self.skill = tk.StringVar(self, value='15')
        self.energy = tk.StringVar(self, value='1')
        self.mage = tk.BooleanVar(self, value=True)
        ttk.Label(self.form, text=t('ui_ceremony_help'), wraplength=730).grid(row=0, column=0, columnspan=2)
        for row, key, var in ((1, 'ui_ceremony_caster', self.caster),
                              (2, 'ui_ceremony_supporters', self.supporters),
                              (3, 'ui_ceremony_opponents', self.opponents),
                              (4, 'ui_ceremony_skill', self.skill),
                              (5, 'ui_ceremony_energy', self.energy)):
            self.entry(row, t(key), var)
        ttk.Checkbutton(self.form, text=t('ui_ceremony_mage'), variable=self.mage).grid(row=6, column=0)
        self.listbox = tk.Listbox(self.form, height=8)
        self.listbox.grid(row=7, column=0, columnspan=2, sticky='ew', pady=8)
        self.refresh()
        self.action('ui_ceremony_add', self.add)
        self.action('ui_ceremony_remove', self.remove)
        self.action('ui_apply_parameters', self.apply_parameters)

    def refresh(self):
        self.listbox.delete(0, 'end')
        for a in self.assistants:
            self.listbox.insert('end', t('ui_ceremony_assistant', skill=a.spell_skill,
                                        mage=t('common_yes') if a.mage else t('common_no'), energy=a.energy))

    def add(self):
        skill, energy = number(self.skill.get(), int), number(self.energy.get(), int)
        mage = self.mage.get()
        if min(skill, energy) < 0 or (skill < 15 and not mage) or (energy > 3 and (not mage or skill < 15)):
            raise ValueError('invalid_ceremonial_contribution')
        self.assistants.append(CeremonialAssistant(skill, mage, energy))
        self.refresh()

    def remove(self):
        for index in reversed(self.listbox.curselection()):
            self.assistants.pop(index)
        self.refresh()

    def apply_parameters(self):
        caster, supporters, opponents = (number(v.get(), int) for v in (self.caster, self.supporters, self.opponents))
        if min(caster, supporters, opponents) < 0:
            raise ValueError('invalid_ceremonial_contribution')
        self.app._magic_ceremony = CeremonialCasting(caster, deepcopy(self.assistants), supporters, opponents)
        self.app.magic_system.set('ceremonial')
        self.destroy()


class CampaignEditor(EditorWindow):
    """Explicit GM records; no invented automatic relationship progression."""
    def __init__(self, app):
        super().__init__(app, 'ui_campaign_editor')
        self.kind = tk.StringVar(self, value=t('ui_campaign_organizations'))
        self.selected = tk.StringVar(self)
        self.records = {}
        self.variables = {}
        self.record_id = None
        ttk.Label(self.form, text=t('ui_campaign_help'), wraplength=730).grid(row=0, column=0, columnspan=2)
        if getattr(app.campaign_session, 'recovered_file', None):
            self.error.configure(text=t('ui_session_recovered', path=str(app.campaign_session.recovered_file)))
        chooser = ttk.Combobox(self.form, textvariable=self.kind, state='readonly',
                               values=(t('ui_campaign_organizations'), t('ui_campaign_relationships')))
        chooser.grid(row=1, column=0, columnspan=2, sticky='ew')
        chooser.bind('<<ComboboxSelected>>', lambda event: self.refresh())
        self.picker = ttk.Combobox(self.form, textvariable=self.selected, state='readonly')
        self.picker.grid(row=2, column=0, columnspan=2, sticky='ew')
        self.picker.bind('<<ComboboxSelected>>', lambda event: self.load_selected())
        self.fields = ttk.Frame(self.form)
        self.fields.grid(row=3, column=0, columnspan=2, sticky='ew')
        self.fields.columnconfigure(1, weight=1)
        self.refresh()
        self.action('ui_campaign_new', self.new)
        self.action('ui_campaign_save', self.save_record)
        self.action('ui_campaign_undo', self.undo)

    def organization_mode(self):
        return self.kind.get() == t('ui_campaign_organizations')

    def refresh(self):
        group = self.app.campaign_session.organizations if self.organization_mode() else self.app.campaign_session.relationships
        self.records = {f"{getattr(record, 'name', record.identifier)} [{record.identifier}]": record for record in group.values()}
        self.picker.configure(values=list(self.records))
        self.new()

    def new(self):
        self.selected.set('')
        record = OrganizationRecord('', '') if self.organization_mode() else RelationshipRecord('', '', '')
        self.show(record)

    def load_selected(self):
        self.show(deepcopy(self.records[self.selected.get()]))

    def show(self, record):
        self.base = deepcopy(record)
        self.record_id = record.identifier
        for child in self.fields.winfo_children(): child.destroy()
        names = ('name', 'size', 'resources', 'influence', 'hierarchy', 'reputation') if self.organization_mode() else (
            'first_id', 'second_id', 'relationship_type', 'intensity', 'frequency_days', 'last_contact')
        self.variables = {}
        for row, name in enumerate(names):
            variable = tk.StringVar(self, value=str(getattr(record, name)))
            self.variables[name] = variable
            ttk.Label(self.fields, text=t('ui_campaign_' + name), wraplength=340).grid(row=row, column=0, sticky='w', pady=5)
            ttk.Entry(self.fields, textvariable=variable).grid(row=row, column=1, sticky='ew', padx=8)

    def save_record(self):
        record = deepcopy(self.base)
        for name, variable in self.variables.items():
            value = number(variable.get(), int) if isinstance(getattr(record, name), int) else variable.get().strip()
            if name in ('size', 'frequency_days') and value < 0 or isinstance(value, str) and name != 'last_contact' and not value:
                raise ValueError('invalid_editor_number')
            setattr(record, name, value)
        if isinstance(record, RelationshipRecord) and record.first_id == record.second_id:
            raise ValueError('invalid_editor_number')
        record.identifier = self.record_id or 'custom.' + uuid4().hex
        if messagebox.askyesno(t('ui_campaign_save'), t('ui_campaign_confirm'), parent=self):
            self.app.campaign_session.upsert_record(record)
            self.refresh()

    def undo(self):
        if messagebox.askyesno(t('ui_campaign_undo'), t('ui_campaign_undo_confirm'), parent=self):
            self.app.campaign_session.undo()
            self.refresh()


class VehicleEditor(EditorWindow):
    def __init__(self, app):
        super().__init__(app, 'ui_vehicle_editor')
        self.base = deepcopy(app._vehicle_map.get(app.vehicle_selected.get()) or
                             VehicleRecord('custom.vehicle.new', '', 'Custom', '-'))
        self.edit_id = self.base.identifier if self.base.identifier.startswith('custom.') else None
        self.metric = app.result_units.get() == 'metric'
        ttk.Label(self.form, text=t('ui_vehicle_editor_help'), wraplength=750).grid(row=0, column=0, columnspan=2, sticky='w', pady=8)
        self.variables = {}
        for row, field in enumerate(('name', 'tech_level', 'vehicle_type') + tuple(VEHICLE_FIELDS), 1):
            value = getattr(self.base, field)
            factor = self.factor(field)
            if field in VEHICLE_FIELDS:
                try:
                    value = format(float(value) * factor, '.15g')
                except (TypeError, ValueError):
                    pass
            variable = tk.StringVar(self, value=value)
            self.variables[field] = variable
            label = t('ui_vehicle_' + field)
            if field in ('move_acceleration', 'move_top_speed'):
                label += ' (' + ('m/s' if self.metric else 'yd/s') + ('²' if field == 'move_acceleration' else '') + ')'
            elif field == 'range_miles':
                label += ' (km)' if self.metric else ' (mi)'
            self.entry(row, label, variable)
        self.action('ui_save_copy', lambda: self.save(False))
        if self.base.identifier.startswith('custom.'):
            self.action('ui_update_custom', lambda: self.save(True))
        self.action('common_import', self.import_record)
        self.action('common_export', self.export_record)

    def factor(self, field):
        if not self.metric:
            return 1
        return 0.9144 if field in ('move_acceleration', 'move_top_speed') else 1.609344 if field == 'range_miles' else 1

    def record(self):
        record = deepcopy(self.base)
        for field, variable in self.variables.items():
            raw = variable.get().strip()
            if field in VEHICLE_FIELDS:
                value = number(raw, VEHICLE_FIELDS[field]) / self.factor(field)
                setattr(record, field, int(value) if VEHICLE_FIELDS[field] is int else value)
            else:
                setattr(record, field, raw)
        return validate_vehicle(record)

    def save(self, updating):
        record = self.record()
        if updating and not messagebox.askyesno(t('ui_vehicle_editor'), t('ui_replace_custom'), parent=self):
            return
        if not updating:
            record.identifier = 'custom.vehicle.' + uuid4().hex
        else:
            record.identifier = self.edit_id
        record.original = {'based_on': f'{self.base.name} — {self.base.source} p.{self.base.page}'}
        record.source, record.page = 'Custom', '-'
        self.app.vehicle_catalog.save_custom(record)
        self.app.vehicle_selected.set(f'{record.name} — {record.source} p.{record.page}')
        self.destroy()
        self.app._rebuild_ui()

    def import_record(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('JSON', '*.json')])
        if not path:
            return
        record = load_vehicle_document(read_document(path))
        self.base = record
        for field, variable in self.variables.items():
            value = getattr(record, field)
            variable.set(format(float(value) * self.factor(field), '.15g') if field in VEHICLE_FIELDS else value)

    def export_record(self):
        record = self.record()
        record.identifier = self.edit_id or ('custom.vehicle.' + uuid4().hex)
        record.original = {'based_on': f'{self.base.name} — {self.base.source} p.{self.base.page}'}
        record.source, record.page = 'Custom', '-'
        document = vehicle_document(record)
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            write_document(path, document)


class AbilityEditor(EditorWindow):
    def __init__(self, app):
        super().__init__(app, 'ui_ability_editor')
        self.advantages = dict(app._advantage_map)
        self.modifiers = list(app.extended_catalog.records('modifiers'))
        self.powers = {t('ui_no_power'): None}
        self.powers.update({f'{item.name} — {item.source} p.{item.page}': item for item in app.extended_catalog.records('powers')})
        self.name = tk.StringVar(self, value=t('ui_new_ability'))
        self.advantage = tk.StringVar(self, value=app.power_advantage.get())
        self.levels = tk.StringVar(self, value=app.power_levels.get())
        self.power = tk.StringVar(self, value=t('ui_no_power'))
        self.alternate = tk.BooleanVar(self, value=False)
        ttk.Label(self.form, text=t('ui_ability_editor_help'), wraplength=750).grid(row=0, column=0, columnspan=2, pady=8)
        self.entry(1, t('ui_vehicle_name'), self.name)
        ttk.Label(self.form, text=t('powers_advantage')).grid(row=2, column=0, sticky='w')
        self.advantage_box = ttk.Combobox(self.form, textvariable=self.advantage, values=list(self.advantages), state='readonly')
        self.advantage_box.grid(row=2, column=1, sticky='ew', padx=8)
        self.entry(3, t('powers_levels'), self.levels)
        ttk.Label(self.form, text=t('ui_power_source')).grid(row=4, column=0, sticky='w')
        self.power_box = ttk.Combobox(self.form, textvariable=self.power, values=list(self.powers), state='readonly')
        self.power_box.grid(row=4, column=1, sticky='ew', padx=8)
        ttk.Checkbutton(self.form, text=t('ui_alternate_ability'), variable=self.alternate).grid(row=5, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Label(self.form, text=t('ui_select_modifiers')).grid(row=6, column=0, columnspan=2, sticky='w')
        self.modifier_list = tk.Listbox(self.form, selectmode='multiple', exportselection=False, height=8)
        self.modifier_list.grid(row=7, column=0, columnspan=2, sticky='ew', pady=6)
        for modifier in self.modifiers:
            self.modifier_list.insert('end', f'{modifier.name} ({modifier.percent:+d}%) — {modifier.source} p.{modifier.page}')
        self.modifier_name = tk.StringVar(self, value='')
        self.modifier_percent = tk.StringVar(self, value='0')
        self.entry(8, t('ui_custom_modifier_name'), self.modifier_name)
        self.entry(9, t('ui_custom_modifier_percent'), self.modifier_percent)
        ttk.Button(self.form, text=t('ui_add_custom_modifier'), command=self.add_modifier).grid(row=10, column=0, columnspan=2, sticky='w', pady=5)
        self.output = tk.Text(self.form, height=8, wrap='word', state='disabled')
        self.output.grid(row=11, column=0, columnspan=2, sticky='ew')
        self.action('common_calculate', self.calculate)
        self.action('ui_save_ability', self.save)
        self.action('ui_load_ability', self.load_saved)
        self.action('common_import', self.import_record)
        self.action('common_export', self.export_record)
        self.action('ui_editor_result', self.use)
        if getattr(app, '_edited_ability', None):
            name, build = app._edited_ability
            self.load(ability_document(name, build))
        self._input_traces = []
        for variable in (self.name, self.advantage, self.levels, self.power, self.alternate):
            self._input_traces.append((variable, variable.trace_add('write', self.invalidate)))
        self.modifier_list.bind('<<ListboxSelect>>', self.invalidate)

    def invalidate(self, *_):
        if self.output.get('1.0', 'end-1c').strip():
            self.error.configure(text=t('ui_result_stale'))

    def destroy(self):
        for variable, token in getattr(self, '_input_traces', []):
            variable.trace_remove('write', token)
        super().destroy()

    def build(self):
        build = AbilityBuildInput(deepcopy(self.advantages[self.advantage.get()]),
                                  [deepcopy(self.modifiers[i]) for i in self.modifier_list.curselection()],
                                  deepcopy(self.powers[self.power.get()]), number(self.levels.get(), int), self.alternate.get())
        ability_document(self.name.get(), build)
        return build

    def add_modifier(self):
        try:
            name = self.modifier_name.get().strip()
            if not name:
                raise ValueError('invalid_editor_name')
            percent = number(self.modifier_percent.get(), int)
            record = ModifierRecord('custom.modifier.' + uuid4().hex, name, 'Custom', '-', percent,
                                    'limitation' if percent < 0 else 'enhancement')
            self.modifiers.append(record)
            self.modifier_list.insert('end', f'{name} ({percent:+d}%) — Custom')
            self.modifier_list.selection_set(len(self.modifiers) - 1)
            self.error.configure(text='')
            self.invalidate()
        except ValueError as exc:
            self.error.configure(text=t(str(exc)))

    def calculate(self):
        result = self.app.ability_calc.calculate(self.build())
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', t('ui_ability_cost', base=result.unmodified_cost, modifier=result.net_modifier_percent, final=result.modified_cost))
        for item in result.breakdown:
            self.output.insert('end', f'\n{item["key"]}: {item["value"]} — {item["source"]} p.{item["page"]}')
        self.output.configure(state='disabled')

    def save(self):
        path = self.app.preferences_path.parent / 'ability_build.json'
        if path.exists() and not messagebox.askyesno(t('ui_ability_editor'), t('ui_replace_custom'), parent=self):
            return
        write_document(path, ability_document(self.name.get(), self.build()))
        self.error.configure(text=t('ui_editor_saved'))

    def load_saved(self):
        self.load(read_document(self.app.preferences_path.parent / 'ability_build.json'))

    def load(self, document):
        name, build = load_ability_document(document)
        self.name.set(name)
        label = f'{build.advantage.name} — {build.advantage.source} p.{build.advantage.page}'
        self.advantages[label] = build.advantage
        self.advantage_box.configure(values=list(self.advantages))
        self.advantage.set(label)
        self.levels.set(str(build.levels))
        self.alternate.set(build.alternate_ability)
        power_label = t('ui_no_power')
        if build.power:
            power_label = f'{build.power.name} — {build.power.source} p.{build.power.page}'
            self.powers[power_label] = build.power
        self.power_box.configure(values=list(self.powers))
        self.power.set(power_label)
        self.modifier_list.selection_clear(0, 'end')
        for modifier in build.modifiers:
            # Preserve imported values instead of substituting a same-ID catalog entry.
            if modifier not in self.modifiers:
                self.modifiers.append(modifier)
                self.modifier_list.insert('end', f'{modifier.name} ({modifier.percent:+d}%) — {modifier.source} p.{modifier.page}')
            self.modifier_list.selection_set(self.modifiers.index(modifier))

    def import_record(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('JSON', '*.json')])
        if path:
            self.load(read_document(path))

    def export_record(self):
        document = ability_document(self.name.get(), self.build())
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.json', filetypes=[('JSON', '*.json')])
        if path:
            write_document(path, document)

    def use(self):
        build = self.build()
        self.app._edited_ability = (self.name.get(), build)
        self.calculate()
        self.app._show_result(self.app.powers_result_text, [t('ui_ability_named', name=self.name.get()), self.output.get('1.0', 'end-1c')])
        self.destroy()


class CastingAssistant(EditorWindow):
    def __init__(self, app):
        super().__init__(app, 'ui_casting_assistant')
        self.selected = app.magic_spell.get()
        spell = app._magic_map[self.selected]
        self.cost = tk.StringVar(self, value=app.magic_cost_override.get())
        self.time = tk.StringVar(self, value=app.magic_time_override.get())
        original = spell.original
        details = '\n'.join((self.selected, t('ui_casting_help'),
                              t('ui_casting_source', cost=original.get('energy', spell.base_cost),
                                time=original.get('casting_time', spell.casting_time_seconds)),
                              t('ui_field_prerequisites') + ': ' + (', '.join(map(str, spell.prerequisites)) or '—')))
        ttk.Label(self.form, text=details, wraplength=750).grid(row=0, column=0, columnspan=2, sticky='w', pady=10)
        self.entry(1, t('magic_cost_override'), self.cost)
        self.entry(2, t('magic_time_override'), self.time)
        self.action('ui_apply_parameters', self.apply_parameters)

    def apply_parameters(self):
        if self.selected != self.app.magic_spell.get():
            raise ValueError('ui_editor_selection_changed')
        values = []
        for variable in (self.cost, self.time):
            raw = variable.get().strip()
            if not raw:
                values.append('')
                continue
            value = number(raw, int)
            if value < 0:
                raise ValueError('invalid_editor_number')
            values.append(str(value))
        self.app.magic_cost_override.set(values[0])
        self.app.magic_time_override.set(values[1])
        self.destroy()
