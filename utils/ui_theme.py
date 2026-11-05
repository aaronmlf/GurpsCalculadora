"""Oficina palette and native Tk styles; no assets or external dependencies."""
import re


THEME_FIELDS = ('bg', 'panel', 'accent')
DEFAULTS = {
    'dark': {'bg': '#141d2e', 'panel': '#202c43', 'accent': '#2859dc', 'sidebar': '#101725'},
    'light': {'bg': '#f2f4f7', 'panel': '#ffffff', 'accent': '#2455c7', 'sidebar': '#e9eef7'},
}


def clean_theme_colors(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for theme in DEFAULTS:
        values = value.get(theme)
        if isinstance(values, dict):
            valid = {key: color.lower() for key, color in values.items()
                     if key in THEME_FIELDS and isinstance(color, str)
                     and re.fullmatch(r'#[0-9a-fA-F]{6}', color)}
            if valid:
                result[theme] = valid
    return result


def _channels(color):
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def _mix(first, second, fraction):
    return '#' + ''.join(f'{round(a + (b - a) * fraction):02x}'
                         for a, b in zip(_channels(first), _channels(second)))


def contrast(first, second):
    def luminance(color):
        values = [v / 255 for v in _channels(color)]
        return sum(weight * (v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4)
                   for weight, v in zip((.2126, .7152, .0722), values))
    low, high = sorted((luminance(first), luminance(second)))
    return (high + .05) / (low + .05)


def _ink(background, preferred=('#eff3fa', '#17212b')):
    return next((color for color in preferred if contrast(color, background) >= 4.5),
                max(('#ffffff', '#000000'), key=lambda color: contrast(color, background)))


def make_palette(theme='dark', overrides=None):
    theme = theme if theme in DEFAULTS else 'dark'
    custom = clean_theme_colors(overrides).get(theme, {})
    palette = {**DEFAULTS[theme], **custom}
    bg, panel, accent = (palette[key] for key in THEME_FIELDS)
    if 'bg' in custom or 'panel' in custom:
        palette['sidebar'] = _mix(bg, _ink(bg), .05)
    fg = _ink(bg)
    palette.update(surface=panel, fg=fg, panel_fg=_ink(panel), sidebar_fg=_ink(palette['sidebar']),
                   accent_fg=_ink(accent), border=_mix(bg, fg, .24), button=panel,
                   hover=_mix(panel, _ink(panel), .10), pressed=_mix(panel, _ink(panel), .16),
                   muted=_ink(bg, (_mix(bg, fg, .72), fg)),
                   accent_text=_ink(bg, (accent, fg)),
                   error=_ink(bg, ('#ff9d9d', '#9b1c1c', fg)),
                   warning=_ink(bg, ('#ffd297', '#854d0e', fg)),
                   success=_ink(bg, ('#9ae6b4', '#166534', fg)))
    return palette


def apply_theme(root, colors):
    from tkinter import ttk

    style = ttk.Style(root)
    style.theme_use('clam')
    bg, fg, panel, panel_fg, border, accent = (colors[key] for key in
        ('bg', 'fg', 'panel', 'panel_fg', 'border', 'accent'))
    root.configure(bg=bg)
    style.configure('.', background=bg, foreground=fg, bordercolor=border,
                    lightcolor=border, darkcolor=border, troughcolor=bg,
                    selectbackground=accent, selectforeground=colors['accent_fg'])
    for name in ('TFrame', 'TLabel', 'TLabelframe', 'TLabelframe.Label',
                 'TNotebook', 'TCheckbutton', 'TRadiobutton'):
        style.configure(name, background=bg, foreground=fg)
    style.configure('TLabelframe', borderwidth=1, relief='solid')
    style.configure('TNotebook.Tab', background=panel, foreground=panel_fg, padding=(10, 5))
    style.map('TNotebook.Tab', background=[('selected', accent)],
              foreground=[('selected', colors['accent_fg'])])
    style.configure('Title.TLabel', foreground=fg, font=('Arial', 15, 'bold'))
    style.configure('PageTitle.TLabel', foreground=fg, font=('Arial', 23, 'bold'))
    style.configure('ResultSummary.TLabel', foreground=fg, font=('Arial', 12, 'bold'))
    style.configure('Result.TLabelframe', background=bg, bordercolor=border, relief='solid')
    style.configure('Result.TLabelframe.Label', foreground=colors['accent_text'], background=bg)
    style.configure('Subtitle.TLabel', foreground=colors['muted'], font=('Arial', 10))
    style.configure('Metric.TLabel', foreground=fg, font=('Arial', 20, 'bold'))
    style.configure('Muted.TLabel', foreground=colors['muted'])
    style.configure('Error.TLabel', foreground=colors['error'])
    style.configure('Warning.TLabel', foreground=colors['warning'])
    style.configure('Sidebar.TFrame', background=colors['sidebar'])
    style.configure('Sidebar.TLabel', background=colors['sidebar'], foreground=colors['sidebar_fg'])
    style.configure('Header.TFrame', background=bg)
    style.configure('Brand.TLabel', background=bg, foreground=fg, font=('Arial', 11, 'bold'))
    style.configure('TButton', background=panel, foreground=panel_fg, padding=(9, 5), width=0,
                    borderwidth=1, focuscolor=colors['accent_text'])
    style.map('TButton', background=[('disabled', bg), ('pressed', colors['pressed']),
                                    ('active', colors['hover'])],
              foreground=[('disabled', colors['muted']), ('pressed', _ink(colors['pressed'])),
                          ('active', _ink(colors['hover']))])
    style.configure('TMenubutton', background=panel, foreground=panel_fg, padding=(7, 5), width=0,
                    arrowsize=10, arrowcolor=panel_fg)
    style.map('TMenubutton', background=[('active', colors['hover'])],
              foreground=[('active', _ink(colors['hover']))])
    active = _mix(accent, colors['accent_fg'], .10)
    pressed = _mix(accent, colors['accent_fg'], .16)
    style.configure('Primary.TButton', background=accent, foreground=colors['accent_fg'],
                    bordercolor=accent, padding=(12, 6), focuscolor=colors['accent_fg'])
    style.map('Primary.TButton', background=[('disabled', bg), ('pressed', pressed), ('active', active)],
              foreground=[('disabled', colors['muted']), ('pressed', _ink(pressed)), ('active', _ink(active))])
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=panel, background=panel, foreground=panel_fg,
                        insertcolor=panel_fg, padding=(5, 3), arrowsize=12)
        style.map(name, fieldbackground=[('disabled', bg), ('readonly', panel)],
                  foreground=[('disabled', colors['muted']), ('readonly', panel_fg)],
                  bordercolor=[('invalid', colors['error']), ('focus', colors['accent_text'])])
    for name in ('TScrollbar', 'Vertical.TScrollbar', 'Horizontal.TScrollbar'):
        style.configure(name, arrowsize=11, background=panel, troughcolor=bg, arrowcolor=fg)
        style.map(name, background=[('pressed', colors['pressed']), ('active', colors['hover'])])
    style.configure('TProgressbar', background=accent)
    for widget_class in ('Text', 'Listbox'):
        root.option_add(f'*{widget_class}.background', panel, 80)
        root.option_add(f'*{widget_class}.foreground', panel_fg, 80)
        root.option_add(f'*{widget_class}.selectBackground', accent, 80)
        root.option_add(f'*{widget_class}.selectForeground', colors['accent_fg'], 80)
    root.option_add('*Text.insertBackground', panel_fg, 80)
