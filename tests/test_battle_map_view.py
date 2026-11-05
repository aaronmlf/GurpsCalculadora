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
        self.assertEqual(public.tokens[0].color, "#3311aa")
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
