"""Verify a built application opens its main window under an isolated X server.

Usage: xvfb-run -a python3 tools/verify_gui_launch.py dist/GurpsCalculadora
       WINEPREFIX=... xvfb-run -a python3 tools/verify_gui_launch.py wine app.exe
"""
import ctypes as C
import json
import os
import subprocess
import sys
import tempfile
import time


def window_titles():
    x = C.CDLL('libX11.so.6')
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = C.c_void_p
    x.XDefaultRootWindow.argtypes = [C.c_void_p]
    x.XDefaultRootWindow.restype = C.c_ulong
    x.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                            C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
    x.XFetchName.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_void_p)]
    x.XFree.argtypes = [C.c_void_p]
    x.XCloseDisplay.argtypes = [C.c_void_p]
    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError('No X display')
    titles = []
    def visit(window, depth=0):
        name = C.c_void_p()
        if x.XFetchName(display, window, C.byref(name)) and name:
            titles.append(C.string_at(name).decode('utf-8', errors='replace'))
            x.XFree(name)
        if depth >= 3:
            return
        root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
        children = C.POINTER(C.c_ulong)()
        if x.XQueryTree(display, window, C.byref(root), C.byref(parent), C.byref(children), C.byref(count)):
            for i in range(count.value):
                visit(children[i], depth + 1)
            if children:
                x.XFree(children)
    try:
        visit(x.XDefaultRootWindow(display))
        return titles
    finally:
        x.XCloseDisplay(display)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='gurps-gui-check-') as directory:
        process = subprocess.Popen(sys.argv[1:], env={**os.environ, 'XDG_DATA_HOME': directory})
        try:
            titles = []
            for _ in range(45):
                titles = window_titles()
                if any('GURPS' in title and '1.6.0' in title for title in titles):
                    print(json.dumps({'main_window': True, 'titles': titles}))
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f'Main window did not open: {titles}')
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
