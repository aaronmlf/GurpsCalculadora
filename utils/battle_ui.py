"""Explicit eligible TS allocation; not an army or terrain rules editor."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox
from calculators.battle_modifiers import CLASSES
from utils.gui_editors import EditorWindow
from utils.editor_records import number
from utils.i18n import t
from calculators.battle_aftermath import AftermathInput, BattleAftermathEngine
from calculators.battle_modifiers import class_superiority


class BattleClassEditor(EditorWindow):
    def __init__(self, app):
        super().__init__(app, 'mass_classes_title')
        for column in range(1, 5):
            self.form.columnconfigure(column, weight=1, uniform='class_values')
        ttk.Label(self.form, text=t('mass_classes_help'), wraplength=760).grid(row=0, column=0, columnspan=5, sticky='w', pady=8)
        self.values = {}
        for col, label in enumerate(('mass_class_name', 'mass_class_a', 'mass_neutral_a', 'mass_class_d', 'mass_neutral_d')):
            ttk.Label(self.form, text=t(label), wraplength=130).grid(row=1, column=col, padx=4, sticky='w')
        for row, key in enumerate(CLASSES, 2):
            ttk.Label(self.form, text=key).grid(row=row, column=0, sticky='w')
            a = app._mass_classes.get('attacker', {}).get(key, [0, 0])
            d = app._mass_classes.get('defender', {}).get(key, [0, 0])
            variables = [tk.StringVar(self, value=str(v)) for v in a + d]
            self.values[key] = variables
            for col, variable in enumerate(variables, 1):
                ttk.Entry(self.form, textvariable=variable, width=12).grid(row=row, column=col, padx=4, pady=4, sticky='ew')
        self.action('ui_apply_parameters', self.apply_parameters)

    def apply_parameters(self):
        strengths = {'attacker': {}, 'defender': {}}
        for key, variables in self.values.items():
            values = [number(v.get(), float) for v in variables]
            if min(values) < 0:
                raise ValueError('invalid_editor_number')
            if any(values):
                strengths['attacker'][key] = values[:2]
                strengths['defender'][key] = values[2:]
        self.app._mass_classes = deepcopy(strengths)
        self.app._pending_mass_round = None
        self.app.mass_attacker_position.set(self.app.mass_attacker_position.get())
        self.destroy()


class BattleAftermathEditor(EditorWindow):
    """Explicit victor and post-battle choices; opening never changes the campaign."""
    def __init__(self, app):
        if set(app.campaign_session.battle_casualties) != {'gui.mass.attacker', 'gui.mass.defender'}:
            raise ValueError('mass_no_active_battle')
        super().__init__(app, 'mass_aftermath_title')
        self.snapshot = deepcopy(app.campaign_session.to_dict())
        self.pending = None
        self.displays = []
        self.victor = tk.StringVar(self, value=app.campaign_session.battle_ended.get('victor','attacker'))
        self.choice = tk.StringVar(self, value='hold')
        self.retreat = tk.BooleanVar(self, value=app.campaign_session.battle_ended.get('voluntary_retreat',False))
        self.leadership = tk.StringVar(self, value='10')
        self.rolls = {key: tk.StringVar(self, value='') for key in ('leadership', 'reaction', 'logistic')}
        ttk.Label(self.form, text=t('mass_aftermath_help'), wraplength=720).grid(row=0, column=0, columnspan=2, sticky='w')
        self.select(1, 'mass_aftermath_victor', self.victor, ('attacker', 'defender', 'mutual', 'neither'))
        ttk.Checkbutton(self.form, text=t('mass_aftermath_retreat'), variable=self.retreat).grid(row=2, column=0, columnspan=2, sticky='w')
        self.entry(3, t('mass_aftermath_leadership'), self.leadership)
        self.select(4, 'mass_aftermath_choice', self.choice, ('hold', 'pursue'))
        for row, key in enumerate(self.rolls, 5):
            self.entry(row, t('mass_aftermath_roll_' + key), self.rolls[key])
        self.output = ttk.Label(self.form, text='', wraplength=720, justify='left')
        self.output.grid(row=8, column=0, columnspan=2, sticky='w', pady=12)
        self.action('common_calculate', lambda: self.run(False))
        self.action('common_resolve', lambda: self.run(True))
        self.action('mass_aftermath_apply', self.apply_result)

    def select(self, row, label, canonical, choices):
        labels = {t('mass_aftermath_' + key): key for key in choices}
        display = tk.StringVar(self, value=t('mass_aftermath_' + canonical.get()))
        self.displays.append(display)
        ttk.Label(self.form, text=t(label)).grid(row=row, column=0, sticky='w', pady=4)
        box = ttk.Combobox(self.form, textvariable=display, values=tuple(labels), state='readonly')
        box.grid(row=row, column=1, sticky='ew', padx=8)
        box.bind('<<ComboboxSelected>>', lambda event: canonical.set(labels[display.get()]))

    def inputs(self):
        return (self.victor.get(), self.choice.get(), self.retreat.get(), self.leadership.get(),
                *(v.get() for v in self.rolls.values()))

    def run(self, resolve):
        self.pending = None
        session = self.app.campaign_session
        if session.to_dict() != self.snapshot:
            raise ValueError('stale_battle_result')
        a, d = 'gui.mass.attacker', 'gui.mass.defender'
        ats, dts = session.forces[a].troop_strength, session.forces[d].troop_strength
        ab, db = class_superiority(session.battle_class_strengths.get(a, {}), session.battle_class_strengths.get(d, {}),
                                   ats, dts, session.battle_encounter)
        superiority = ab if self.victor.get() == 'attacker' else db
        data = AftermathInput(session.battle_casualties[a], session.battle_casualties[d], ats, dts,
            self.victor.get(), voluntary_retreat=self.retreat.get(), choice=self.choice.get(),
            leadership=number(self.leadership.get(), int), cavalry_superiority=superiority.get('Cav', 0) > 0,
            air_superiority=superiority.get('Air', 0) > 0,
            attacker_logistic_losses=session.battle_logistic_casualties.get(a, 0),
            defender_logistic_losses=session.battle_logistic_casualties.get(d, 0),
            **{key + '_roll': number(var.get(), int) if var.get().strip() else None for key, var in self.rolls.items()})
        engine = BattleAftermathEngine()
        result = engine.resolve(data) if resolve else engine.calculate(data)
        if not result.complete:
            self.output.configure(text=t('mass_aftermath_pending', roll=t('mass_aftermath_roll_' + result.pending[0].removesuffix('_roll'))))
            return
        lines = [t('mass_aftermath_action', action=t('mass_aftermath_' + result.action))]
        for side in ('attacker', 'defender'):
            lines.append(t('mass_aftermath_result', side=t('mass_aftermath_side_' + side),
                loss=result.final_casualties[side], ts=result.remaining_ts[side], logistic=result.logistic_losses[side]))
        for key, value in result.rolls.items():
            label = 'logistic' if key == 'logistics' else key
            lines.append(t('mass_aftermath_roll_value', label=t('mass_aftermath_roll_' + label), value=value))
        lines.append('Mass Combat, p. 38')
        self.output.configure(text='\n'.join(lines))
        self.pending = (data, result, self.inputs())

    def apply_result(self):
        if self.pending is None:
            raise ValueError('stale_battle_result')
        data, result, inputs = self.pending
        if self.inputs() != inputs or self.app.campaign_session.to_dict() != self.snapshot:
            raise ValueError('stale_battle_result')
        if not messagebox.askyesno(t('mass_aftermath_apply'), self.output.cget('text'), parent=self):
            return
        self.app.campaign_session.finalize_aftermath(data, result, self.snapshot)
        self.app._pending_mass_round = None
        self.app._sync_mass_fields()
        self.app._show_result(self.app.mass_result_text, [t('mass_final_applied')])
        self.destroy()
