"""Vehicle-on-vehicle previews backed by the existing GURPS engines."""

from dataclasses import replace
import math
import tkinter as tk
from tkinter import ttk

from calculators.vehicles import VehicleAttackInput, VehicleCollisionInput, VehicleState
from utils.i18n import t
from utils.ranged_layout import FieldGrid, wrap_label
from utils.units import UnitSystem


class VehicleCombatPanel:
    def __init__(self, app, content):
        self.app = app
        if not hasattr(app, "vehicle_combat_distance"):
            app.vehicle_combat_distance = tk.StringVar(value="100.0")
            app.vehicle_combat_speed_first = tk.StringVar()
            app.vehicle_combat_speed_second = tk.StringVar()
            app.vehicle_combat_target = tk.StringVar()
            app.vehicle_combat_weapon = tk.StringVar()
            app.vehicle_combat_query = tk.StringVar()
            app.vehicle_combat_skill = tk.StringVar(value="12")
            app.vehicle_combat_aim = tk.StringVar(value="0")
            app.vehicle_combat_shots = tk.StringVar(value="1")
            app.vehicle_combat_geometry = tk.StringVar(value="head_on")
        frame = app._extended_options(content, "vehicle_combat", "vehicle_combat_title")
        collision = FieldGrid(frame, columns=2)
        collision.pack(fill="x")
        self._combo(collision, "vehicle_combat_target", app.vehicle_combat_target, list(app._vehicle_map))
        if app.vehicle_combat_target.get() not in app._vehicle_map and app._vehicle_map:
            app.vehicle_combat_target.set(next((key for key in app._vehicle_map if key != app.vehicle_selected.get()),
                                               next(iter(app._vehicle_map))))
        geometry = {t("vehicle_combat_" + key): key for key in ("head_on", "rear_end", "side_on")}
        self.geometry_label = tk.StringVar(value=next(label for label, key in geometry.items()
                                                     if key == app.vehicle_combat_geometry.get()))
        selection = self._combo(collision, "vehicle_combat_geometry", self.geometry_label, list(geometry))
        selection.bind("<<ComboboxSelected>>", lambda _event: app.vehicle_combat_geometry.set(
            geometry[self.geometry_label.get()]))
        first = self._entry(collision, "vehicle_combat_speed_first", app.vehicle_combat_speed_first)
        second = self._entry(collision, "vehicle_combat_speed_second", app.vehicle_combat_speed_second)
        self.speed_labels = (first.unit_label, second.unit_label)
        app._extended_actions(frame, (("vehicle_combat_collision", self.collision),))
        shooting = FieldGrid(frame, columns=2)
        shooting.pack(fill="x")
        search = self._entry(shooting, "ranged_search", app.vehicle_combat_query)
        self.weapon_box = self._combo(shooting, "ranged_weapon", app.vehicle_combat_weapon, ())
        self.weapons = {f"{item.name} — {item.source} p.{item.page} [{item.identifier}]": item
                        for item in app.weapon_catalog.weapons}
        search.bind("<KeyRelease>", lambda _event: self.filter_weapons())
        self.filter_weapons()
        self._entry(shooting, "common_distance", app.vehicle_combat_distance)
        self._entry(shooting, "ranged_skill", app.vehicle_combat_skill)
        self._entry(shooting, "ranged_aim_seconds", app.vehicle_combat_aim)
        self._entry(shooting, "ranged_shots_fired", app.vehicle_combat_shots)
        app._extended_actions(frame, (("ranged_calculate", lambda: self.attack(False)),
                                      ("ranged_resolve", lambda: self.attack(True))))
        ttk.Label(frame, text=t("vehicle_combat_hint"), wraplength=380).pack(fill="x", padx=5, pady=(0, 6))

    @staticmethod
    def _cell(parent, label):
        cell = ttk.Frame(parent)
        title = wrap_label(ttk.Label(cell, text=t(label), width=1, wraplength=160))
        title.pack(fill="x")
        parent.add(cell)
        return cell, title

    def _combo(self, parent, label, variable, values):
        cell, _title = self._cell(parent, label)
        box = ttk.Combobox(cell, textvariable=variable, values=values, state="readonly", width=1)
        box.pack(fill="x")
        return box

    def _entry(self, parent, label, variable):
        cell, title = self._cell(parent, label)
        entry = ttk.Entry(cell, textvariable=variable, width=1)
        entry.unit_label = title
        entry.pack(fill="x")
        return entry

    def filter_weapons(self):
        query = self.app.vehicle_combat_query.get().strip().casefold()
        names = tuple(label for label in self.weapons if query in label.casefold())
        self.weapon_box["values"] = names
        if self.app.vehicle_combat_weapon.get() not in names:
            self.app.vehicle_combat_weapon.set(names[0] if names else "")

    @staticmethod
    def _number(raw):
        number = float(raw.replace(",", "."))
        if not math.isfinite(number) or number < 0 or number > 1e9:
            raise ValueError("vehicle_combat_bad_input")
        return number

    def _states(self):
        app = self.app
        first = app._vehicle_map[app.vehicle_selected.get()]
        second = app._vehicle_map[app.vehicle_combat_target.get()]
        units = UnitSystem(app.result_units.get())
        result = []
        for item, var in ((first, app.vehicle_combat_speed_first), (second, app.vehicle_combat_speed_second)):
            state = app.vehicle_session.vehicles.get(item.identifier, VehicleState(item))
            if var.get().strip():
                state = replace(state, speed_yards_per_second=self._number(var.get()))
            result.append(state)
        return result[0], result[1], units

    def _show(self, lines):
        self.app._pending_vehicle_movement = None
        self.app._show_result(self.app.vehicles_result_text, lines)

    def _error(self, exc):
        key = str(exc)
        self._show([t(key) if key.startswith("vehicle_combat_") else t("vehicle_combat_bad_input")])

    def collision(self):
        try:
            first, second, units = self._states()
            # Keep synchronous vehicle rolls bounded; Dice is the dedicated
            # workbench for rolling very large expressions in the background.
            max_damage_dice = max(first.record.st_hp, second.record.st_hp) * (
                first.speed_yards_per_second + second.speed_yards_per_second) / 100
            if max_damage_dice > 100_000:
                raise ValueError("vehicle_combat_too_many_dice")
            result = self.app.vehicle_calc.calculate_collision(VehicleCollisionInput(
                first, second, collision_type=self.app.vehicle_combat_geometry.get()))
            if not result["valid"]:
                self._show([t("vehicle_combat_no_collision")])
                return
            lines = [t("vehicle_combat_relative_speed",
                       speed=units.display(result["collision_velocity"], "yards_per_second"))]
            for index, state in enumerate((first, second), 1):
                injury = result[f"object{index}_injury_result"]
                lines.append(t("vehicle_combat_damage", name=state.record.name,
                               basic=injury["packet"]["basic_damage"], dr=injury["effective_dr"],
                               injury=injury["injury"]))
            self._show(lines + [t("common_references") + " Basic Set pp. 430–432"])
        except (ValueError, KeyError, OverflowError) as exc:
            self._error(exc)

    def attack(self, resolve):
        try:
            app = self.app
            first, second, _units = self._states()
            weapon = self.weapons[app.vehicle_combat_weapon.get()]
            data = VehicleAttackInput(
                first, second, weapon, gunner_skill=int(app.vehicle_combat_skill.get()),
                distance_m=self._number(app.vehicle_combat_distance.get()),
                target_speed_mps=second.speed_yards_per_second * 0.9144,
                aim_seconds=int(app.vehicle_combat_aim.get()), shots_fired=int(app.vehicle_combat_shots.get()),
            )
            result = app.vehicle_calc.resolve_attack(data) if resolve else app.vehicle_calc.calculate_attack(data)
            lines = [t("ranged_summary", weapon=weapon.name, profile=t("ranged_profile_basic")),
                     t("ranged_effective_skill", value=result.effective_skill, probability=result.probability)]
            if result.errors:
                lines.append(t("ranged_errors") + " " + ", ".join(t("ranged_error_" + error) for error in result.errors))
            for item in result.modifiers:
                lines.append(f"{item['value']:+d} {t('ranged_modifier_' + item['key'])} · {item['source']} p.{item['page']}")
            if result.attack:
                lines += [f"{t('summary_roll')}: {result.attack['roll']} · {app._format_roll(result.attack)}",
                          t("ranged_hits_after_defense", value=result.hits_after_defense)]
                if result.malfunction:
                    lines.append(t("ranged_malfunction"))
            for index, hit in enumerate(result.damages, 1):
                lines.append(t("ranged_damage_result", index=index, basic=hit["basic_damage"],
                               dr=hit["effective_dr"], penetrating=hit["penetrating_damage"],
                               multiplier=hit["wounding_modifier"], injury=hit["injury"]))
                if any(key in hit for key in ("effect_type", "effect_shape", "resistance", "follow_up", "explosion")):
                    lines.append(t("vehicle_combat_special_hit"))
            self._show(lines + [f"{t('common_references')} {weapon.source} p.{weapon.page}"])
        except (ValueError, KeyError, OverflowError) as exc:
            self._error(exc)
