"""Tk renderers for the local battle map. No session mutations live here."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
import tkinter as tk

from calculators.battle_map import BattleMap, MAX_CELL_INDEX, MAX_WORLD_COORDINATE
from utils.battle_map_assets import BattleMapAssetError, BattleMapAssetStore
from utils.i18n import t


_DEFAULT_COLOR = "#699bea"
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_MAP_LIMIT = MAX_WORLD_COORDINATE
_MIN_SCALE = 1e-7
_MAX_SCALE = 8.0
_MAX_GRID_CELLS = 3600
_MIN_GRID_SPACING = 10.0
_SINGLE_CROP_PIXELS = 1024 * 1024
_IMAGE_TILE_SIDE = 384
_MAX_TILE_PIXELS = 24 * 1024 * 1024
_DRAG_THRESHOLD = 4
_LABEL_GAP = 7
_IMAGE_SCALES = tuple(1 / step for step in (
    10_000_000, 4_194_304, 2_097_152, 1_048_576, 524_288, 262_144, 131_072,
    65_536, 32_768, 16_384, 8192, 4096, 2048, 1024, 512, 256, 128, 64,
    48, 32, 24, 16, 12, 8, 6, 5, 4, 3, 2, 1,
)) + (2.0, 3.0, 4.0, 6.0, 8.0)


def _grid_cell_bound(grid, width, height, radius, spacing):
    """Bound visible cells for *any* pan phase at these viewport dimensions."""
    rx, ry = radius
    if grid == "hex_flat":
        width, height, rx, ry = height, width, ry, rx
    pitch = math.sqrt(3) / 2 if grid != "square" else 1.0
    # In a closed interval of length n there are at most floor(n) + 1
    # integers. Leave a little room for subtraction at distant origins.
    columns = math.floor(width / spacing + 2 * rx + 1e-6) + 1
    rows = math.floor((height / spacing + 2 * ry) / pitch + 1e-6) + 1
    return columns * rows


def _viewport_grid_cells(grid, bounds, radius, stride):
    """Collect visible axial cells row by row (column by column for flat hexes)."""
    left, top, right, bottom = bounds
    rx, ry = radius
    flat = grid == "hex_flat"
    staggered = grid != "square"
    if flat:
        left, top, right, bottom = top, left, bottom, right
        rx, ry = ry, rx
    pitch = math.sqrt(3) / 2 if staggered else 1.0
    limit = MAX_CELL_INDEX // stride
    cells = []
    for row in range(max(-limit, math.ceil((top - ry) / pitch)),
                     min(limit, math.floor((bottom + ry) / pitch)) + 1):
        shift = row / 2 if staggered else 0
        start = max(-limit, math.ceil(left - rx - shift))
        stop = min(limit, math.floor(right + rx - shift))
        if start > stop:
            continue
        if len(cells) + stop - start + 1 > _MAX_GRID_CELLS:
            return None
        for col in range(start, stop + 1):
            q, r = (row, col) if flat else (col, row)
            cells.append((q * stride, r * stride))
    return cells


def _clip_segment(endpoints, width, height):
    """Clip a line segment to the viewport before handing coordinates to Tk."""
    x, y, end_x, end_y = endpoints
    dx, dy = end_x - x, end_y - y
    start, end = 0.0, 1.0
    for slope, limit in ((-dx, x), (dx, width - x), (-dy, y), (dy, height - y)):
        if not slope:
            if limit < 0:
                return None
            continue
        fraction = limit / slope
        if slope < 0:
            start = max(start, fraction)
        else:
            end = min(end, fraction)
        if start > end:
            return None
    return tuple(value for step in (start, end) for value in (
        min(width, max(0.0, x + step * dx)), min(height, max(0.0, y + step * dy))))


def _label_box(x, y, radius, label_width, label_height, width, height, occupied):
    """Try nearby positions without covering marker circles or accepted labels."""
    gap = radius + _LABEL_GAP
    margin = 3
    center_x = max(margin, min(width - label_width - margin, x - label_width / 2))
    center_y = max(margin, min(height - label_height - margin, y - label_height / 2))
    for left, top in ((center_x, y + gap), (center_x, y - gap - label_height),
                      (x + gap, center_y), (x - gap - label_width, center_y),
                      (x + gap, y + gap), (x - gap - label_width, y + gap),
                      (x + gap, y - gap - label_height), (x - gap - label_width, y - gap - label_height)):
        right, bottom = left + label_width, top + label_height
        if (left >= margin and top >= margin and right <= width - margin and bottom <= height - margin
                and all(right + 2 <= l or left - 2 >= r or bottom + 2 <= t or top - 2 >= b
                        for l, t, r, b in occupied)):
            return left, top, right, bottom
    return None


@dataclass(slots=True)
class _PointerGesture:
    button: int
    x: int
    y: int
    center: tuple[float, float]
    token: str | None
    dragging: bool = False

    def past_threshold(self, event):
        return abs(event.x - self.x) + abs(event.y - self.y) >= _DRAG_THRESHOLD


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
        """Replace roster IDs and private group/team colors with public values."""
        visible = (token for token in self.tokens if token.visible)
        return MapScene(replace(self.geometry, tokens={}), tuple(
            MapTokenView(f"visible-{index}", token.label, token.q, token.r)
            for index, token in enumerate(visible)
        ))


class MapCanvas(tk.Canvas):
    """Camera, viewport rendering and optional master interaction callbacks."""

    def __init__(self, parent, asset_store=None, on_select=None, on_move=None, on_click=None,
                 is_placing=None, **canvas_options):
        canvas_options.setdefault("background", "#262c38")
        canvas_options.setdefault("highlightthickness", 0)
        canvas_options.setdefault("takefocus", True)
        super().__init__(parent, **canvas_options)
        self.asset_store = asset_store if asset_store is not None else BattleMapAssetStore()
        self.on_select, self.on_move, self.on_click = on_select, on_move, on_click
        self.is_placing = is_placing
        self.scene = None
        self.selected_id = None
        self.background_unavailable = False
        self._source_id = None
        self._source_image = self._crop_image = None
        self._crop_key = None
        self._image_tiles = {}
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
            self.bind(f"<B{button}-Motion>", lambda event, b=button: self._motion(event, b))
            self.bind(f"<ButtonRelease-{button}>", lambda event, b=button: self._release(event, b))
        for key, method in (("plus", self.zoom_in), ("equal", self.zoom_in),
                            ("minus", self.zoom_out), ("f", self.fit), ("F", self.fit)):
            self.bind(f"<KeyPress-{key}>", lambda _event, action=method: action())

    def destroy(self):
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self._source_image = self._crop_image = None
        self._image_tiles.clear()
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

    def snapshot_camera(self):
        """Return a world-space camera independent of the current widget dimensions."""
        if self.scene is None or self._fit_pending:
            return None
        return self._center, self._scale

    def restore_camera(self, camera):
        center, self._scale = camera
        self._fit_pending = False
        self._set_center(*center)

    def _set_image(self, identifier):
        self._source_id = identifier
        self._source_image = self._crop_image = None
        self._crop_key = None
        self._image_tiles.clear()
        self.background_unavailable = False
        if identifier is not None:
            try:
                source = self.asset_store.read_png(identifier)
                self._source_image = self.decode_background(source)
            except BattleMapAssetError:
                self.background_unavailable = True

    def decode_background(self, source):
        """Confirm that the same Tk renderer used on the map can open these bytes."""
        try:
            photo = tk.PhotoImage(master=self, data=source.data, format="png")
        except tk.TclError as exc:
            raise BattleMapAssetError("battle_map_image_invalid") from exc
        if (photo.width(), photo.height()) != (source.width, source.height):
            raise BattleMapAssetError("battle_map_image_invalid")
        return photo

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
        grid_stride = self._draw_grid(width, height)
        self._draw_ruler(width, height)
        if grid_stride > 1:
            self._draw_grid_overview(width, grid_stride)
        self._draw_tokens(width, height)
        if grid_stride > 1:
            self.tag_raise("map-grid-overview")

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
            self._crop_image = self._crop_key = None
            self._image_tiles.clear()
            return
        step = max(subsample, subsample * (64 // zoom))
        x1, y1 = (max(0, math.floor(value / step) * step) for value in (left, top))
        x2 = min(iw, math.ceil(right / step) * step)
        y2 = min(ih, math.ceil(bottom / step) * step)
        crop_w = math.ceil((x2 - x1) / subsample) * zoom
        crop_h = math.ceil((y2 - y1) / subsample) * zoom
        if crop_w * crop_h > _SINGLE_CROP_PIXELS:
            self._crop_image = self._crop_key = None
            self._draw_image_tiles(left, top, right, bottom, iw, ih, zoom, subsample)
            return
        self._image_tiles.clear()
        key = (x1, y1, x2, y2, zoom, subsample)
        if key != self._crop_key:
            image = self._copy_image_region(key)
            if image is None:
                return
            self._crop_image, self._crop_key = image, key
        self.create_image(*self.canvas_coords(x1, y1), anchor="nw", image=self._crop_image,
                          tags=("battle-map", "map-image"))

    def _copy_image_region(self, key):
        x1, y1, x2, y2, zoom, subsample = key
        try:
            image = tk.PhotoImage(master=self)
            self.tk.call(str(image), "copy", str(self._source_image), "-from", x1, y1, x2, y2,
                         "-zoom", zoom, zoom, "-subsample", subsample, subsample)
        except tk.TclError:
            return None
        return image

    def _draw_image_tiles(self, left, top, right, bottom, iw, ih, zoom, subsample):
        # Anchor tiles in source pixels, not the viewport. A small pan only
        # needs to decode tiles on the newly exposed edge, not the entire map.
        samples = max(1, _IMAGE_TILE_SIDE // zoom)
        source_side = samples * subsample
        first_x, first_y = (max(0, math.floor(pos / source_side)) for pos in (left, top))
        last_x = math.ceil(min(iw, right) / source_side)
        last_y = math.ceil(min(ih, bottom) / source_side)
        columns, rows = last_x - first_x, last_y - first_y
        max_tiles = max(1, _MAX_TILE_PIXELS // ((samples * zoom) ** 2))
        if columns * rows > max_tiles:
            # A window far beyond ordinary 5K displays still shows its
            # center rather than dropping the entire background. Cap live
            # PhotoImage pixels independently of source size and zoom level.
            ratio = math.sqrt(max_tiles / (columns * rows))
            limited_columns = max(1, min(max_tiles, math.floor(columns * ratio)))
            limited_rows = max(1, min(max_tiles // limited_columns, math.floor(rows * ratio)))
            first_x += (columns - limited_columns) // 2
            first_y += (rows - limited_rows) // 2
            last_x, last_y = first_x + limited_columns, first_y + limited_rows
        needed = {}
        for row in range(first_y, last_y):
            for column in range(first_x, last_x):
                x, y = column * source_side, row * source_side
                key = (x, y, min(iw, x + source_side), min(ih, y + source_side), zoom, subsample)
                needed[key] = None
        for key in self._image_tiles.keys() - needed.keys():
            del self._image_tiles[key]
        for key in needed:
            image = self._image_tiles.get(key)
            if image is None:
                image = self._copy_image_region(key)
                if image is None:
                    continue
                self._image_tiles[key] = image
            self.create_image(*self.canvas_coords(key[0], key[1]), anchor="nw", image=image,
                              tags=("battle-map", "map-image"))

    def _draw_grid(self, width, height):
        geometry = self.scene.geometry
        if not geometry.show_grid:
            return 1
        size = geometry.cell_size
        ox, oy = geometry.cell_center(0, 0)
        offsets = tuple(((x - ox) / size, (y - oy) / size) for x, y in geometry.cell_polygon(0, 0))
        radius = (max(abs(dx) for dx, _ in offsets), max(abs(dy) for _, dy in offsets))
        sx, sy = self.canvas_coords(ox, oy)
        stride, spacing = 1, self._scale * size
        # Thin lines below this scale become unreadable. Draw an explicitly
        # labeled overview anchored at the same origin, without changing the
        # actual grid, placement, distances, or the allowed camera zoom.
        while spacing < _MIN_GRID_SPACING or _grid_cell_bound(
            geometry.grid, width, height, radius, spacing,
        ) > _MAX_GRID_CELLS:
            stride, spacing = stride * 2, spacing * 2
        bounds = (-sx / spacing, -sy / spacing, (width - sx) / spacing, (height - sy) / spacing)
        cells = _viewport_grid_cells(geometry.grid, bounds, radius, stride) or ()
        for q, r in cells:
            cx, cy = self.canvas_coords(*geometry.cell_center(q, r))
            vertices = [component for dx, dy in offsets for component in (cx + dx * spacing, cy + dy * spacing)]
            self.create_polygon(*vertices, fill="", outline="#77879b", width=1,
                                tags=("battle-map", "map-grid"))
        return stride if cells else 1

    def _draw_grid_overview(self, width, stride):
        tags = ("battle-map", "map-grid-overview")
        text = self.create_text(width - 10, 8, anchor="ne", justify="right",
                                width=max(1, width - 24), fill="#fafbff",
                                text=t("map_grid_overview", factor=stride), tags=tags)
        left, top, right, bottom = self.bbox(text)
        badge = self.create_rectangle(left - 4, top - 2, right + 4, bottom + 2,
                                      fill="#202735", outline="", tags=tags)
        self.tag_lower(badge, text)

    def _draw_ruler(self, width, height):
        if self._ruler_ids is None:
            return
        by_id = {token.identifier: token for token in self.scene.tokens}
        endpoints = []
        for identifier in self._ruler_ids:
            token = by_id.get(identifier)
            if token is None:
                return
            endpoints.extend(self.canvas_coords(*self.scene.geometry.cell_center(token.q, token.r)))
        visible = _clip_segment(endpoints, width, height)
        if visible is not None:
            self.create_line(*visible, fill="#ffd383", width=2, dash=(4, 4),
                             tags=("battle-map", "map-ruler"))

    def _draw_tokens(self, width, height):
        geometry = self.scene.geometry
        base_radius = max(8, min(20, self._scale * geometry.cell_size * 0.30))
        if getattr(self, '_public_view', False):
            # A single public marker with a count and a name list keeps every
            # occupant legible without implying different physical positions.
            cells = {}
            for token in self.scene.tokens:
                cells.setdefault((token.q, token.r), []).append(token)
            groups = cells.values()
        else:
            # In the master view a selected, co-located token stays on top so
            # either one can still be chosen and dragged from the roster.
            tokens = self.scene.tokens if self.selected_id is None else sorted(
                self.scene.tokens, key=lambda token: token.identifier == self.selected_id)
            groups = ((token,) for token in tokens)
        overview = self.bbox("map-grid-overview")
        occupied = [overview] if overview is not None else []
        labels = []
        for group in groups:
            token = group[0]
            world = geometry.cell_center(token.q, token.r)
            if self._drag_world is not None and self._drag_world[0] == token.identifier:
                world = self._drag_world[1:]
            x, y = self.canvas_coords(*world)
            if not (-60 <= x <= width + 60 and -60 <= y <= height + 60):
                continue
            selected = token.identifier == self.selected_id
            shared = len(group) > 1
            radius = max(base_radius, 14) if shared else base_radius
            marker = self.create_oval(x - radius, y - radius, x + radius, y + radius,
                                      fill=token.color, outline="#ffd383" if selected else "#111521",
                                      width=3 if selected else 2, dash=() if token.visible else (3, 2),
                                      stipple="" if token.visible else "gray50",
                                      tags=("battle-map", "map-token"))
            self._hits[marker] = token.identifier
            occupied.append(self.bbox(marker))
            if shared:
                count = self.create_text(x, y, text=str(len(group)), font=('TkDefaultFont', 9, 'bold'),
                                         fill="#111521", tags=("battle-map", "map-token-count"))
                self._hits[count] = token.identifier
            label = "\n".join(member.label for member in group if member.label)
            if label and -radius <= x <= width + radius and -radius <= y <= height + radius:
                labels.append((selected, token, x, y, radius, label))

        # Reserve all marker circles first, then choose label positions in a
        # stable order. Only the detached public scene takes part in the player
        # window, so a hidden token cannot displace a public name.
        labels.sort(key=lambda item: not item[0])
        for _selected, token, x, y, radius, label in labels:
            text = self.create_text(0, 0, text=label, anchor="nw",
                                    fill="#fafbff" if token.visible else "#bdc4d0",
                                    width=125, justify="center", tags=("battle-map", "map-token"))
            lx, ty, rx, by = self.bbox(text)
            box = _label_box(x, y, radius, rx - lx + 4, by - ty, width, height, occupied)
            if box is None:
                self.delete(text)
                continue  # Keep the circle at its exact position on crowded maps.
            left, top, right, bottom = box
            self.move(text, left + 2 - lx, top - ty)
            plaque = self.create_rectangle(*box, fill="#202735", outline="",
                                           tags=("battle-map", "map-token"))
            self.tag_lower(plaque, text)
            # A small leader disambiguates a name placed beside its marker.
            aim_x, aim_y = min(right, max(left, x)), min(bottom, max(top, y))
            dx, dy = aim_x - x, aim_y - y
            scale = (radius + 1) / math.hypot(dx, dy)
            self.create_line(x + dx * scale, y + dy * scale, aim_x, aim_y, fill=token.color,
                             tags=("battle-map", "map-token-leader"))
            occupied.append(self.bbox(plaque))
            self._hits[text] = self._hits[plaque] = token.identifier

    def token_at(self, x, y):
        for item in reversed(self.find_overlapping(x, y, x, y)):
            if item in self._hits:
                return self._hits[item]
        return None

    def _press(self, event, button):
        if self._gesture is not None:
            return "break"
        self.focus_set()
        token = None
        if (button == 1 and not (self.is_placing is not None and self.is_placing())
                and any(action is not None for action in (self.on_select, self.on_move, self.on_click))):
            if self._redraw_job is not None:  # Hit-test current positions, not a pending drag preview.
                self.after_cancel(self._redraw_job)
                self._draw()
            token = self.token_at(event.x, event.y)
        self._gesture = _PointerGesture(button, event.x, event.y, self._center, token)
        if token is not None and self.on_select is not None:
            self.on_select(token)
        return "break"

    def _pan(self, gesture, event):
        x, y = gesture.center
        self._set_center(x - (event.x - gesture.x) / self._scale,
                         y - (event.y - gesture.y) / self._scale)

    def _motion(self, event, button=None):
        gesture = self._gesture
        if gesture is None or (button is not None and button != gesture.button):
            return "break"
        if not gesture.dragging and not gesture.past_threshold(event):
            return "break"
        gesture.dragging = True  # Returning to the press position is still a drag.
        if gesture.token is None:
            self._pan(gesture, event)
        elif self.on_move is not None:
            self._drag_world = (gesture.token, *self.map_coords(event.x, event.y))
            self._queue_redraw()
        return "break"

    def _release(self, event, button=None):
        gesture = self._gesture
        if gesture is None or (button is not None and button != gesture.button):
            return "break"
        self._gesture = None
        dragged, self._drag_world = self._drag_world, None
        if dragged is not None:
            self._queue_redraw()
        moved = gesture.past_threshold(event)
        if gesture.dragging or moved:
            if gesture.token is None:
                self._pan(gesture, event)  # Include a final release without a Motion event.
            elif moved and self.on_move is not None:
                self.on_move(gesture.token, *self.map_coords(event.x, event.y))
        elif gesture.button == 1 and gesture.token is None and self.on_click is not None:
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
        self.canvas._public_view = True
        self.canvas.pack(fill="both", expand=True)

    def render(self, scene: MapScene, *, fit=False):
        self.canvas.render(scene.player_projection(), fit=fit)
