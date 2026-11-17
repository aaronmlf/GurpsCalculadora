"""Typed, read-only references for the Basic Set Revised workbench."""
from dataclasses import dataclass
from typing import Callable
import math


@dataclass(frozen=True)
class Field:
    key: str
    title: str
    kind: str = 'number'
    default: str | bool = '0'
    options: tuple = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    unit: str | None = None

    def parse(self, raw):
        """Parse a single canonical value; blank defaults mark optional fields."""
        if self.kind == 'bool' and isinstance(raw, bool):
            return raw
        if self.kind == 'choice' and any(key == raw for key, _ in self.options):
            return raw
        if self.kind not in ('number', 'integer') or not isinstance(raw, str):
            raise ValueError('qt_reference_invalid_field')
        raw = raw.strip().replace(',', '.')
        if not raw and self.default == '':
            return None
        try:
            if not raw or len(raw) > 64:
                raise ValueError
            value = int(raw) if self.kind == 'integer' else float(raw)
            if not math.isfinite(value):
                raise ValueError
        except (ValueError, OverflowError):
            raise ValueError('qt_reference_invalid_integer' if self.kind == 'integer'
                             else 'qt_reference_invalid_number') from None
        if ((self.minimum is not None and value < self.minimum)
                or (self.maximum is not None and value > self.maximum)):
            raise ValueError('qt_reference_out_of_range')
        return value


@dataclass(frozen=True)
class Quantity:
    value: int | float
    unit: str


def measure(value, unit):
    return Quantity(value, unit)


@dataclass(frozen=True)
class Localized:
    key: str


def label(key):
    return Localized(key)


@dataclass(frozen=True)
class Line:
    key: str
    arguments: dict


def line(key, **kwargs):
    return Line(key, kwargs)


@dataclass(frozen=True)
class Result:
    lines: tuple[Line, ...]
    expression: str | None = None
    allows_roll: bool = True


@dataclass(frozen=True)
class Card:
    key: str
    section: str
    title: str
    pages: str | int | tuple[int, ...]
    fields: tuple[Field, ...]
    calculate: Callable[[dict], Result]
    tool: int | None = None
    roll: tuple[str, int, int] | None = None
    source: str = 'Basic Set Revised'
    requirement: str | None = None
    package: str = 'basic'

    def __post_init__(self):
        if isinstance(self.pages, tuple):
            object.__setattr__(self, 'pages', ', '.join(map(str, self.pages)))
        elif type(self.pages) is int:
            object.__setattr__(self, 'pages', str(self.pages))

    def resolve(self, raw_values):
        return self.calculate({field.key: field.parse(raw_values.get(field.key, field.default))
                               for field in self.fields})


SECTIONS = ('senses', 'travel', 'trauma', 'hazards', 'objects', 'magic')
SUPPLEMENT_SECTIONS = ('combat', 'powers', 'social', 'battles', 'space')


def reference_cards(packages=()):
    """Import the small reference books only upon opening the reference view."""
    from utils.quick_tables_explore import CARDS as explore
    from utils.quick_tables_hazards import CARDS as hazards
    from utils.quick_tables_prep import CARDS as prep
    from utils.quick_tables_packages import enabled_cards

    return tuple(explore) + tuple(hazards) + tuple(prep) + enabled_cards(packages)
