"""Independent, bounded dice rolls for the GM, without damage rounding rules."""

from array import array
from dataclasses import dataclass
import random
import re
from typing import Callable, Iterable, Optional, Protocol, Tuple, Union


MAX_DICE = 10_000_000
MAX_SIDES = 1_000_000
MAX_MODIFIER = 1_000_000_000
MAX_EXPRESSION_LENGTH = 128
ROLL_CHUNK_SIZE = 10_000

_EXPRESSION = re.compile(
    r"\s*([0-9]+)\s*[dD]\s*([0-9]*)\s*(?:([+-])\s*([0-9]+)\s*)?"
)


class DiceRollError(ValueError):
    """A machine-readable validation error that the GUI can translate."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RandomSource(Protocol):
    def randint(self, lower: int, upper: int) -> int:
        """Return an integer in the inclusive interval."""


@dataclass(frozen=True)
class DiceExpression:
    expression: str
    count: int
    sides: int
    modifier: int


@dataclass(frozen=True)
class DiceRollResult:
    expression: str
    count: int
    sides: int
    modifier: int
    rolls: Union[Tuple[int, ...], memoryview]
    subtotal: int
    total: int


def _bounded_integer(digits: str, maximum: int, code: str) -> int:
    # Check length before int(), including long strings containing only zeros.
    if len(digits) > len(str(maximum)):
        raise DiceRollError(code)
    value = int(digits)
    if value > maximum:
        raise DiceRollError(code)
    return value


def parse_dice(expression: str) -> DiceExpression:
    """Parse ``104d6+20`` or GURPS shorthand ``3d`` using no executable code.

    Whitespace may separate tokens and the letter D is case-insensitive.
    The supported grammar is one group of dice and an optional integer add.
    Bounds are checked before callers consume randomness.
    """
    if not isinstance(expression, str) or len(expression) > MAX_EXPRESSION_LENGTH:
        raise DiceRollError("invalid_expression")
    match = _EXPRESSION.fullmatch(expression)
    if match is None:
        raise DiceRollError("invalid_expression")
    count = _bounded_integer(match[1], MAX_DICE, "dice_count")
    sides = (
        _bounded_integer(match[2], MAX_SIDES, "dice_sides") if match[2] else 6
    )
    if count < 1:
        raise DiceRollError("dice_count")
    if sides < 1:
        raise DiceRollError("dice_sides")
    modifier = (
        _bounded_integer(match[4], MAX_MODIFIER, "dice_modifier") if match[4] else 0
    )
    if match[3] == "-":
        modifier = -modifier
    canonical = f"{count}d{sides}"
    if modifier:
        canonical += f"{modifier:+d}"
    return DiceExpression(canonical, count, sides, modifier)


def roll_dice(
    expression: str,
    *,
    rng: Optional[RandomSource] = None,
    values: Optional[Iterable[int]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> DiceRollResult:
    """Roll the parsed group and retain every die, subtotal, add and final sum.

    ``rng`` can be a random.Random instance or any object with randint().
    ``values`` supplies exactly one valid integer per die for deterministic
    examples and tests. Explicit values do not consume randomness. Large rolls
    use compact storage and expose a readonly memoryview. ``progress`` receives
    (completed dice, total dice) after each 10,000-die chunk and at completion.
    ``should_cancel`` is checked before the first die and between chunks; an
    Event.is_set method can be passed directly. This is a general-purpose sum:
    unlike damage, negative results are preserved.
    """
    parsed = parse_dice(expression)
    explicit = None
    if values is not None:
        try:
            explicit = iter(values)
        except TypeError as error:
            raise DiceRollError("explicit_rolls") from error
    source = rng if rng is not None else random
    stored = [] if parsed.count <= ROLL_CHUNK_SIZE else array("I")
    subtotal = 0
    sentinel = object()
    for chunk_start in range(0, parsed.count, ROLL_CHUNK_SIZE):
        if should_cancel is not None and should_cancel():
            raise DiceRollError("cancelled")
        chunk_end = min(chunk_start + ROLL_CHUNK_SIZE, parsed.count)
        for _ in range(chunk_start, chunk_end):
            if explicit is not None:
                value = next(explicit, sentinel)
                if type(value) is not int or not 1 <= value <= parsed.sides:
                    raise DiceRollError("explicit_rolls")
            else:
                value = source.randint(1, parsed.sides)
            stored.append(value)
            subtotal += value
        if progress is not None:
            progress(chunk_end, parsed.count)
    if explicit is not None and next(explicit, sentinel) is not sentinel:
        raise DiceRollError("explicit_rolls")
    rolls = tuple(stored) if isinstance(stored, list) else memoryview(stored).toreadonly()
    return DiceRollResult(
        parsed.expression,
        parsed.count,
        parsed.sides,
        parsed.modifier,
        rolls,
        subtotal,
        subtotal + parsed.modifier,
    )
