"""Presentation-only form validation and result snapshots; no engine calls."""
import math
import tkinter as tk
from tkinter import ttk
from utils.i18n import t


def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)


def numeric_error(raw, integer=False, optional=False):
    if optional and not raw.strip():
        return ''
    try:
        number = float(raw.replace(',', '.'))
        if not math.isfinite(number) or (integer and not number.is_integer()):
            raise ValueError
    except ValueError:
        return t('ui_integer_required' if integer else 'ui_number_required')
    return ''


class InlineError:
    """Show an error below a grid field without changing neighboring columns."""
    def __init__(self, widget):
        self.widget = widget
        self.grid = widget.grid_info()
        color = '#b42318' if widget.winfo_toplevel().cget('background') == '#f2f4f7' else '#ff8585'
        self.label = ttk.Label(widget.master, foreground=color, wraplength=155)

    def configure(self, text):
        self.label.configure(text=text)
        if self.grid:
            if text:
                self.label.grid(row=self.grid['row'], column=self.grid['column'], sticky='sw', pady=(30, 0))
                self.widget.grid_configure(sticky='nw', pady=(5, 42))
            else:
                self.label.grid_remove()
                self.widget.grid_configure(sticky=self.grid['sticky'], pady=self.grid['pady'])
        elif self.widget.winfo_manager() == 'pack':
            if text:
                self.label.pack(side='left', after=self.widget, padx=4)
            else:
                self.label.pack_forget()


class FormState:
    def __init__(self, app, tab):
        self.app, self.tab = app, tab
        self.widgets = list(descendants(tab))
        self.boxes = [w for w in self.widgets if isinstance(w, tk.Text) and hasattr(w, 'comparison')]
        self.traces = []
        self.errors = {}
        self.fields = []
        self.restoring = False
        variables = {}
        for widget in self.widgets:
            if 'textvariable' in widget.keys():
                name = str(widget.cget('textvariable'))
            elif 'variable' in widget.keys():
                name = str(widget.cget('variable'))
            else:
                continue
            if not name:
                continue
            if name not in variables:
                variables[name] = tk.StringVar(master=tab, name=name)
            if isinstance(widget, ttk.Spinbox) and not hasattr(widget, 'numeric_spec'):
                canonical = next((value for value in vars(app).values()
                                  if isinstance(value, tk.Variable) and str(value) == name), None)
                widget.numeric_spec = {'integer': isinstance(canonical, tk.IntVar), 'optional': False}
                widget.validation_label = InlineError(widget)
            if hasattr(widget, 'numeric_spec'):
                self.fields.append((widget, variables[name], widget.numeric_spec))
        self.variables = variables
        for widget, variable, spec in self.fields:
            if any(str(binding.display) == str(variable) for binding in app._unit_bindings):
                widget.numeric_spec = dict(spec, integer=False)
        self.fields = [(w, v, w.numeric_spec) for w, v, spec in self.fields]
        commands = {t(key) for key in ('common_calculate', 'common_resolve', 'powers_build',
                                       'social_reaction', 'social_influence',
                                       'knockback_calculate', 'knockback_check_button', 'slam_calculate',
                                       'falls_calculate', 'collisions_calculate', 'explosions_calculate',
                                       'falling_objects_calculate')}
        commands.update(t(key) for key in ('ranged_calculate', 'ranged_roll_attack', 'ranged_resolve',
                                          'melee_roll_attack', 'melee_resolve', 'injury_resolve_checks', 'grapple_resolve'))
        for widget in self.widgets:
            if isinstance(widget, ttk.Button) and widget.cget('text') in commands:
                original = widget.cget('command')
                def invoke(original=original):
                    if self.validate():
                        for field, variable, spec in self.fields:
                            raw = variable.get()
                            if raw.strip():
                                normalized = (str(int(float(raw.replace(',', '.')))) if spec['integer']
                                              else raw.replace(',', '.'))
                                if normalized != raw:
                                    variable.set(normalized)
                        self.tab.tk.call(original)
                    elif self.errors:
                        next(iter(self.errors)).focus_set()
                widget.configure(command=invoke)
        for variable in variables.values():
            token = variable.trace_add('write', self.edited)
            self.traces.append((variable, token))
        for box in self.boxes:
            box.form_state = self
            box.stale = False
            box.origin = ''
        self.validate()

    def validate(self):
        self.errors.clear()
        for widget, variable, spec in self.fields:
            error = numeric_error(variable.get(), **spec)
            widget.state(['invalid'] if error else ['!invalid'])
            widget.validation_label.configure(text=error)
            if error:
                self.errors[widget] = error
        return not self.errors

    def edited(self, *_):
        self.validate()
        for box in self.boxes:
            if box.get('1.0', 'end-1c').strip():
                box.stale = True
                self.status(box)

    def result_changed(self, box):
        value = box.get('1.0', 'end-1c')
        box._last_output = value
        box.stale = False
        box.origin = self.app.i18n.get_language() + ' / ' + self.app.result_units.get()
        entry = (box.origin, value)
        if value.strip() and (not box.comparison.history or box.comparison.history[-1] != entry):
            box.comparison.history.append(entry)
            box.comparison.history = box.comparison.history[-20:]
        self.status(box)

    def status(self, box):
        message = t('ui_result_stale') if box.stale else ''
        current = self.app.i18n.get_language() + ' / ' + self.app.result_units.get()
        if box.origin and box.origin != current:
            message += ('\n' if message else '') + t('ui_result_original', context=box.origin)
        box.status_label.configure(text=message)

    def close(self):
        for variable, token in self.traces:
            variable.trace_remove('write', token)
        # These are aliases of existing Tcl variables. Do not let StringVar's
        # destructor unset variables still owned by the application.
        for variable in self.variables.values():
            variable._tk = None
        self.traces.clear()


def capture_results(app):
    saved = {}
    for name, box in vars(app).items():
        if isinstance(box, tk.Text) and hasattr(box, 'comparison'):
            saved[name] = (box.get('1.0', 'end-1c'), box.comparison.saved,
                           getattr(box, 'stale', False), getattr(box, 'origin', ''), list(box.comparison.history))
    for form in getattr(app, '_form_states', []):
        form.close()
    return saved


def install_form_states(app, saved):
    app._form_states = [FormState(app, app.root.nametowidget(tab)) for tab in app.notebook.tabs()]
    for name, (text, comparison, stale, origin, history) in saved.items():
        box = getattr(app, name)
        box.delete('1.0', 'end')
        box.insert('1.0', text)
        box.edit_modified(False)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        box.summary_label.configure(text='  |  '.join(lines[:2]) if lines else t('ui_result_empty'))
        box._last_output = text
        box.stale, box.origin = stale, origin
        box.comparison.saved = comparison
        box.comparison.history = history
        if comparison:
            box.comparison.button.configure(state='normal')
        box.form_state.status(box)
