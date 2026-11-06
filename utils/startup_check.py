"""Opt-in packaged GUI check in an empty profile."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

REPORT_NAME = 'startup-check.json'
PROFILE_ENV = 'GURPS_CALCULADORA_DATA_DIR'


def _check_encounter_workflow(app):
    from utils.gui_hub import session_window
    from utils.i18n import t
    from utils.ui_preferences import BATTLE_MAP_TOOL

    session = app.combat_session
    actor, target = session.selected_pair()
    prep = session_window(app)
    app.root.update()
    if not prep.winfo_viewable():
        raise RuntimeError('The encounter preparation window did not become visible')
    prep.destroy()

    app.choose_tool(BATTLE_MAP_TOOL)
    panel = app.battle_map_panel
    panel.place_token(actor, *panel.state.cell_center(0, 0))
    panel.place_token(target, *panel.state.cell_center(7, 0))
    panel.select_token(actor)
    panel.visible_to_players.set(True)
    panel._toggle_visibility()
    app.combat_library.save_session('Smoke check', session)
    app._replace_active_session(app.combat_library.open_session('Smoke check', session.autosave_path))
    player = panel.open_player_view()
    for language in ('pt_BR', 'en_US'):
        app._change_language(language)
        app.choose_tool(BATTLE_MAP_TOOL)
        app.root.update()
        panel = app.battle_map_panel
        if (not player.winfo_viewable() or player.title() != t('map_players')
                or len(player.canvas.scene.tokens) != 1
                or player.canvas.scene.tokens[0].label != session.combatants[actor].name):
            raise RuntimeError('The player view exposed a hidden token or did not update')
        for canvas in (panel.canvas, player.canvas):
            canvas.fit()
            for _ in range(35):
                canvas.zoom_out()
        app.root.update()
        if not all(canvas.find_withtag('map-grid') and canvas.find_withtag('map-grid-overview')
                   for canvas in (panel.canvas, player.canvas)):
            raise RuntimeError('The overview grid disappeared when zooming out')
        panel.send_distance()
        if (app._current_tool != 8 or app._current_ranged_input().distance_in_yards != 7
                or app.i18n.get_language() != language):
            raise RuntimeError('The battle map distance did not reach the Ranged tool')


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
                _check_encounter_workflow(app)
                result['encounter_map_ranged'] = True
                result['map_zoom_grid'] = True
                result['languages_checked'] = ['pt_BR', 'en_US']
            finally:
                app.root.destroy()
    finally:
        if previous_profile is None:
            os.environ.pop(PROFILE_ENV, None)
        else:
            os.environ[PROFILE_ENV] = previous_profile
    with report.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False)
