from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zlib import compress, crc32

from calculators.battle_map import BattleMap, MapToken
from utils.battle_map_assets import BattleMapAssetError, BattleMapAssetStore, inspect_png
from utils.battle_map_view import MapCanvas, MapScene, PlayerMapWindow


def chunk(name, data):
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc32(name + data))


def png(width=96, height=72, *, scanlines=None, interlace=0):
    if scanlines is None:
        scanlines = (b"\0" + b"\x40\x60\x88" * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(
        ">IIBBBBB", width, height, 8, 2, 0, 0, interlace,
    )) + chunk(b"IDAT", compress(scanlines)) + chunk(b"IEND", b""))


class MapAssetTests(unittest.TestCase):
    def test_content_addressing_never_overwrites_and_no_external_paths(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "map name.png"
            original = png()
            source.write_bytes(original)
            store = BattleMapAssetStore(folder / "user-data")
            identifier = store.import_png(source)
            self.assertEqual(identifier, sha256(original).hexdigest())
            dest = store.directory / (identifier + ".png")
            self.assertEqual(list(store.directory.iterdir()), [dest])
            self.assertEqual(store.read_png(identifier).data, original)
            self.assertEqual(store.import_png(source), identifier)
            self.assertEqual(source.read_bytes(), original)
            other = png(32, 32)
            dest.write_bytes(other)
            with self.assertRaisesRegex(BattleMapAssetError, "battle_map_image_invalid"):
                store.import_png(source)
            self.assertEqual(dest.read_bytes(), other)
            for unsafe in ("../secret.png", str(source), "a" * 63, "A" * 64):
                with self.assertRaisesRegex(BattleMapAssetError, "battle_map_image_invalid_id"):
                    store.read_png(unsafe)

    def test_size_pixels_crc_and_decompressed_scanline_bounds(self):
        good = png()
        invalid_inputs = (good[:-1], b"not png", png(1, 1, scanlines=b"\x00" * 500_000),
                          png(2, 2, scanlines=b"\x00" * 4),
                          good[:40] + bytes([good[40] ^ 1]) + good[41:])
        for data in invalid_inputs:
            with self.subTest(size=len(data)), self.assertRaisesRegex(BattleMapAssetError, "battle_map_image_invalid"):
                inspect_png(data)
        for data in (png(4097, 1, scanlines=b""), png(4096, 4096, scanlines=b"")):
            with self.assertRaisesRegex(BattleMapAssetError, "battle_map_image_too_large"):
                inspect_png(data)
        self.assertEqual((inspect_png(good).width, inspect_png(good).height), (96, 72))
        self.assertEqual(inspect_png(png(1, 1, interlace=1)).width, 1)
        with TemporaryDirectory() as directory:
            source = Path(directory) / "map.png"
            source.write_bytes(good)
            with patch("utils.battle_map_assets.MAX_PNG_BYTES", len(good) - 1):
                with self.assertRaisesRegex(BattleMapAssetError, "battle_map_image_too_large"):
                    BattleMapAssetStore(directory).import_png(source)

    def test_scanline_filters_across_idat_chunks_and_adam7_passes(self):
        # A 2x2 Adam7 image has passes of 1, 1, and 2 RGB pixels. The filter
        # byte is separate from pixel data even if split across IDAT chunks.
        data = (b"\x00" + b"\xff" * 3 + b"\x04" + b"\xff" * 3
                + b"\x02" + b"\xff" * 6)
        header = png(2, 2, scanlines=data, interlace=1)[:33]

        def encode(scanlines):
            return header + b"".join(chunk(b"IDAT", bytes((byte,)))
                                      for byte in compress(scanlines)) + chunk(b"IEND", b"")

        self.assertEqual(inspect_png(encode(data)).height, 2)
        with self.assertRaisesRegex(BattleMapAssetError, "battle_map_image_invalid"):
            inspect_png(encode(data[:8] + b"\x05" + data[9:]))


class SceneProjectionTests(unittest.TestCase):
    def test_only_public_display_fields_in_projection(self):
        battle_map = BattleMap(grid="hex_flat", cell_size=48, origin_x=8, origin_y=30,
                               tokens={"a": MapToken(2, -1), "hidden-id": MapToken(1, 2, False),
                                       "c": MapToken(-2, 2)})
        labels = {"a": "Aliado\n Um", "hidden-id": "Secret encounter", "c": "Aliado Dois"}
        colors = {"a": "#3311aa", "hidden-id": "#ff1111", "c": "not-a-color"}
        master = MapScene.from_map(battle_map, labels, colors)
        public = MapScene.from_map(battle_map, labels, colors, player=True)
        self.assertEqual(public, master.player_projection())
        self.assertEqual(public, public.player_projection())
        self.assertEqual(list(master.geometry.tokens), [])
        self.assertIsNot(master.geometry, battle_map)
        self.assertEqual(tuple(token.identifier for token in public.tokens), ("visible-0", "visible-1"))
        self.assertEqual(tuple(token.label for token in public.tokens), ("Aliado Um", "Aliado Dois"))
        self.assertEqual(master.tokens[0].color, "#3311aa")
        self.assertNotEqual(public.tokens[0].color, master.tokens[0].color)
        self.assertEqual(public.tokens[0].color, public.tokens[1].color)
        self.assertNotIn("Secret", repr(public))
        self.assertNotIn("hidden-id", repr(public))


class MapCanvasTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)
        self.root.geometry("800x600")
        self.callback_errors = []
        self.root.report_callback_exception = lambda *parts: self.callback_errors.append(parts)

    def test_grid_live_privacy_and_unbound_player_mutations(self):
        battle_map = BattleMap(tokens={"hero": MapToken(0, 0), "secret": MapToken(2, 0, False)})
        labels = {"hero": "Vigia", "secret": "Perseguidor"}
        master = MapCanvas(self.root)
        master.pack(fill="both", expand=True)
        player = PlayerMapWindow(self.root, title="Jogador")
        master.render(MapScene.from_map(battle_map, labels))
        master.set_ruler_ids("hero", "secret")
        player.render(MapScene.from_map(battle_map, labels))
        self.root.update()

        def texts(canvas):
            return [canvas.itemcget(item, "text") for item in canvas.find_withtag("map-token")
                    if canvas.type(item) == "text"]

        self.assertEqual(texts(master), ["Vigia", "Perseguidor"])
        self.assertEqual(texts(player.canvas), ["Vigia"])
        self.assertTrue(master.find_withtag("map-ruler"))
        self.assertFalse(player.canvas.find_withtag("map-ruler"))
        self.assertGreater(len(master.find_withtag("map-grid")), 8)
        self.assertLess(len(master.find_withtag("map-grid")), 500)
        self.assertIsNone(player.canvas.on_move)
        self.assertIsNone(player.canvas.on_select)
        self.assertIsNone(player.canvas.on_click)
        self.assertEqual(player.canvas.token_at(*player.canvas.canvas_coords(0, 0)), "visible-0")
        player.render(MapScene.from_map(battle_map.with_token_visibility("hero", False), labels))
        self.root.update()
        self.assertEqual(texts(player.canvas), [])
        self.assertEqual(self.callback_errors, [])

    def _assert_grid(self, canvas, *, overview, vertex_count):
        cells = canvas.find_withtag("map-grid")
        self.assertGreater(len(cells), 0)
        self.assertLessEqual(len(cells), 3600)
        self.assertTrue(all(canvas.type(item) == "polygon" for item in cells))
        self.assertEqual(len(canvas.coords(cells[0])), vertex_count * 2)
        indicators = canvas.find_withtag("map-grid-overview")
        if overview:
            self.assertTrue(any(canvas.type(item) == "text" and canvas.itemcget(item, "text").strip()
                                for item in indicators))
        else:
            self.assertFalse(indicators)

    def test_adjacent_player_names_do_not_overlap_or_depend_on_hidden_tokens(self):
        from tkinter import font

        font.nametofont('TkDefaultFont', root=self.root).configure(size=18)
        player = PlayerMapWindow(self.root, title='Jogador')
        canvas = player.canvas
        names = {'side_a': 'Ardent Sentinel', 'side_b': 'Nimble Pathfinder', 'hidden': 'Secret information'}
        state = BattleMap().with_token('side_a', 0, 0).with_token('side_b', 1, 0)

        def reject_overlap(a, b):
            x_overlap = min(a[2], b[2]) - max(a[0], b[0])
            y_overlap = min(a[3], b[3]) - max(a[1], b[1])
            self.assertFalse(x_overlap > 0 and y_overlap > 0, (a, b))

        def drawn():
            items = canvas.find_withtag('map-token')
            labels = {canvas.itemcget(item, 'text'): canvas.bbox(item) for item in items if canvas.type(item) == 'text'}
            self.assertEqual(set(labels), {names['side_a'], names['side_b']})
            plaques = [canvas.bbox(item) for item in items if canvas.type(item) == 'rectangle']
            markers = [canvas.bbox(item) for item in items if canvas.type(item) == 'oval']
            self.assertEqual(len(plaques), 2)
            reject_overlap(*plaques)
            for plaque in plaques:
                for marker in markers:
                    reject_overlap(plaque, marker)
            return labels, plaques, markers

        player.render(MapScene.from_map(state, names))
        self.root.update()
        drawn()
        for _ in range(3):
            canvas.zoom_out()
        self.root.update()
        visible = drawn()
        player.render(MapScene.from_map(state.with_token('hidden', 0, -1, visible=False), names))
        self.root.update()
        self.assertEqual(drawn(), visible)
        self.assertEqual(self.callback_errors, [])

    def test_large_viewport_and_tiny_cells_keep_a_bounded_grid_at_every_orientation(self):
        clicked = []
        canvas = MapCanvas(self.root, on_click=lambda x, y: clicked.append((x, y)))
        canvas.place(x=0, y=0, width=1688, height=760)
        self.root.update()
        self.assertEqual((canvas.winfo_width(), canvas.winfo_height()), (1688, 760))

        for kind, vertex_count in (("hex", 6), ("hex_flat", 6), ("square", 4)):
            with self.subTest(grid=kind):
                state = BattleMap(grid=kind, origin_x=23.25, origin_y=-17.75)
                canvas.render(MapScene.from_map(state), fit=True)
                self.root.update()
                # Exercise the precise camera scale at which the old axial
                # bounding rectangle overcounted the actual visible cells.
                canvas._scale = .35
                canvas.render(MapScene.from_map(state))
                self.root.update()
                self._assert_grid(canvas, overview=False, vertex_count=vertex_count)
                center = state.cell_center(0, 0)
                initial = canvas.canvas_coords(*center)

                def projected_cell_size():
                    adjacent = canvas.canvas_coords(*state.cell_center(1, 0))
                    x, y = canvas.canvas_coords(*center)
                    return ((adjacent[0] - x) ** 2 + (adjacent[1] - y) ** 2) ** .5

                for _ in range(2):
                    canvas.zoom_out()
                self.root.update()
                # The old implementation dropped this grid for exceeding the
                # item budget, not because the individual cells were too small.
                self.assertGreater(projected_cell_size(), 10)
                self._assert_grid(canvas, overview=True, vertex_count=vertex_count)

                cell = (-7, -3)
                world = state.cell_center(*cell)
                x, y = map(round, canvas.canvas_coords(*world))
                canvas.event_generate("<ButtonPress-1>", x=x, y=y)
                canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
                self.assertTrue(clicked)
                self.assertEqual(state.cell_at(*clicked.pop()), cell)

                for _ in range(11):
                    canvas.zoom_out()
                self.root.update()
                self.assertLess(projected_cell_size(), 10)
                self._assert_grid(canvas, overview=True, vertex_count=vertex_count)

                before_toggle = canvas.canvas_coords(*world)
                canvas.render(MapScene.from_map(replace(state, show_grid=False)))
                self.root.update()
                self.assertFalse(canvas.find_withtag("map-grid"))
                self.assertFalse(canvas.find_withtag("map-grid-overview"))
                canvas.render(MapScene.from_map(state))
                self.root.update()
                self._assert_grid(canvas, overview=True, vertex_count=vertex_count)
                self.assertEqual(canvas.canvas_coords(*world), before_toggle)

                for _ in range(13):
                    canvas.zoom_in()
                self.root.update()
                self._assert_grid(canvas, overview=False, vertex_count=vertex_count)
                self.assertAlmostEqual(projected_cell_size(), state.cell_size * .35)
                for current, original in zip(canvas.canvas_coords(*center), initial):
                    self.assertAlmostEqual(current, original)
        self.assertEqual(self.callback_errors, [])

    def test_player_window_shows_reference_grid_at_low_zoom(self):
        player = PlayerMapWindow(self.root, title="Jogador")
        player.canvas.pack_forget()
        player.canvas.place(x=0, y=0, width=820, height=600)
        state = BattleMap(grid="hex_flat", tokens={"hero": MapToken(0, 0), "secret": MapToken(2, 0, False)})
        player.render(MapScene.from_map(state, {"hero": "Vigia", "secret": "Segredo"}))
        self.root.update()
        self._assert_grid(player.canvas, overview=False, vertex_count=6)
        for _ in range(18):
            player.canvas.zoom_out()
        self.root.update()
        self._assert_grid(player.canvas, overview=True, vertex_count=6)
        self.assertEqual([token.label for token in player.canvas.scene.tokens], ["Vigia"])
        self.assertEqual(self.callback_errors, [])

    def test_grid_budget_does_not_change_detail_when_panning(self):
        canvas = MapCanvas(self.root)
        canvas.place(x=0, y=0, width=756, height=755)
        canvas.render(MapScene.from_map(BattleMap(grid="square")))
        self.root.update()
        self.assertEqual((canvas.winfo_width(), canvas.winfo_height()), (756, 755))
        canvas._scale = .2
        # At this spacing one pan phase intersects 3,599 exact cells while
        # the next intersects 3,660. The selected level must not blink.
        for center in ((0, 0), (0, 32), (0, 0), (32, 32), (0, 0)):
            with self.subTest(center=center):
                canvas._set_center(*center)
                self.root.update()
                self._assert_grid(canvas, overview=True, vertex_count=4)
        canvas.zoom_in()
        self.root.update()
        self._assert_grid(canvas, overview=False, vertex_count=4)
        self.assertEqual(self.callback_errors, [])

    def test_ruler_clips_crossing_segments_with_offscreen_endpoints(self):
        canvas = MapCanvas(self.root)
        canvas.pack(fill="both", expand=True)
        state = BattleMap(grid="square", cell_size=2048,
                          tokens={"left": MapToken(-100000, 0), "right": MapToken(100000, 0)})
        canvas.render(MapScene.from_map(state))
        canvas.set_ruler_ids("left", "right")
        self.root.update()
        canvas._scale = 8
        canvas._set_center(0, 0)
        self.root.update()
        width, height = canvas.winfo_width(), canvas.winfo_height()
        line, = canvas.find_withtag("map-ruler")
        for actual, expected in zip(canvas.coords(line), (0, height / 2, width, height / 2)):
            self.assertAlmostEqual(actual, expected, places=5)

        canvas.render(MapScene.from_map(state.with_token("left", 0, 0)))
        self.root.update()
        line, = canvas.find_withtag("map-ruler")
        for actual, expected in zip(canvas.coords(line), (width / 2, height / 2, width, height / 2)):
            self.assertAlmostEqual(actual, expected, places=5)

        canvas.render(MapScene.from_map(state.with_token("left", -100000, 1).with_token("right", 100000, 1)))
        self.root.update()
        self.assertEqual(canvas.find_withtag("map-ruler"), ())
        self.assertEqual(self.callback_errors, [])

    def test_returning_pan_does_not_trigger_placement_click(self):
        clicked = []
        canvas = MapCanvas(self.root, on_click=lambda *v: clicked.append(v), is_placing=lambda: True)
        canvas.pack(fill="both", expand=True)
        canvas.render(MapScene.from_map(BattleMap(tokens={"hero": MapToken(0, 0)})))
        self.root.update()
        x, y = map(round, canvas.canvas_coords(0, 0))
        center = canvas._center
        for button, return_motion in ((1, True), (1, False), (2, True), (2, False)):
            with self.subTest(button=button, return_motion=return_motion):
                canvas.event_generate(f"<ButtonPress-{button}>", x=x, y=y)
                canvas.event_generate(f"<B{button}-Motion>", x=x + 56, y=y + 19)
                self.assertNotEqual(canvas._center, center)
                if return_motion:
                    canvas.event_generate(f"<B{button}-Motion>", x=x, y=y)
                    self.assertEqual(canvas._center, center)
                canvas.event_generate(f"<ButtonRelease-{button}>", x=x, y=y)
                self.root.update()
                self.assertEqual(canvas._center, center)
                self.assertEqual(clicked, [])

        canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.assertEqual(clicked, [canvas.map_coords(x, y)])
        self.assertEqual(self.callback_errors, [])

    def test_returning_marker_drag_clears_preview_without_a_move(self):
        moves, clicks = [], []
        canvas = MapCanvas(self.root, on_move=lambda *v: moves.append(v), on_click=lambda *v: clicks.append(v))
        canvas.pack(fill="both", expand=True)
        state = BattleMap(tokens={"hero": MapToken(0, 0)})
        canvas.render(MapScene.from_map(state, {"hero": "Vigia"}))
        self.root.update()
        x, y = map(round, canvas.canvas_coords(0, 0))
        start = canvas.map_coords(x, y)
        canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        canvas.event_generate("<B1-Motion>", x=x + 72, y=y + 12)
        self.assertNotEqual(canvas._drag_world, ("hero", *start))
        canvas.event_generate("<B1-Motion>", x=x, y=y)
        self.assertEqual(canvas._drag_world, ("hero", *start))
        canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.root.update()
        self.assertIsNone(canvas._drag_world)
        self.assertEqual((moves, clicks), ([], []))
        self.assertEqual(canvas.token_at(x, y), "hero")
        self.assertEqual(self.callback_errors, [])

    def test_png_remains_visible_at_5k_and_4k_pan_reuses_bounded_tiles(self):
        with TemporaryDirectory() as directory:
            asset_store = BattleMapAssetStore(directory)
            source = Path(directory) / "map.png"
            source.write_bytes(png(2800, 1600))
            state = BattleMap(image_id=asset_store.import_png(source), show_grid=False)
            canvas = MapCanvas(self.root, asset_store)
            canvas.place(x=0, y=0, width=5120, height=2880)
            canvas.render(MapScene.from_map(state))
            self.root.update()
            self.assertEqual((canvas.winfo_width(), canvas.winfo_height(), canvas._scale), (5120, 2880, 1))
            self.assertTrue(canvas.find_withtag("map-image"))
            canvas.zoom_in()
            self.root.update()
            self.assertEqual(canvas._scale, 2)

            def check_tiles():
                images = set(canvas.find_withtag("map-image"))
                self.assertGreater(len(images), 1)
                for x, y in ((2, 2), (canvas.winfo_width() - 2, 2), (2, canvas.winfo_height() - 2),
                             (canvas.winfo_width() - 2, canvas.winfo_height() - 2)):
                    self.assertTrue(images.intersection(canvas.find_overlapping(x, y, x, y)))
                pixels = sum(tile.width() * tile.height() for tile in canvas._image_tiles.values())
                self.assertLessEqual(pixels, 24 * 1024 * 1024)

            check_tiles()
            canvas.place_configure(width=3840, height=2160)
            self.root.update()
            check_tiles()
            before = dict(canvas._image_tiles)
            x, y = canvas._center
            canvas._set_center(x + 20, y + 13)
            self.root.update()
            check_tiles()
            reusable = before.keys() & canvas._image_tiles.keys()
            self.assertGreaterEqual(len(reusable), len(before) * .8)
            for key in reusable:
                self.assertIs(canvas._image_tiles[key], before[key])
            self.assertEqual(self.callback_errors, [])

    def test_png_photo_fit_crop_cache_and_missing_image(self):
        with TemporaryDirectory() as directory:
            asset_store = BattleMapAssetStore(directory)
            source = Path(directory) / "map.png"
            source.write_bytes(png(1200, 900))
            identifier = asset_store.import_png(source)
            canvas = MapCanvas(self.root, asset_store)
            canvas.pack(fill="both", expand=True)
            battle_map = BattleMap(image_id=identifier, origin_x=200, origin_y=160, grid="square")
            canvas.render(MapScene.from_map(battle_map))
            self.root.update()
            self.assertFalse(canvas.background_unavailable)
            self.assertEqual(canvas._source_image.width(), 1200)
            self.assertEqual(len(canvas.find_withtag("map-image")), 1)
            self.assertAlmostEqual(canvas._scale, 0.5)
            marker = canvas.find_withtag("map-image")[0]
            self.assertEqual(canvas.coords(marker), list(canvas.canvas_coords(0, 0)))
            before = canvas._crop_image
            canvas.render(MapScene.from_map(battle_map.with_token("hero", 0, 0)))
            self.root.update()
            self.assertIs(before, canvas._crop_image)
            for _ in range(8):
                canvas.zoom_in()
            self.root.update()
            self.assertLessEqual(canvas._crop_image.width() * canvas._crop_image.height(), 1000 * 800)
            self.assertEqual(len(canvas.find_withtag("map-image")), 1)
            canvas.render(MapScene.from_map(replace(battle_map, image_id="0" * 64)))
            self.root.update()
            self.assertTrue(canvas.background_unavailable)
            self.assertEqual(canvas.find_withtag("map-image"), ())
            self.assertTrue(canvas.find_withtag("map-grid"))
            self.assertEqual(self.callback_errors, [])

    def test_master_drag_does_not_commit_until_release_and_zoom_keeps_anchor(self):
        selected, dragged, clicked = [], [], []
        canvas = MapCanvas(self.root, on_select=selected.append, on_move=lambda *v: dragged.append(v),
                           on_click=lambda *v: clicked.append(v))
        canvas.pack(fill="both", expand=True)
        state = BattleMap(tokens={"hero": MapToken(0, 0)})
        canvas.render(MapScene.from_map(state, {"hero": "Vigia"}))
        self.root.update()
        sx, sy = (round(v) for v in canvas.canvas_coords(0, 0))
        start, end = SimpleNamespace(x=sx, y=sy), SimpleNamespace(x=sx + 64, y=sy + 20)
        canvas._press(start, 1)
        canvas._motion(end)
        self.root.update()
        self.assertEqual(selected, ["hero"])
        self.assertEqual(dragged, [])
        expected = canvas.map_coords(end.x, end.y)
        canvas._release(end)
        self.assertEqual(dragged, [("hero", *expected)])
        self.assertEqual(state.tokens["hero"], MapToken(0, 0))
        canvas._press(end, 1)
        canvas._release(end)
        self.assertEqual(clicked, [expected])
        canvas._wheel(end, 1)
        for world, previous in zip(canvas.map_coords(end.x, end.y), expected):
            self.assertAlmostEqual(world, previous)
        self.assertEqual(self.callback_errors, [])


if __name__ == "__main__":
    unittest.main()
