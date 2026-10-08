"""Portable numeric input presets; never import session state or Python code."""
import json
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from utils.gui_form_state import numeric_error
from utils.i18n import t


SCHEMA = 'gurps-calculadora.numeric-inputs.v1'


def fields_for(app, index):
    fields = {}
    for widget, variable, spec in app._form_states[index].fields:
        name = str(variable)
        for binding in app._unit_bindings:
            if str(binding.display) == name:
                name = str(binding.canonical)
                break
        for key, canonical in vars(app).items():
            if isinstance(canonical, tk.Variable) and str(canonical) == name:
                fields[key] = (canonical, spec)
    return fields


def validate_preset(document, index, fields):
    if not isinstance(document, dict) or document.get('schema') != SCHEMA or document.get('tool') != index:
        raise ValueError(t('ui_preset_invalid'))
    values = document.get('values')
    if not isinstance(values, dict) or not values or set(values) - set(fields):
        raise ValueError(t('ui_preset_invalid'))
    for name, value in values.items():
        if not isinstance(value, str) or numeric_error(value, **fields[name][1]):
            raise ValueError(t('ui_preset_invalid'))
    return values


def input_preset(app, importing=False):
    index = app._current_tool
    if index == 'home':
        messagebox.showinfo(t('ui_presets'), t('ui_preset_choose'))
        return
    fields = fields_for(app, index)
    try:
        if importing:
            filename = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
            if not filename:
                return
            path = Path(filename)
            if path.stat().st_size > 1024 * 1024:
                raise ValueError(t('ui_preset_invalid'))
            values = validate_preset(json.loads(path.read_text(encoding='utf-8')), index, fields)
            if not messagebox.askyesno(t('ui_presets'), t('ui_preset_confirm')):
                return
            for name, value in values.items():
                spec = fields[name][1]
                if value.strip():
                    value = str(int(float(value.replace(',', '.')))) if spec['integer'] else value.replace(',', '.')
                fields[name][0].set(value)
        else:
            if not app._form_states[index].validate():
                raise ValueError(t('ui_preset_invalid'))
            values = {name: str(variable.get()) for name, (variable, _) in fields.items()}
            document = {'schema': SCHEMA, 'tool': index, 'values': values}
            validate_preset(document, index, fields)
            filename = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
            if filename:
                Path(filename).write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    except (OSError, ValueError, tk.TclError) as exc:
        messagebox.showerror(t('ui_presets'), str(exc))
