"""Tk renderers for the local battle map. No session mutations live here."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
import tkinter as tk

from calculators.battle_map import BattleMap, MAX_CELL_INDEX, MAX_WORLD_COORDINATE
from utils.battle_map_assets import BattleMapAssetError, BattleMapAssetStore


_DEFAULT_COLOR = "#699bea"
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_MAP_LIMIT = MAX_WORLD_COORDINATE
_MIN_SCALE = 1e-7
_MAX_SCALE = 8.0
_MAX_GRID_CELLS = 3600
_MAX_CROP_PIXELS = 10 * 1024 * 1024
_IMAGE_SCALES = tuple(1 / step for step in (
    10_000_000, 4_194_304, 2_097_152, 1_048_576, 524_288, 262_144, 131_072,
    65_536, 32_768, 16_384, 8192, 4096, 2048, 1024, 512, 256, 128, 64,
    48, 32, 24, 16, 12, 8, 6, 5, 4, 3, 2, 1,
)) + (2.0, 3.0, 4.0, 6.0, 8.0)


@dataclass(frozen=True)
class MapTokenView:
    identifier: str
    label: str
    q: int
    r: int
    color: str = _DEFAULT_COLOR
    visible: bool = True


@dataclass(frozen=True)
class MapScene:
    """Detached draw inputs: geometry and display fields, never a roster/session."""

    geometry: BattleMap
    tokens: tuple[MapTokenView, ...] = ()

    @classmethod
    def from_map(cls, battle_map: BattleMap, labels=None, colors=None, *, player=False):
        # Explicit construction avoids retaining either the original map or its token mapping.
        geometry = BattleMap(grid=battle_map.grid, cell_size=battle_map.cell_size,
                             origin_x=battle_map.origin_x, origin_y=battle_map.origin_y,
                             yards_per_cell=battle_map.yards_per_cell,
                             show_grid=battle_map.show_grid, image_id=battle_map.image_id)
        labels = {} if labels is None else labels
        colors = {} if colors is None else colors
        tokens = []
        for identifier, token in battle_map.tokens.items():
            if player and not token.visible:
                continue
            label = labels.get(identifier, "")
            # Keep a single line; no fallback to IDs, filenames or internal roster fields.
            label = " ".join(label[:160].split())[:80] if isinstance(label, str) else ""
            color = colors.get(identifier, _DEFAULT_COLOR)
            if not isinstance(color, str) or _COLOR.fullmatch(color) is None:
                color = _DEFAULT_COLOR
            tokens.append(MapTokenView(identifier, label, token.q, token.r, color, token.visible))
        scene = cls(geometry, tuple(tokens))
        return scene.player_projection() if player else scene

    def player_projection(self):
        """Copy only public values and replace all roster IDs with local display IDs."""
        visible = (token for token in self.tokens if token.visible)
        return MapScene(replace(self.geometry, tokens={}), tuple(
            MapTokenView(f"visible-{index}", token.label, token.q, token.r, token.color)
            for index, token in enumerate(visible)
        ))


class MapCanvas(tk.Canvas):
    """Camera, viewport rendering and optional master interaction callbacks."""

    def __init__(self, parent, asset_store=None, on_select=None, on_move=None, on_click=None,
                 **canvas_options):
        canvas_options.setdefault("background", "#262c38")
        canvas_options.setdefault("highlightthickness", 0)
        canvas_options.setdefault("takefocus", True)
        super().__init__(parent, **canvas_options)
        self.asset_store = asset_store if asset_store is not None else BattleMapAssetStore()
        self.on_select, self.on_move, self.on_click = on_select, on_move, on_click
        self.scene = None
        self.selected_id = None
        self.background_unavailable = False
        self._source_id = None
        self._source_image = self._crop_image = None
        self._crop_key = None
        self._center = (0.0, 0.0)
        self._scale = 1.0
        self._fit_pending = False
        self._redraw_job = None
        self._hits = {}
        self._gesture = None
        self._drag_world = None
        self._ruler_ids = None

        self.bind("<Configure>", self._on_configure)
        self.bind("<MouseWheel>", lambda event: self._wheel(event, 1 if event.delta > 0 else -1)
                  if event.delta else "break")
        self.bind("<Button-4>", lambda event: self._wheel(event, 1))
        self.bind("<Button-5>", lambda event: self._wheel(event, -1))
        for button in (1, 2, 3):
            self.bind(f"<ButtonPress-{button}>", lambda event, b=button: self._press(event, b))
            self.bind(f"<B{button}-Motion>", self._motion)
            self.bind(f"<ButtonRelease-{button}>", self._release)
        for key, method in (("plus", self.zoom_in), ("equal", self.zoom_in),
                            ("minus", self.zoom_out), ("f", self.fit), ("F", self.fit)):
            self.bind(f"<KeyPress-{key}>", lambda _event, action=method: action())

    def destroy(self):
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self._source_image = self._crop_image = None
        super().destroy()

    def render(self, scene: MapScene, selected_id=None, *, fit=False):
        initial = self.scene is None
        self.scene, self.selected_id = scene, selected_id
        image_id = scene.geometry.image_id
        changed_image = image_id != self._source_id
        if changed_image or (fit and self.background_unavailable):
            self._set_image(image_id)
        if initial or changed_image or fit:
            self.fit()
        else:
            self._queue_redraw()

    def set_ruler_ids(self, actor_id, target_id):
        pair = (actor_id, target_id) if actor_id and target_id and actor_id != target_id else None
        if pair != self._ruler_ids:
            self._ruler_ids = pair
            self._queue_redraw()

    def _set_image(self, identifier):
        self._source_id = identifier
        self._source_image = self._crop_image = None
        self._crop_key = None
        self.background_unavailable = False
        if identifier is not None:
            try:
                source = self.asset_store.read_png(identifier)
                photo = tk.PhotoImage(master=self, data=source.data, format="png")
                if (photo.width(), photo.height()) != (source.width, source.height):
                    raise BattleMapAssetError("battle_map_image_invalid")
                self._source_image = photo
            except (BattleMapAssetError, tk.TclError):
                self.background_unavailable = True

    def _viewport(self):
        return self.winfo_width(), self.winfo_height()

    def map_coords(self, x, y):
        width, height = self._viewport()
        return (self._center[0] + (x - width / 2) / self._scale,
                self._center[1] + (y - height / 2) / self._scale)

    def canvas_coords(self, x, y):
        width, height = self._viewport()
        return ((x - self._center[0]) * self._scale + width / 2,
                (y - self._center[1]) * self._scale + height / 2)

    def fit(self):
        if self.scene is None:
            return
        width, height = self._viewport()
        self._fit_pending = min(width, height) <= 1
        if self._fit_pending:
            return
        grid = self.scene.geometry
        margin = grid.cell_size * 0.8
        points = [grid.cell_center(token.q, token.r) for token in self.scene.tokens]
        if self._source_image is None:
            points.extend(((grid.origin_x - grid.cell_size * 4, grid.origin_y - grid.cell_size * 3),
                           (grid.origin_x + grid.cell_size * 4, grid.origin_y + grid.cell_size * 3)))
        else:
            points.extend(((0.0, 0.0), (self._source_image.width(), self._source_image.height())))
        left = min(x for x, _ in points) - margin
        right = max(x for x, _ in points) + margin
        top = min(y for _, y in points) - margin
        bottom = max(y for _, y in points) + margin
        self._center = ((left + right) / 2, (top + bottom) / 2)
        desired = min(width / (right - left), height / (bottom - top), _MAX_SCALE)
        if self._source_image is not None:
            self._scale = max((level for level in _IMAGE_SCALES if level <= desired), default=_MIN_SCALE)
        else:
            self._scale = max(desired, _MIN_SCALE)
        self._queue_redraw()

    def zoom_in(self):
        self._zoom(1)

    def zoom_out(self):
        self._zoom(-1)

    def _wheel(self, event, direction):
        self._zoom(direction, event.x, event.y)
        return "break"

    def _zoom(self, direction, x=None, y=None):
        if self.scene is None:
            return
        width, height = self._viewport()
        x, y = width / 2 if x is None else x, height / 2 if y is None else y
        anchor_x, anchor_y = self.map_coords(x, y)
        if self._source_image is not None:
            if direction > 0:
                self._scale = next((n for n in _IMAGE_SCALES if n > self._scale), _MAX_SCALE)
            else:
                self._scale = next((n for n in reversed(_IMAGE_SCALES) if n < self._scale), _MIN_SCALE)
        else:
            self._scale = max(_MIN_SCALE, min(_MAX_SCALE, self._scale * (1.25 ** direction)))
        self._set_center(anchor_x - (x - width / 2) / self._scale,
                         anchor_y - (y - height / 2) / self._scale)

    def _set_center(self, x, y):
        self._center = tuple(max(-_MAP_LIMIT, min(_MAP_LIMIT, value)) for value in (x, y))
        self._queue_redraw()

    def _on_configure(self, _event):
        if self._fit_pending:
            self.fit()
        else:
            self._queue_redraw()

    def _queue_redraw(self):
        if self._redraw_job is None:
            self._redraw_job = self.after_idle(self._draw)

    def _draw(self):
        self._redraw_job = None
        if self.scene is None:
            return
        self.delete("battle-map")
        self._hits.clear()
        width, height = self._viewport()
        if min(width, height) <= 1:
            return
        self._draw_image(width, height)
        self._draw_grid(width, height)
        self._draw_ruler(width, height)
        self._draw_tokens(width, height)

    def _draw_image(self, width, height):
        if self._source_image is None:
            return
        iw, ih = self._source_image.width(), self._source_image.height()
        zoom = max(1, round(self._scale))
        subsample = max(1, round(1 / self._scale))
        # Crop to the viewport plus modest, quantized overscan. Tk's integer scaling
        # is exact at camera zoom levels; the crop is bounded even for 8x zoom.
        left, top = self.map_coords(0, 0)
        right, bottom = self.map_coords(width, height)
        if left >= iw or top >= ih or right <= 0 or bottom <= 0:
            return
        step = max(subsample, subsample * (64 // zoom))
        x1, y1 = (max(0, math.floor(value / step) * step) for value in (left, top))
        x2 = min(iw, math.ceil(right / step) * step)
        y2 = min(ih, math.ceil(bottom / step) * step)
        crop_w = math.ceil((x2 - x1) / subsample) * zoom
        crop_h = math.ceil((y2 - y1) / subsample) * zoom
        if crop_w * crop_h > _MAX_CROP_PIXELS:
            # Keep the viewport interactive on very large displays without allocating
            # a giant scaled image; this guard is independent from source PNG limits.
            return
        key = (x1, y1, x2, y2, zoom, subsample)
        if key != self._crop_key:
            image = tk.PhotoImage(master=self)
            try:
                self.tk.call(str(image), "copy", str(self._source_image), "-from", x1, y1, x2, y2,
                             "-zoom", zoom, zoom, "-subsample", subsample, subsample)
            except tk.TclError:
                return
            self._crop_image, self._crop_key = image, key
        self.create_image(*self.canvas_coords(x1, y1), anchor="nw", image=self._crop_image,
                          tags=("battle-map", "map-image"))

    def _draw_grid(self, width, height):
        geometry = self.scene.geometry
        if not geometry.show_grid or self._scale * geometry.cell_size < 10:
            return
        corners = []
        for cx, cy in ((0, 0), (width, 0), (0, height), (width, height)):
            x, y = self.map_coords(cx, cy)
            corners.append(geometry.fractional_cell_at(
                max(-_MAP_LIMIT, min(_MAP_LIMIT, x)), max(-_MAP_LIMIT, min(_MAP_LIMIT, y)),
            ))
        q1 = max(-MAX_CELL_INDEX, math.floor(min(q for q, _ in corners)) - 1)
        q2 = min(MAX_CELL_INDEX, math.ceil(max(q for q, _ in corners)) + 1)
        r1 = max(-MAX_CELL_INDEX, math.floor(min(r for _, r in corners)) - 1)
        r2 = min(MAX_CELL_INDEX, math.ceil(max(r for _, r in corners)) + 1)
        if q1 > q2 or r1 > r2 or (q2 - q1 + 1) * (r2 - r1 + 1) > _MAX_GRID_CELLS:
            return
        for r in range(r1, r2 + 1):
            for q in range(q1, q2 + 1):
                vertices = [component for x, y in geometry.cell_polygon(q, r)
                            for component in self.canvas_coords(x, y)]
                if (max(vertices[::2]) < 0 or min(vertices[::2]) > width
                        or max(vertices[1::2]) < 0 or min(vertices[1::2]) > height):
                    continue
                self.create_polygon(*vertices, fill="", outline="#77879b", width=1,
                                    tags=("battle-map", "map-grid"))

    def _draw_ruler(self, width, height):
        if self._ruler_ids is None:
            return
        by_id = {token.identifier: token for token in self.scene.tokens}
        endpoints = []
        for identifier in self._ruler_ids:
            token = by_id.get(identifier)
            if token is None:
                return
            x, y = self.canvas_coords(*self.scene.geometry.cell_center(token.q, token.r))
            if not (-60 <= x <= width + 60 and -60 <= y <= height + 60):
                return
            endpoints.extend((x, y))
        self.create_line(*endpoints, fill="#ffd383", width=2, dash=(4, 4),
                         tags=("battle-map", "map-ruler"))

    def _draw_tokens(self, width, height):
        geometry = self.scene.geometry
        radius = max(8, min(20, self._scale * geometry.cell_size * 0.30))
        for token in self.scene.tokens:
            world = geometry.cell_center(token.q, token.r)
            if self._drag_world is not None and self._drag_world[0] == token.identifier:
                world = self._drag_world[1:]
            x, y = self.canvas_coords(*world)
            if not (-60 <= x <= width + 60 and -60 <= y <= height + 60):
                continue
            selected = token.identifier == self.selected_id
            marker = self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                      fill=token.color, outline="#ffd383" if selected else "#111521",
                                      width=3 if selected else 2, dash=() if token.visible else (3, 2),
                                      stipple="" if token.visible else "gray50",
                                      tags=("battle-map", "map-token"))
            self._hits[marker] = token.identifier
            if token.label:
                text = self.create_text(x, y + radius + 2, text=token.label, anchor="n",
                                        fill="#fafbff" if token.visible else "#bdc4d0",
                                        width=125, justify="center", tags=("battle-map", "map-token"))
                lx, ty, rx, by = self.bbox(text)
                plaque = self.create_rectangle(lx - 2, ty, rx + 2, by, fill="#202735", outline="",
                                               tags=("battle-map", "map-token"))
                self.tag_lower(plaque, text)
                self._hits[text] = self._hits[plaque] = token.identifier

    def token_at(self, x, y):
        for item in reversed(self.find_overlapping(x, y, x, y)):
            if item in self._hits:
                return self._hits[item]
        return None

    def _press(self, event, button):
        self.focus_set()
        token = None
        if button == 1 and any(action is not None for action in (self.on_select, self.on_move, self.on_click)):
            if self._redraw_job is not None:  # Hit-test current positions, not a pending drag preview.
                self.after_cancel(self._redraw_job)
                self._draw()
            token = self.token_at(event.x, event.y)
        self._gesture = (button, event.x, event.y, self._center, token)
        if token is not None and self.on_select is not None:
            self.on_select(token)
        return "break"

    def _motion(self, event):
        if self._gesture is None:
            return "break"
        _button, x, y, center, token = self._gesture
        if token is None:
            if abs(event.x - x) + abs(event.y - y) >= 4:
                self._set_center(center[0] - (event.x - x) / self._scale,
                                 center[1] - (event.y - y) / self._scale)
        elif self.on_move is not None and abs(event.x - x) + abs(event.y - y) >= 4:
            self._drag_world = (token, *self.map_coords(event.x, event.y))
            self._queue_redraw()
        return "break"

    def _release(self, event):
        gesture, self._gesture = self._gesture, None
        dragged, self._drag_world = self._drag_world, None
        if dragged is not None:
            self._queue_redraw()
        if gesture is not None:
            button, x, y, _, token = gesture
            moved = abs(event.x - x) + abs(event.y - y) >= 4
            if button == 1 and moved and token is not None and self.on_move is not None:
                self.on_move(token, *self.map_coords(event.x, event.y))
            elif button == 1 and not moved and token is None and self.on_click is not None:
                self.on_click(*self.map_coords(event.x, event.y))
        return "break"


class PlayerMapWindow(tk.Toplevel):
    """Local, read-only player view. No edit callbacks and no reference to a roster."""

    def __init__(self, parent, asset_store=None, title="", **canvas_options):
        super().__init__(parent)
        self.title(title)
        self.geometry("820x600")
        self.minsize(300, 240)
        self.canvas = MapCanvas(self, asset_store, on_select=None, on_move=None, on_click=None,
                                **canvas_options)
        self.canvas.pack(fill="both", expand=True)

    def render(self, scene: MapScene, *, fit=False):
        self.canvas.render(scene.player_projection(), fit=fit)
