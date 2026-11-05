"""Immutable encounter map data and grid geometry; no Tk or filesystem access."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import math
import re
from types import MappingProxyType


GRID_MODES = frozenset({"hex", "hex_flat", "square"})
MIN_CELL_SIZE, MAX_CELL_SIZE = 8.0, 2048.0
MIN_YARDS_PER_CELL, MAX_YARDS_PER_CELL = 0.01, 10_000.0
MAX_ORIGIN = 100_000_000.0
MAX_WORLD_COORDINATE = 1_000_000_000.0
MAX_CELL_INDEX = 100_000
MAX_MAP_TOKENS = 100
_SQRT_3 = math.sqrt(3.0)
_HEX_AXIS = _SQRT_3 / 2.0
_TOKEN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
_IMAGE_ID = re.compile(r"[0-9a-f]{64}\Z")
_MAP_FIELDS = frozenset({
    "grid", "cell_size", "origin_x", "origin_y", "yards_per_cell", "show_grid", "image_id", "tokens",
})
_POINTY_VERTICES = tuple((math.cos(math.radians(30 + 60 * i)) / _SQRT_3,
                         math.sin(math.radians(30 + 60 * i)) / _SQRT_3) for i in range(6))
_FLAT_VERTICES = tuple((math.cos(math.radians(60 * i)) / _SQRT_3,
                       math.sin(math.radians(60 * i)) / _SQRT_3) for i in range(6))
_SQUARE_VERTICES = ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))


def _bounded_number(value, lower, upper):
    return type(value) in (int, float) and lower <= value <= upper


def _valid_token_id(value):
    return isinstance(value, str) and value != "system" and _TOKEN_ID.fullmatch(value) is not None


def _check_cell(q, r):
    if any(type(value) is not int or abs(value) > MAX_CELL_INDEX for value in (q, r)):
        raise ValueError("map_invalid_coordinate")


@dataclass(frozen=True, slots=True)
class MapToken:
    q: int
    r: int
    visible: bool = True

    def __post_init__(self):
        _check_cell(self.q, self.r)
        if type(self.visible) is not bool:
            raise ValueError("map_invalid_token")

    @classmethod
    def from_dict(cls, value):
        if (not isinstance(value, Mapping) or set(value) - {"q", "r", "visible"}
                or not {"q", "r"} <= set(value)):
            raise ValueError("map_invalid_token")
        return cls(value["q"], value["r"], value.get("visible", True))

    def to_dict(self):
        return {"q": self.q, "r": self.r, "visible": self.visible}


@dataclass(frozen=True, slots=True)
class BattleMap:
    """Grid settings in world pixels and stable combatant-ID placements.

    Hex grids use axial q/r and square grids use column/row. In all modes,
    cell_size is the pixel distance to an adjacent edge-sharing cell center,
    and the origin is the center of cell (0, 0). Image pixels are independent
    of the grid origin and begin at world (0, 0).
    """

    grid: str = "hex"
    cell_size: float = 64.0
    origin_x: float = 0.0
    origin_y: float = 0.0
    yards_per_cell: float = 1.0
    show_grid: bool = True
    image_id: str | None = None
    tokens: Mapping[str, MapToken] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.grid, str) or self.grid not in GRID_MODES or type(self.show_grid) is not bool:
            raise ValueError("map_invalid_grid")
        if (not _bounded_number(self.cell_size, MIN_CELL_SIZE, MAX_CELL_SIZE)
                or not _bounded_number(self.yards_per_cell, MIN_YARDS_PER_CELL, MAX_YARDS_PER_CELL)):
            raise ValueError("map_invalid_scale")
        if any(not _bounded_number(value, -MAX_ORIGIN, MAX_ORIGIN) for value in (self.origin_x, self.origin_y)):
            raise ValueError("map_invalid_coordinate")
        if self.image_id is not None and (
            not isinstance(self.image_id, str) or _IMAGE_ID.fullmatch(self.image_id) is None
        ):
            raise ValueError("map_invalid_image")
        if not isinstance(self.tokens, Mapping) or len(self.tokens) > MAX_MAP_TOKENS:
            raise ValueError("map_invalid_token")
        if any(not _valid_token_id(key) or not isinstance(token, MapToken) for key, token in self.tokens.items()):
            raise ValueError("map_invalid_token")
        object.__setattr__(self, "tokens", MappingProxyType(dict(self.tokens)))

    def __deepcopy__(self, memo):
        return self  # The map, its placements and the mapping are immutable.

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, Mapping) or set(value) - _MAP_FIELDS:
            raise ValueError("map_invalid_document")
        raw = value.get("tokens", {})
        if not isinstance(raw, Mapping) or len(raw) > MAX_MAP_TOKENS:
            raise ValueError("map_invalid_token")
        return cls(**dict(value, tokens={key: MapToken.from_dict(token) for key, token in raw.items()}))

    def to_dict(self):
        return {
            "grid": self.grid, "cell_size": self.cell_size, "origin_x": self.origin_x, "origin_y": self.origin_y,
            "yards_per_cell": self.yards_per_cell, "show_grid": self.show_grid, "image_id": self.image_id,
            "tokens": {key: token.to_dict() for key, token in self.tokens.items()},
        }

    def cell_center(self, q: int, r: int) -> tuple[float, float]:
        _check_cell(q, r)
        if self.grid == "hex":
            x, y = q + r * .5, _HEX_AXIS * r
        elif self.grid == "hex_flat":
            x, y = _HEX_AXIS * q, r + q * .5
        else:
            x, y = q, r
        return self.origin_x + self.cell_size * x, self.origin_y + self.cell_size * y

    def fractional_cell_at(self, x: float, y: float) -> tuple[float, float]:
        """Return unsnapped q/r for viewport calculations or hit testing."""
        if any(not _bounded_number(value, -MAX_WORLD_COORDINATE, MAX_WORLD_COORDINATE) for value in (x, y)):
            raise ValueError("map_invalid_coordinate")
        x, y = (x - self.origin_x) / self.cell_size, (y - self.origin_y) / self.cell_size
        if self.grid == "hex":
            r = y / _HEX_AXIS
            return x - r * .5, r
        if self.grid == "hex_flat":
            q = x / _HEX_AXIS
            return q, y - q * .5
        return x, y

    def cell_at(self, x: float, y: float) -> tuple[int, int]:
        q, r = self.fractional_cell_at(x, y)
        if self.grid == "square":
            result = math.floor(q + .5), math.floor(r + .5)
        else:
            # Round the three cube components, then repair the largest error
            # to keep their sum at zero (the nearest hex center).
            s = -q - r
            rq, rr, rs = round(q), round(r), round(s)
            eq, er, es = abs(rq - q), abs(rr - r), abs(rs - s)
            if eq >= er and eq >= es:
                rq = -rr - rs
            elif er >= es:
                rr = -rq - rs
            result = rq, rr
        _check_cell(*result)
        return result

    def cell_polygon(self, q: int, r: int) -> tuple[tuple[float, float], ...]:
        x, y = self.cell_center(q, r)
        offsets = _POINTY_VERTICES if self.grid == "hex" else (
            _FLAT_VERTICES if self.grid == "hex_flat" else _SQUARE_VERTICES
        )
        return tuple((x + self.cell_size * dx, y + self.cell_size * dy) for dx, dy in offsets)

    def distance_yards(self, q1: int, r1: int, q2: int, r2: int) -> float:
        _check_cell(q1, r1)
        _check_cell(q2, r2)
        dq, dr = q2 - q1, r2 - r1
        cells = math.hypot(dq, dr) if self.grid == "square" else max(abs(dq), abs(dr), abs(dq + dr))
        return float(cells * self.yards_per_cell)

    def with_token(self, combatant_id: str, q: int, r: int, visible: bool | None = None) -> BattleMap:
        if not _valid_token_id(combatant_id):
            raise ValueError("map_invalid_token")
        previous = self.tokens.get(combatant_id)
        if visible is None:
            visible = previous.visible if previous is not None else True
        token = MapToken(q, r, visible)
        return self if previous == token else replace(self, tokens={**self.tokens, combatant_id: token})

    def without_token(self, combatant_id: str) -> BattleMap:
        if not _valid_token_id(combatant_id):
            raise ValueError("map_invalid_token")
        if combatant_id not in self.tokens:
            return self
        return replace(self, tokens={key: token for key, token in self.tokens.items() if key != combatant_id})

    def with_token_visibility(self, combatant_id: str, visible: bool) -> BattleMap:
        if not _valid_token_id(combatant_id) or combatant_id not in self.tokens or type(visible) is not bool:
            raise ValueError("map_invalid_token")
        token = self.tokens[combatant_id]
        return self.with_token(combatant_id, token.q, token.r, visible)

    def public_tokens(self) -> Mapping[str, MapToken]:
        """Detached read-only placement projection, excluding all hidden tokens."""
        return MappingProxyType({key: token for key, token in self.tokens.items() if token.visible})
