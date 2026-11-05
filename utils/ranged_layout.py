"""Responsive Tk layout for the ranged combat workbench."""
import tkinter as tk
from tkinter import font, ttk

from utils.gui_form_state import InlineError
from utils.i18n import get_i18n, t


def wrap_label(label):
    """Wrap to the assigned width, including after a font change."""
    def fit(_event):
        available = label.winfo_width()
        if label.winfo_viewable() and available > 24:
            # Leave room for label padding and damp single-pixel changes from
            # the geometry manager as wrapping alters requested height.
            width = max(16, (available - 8) // 8 * 8)
            current = int(label.cget('wraplength') or 0)
            if not current or width < current or width >= current + 16:
                label.configure(wraplength=width)
    label.bind('<Configure>', fit, add='+')
    label.bind('<Map>', fit, add='+')
    return label


def checkbutton(parent, text, variable):
    return wrap_toggle(ttk.Checkbutton(parent, text=text, variable=variable))


def wrap_toggle(button):
    text = button.cget('text')

    def fit(_event):
        width = button.winfo_width()
        if not button.winfo_viewable() or width < 45:
            return
        measure = font.nametofont('TkDefaultFont', root=button).measure
        lines = ['']
        for word in text.split():
            line = (lines[-1] + ' ' + word).strip()
            if lines[-1] and measure(line) > width - 30:
                lines.append(word)
            else:
                lines[-1] = line
        wrapped = '\n'.join(lines)
        if button.cget('text') != wrapped:
            button.configure(text=wrapped)

    button.bind('<Configure>', fit, add='+')
    button.bind('<Map>', fit, add='+')
    return button


class FieldGrid(ttk.Frame):
    """Reposition existing field containers without replacing their widgets."""
    def __init__(self, parent, columns=3):
        super().__init__(parent)
        self.max_columns = columns
        self.items = []
        self.columns = 1
        self.columnconfigure(0, weight=1, uniform='fields')
        self.bind('<Configure>', self._fit)
        self.bind('<Map>', self._fit)

    def add(self, widget):
        self.items.append(widget)
        self._place(widget, len(self.items) - 1)

    def _place(self, widget, index):
        row, column = divmod(index, self.columns)
        widget.grid(row=row, column=column, sticky='ew', padx=4, pady=3)

    def _fit(self, _event):
        if not self.winfo_viewable():
            return
        minimum = max(145, font.nametofont('TkDefaultFont', root=self).measure('0' * 14))
        columns = min(self.max_columns, max(1, self.winfo_width() // minimum))
        if columns == self.columns:
            return
        for column in range(self.max_columns):
            self.columnconfigure(column, weight=int(column < columns), uniform='fields' if column < columns else '')
        self.columns = columns
        for index, widget in enumerate(self.items):
            self._place(widget, index)


class FieldError(InlineError):
    """Reserve a separate row below the input, also for enlarged fonts."""
    def __init__(self, widget, reveal=None):
        super().__init__(widget)
        self.reveal = reveal
        wrap_label(self.label)

    def configure(self, text):
        self.label.configure(text=text)
        if text:
            self.label.grid(row=2, column=0, sticky='ew', pady=(2, 0))
            if self.reveal is not None:
                self.reveal()
        else:
            self.label.grid_remove()


def flow_buttons(parent, buttons):
    """Wrap actions to width; return a refit callback for dynamic labels."""
    rows = [ttk.Frame(parent) for _ in buttons]
    arranged = None

    def fit(event=None):
        nonlocal arranged
        if event is not None and not parent.winfo_viewable():
            return
        width = parent.winfo_width()
        previous_rows = {button: index for index, row in enumerate(arranged or ()) for button in row}
        groups = [[]]
        used = 0
        for button in buttons:
            required = button.winfo_reqwidth() + 8
            current = groups[-1]
            # Joining rows changes the frame's requested width. Require a little
            # slack to rejoin so a one-pixel geometry adjustment cannot split and
            # rejoin the same buttons indefinitely. Split immediately if needed.
            rejoining = current and previous_rows.get(current[0]) != previous_rows.get(button)
            if current and used + required > width - (8 if rejoining else 0):
                groups.append([])
                used = 0
            groups[-1].append(button)
            used += required
        if groups == arranged:
            return
        arranged = groups
        for button in buttons:
            button.pack_forget()
        for row in rows:
            row.pack_forget()
        for row, group in zip(rows, groups):
            row.pack(fill='x')
            for button in group:
                button.pack(in_=row, side='left', fill='x', expand=True, padx=4, pady=3)
                # `in_` does not reparent a Tk window. Keep the button above
                # the sibling frame used as its geometry container.
                button.lift(row)

    parent.bind('<Configure>', fit, add='+')
    parent.bind('<Map>', fit, add='+')
    fit()
    return fit


class Disclosure(ttk.Frame):
    """A collapsible section; opening it never marks a calculation stale."""
    def __init__(self, parent, caption, on_toggle):
        super().__init__(parent)
        self.caption = caption
        self.toggle = ttk.Button(self, command=on_toggle)
        self.toggle.pack(fill='x')
        self.section = ttk.Frame(self, padding=(0, 4))
        self.expanded = False
        self.show(False)

    def show(self, visible):
        self.expanded = visible
        self.toggle.configure(text=('▾ ' if visible else '▸ ') + self.caption)
        if visible:
            self.section.pack(fill='x')
        else:
            self.section.pack_forget()


class RangedWorkbench(ttk.Frame):
    """Fit the form and result to one vertically scrollable viewport."""
    WIDE = 900

    def __init__(self, tab, background):
        self.canvas = tk.Canvas(tab, bg=background, highlightthickness=0)
        super().__init__(self.canvas, padding=(12, 8))
        scrollbar = ttk.Scrollbar(tab, orient='vertical', command=self.canvas.yview)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self._window = self.canvas.create_window(0, 0, anchor='nw', window=self)
        self._viewport_width = 0
        self.bind('<Configure>', self._update_scrollregion)
        self.canvas.bind('<Configure>', self._resize)
        tab.bind('<Map>', self._resize, add='+')
        self.canvas.bind('<Map>', self._resize, add='+')
        self.header = ttk.Frame(self)
        self.header.pack(fill='x', pady=(0, 8))
        self.body = ttk.Frame(self)
        self.body.pack(fill='both', expand=True)
        self.inputs = ttk.Frame(self.body)
        self.result = ttk.Frame(self.body)
        self.metric_values = None
        self.wide = None
        self._place(False)

    def create_metrics(self, parent):
        row = FieldGrid(parent, columns=2)
        row.pack(fill='x', pady=(0, 8))
        values = []
        for key in ('ranged_metric_skill', 'ranged_metric_chance'):
            cell = ttk.Frame(row, padding=(6, 4))
            wrap_label(ttk.Label(cell, text=t(key))).pack(fill='x')
            value = ttk.Label(cell, style='Metric.TLabel')
            value.pack(anchor='w')
            values.append(value)
            row.add(cell)
        self.metric_values = tuple(values)

    def set_metrics(self, metrics):
        if self.metric_values is None:
            return
        if metrics is None:
            values = ('—', '—')
        else:
            skill, chance = metrics
            chance_text = f'{chance:.1f}'
            if get_i18n().get_language() == 'pt_BR':
                chance_text = chance_text.replace('.', ',')
            values = (str(skill), chance_text + '%')
        for label, value in zip(self.metric_values, values):
            label.configure(text=value)

    def _update_scrollregion(self, _event):
        if self.canvas.winfo_viewable():
            self.canvas.configure(scrollregion=self.canvas.bbox(self._window))

    def _resize(self, _event):
        # A notebook can queue Configure events for its hidden pages. Fitting
        # those pages feeds their changing requisitions back into the notebook.
        if not self.canvas.winfo_viewable():
            return
        width = self.canvas.winfo_width()
        if width != self._viewport_width:
            self._viewport_width = width
            self.canvas.itemconfigure(self._window, width=width)
            self._place(width >= self.WIDE)
        self._update_scrollregion(None)

    def _place(self, wide):
        if self.wide == wide:
            return
        self.wide = wide
        self.body.columnconfigure(0, weight=3 if wide else 1, uniform='workbench' if wide else '')
        self.body.columnconfigure(1, weight=2 if wide else 0, uniform='workbench' if wide else '')
        self.inputs.grid(row=0, column=0, sticky='new', padx=(0, 8) if wide else 0)
        self.result.grid(row=0 if wide else 1, column=1 if wide else 0,
                         sticky='new', pady=0 if wide else (8, 0))

    def reveal(self, widget, *, align_top=False):
        if not widget.winfo_ismapped():
            return
        top = widget.winfo_rooty() - self.winfo_rooty()
        current = self.canvas.canvasy(0)
        end = top + widget.winfo_height()
        height = self.canvas.winfo_height()
        if align_top or top < current:
            offset = top
        elif end > current + height:
            offset = end - height
        else:
            return
        self.canvas.yview_moveto(max(0, offset) / max(1, self.winfo_height()))

    def bind_scrolling(self):
        """Keyboard focus follows the form; the wheel scrolls its viewport."""
        def wheel(event):
            if event.num == 4:
                direction = -1
            elif event.num == 5:
                direction = 1
            else:
                if not event.delta:
                    return 'break'
                step = max(1, abs(event.delta) // 120)
                direction = -step if event.delta > 0 else step
            self.canvas.yview_scroll(direction, 'units')
            return 'break'

        def focus(event):
            if isinstance(event.widget, (ttk.Entry, ttk.Button, ttk.Checkbutton, ttk.Radiobutton, ttk.Menubutton)):
                self.reveal(event.widget)

        # Descendants share four Tcl callbacks rather than each registering
        # their own. Remove the private bindtag on language/theme rebuilds.
        tag = 'RangedScroll:' + str(self)
        bindings = {sequence: self.bind_class(tag, sequence, handler) for sequence, handler in (
            ('<FocusIn>', focus), ('<MouseWheel>', wheel), ('<Button-4>', wheel), ('<Button-5>', wheel),
        )}
        root = self.winfo_toplevel()

        def cleanup(_event):
            for sequence, callback in bindings.items():
                self.unbind_class(tag, sequence)
                root.deletecommand(callback)

        self.bind('<Destroy>', cleanup, add='+')

        def visit(widget):
            if isinstance(widget, tk.Text):
                return
            tags = widget.bindtags()
            if tag not in tags:
                widget.bindtags((tag, *tags))
            for child in widget.winfo_children():
                visit(child)

        visit(self.canvas)
