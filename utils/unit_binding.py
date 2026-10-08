"""Tk presentation adapter. Stored values always retain their original units."""
import math
import tkinter as tk
from tkinter import ttk


class UnitBinding:
    def __init__(self, widget, canonical, factor, symbol):
        self.canonical = canonical
        self.factor = factor  # canonical value * factor = displayed value
        self.symbol = symbol
        self.display = tk.StringVar(master=widget)
        self.busy = False
        self.refresh()
        widget.configure(textvariable=self.display)
        if isinstance(widget, ttk.Spinbox):
            widget.configure(from_=float(widget.cget('from')) * factor,
                             to=float(widget.cget('to')) * factor, increment=0.1)
        self.source_trace = canonical.trace_add("write", self.refresh)
        self.display_trace = self.display.trace_add("write", self.commit)

    def refresh(self, *_):
        if self.busy:
            return
        self.busy = True
        try:
            raw = self.canonical.get()
            try:
                value = float(raw) * self.factor
                self.display.set(format(value, '.15g') if math.isfinite(value) else str(raw))
            except (ValueError, TypeError):
                self.display.set(raw)
        except tk.TclError:
            self.display.set("")
        finally:
            self.busy = False

    def commit(self, *_):
        if self.busy:
            return
        self.busy = True
        try:
            raw = self.display.get().replace(',', '.')
            try:
                number = float(raw)
                self.canonical.set(number / self.factor if math.isfinite(number) else "invalid")
            except ValueError:
                # Never silently calculate the last valid value after an invalid edit.
                self.canonical.set(raw)
        finally:
            self.busy = False

    def close(self):
        self.canonical.trace_remove("write", self.source_trace)
        self.display.trace_remove("write", self.display_trace)
