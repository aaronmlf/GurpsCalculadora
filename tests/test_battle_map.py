from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from calculators.battle_map import BattleMap, MapToken, MAX_CELL_INDEX, MAX_MAP_TOKENS
from calculators.combat_library import CombatLibrary
from calculators.combat_session import (
    CombatSession, LEGACY_SESSION_SCHEMA, MAP_CHANGE_EVENT, PREVIOUS_SESSION_SCHEMA, SESSION_SCHEMA,
)
from calculators.injury import CombatantState, StateDelta


A, B = "combatant_a", "combatant_b"
IMAGE = "7a" * 32
AXIAL_NEIGHBORS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))


class BattleMapGeometryTests(unittest.TestCase):
    def test_centers_neighbors_and_polygon_dimensions(self):
        for grid in ("hex", "hex_flat", "square"):
            with self.subTest(grid=grid):
                size = 37.5
                board = BattleMap(grid=grid, cell_size=size, origin_x=-14, origin_y=83)
                center = board.cell_center(0, 0)
                self.assertEqual(center, (-14, 83))
                neighbors = AXIAL_NEIGHBORS if grid != "square" else ((1, 0), (0, 1), (-1, 0), (0, -1))
                for q, r in neighbors:
                    self.assertAlmostEqual(math.dist(center, board.cell_center(q, r)), size)
                    self.assertAlmostEqual(board.distance_yards(0, 0, q, r), 1)
                polygon = board.cell_polygon(0, 0)
                expected = 4 if grid == "square" else 6
                self.assertEqual(len(polygon), expected)
                edges = [math.dist(a, b) for a, b in zip(polygon, polygon[1:] + polygon[:1])]
                for edge in edges:
                    self.assertAlmostEqual(edge, size if grid == "square" else size / math.sqrt(3))
                xs, ys = zip(*polygon)
                width, height = max(xs) - min(xs), max(ys) - min(ys)
                if grid == "square":
                    self.assertAlmostEqual(width, height)
                else:
                    self.assertEqual(width < height, grid == "hex")

    def test_all_modes_round_trip_with_offsets_and_negative_indices(self):
        for grid in ("hex", "hex_flat", "square"):
            board = BattleMap(grid=grid, cell_size=19.5, origin_x=-52.25, origin_y=32.5)
            for q, r in ((0, 0), (-1, 4), (13, -9), (-61, -121), (MAX_CELL_INDEX, -MAX_CELL_INDEX)):
                with self.subTest(grid=grid, q=q, r=r):
                    x, y = board.cell_center(q, r)
                    self.assertEqual(board.cell_at(x, y), (q, r))
                    self.assertEqual(board.cell_at(x + 1, y - 2), (q, r))

    def test_hex_snapping_rounds_cube_not_independent_axial_components(self):
        for grid in ("hex", "hex_flat"):
            board = BattleMap(grid=grid, origin_x=22, origin_y=19)
            zero = board.cell_center(0, 0)
            q_step = tuple(value - origin for value, origin in zip(board.cell_center(1, 0), zero))
            r_step = tuple(value - origin for value, origin in zip(board.cell_center(0, 1), zero))
            point = tuple(origin + .47 * q + .42 * r for origin, q, r in zip(zero, q_step, r_step))
            self.assertEqual(board.cell_at(*point), (1, 0))
            q, r = board.fractional_cell_at(*point)
            self.assertAlmostEqual(q, .47)
            self.assertAlmostEqual(r, .42)

    def test_distances_use_cube_steps_or_square_euclidean(self):
        for grid in ("hex", "hex_flat"):
            board = BattleMap(grid=grid, yards_per_cell=2.5)
            self.assertEqual(board.distance_yards(-1, 1, 1, -1), 5)
            self.assertEqual(board.distance_yards(3, 4, 1, 1), 12.5)
            self.assertEqual(board.distance_yards(1, 1, 3, 4), 12.5)
        square = BattleMap(grid="square", yards_per_cell=3)
        self.assertEqual(square.distance_yards(0, 0, 3, -4), 15)
        self.assertAlmostEqual(square.distance_yards(0, 0, 1, 1), 3 * math.sqrt(2))
        self.assertEqual(square.distance_yards(2, 2, 2, 2), 0)

    def test_bounded_input_rejects_non_finite_paths_and_invalid_types(self):
        for kwargs in (
            {"grid": "iso"}, {"show_grid": 1}, {"grid": []}, {"cell_size": True}, {"cell_size": 7},
            {"cell_size": float("nan")}, {"yards_per_cell": 0}, {"yards_per_cell": float("inf")},
            {"origin_x": 1e9}, {"origin_y": "9"}, {"image_id": "/tmp/map.png"}, {"image_id": "AB" * 32},
            {"tokens": {"../hidden": MapToken(0, 0)}}, {"tokens": {"system": MapToken(0, 0)}},
            {"tokens": {A: {"q": 0, "r": 0}}},
            {"tokens": {f"token{i}": MapToken(0, 0) for i in range(MAX_MAP_TOKENS + 1)}},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BattleMap(**kwargs)
        board = BattleMap()
        for invalid in (lambda: MapToken(True, 0), lambda: MapToken(0, MAX_CELL_INDEX + 1),
                        lambda: MapToken(0, 0, 0), lambda: board.cell_at(float("inf"), 0),
                        lambda: board.cell_at(1e9, 0), lambda: board.distance_yards(0, 0, .5, 1),
                        lambda: board.cell_polygon(-MAX_CELL_INDEX - 1, 0),
                        lambda: board.with_token_visibility(A, False)):
            with self.assertRaises(ValueError):
                invalid()


class BattleMapDataTests(unittest.TestCase):
    def test_round_trip_no_shared_mutable_tokens_and_private_projection(self):
        supplied = {A: MapToken(1, -2), B: MapToken(-4, 3, False)}
        board = BattleMap(grid="hex_flat", cell_size=80, origin_x=-7, show_grid=False, image_id=IMAGE, tokens=supplied)
        supplied.clear()
        self.assertEqual(set(board.tokens), {A, B})
        with self.assertRaises(TypeError):
            board.tokens[A] = MapToken(0, 0)
        with self.assertRaises(FrozenInstanceError):
            board.tokens[A].visible = False
        public = board.public_tokens()
        self.assertEqual(dict(public), {A: MapToken(1, -2)})
        with self.assertRaises(TypeError):
            public[B] = MapToken(-4, 3)
        self.assertEqual(BattleMap.from_dict(json.loads(json.dumps(board.to_dict()))), board)
        self.assertIs(deepcopy(board), board)
        moved = board.with_token(B, 6, 0)
        self.assertEqual(moved.tokens[B], MapToken(6, 0, False))
        self.assertNotIn(B, moved.public_tokens())
        self.assertIn(B, moved.with_token_visibility(B, True).public_tokens())
        self.assertEqual(board.tokens[B], MapToken(-4, 3, False))
        self.assertIs(board.with_token(A, 1, -2), board)
        self.assertIs(board.without_token("not_there"), board)

    def test_serialization_cannot_carry_extra_private_fields(self):
        with self.assertRaisesRegex(ValueError, "map_invalid_document"):
            BattleMap.from_dict({"asset_path": "/home/Private/map.png"})
        with self.assertRaisesRegex(ValueError, "map_invalid_token"):
            BattleMap.from_dict({"tokens": {A: {"q": 0, "r": 0, "current_hp": 6}}})
        with self.assertRaisesRegex(ValueError, "map_invalid_token"):
            BattleMap.from_dict({"tokens": {A: {"visible": True}}})


class SessionBattleMapTests(unittest.TestCase):
    def test_legacy_v1_and_v2_load_default_without_rewriting(self):
        for schema in (LEGACY_SESSION_SCHEMA, PREVIOUS_SESSION_SCHEMA):
            with self.subTest(schema=schema), TemporaryDirectory() as folder:
                path = Path(folder) / "session.json"
                raw = CombatSession.new().to_dict()
                raw["schema"] = schema
                raw.pop("battle_map")
                if schema == LEGACY_SESSION_SCHEMA:
                    raw.pop("combatant_order")
                raw["combatants"][B]["current_hp"] = 6
                original = json.dumps(raw)
                path.write_text(original, encoding="utf-8")
                session = CombatSession.load_or_new(path)
                self.assertEqual(path.read_text(encoding="utf-8"), original)
                self.assertEqual(session.battle_map, BattleMap())
                self.assertEqual(session.combatants[B].current_hp, 6)
                session.set_battle_map(session.battle_map.with_token(A, 1, 2))
                updated = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(updated["schema"], SESSION_SCHEMA)
                self.assertEqual(updated["battle_map"]["tokens"], {A: {"q": 1, "r": 2, "visible": True}})

    def test_named_snapshot_stores_map_and_independent_updates(self):
        with TemporaryDirectory() as folder:
            base = Path(folder)
            session = CombatSession.new(base / "active.json")
            board = BattleMap(grid="square", yards_per_cell=1.5, image_id=IMAGE).with_token(A, 4, -2, False)
            session.set_battle_map(board)
            self.assertEqual(session.events[-1].label, MAP_CHANGE_EVENT)
            session.apply(A, B, StateDelta(hp_change=-2))
            library = CombatLibrary(base / "library.json")
            library.save_session("Gate", session)
            session.set_battle_map(board.with_token_visibility(A, True))
            opened = CombatLibrary(base / "library.json").open_session("Gate")
            self.assertEqual(opened.battle_map, board)
            self.assertEqual(opened.combatants[B].current_hp, 8)
            self.assertTrue(CombatSession.load_or_new(base / "active.json").battle_map.tokens[A].visible)
            self.assertTrue(session.undo())
            self.assertEqual(session.battle_map, board)
            self.assertEqual(session.combatants[B].current_hp, 8)

    def test_save_error_and_noop_do_not_mutate_map_events_or_undo(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            session = CombatSession.new(path)
            board = BattleMap().with_token(A, 1, 2)
            session.set_battle_map(board)
            before = session.to_dict()
            data = path.read_bytes()
            with patch("calculators.combat_session.write_atomic_json", side_effect=OSError):
                session.set_battle_map(board)
                with self.assertRaises(OSError):
                    session.set_battle_map(board.with_token(A, 3, 4))
                with self.assertRaises(OSError):
                    session.replace_participant(A, CombatantState(identifier=A, name="Scout"))
                with self.assertRaisesRegex(ValueError, "unknown_combatant"):
                    session.set_battle_map(board.with_token("unknown", 4, 1))
            self.assertEqual(session.to_dict(), before)
            self.assertEqual(path.read_bytes(), data)
            self.assertTrue(session.undo())
            self.assertFalse(session.undo())
            self.assertEqual(session.battle_map, BattleMap())

    def test_roster_removal_and_replacement_clear_only_associated_tokens(self):
        session = CombatSession.new()
        c = session.add_combatant(CombatantState(name="Guest"))
        board = BattleMap(image_id=IMAGE).with_token(A, 1, 0).with_token(B, 2, 0).with_token(c, 3, 0, False)
        session.set_battle_map(board)
        session.move_combatant(c, 0)
        self.assertEqual(session.battle_map, board)
        session.replace_participant(A, CombatantState(identifier=A, name="Scout"))
        self.assertEqual(session.battle_map.tokens.keys(), {B, c})
        session.remove_combatant(c)
        self.assertEqual(session.battle_map.tokens.keys(), {B})
        self.assertEqual(session.battle_map.image_id, IMAGE)
        self.assertTrue(session.undo())
        self.assertEqual(session.battle_map.tokens[c], MapToken(3, 0, False))
        self.assertTrue(session.undo())
        self.assertEqual(session.battle_map, board)

    def test_setup_map_before_first_roster_preserves_settings_and_discards_unused_placeholders(self):
        session = CombatSession.new()
        board = replace(session.battle_map, image_id=IMAGE, grid="hex_flat")
        session.set_battle_map(board)
        ids = session.add_combatants([CombatantState(name="One"), CombatantState(name="Two")], replace_defaults=True)
        self.assertEqual(session.combatant_order, ids)
        self.assertEqual(session.battle_map, board)
        self.assertTrue(session.undo())
        self.assertEqual(session.combatant_order, [A, B])
        session.set_battle_map(board.with_token(A, 1, 0))
        session.add_combatants([CombatantState(name="Extra")], replace_defaults=True)
        self.assertIn(A, session.combatants)
        self.assertIn(A, session.battle_map.tokens)

    def test_v3_rejects_orphan_placements(self):
        raw = CombatSession.new().to_dict()
        raw["battle_map"] = BattleMap().with_token("not-in-roster", 0, 0).to_dict()
        with self.assertRaisesRegex(ValueError, "unknown_combatant"):
            CombatSession.from_dict(raw)
