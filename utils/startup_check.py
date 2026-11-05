"""Opt-in check that the built app can map its Tk window in an empty profile."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

REPORT_NAME = 'startup-check.json'
PROFILE_ENV = 'GURPS_CALCULADORA_DATA_DIR'


def run(app_factory):
    from utils.weapon_catalog import application_data_dir
    from version import __version__

    report = Path.cwd() / REPORT_NAME
    if report.exists() or report.is_symlink():
        raise FileExistsError(report)
    previous_profile = os.environ.get(PROFILE_ENV)
    try:
        with TemporaryDirectory(prefix='gurps-startup-profile-') as directory:
            profile = Path(directory).resolve()
            os.environ[PROFILE_ENV] = str(profile)
            if application_data_dir().resolve() != profile:
                raise RuntimeError('Startup check could not isolate the user profile')
            app = app_factory()
            try:
                app.root.update_idletasks()
                app.root.update()
                if not app.root.winfo_viewable():
                    raise RuntimeError('The main window did not become visible')
                result = {
                    'main_window': True,
                    'version': __version__,
                    'title': app.root.title(),
                    'tk': app.root.tk.call('package', 'provide', 'Tk'),
                    'tool_count': len(app.notebook.tabs()),
                }
            finally:
                app.root.destroy()
    finally:
        if previous_profile is None:
            os.environ.pop(PROFILE_ENV, None)
        else:
            os.environ[PROFILE_ENV] = previous_profile
    with report.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False)
