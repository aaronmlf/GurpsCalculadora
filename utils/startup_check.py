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
    previous_camera = None
    for language in ('pt_BR', 'en_US'):
        app._change_language(language)
        app.choose_tool(BATTLE_MAP_TOOL)
        app.root.update()
        panel = app.battle_map_panel
        if (not player.winfo_viewable() or player.title() != t('map_players')
                or len(player.canvas.scene.tokens) != 1
                or player.canvas.scene.tokens[0].label != session.combatants[actor].name):
            raise RuntimeError('The player view exposed a hidden token or did not update')
        if previous_camera is not None and (player.canvas._center, player.canvas._scale) != previous_camera:
            raise RuntimeError('Changing language reset the player camera')
        for canvas in (panel.canvas, player.canvas):
            canvas.fit()
            for _ in range(35):
                canvas.zoom_out()
        app.root.update()
        if not all(canvas.find_withtag('map-grid') and canvas.find_withtag('map-grid-overview')
                   for canvas in (panel.canvas, player.canvas)):
            raise RuntimeError('The overview grid disappeared when zooming out')
        previous_camera = (player.canvas._center, player.canvas._scale)
        panel.send_distance()
        if (app._current_tool != 8 or app._current_ranged_input().distance_in_yards != 7
                or app.i18n.get_language() != language):
            raise RuntimeError('The battle map distance did not reach the Ranged tool')
        geometry = panel.state
        panel.commit(geometry.with_token(target, 8, 0))
        try:
            app._current_ranged_input()
        except ValueError as exc:
            if str(exc) != t('ranged_map_distance_stale'):
                raise
        else:
            raise RuntimeError('Ranged accepted a stale measurement after a token moved')
        panel.commit(geometry)


def _check_quick_tables(app):
    from utils.i18n import t
    from utils.quick_tables_packages import PACKAGE_IDS
    from utils.ui_preferences import BATTLE_MAP_TOOL, QUICK_TABLES_TOOL

    original = app.combat_session.to_dict()
    for language, units in (('pt_BR', 'metric'), ('en_US', 'imperial')):
        app._change_language(language)
        app.result_units.set(units)
        app._change_units()
        app.choose_tool(BATTLE_MAP_TOOL)
        app.battle_map_panel.map_menu.invoke(t('tab_quick_tables'))
        app.root.update()
        panel = app.quick_tables_panel
        if (not panel.canvas.winfo_viewable() or app._current_tool != QUICK_TABLES_TOOL
                or app.notebook.tab(QUICK_TABLES_TOOL, 'text') != t('tab_quick_tables')
                or panel.range_result.modifier != -3
                or abs(float(panel.range_distance_entry.get()) - (7 if units == 'imperial' else 6.4008)) > 1e-10):
            raise RuntimeError('Quick Tables did not load the correct battle map distance or units')
        panel.ambient_var.set('full_moon')
        if panel.illumination_result.modifier != -4:
            raise RuntimeError('Quick Tables did not resolve the full-moon lighting preset')
        panel.send_current_lighting()
        panel.send_range()
        data = app._current_ranged_input()
        if app._current_tool != 8 or data.map_distance_yards != 7 or data.illumination_modifier != -4:
            raise RuntimeError('Quick Tables did not send lighting and distance to Ranged')
        app.choose_tool(QUICK_TABLES_TOOL)
        panel.show_page('reference')
        reference = panel.reference
        reference.query.set('hearing')
        reference.inputs['hearing_distance'].set('8')
        app.root.update()
        unit = 'yd' if units == 'imperial' else 'm'
        hearing = reference.result
        if (reference.current.key != 'hearing' or not reference.readout.winfo_viewable()
                or hearing.lines[1].arguments.get('modifier') != -3
                or f' {unit}' not in reference.readout.cget('text')
                or t(reference.current.title) == reference.current.title):
            raise RuntimeError('The Quick Tables reference did not resolve hearing in the selected language/units')
        reference.query.set('sup_df_treasure_cost')
        if reference.enabled_packages or reference.current is not None:
            raise RuntimeError('Quick Tables did not start with only the Basic Set Revised')
        reference.package_menu.invoke(PACKAGE_IDS.index('treasure'))
        if (reference.current is None or reference.current.package != 'treasure'
                or not reference.current.requirement
                or t('qt_sfant_cost_total_result', value='100.00') not in reference.readout.cget('text')):
            raise RuntimeError('The Quick Tables supplement did not resolve when enabled')
        reference.package_menu.invoke('end')
        if reference.current is not None or app.ui_preferences['quick_tables_packs']:
            raise RuntimeError('Disabling a Quick Tables supplement did not restore Basic-only lookup')
        reference.query.set('terrain')
        if reference.current.key != 'terrain' or not reference.result.expression:
            raise RuntimeError('The terrain reference did not offer a dice expression')
        reference._send_expression()
        if app._current_tool != 15 or app.gm_dice_last_result is not None:
            raise RuntimeError('A reference did not prepare Dice without rolling')
        reference.query.set('')
    if original != app.combat_session.to_dict():
        raise RuntimeError('Quick Tables unexpectedly changed the encounter')


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
                _check_quick_tables(app)
                result['encounter_map_ranged'] = True
                result['map_zoom_grid'] = True
                result['map_stale_distance_blocked'] = True
                result['quick_tables_lighting_range'] = True
                result['quick_tables_map_ranged'] = True
                result['quick_tables_exploration'] = True
                result['quick_tables_supplements'] = True
                result['quick_tables_units_checked'] = ['metric', 'imperial']
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
