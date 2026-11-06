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


def assert_workbench_reflow(case, layout, *, wide=None):
    """Check the rendered arrangement, including when the desktop caps a resize."""
    canvas = layout.canvas
    case.assertTrue(canvas.winfo_viewable())
    width = canvas.winfo_width()
    if wide is None:
        wide = width >= layout.WIDE
    case.assertEqual(layout.wide, wide, f'viewport={width}px, breakpoint={layout.WIDE}px')
    case.assertEqual(layout.winfo_width(), width)
    case.assertEqual(canvas.xview(), (0.0, 1.0))
    if wide:
        case.assertEqual(layout.inputs.grid_info()['row'], layout.result.grid_info()['row'])
        case.assertGreater(layout.result.winfo_rootx(), layout.inputs.winfo_rootx())
    else:
        case.assertGreater(layout.result.grid_info()['row'], layout.inputs.grid_info()['row'])
        case.assertGreater(layout.result.winfo_rooty(), layout.inputs.winfo_rooty())
