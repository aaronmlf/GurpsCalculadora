"""Input cards for the movement and impact calculators."""
import tkinter as tk
from tkinter import ttk

from utils.i18n import t
from utils.ranged_layout import FieldError, FieldGrid, checkbutton, flow_buttons, wrap_label


class ImpactForm:
    def __init__(self, layout, reference):
        self.layout = layout
        ttk.Label(layout.header, text=f'Basic Set · {reference}', style='Subtitle.TLabel').pack(anchor='w')

    def paired(self):
        row = FieldGrid(self.layout.inputs, columns=2)
        row.pack(fill='x')
        return row

    def panel(self, title_key, parent=None):
        parent = self.layout.inputs if parent is None else parent
        group = ttk.Frame(parent)
        if isinstance(parent, FieldGrid):
            parent.add(group)
        else:
            group.pack(fill='x', pady=(0, 7))
        title = t(title_key).strip('- ').rstrip(':')
        wrap_label(ttk.Label(group, text=title, style='Subtitle.TLabel')).pack(fill='x', pady=(0, 3))
        card = ttk.LabelFrame(group, padding=6)
        card.pack(fill='x')
        return card

    @staticmethod
    def spin(parent, *fields, columns=3):
        grid = FieldGrid(parent, columns=columns)
        grid.pack(fill='x')
        for label_key, variable, lower, upper in fields:
            cell = ttk.Frame(grid)
            cell.columnconfigure(0, weight=1)
            label = wrap_label(ttk.Label(cell, text=t(label_key)))
            label.grid(row=0, column=0, sticky='ew', pady=(0, 2))
            entry = ttk.Spinbox(cell, from_=lower, to=upper, textvariable=variable, width=1)
            entry.grid(row=1, column=0, sticky='ew')
            entry.unit_label = label
            entry.numeric_spec = {'integer': isinstance(variable, tk.IntVar), 'optional': False}
            entry.validation_label = FieldError(entry)
            grid.add(cell)

    @staticmethod
    def choices(parent, variable, *options):
        row = ttk.Frame(parent)
        row.pack(fill='x')
        flow_buttons(row, [ttk.Radiobutton(row, text=t(key), variable=variable, value=value)
                           for key, value in options])

    @staticmethod
    def check(parent, label_key, variable):
        checkbutton(parent, t(label_key), variable).pack(fill='x', padx=4, pady=3)

    def actions(self, parent, *actions, primary=None):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(2, 7))

        flow_buttons(row, [
            ttk.Button(row, text=t(key), style='Primary.TButton' if key == primary else 'TButton', command=command)
            for key, command in actions
        ])

    def calculate(self, key, command):
        self.actions(self.layout.inputs, (key, command), primary=key)
