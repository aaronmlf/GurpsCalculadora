"""Skip GUI tests only if Tk itself cannot open, including on native Windows."""
from functools import lru_cache
import os
import unittest


@lru_cache(maxsize=1)
def _unavailable_reason():
    try:
        import tkinter
    except ImportError as exc:
        return str(exc)
    try:
        root = tkinter.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
    except tkinter.TclError as exc:
        return str(exc)
    return ''


def requires_tk(case):
    reason = _unavailable_reason()
    if reason and os.environ.get('GURPS_REQUIRE_TK') == '1':
        raise RuntimeError(f'GUI tests required but Tk is unavailable: {reason}')
    return unittest.skipIf(bool(reason), f'Tk unavailable: {reason}')(case)
