from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from calculators.injury import StateDelta
from calculators.injury import DamagePacket
from tests.tk_support import requires_tk
from utils.gui_hub import session_window
from utils.i18n import t
from utils.ranged_handoff import RangedHitDraft


@requires_tk
class TableWorkflowGuiTests(unittest.TestCase):
    def setUp(self):
        from main import GURPSCalculator
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        patcher = patch.dict("os.environ", {"GURPS_CALCULADORA_DATA_DIR": folder.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = GURPSCalculator()
        self.addCleanup(self._close)
        self.app.root.update()

    def _close(self):
        for form in self.app._form_states:
            form.close()
        for binding in self.app._unit_bindings:
            binding.close()
        self.app.root.destroy()

    def _sheet(self, name, identifier, hp=15, current_hp=13, speed=6):
        fields = dict(st=13, dx=12, iq=11, ht=12, basic_speed=speed, hp=hp, fp=12, er_magic=5)
        current = dict(hp=current_hp, fp=9, er_magic=4)
        document = {"version": 5, "id": identifier, "profile": {"name": name},
                    "settings": {"attributes": [{"id": "er_magic", "type": "pool",
                                                  "name": "ER", "full_name": "Energy Reserve (Magic)"}]},
                    "attributes": [{"attr_id": key, "calc": dict(value=value, **(
                        {"current": current[key]} if key in current else {}))}
                                   for key, value in fields.items()]}
        path = self.folder / (identifier + ".gcs")
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_import_roster_edit_encounter_and_reopen_without_rewriting_sheets(self):
        app = self.app
        app.choose_tool("home")
        window = session_window(app)
        paths = (self._sheet("Batedor", "fixture-a", speed=6),
                 self._sheet("Guarda", "fixture-b", speed=5))
        original = {path: path.read_bytes() for path in paths}
        window.import_paths(paths)
        self.assertEqual(len(app.combat_library.imported), 2)
        self.assertEqual(app.combat_session.combatants["combatant_a"].max_hp, 10)
        window.copies.set("2")
        ids = window._add_selected()
        self.assertEqual(len(ids), 4)
        self.assertEqual(len(app.combat_session.combatants), 4)
        scouts = [key for key in ids if app.combat_session.combatants[key].name == "Batedor"]
        guards = [key for key in ids if app.combat_session.combatants[key].name == "Guarda"]
        self.assertEqual(len(scouts), 2)
        app._select_encounter_role("target", scouts[0])
        self.assertEqual(app.melee_target_hp.get(), "13")
        self.assertEqual(app.melee_defense_score.get(), "")
        with self.assertRaises(ValueError) as error:
            app._session_defense(app.combat_session.combatants[scouts[0]])
        self.assertIn(t("melee_defense_dodge"), str(error.exception))
        editor = window.edit_resources(scouts[0])
        editor.current_hp.set("7")
        editor.current_fp.set("6")
        editor.currents["er_magic"].set("1")
        editor.apply_changes()
        injured = app.combat_session.combatants[scouts[0]]
        self.assertEqual((injured.current_hp, injured.current_fp, injured.resource_pools["er_magic"]["current"]),
                         (7, 6, 1))
        self.assertEqual(app.combat_session.combatants[scouts[1]].current_hp, 13)
        self.assertEqual(app.combat_library.imported[injured.source_id].current_hp, 13)
        app.combat_session.edit_combatant_state(guards[0], group="Vigias")
        app.combat_session.move_combatant(guards[0], 0)
        app._session_changed()
        order = app.combat_session.combatant_order.copy()
        window.session_name.set("Ponte")
        window._save_session()
        app.combat_session.apply(guards[1], scouts[0], StateDelta(hp_change=-2))
        with patch("utils.combat_prep_ui.messagebox.askyesno", return_value=True):
            window._open_session()
        self.assertEqual(app.combat_session.combatants[scouts[0]].current_hp, 7)
        self.assertEqual(app.combat_session.combatants[guards[0]].group, "Vigias")
        self.assertEqual(app.combat_session.combatant_order, order)
        self.assertTrue(Path(app.combat_session.autosave_path).is_file())
        app._select_encounter_role("actor", scouts[0])
        app._swap_encounter_roles()
        self.assertEqual(app.session_target_key, scouts[0])
        self.assertIn("Batedor", app.session_target.get())
        self.assertEqual({path: path.read_bytes() for path in paths}, original)
        app._change_language("en_US")
        self.assertFalse(window.winfo_exists())
        self.assertEqual(session_window(app).title(), "Prepare session")

    def test_hit_handoff_confirms_only_once_with_real_target(self):
        app = self.app
        app.ranged_damage.set("2d")
        app.ranged_damage_type.set("pi")
        app.ranged_armor_divisor.set("2")
        app.ranged_distance.set("2")
        app.ranged_half_damage.set("1")
        app.ranged_skill.set("16")
        app.ranged_dr.set("99")
        app.ranged_dodge.set("")
        app.combat_session.combatants[app.session_target_key].armor.natural_dr = 2
        resolve = app.ranged_calc.resolve
        with patch.object(app.ranged_calc, "resolve", side_effect=lambda attack, **opts: resolve(
            attack, attack_roll=8, damage_rolls=[8], **opts,
        )):
            app._run_ranged("resolve")
        self.assertEqual(app._ranged_drafts[1].packet.basic_damage, 4)
        app._open_ranged_draft()
        self.assertEqual(app._current_tool, 7)
        self.assertEqual(app._last_injury_result.injury, 3)
        self.assertEqual(app.combat_session.combatants[app.session_target_key].current_hp, 10)
        with patch("main.messagebox.showinfo") as notice:
            app._apply_injury_result()
            notice.assert_called_once()
        app._run_injury("resolve")
        with patch("utils.gui_hub.messagebox.askyesno", return_value=True):
            app._apply_injury_result()
        self.assertEqual(app.combat_session.combatants[app.session_target_key].current_hp, 7)
        self.assertFalse(app._ranged_drafts)
        self.assertIsNone(app._injury_ranged_draft)

    def test_localized_catalogs_powers_validation_and_vehicle_controls(self):
        app = self.app
        for language in ("pt_BR", "en_US"):
            with self.subTest(language=language):
                app._change_language(language)
                self.assertTrue(any(t("catalog_status_requires_parameters") in label for label in app._magic_map))
                self.assertTrue(any(t("catalog_status_reference_only") in label for label in app._psi_map))
                app.power_levels.set("0")
                app._run_ability()
                result = app.powers_result_text.get("1.0", "end")
                self.assertNotIn(t("summary_final_cost"), result)
                self.assertIn(t("engine_error_invalid_ability_cost"), result)
                self.assertEqual(app.social_skill.get(), "diplomacy")
                app.vehicle_combat_speed_first.set("15")
                app.vehicle_combat_speed_second.set("5")
                app.result_units.set("imperial" if language == "en_US" else "metric")
                app._change_units()
                app.vehicle_combat_panel.collision()
                result = app.vehicles_result_text.get("1.0", "end")
                self.assertIn("yd/s" if language == "en_US" else "m/s", result)
                self.assertIn("Basic Set", result)

    def test_magic_confirmation_spends_fp_and_heals_and_psi_shows_timing(self):
        app = self.app
        actor, target = app.session_actor_key, app.session_target_key
        app.combat_session.apply(actor, target, StateDelta(hp_change=-4), advance_action=False)
        app.magic_spell.set(next(label for label, spell in app._magic_map.items() if spell.identifier == "spell.minor-healing"))
        app.magic_cost_override.set("2")
        app.magic_use_session.set(True)
        with patch("calculators.magic.roll_3d6", return_value=(10, [3, 3, 4])):
            app._run_magic(True)
        self.assertEqual(app.combat_session.combatants[target].current_hp, 6)
        with patch("main.messagebox.askyesno", return_value=True):
            app._apply_supernatural("magic")
        self.assertEqual(app.combat_session.combatants[target].current_hp, 8)
        self.assertEqual(app.combat_session.combatants[actor].current_fp, 8)
        self.assertTrue(app.combat_session.undo())
        self.assertEqual(app.combat_session.combatants[target].current_hp, 6)
        app.combat_session.edit_combatant_state(actor, resource_pools={
            "er_magic": {"label": "ER (Magic)", "current": 3, "maximum": 5},
        })
        app._session_changed()
        app.magic_session_reserve.set(next(label for label, identifier in app._session_reserve_maps["magic"].items()
                                           if identifier == "er_magic"))
        with patch("calculators.magic.roll_3d6", return_value=(10, [3, 3, 4])):
            app._run_magic(True)
        app.root.update()
        with patch("main.messagebox.askyesno", return_value=True):
            app._apply_supernatural("magic")
        self.assertEqual(app.combat_session.combatants[actor].current_fp, 10)
        self.assertEqual(app.combat_session.combatants[actor].resource_pools["er_magic"]["current"], 1)
        app.power_psi.set(next(label for label, record in app._psi_map.items() if record.operational_model == "mental_surgery"))
        app.power_target_willing.set(True)
        app.power_level.set("3")
        app._run_psi(False)
        result = app.powers_result_text.get("1.0", "end")
        self.assertIn("60s", result)
        self.assertIn(t("psi_point_cost", points=33), result)

    def test_vehicle_labels_and_handoff_action_fit_at_large_font(self):
        app = self.app
        app.root.geometry("900x700")
        app.ui_preferences["font_size"] = 18
        app._oficina_options["vehicle_combat"] = True
        for language in ("pt_BR", "en_US"):
            with self.subTest(language=language):
                app._setup_theme()
                app._change_language(language)
                app.choose_tool(12)
                app.root.update()
                for label in (widget for widget in app.vehicle_movement_form.grid_slaves(column=0)
                              if int(widget.grid_info()["columnspan"]) == 1):
                    self.assertGreater(label.winfo_width(), 95)
                    self.assertLess(label.winfo_height(), 125)
                for label in app.vehicle_combat_panel.speed_labels:
                    self.assertGreater(int(label.cget("wraplength")), 140)
                    self.assertLess(label.winfo_height(), 135)
                app._ranged_drafts = {1: RangedHitDraft(1, "A long weapon name", "basic", DamagePacket(3), True)}
                app._refresh_handoff_choices()
                app._open_ranged_draft()
                app.root.update()
                button = app._injury_handoff_button
                self.assertTrue(button.winfo_ismapped())
                self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                     app.root.winfo_rootx() + app.root.winfo_width())
                app._clear_ranged_draft()
