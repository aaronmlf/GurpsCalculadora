"""Versioned, atomic UI preferences, independent of existing session files."""
import json
import os
from pathlib import Path
import tempfile


def clean_preferences(value):
    result = {'schema': 1, 'theme': 'dark', 'font_size': 10, 'favorites': [], 'recent': [],
              'last_tool': 'home', 'window': '1024x768', 'sidebar_hidden': False, 'catalog_favorites': []}
    if not isinstance(value, dict):
        return result
    if value.get('theme') in ('light', 'dark'):
        result['theme'] = value['theme']
    if type(value.get('sidebar_hidden')) is bool:
        result['sidebar_hidden'] = value['sidebar_hidden']
    if type(value.get('font_size')) is int and 9 <= value['font_size'] <= 18:
        result['font_size'] = value['font_size']
    for key in ('favorites', 'recent'):
        if isinstance(value.get(key), list):
            result[key] = list(dict.fromkeys(item for item in value[key]
                                            if type(item) is int and 0 <= item < 16))[:16]
    if isinstance(value.get('catalog_favorites'), list):
        result['catalog_favorites'] = list(dict.fromkeys(item for item in value['catalog_favorites']
                                                        if isinstance(item, str) and 0 < len(item) < 300))[:1000]
    selected = value.get('last_tool')
    if selected == 'home' or type(selected) is int and 0 <= selected < 16:
        result['last_tool'] = selected
    size = str(value.get('window', '')).split('x')
    if len(size) == 2 and all(s.isdigit() for s in size) and 800 <= int(size[0]) <= 3840 and 600 <= int(size[1]) <= 2160:
        result['window'] = 'x'.join(size)
    return result


def load_ui_preferences(path):
    try:
        return clean_preferences(json.loads(Path(path).read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return clean_preferences({})


def save_ui_preferences(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(clean_preferences(value), handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
