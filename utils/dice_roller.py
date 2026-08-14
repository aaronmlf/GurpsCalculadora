"""Dice and rules-table helpers for GURPS Basic Set, Fourth Edition Revised."""

import math
import random
import re
from typing import Dict, List, Tuple


_DICE_EXPRESSION = re.compile(
    r"(\d+)d(\d*)(?:([+-])(\d+))?(?:\*(\d+(?:\.\d+)?))?"
)


def roll_dice(expression: str, minimum: int = 0) -> Tuple[int, List[int]]:
    """Roll a GURPS dice expression such as ``2d+1`` or ``6d×2``.

    Damage cannot be negative. Callers handling non-crushing damage may pass
    ``minimum=1`` when the attack penetrates and the rule requires a minimum
    basic damage of one point.
    """
    normalized = expression.strip().lower().replace("×", "*").replace("x", "*")
    match = _DICE_EXPRESSION.fullmatch(normalized)
    if not match:
        raise ValueError(f"Invalid dice expression: {expression}")

    number = int(match.group(1))
    sides = int(match.group(2)) if match.group(2) else 6
    if number < 1 or sides < 1:
        raise ValueError("Dice count and number of sides must be positive.")

    sign = match.group(3)
    modifier_value = int(match.group(4)) if match.group(4) else 0
    modifier = -modifier_value if sign == "-" else modifier_value
    multiplier = float(match.group(5)) if match.group(5) else 1.0

    rolls = [random.randint(1, sides) for _ in range(number)]
    total = math.floor((sum(rolls) + modifier) * multiplier)
    return max(minimum, total), rolls


def roll_3d6() -> Tuple[int, List[int]]:
    """Roll the standard GURPS success roll."""
    rolls = [random.randint(1, 6) for _ in range(3)]
    return sum(rolls), rolls


def roll_1d6() -> int:
    """Roll 1d."""
    return random.randint(1, 6)


def roll_2d6() -> int:
    """Roll 2d."""
    return random.randint(1, 6) + random.randint(1, 6)


# Basic Set Revised, p. 16. Values above ST 40 are intentionally listed at
# the five-point breakpoints used by the printed table.
_DAMAGE_TABLE: Dict[int, Tuple[str, str]] = {
    1: ("1d-6", "1d-5"), 2: ("1d-6", "1d-5"),
    3: ("1d-5", "1d-4"), 4: ("1d-5", "1d-4"),
    5: ("1d-4", "1d-3"), 6: ("1d-4", "1d-3"),
    7: ("1d-3", "1d-2"), 8: ("1d-3", "1d-2"),
    9: ("1d-2", "1d-1"), 10: ("1d-2", "1d"),
    11: ("1d-1", "1d+1"), 12: ("1d-1", "1d+2"),
    13: ("1d", "2d-1"), 14: ("1d", "2d"),
    15: ("1d+1", "2d+1"), 16: ("1d+1", "2d+2"),
    17: ("1d+2", "3d-1"), 18: ("1d+2", "3d"),
    19: ("2d-1", "3d+1"), 20: ("2d-1", "3d+2"),
    21: ("2d", "4d-1"), 22: ("2d", "4d"),
    23: ("2d+1", "4d+1"), 24: ("2d+1", "4d+2"),
    25: ("2d+2", "5d-1"), 26: ("2d+2", "5d"),
    27: ("3d-1", "5d+1"), 28: ("3d-1", "5d+1"),
    29: ("3d", "5d+2"), 30: ("3d", "5d+2"),
    31: ("3d+1", "6d-1"), 32: ("3d+1", "6d-1"),
    33: ("3d+2", "6d"), 34: ("3d+2", "6d"),
    35: ("4d-1", "6d+1"), 36: ("4d-1", "6d+1"),
    37: ("4d", "6d+2"), 38: ("4d", "6d+2"),
    39: ("4d+1", "7d-1"), 40: ("4d+1", "7d-1"),
    45: ("5d", "7d+1"), 50: ("5d+2", "8d-1"),
    55: ("6d", "8d+1"), 60: ("7d-1", "9d"),
    65: ("7d+1", "9d+2"), 70: ("8d", "10d"),
    75: ("8d+2", "10d+2"), 80: ("9d", "11d"),
    85: ("9d+2", "11d+2"), 90: ("10d", "12d"),
    95: ("10d+2", "12d+2"), 100: ("11d", "13d"),
}


def _add_dice(expression: str, extra_dice: int) -> str:
    match = re.fullmatch(r"(\d+)d([+-]\d+)?", expression)
    if not match:
        raise ValueError(f"Cannot extend damage expression: {expression}")
    dice = int(match.group(1)) + extra_dice
    return f"{dice}d{match.group(2) or ''}"


def get_damage_dice(st: int) -> Tuple[str, str]:
    """Return thrust and swing damage from the Damage Table (p. 16)."""
    if st < 1:
        raise ValueError("ST must be at least 1.")
    if st <= 40:
        return _DAMAGE_TABLE[st]
    if st <= 100:
        breakpoint = 40 + ((st - 40) // 5) * 5
        return _DAMAGE_TABLE[breakpoint]

    extra_dice = (st - 100) // 10
    thrust, swing = _DAMAGE_TABLE[100]
    return _add_dice(thrust, extra_dice), _add_dice(swing, extra_dice)


_FALLING_VELOCITY_RANGES = (
    (1, 1, 5), (2, 2, 7), (3, 3, 8), (4, 4, 9), (5, 5, 10),
    (6, 6, 11), (7, 7, 12), (8, 8, 13), (9, 9, 14), (10, 11, 15),
    (12, 12, 16), (13, 14, 17), (15, 15, 18), (16, 17, 19),
    (18, 19, 20), (20, 21, 21), (22, 23, 22), (24, 25, 23),
    (26, 27, 24), (28, 29, 25), (30, 32, 26), (33, 34, 27),
    (35, 37, 28), (38, 39, 29), (40, 42, 30), (43, 45, 31),
    (46, 48, 32), (49, 51, 33), (52, 54, 34), (55, 57, 35),
    (58, 61, 36), (62, 64, 37), (65, 67, 38), (68, 71, 39),
    (72, 75, 40), (76, 79, 41), (80, 82, 42), (83, 86, 43),
    (87, 90, 44), (91, 95, 45), (96, 99, 46), (100, 103, 47),
    (104, 108, 48), (109, 112, 49),
)


def get_falling_velocity(distance_yards: int, gravity: float = 1.0) -> int:
    """Return impact velocity in yards/second (Basic Set Revised, p. 431)."""
    if distance_yards <= 0:
        return 0
    if gravity <= 0:
        raise ValueError("Gravity must be positive.")
    if gravity == 1.0:
        for lower, upper, velocity in _FALLING_VELOCITY_RANGES:
            if lower <= distance_yards <= upper:
                return velocity
    return round(math.sqrt(21.4 * gravity * distance_yards))


def collision_damage_expression(raw_dice: float) -> Tuple[int, str]:
    """Convert fractional collision dice to the expression specified on p. 430."""
    if raw_dice <= 0:
        return 0, "0d"
    if raw_dice < 1:
        if raw_dice <= 0.25:
            return 1, "1d-3"
        if raw_dice <= 0.5:
            return 1, "1d-2"
        return 1, "1d-1"
    dice = math.floor(raw_dice + 0.5)
    return dice, f"{dice}d"


def calculate_collision_damage(hp: int, velocity: int) -> Tuple[int, str]:
    """Return collision damage dice and expression for ``(HP × velocity)/100``."""
    if hp < 0 or velocity < 0:
        raise ValueError("HP and velocity cannot be negative.")
    return collision_damage_expression((hp * velocity) / 100)


def get_range_modifier(distance_yards: int) -> int:
    """Return the Size and Speed/Range Table range modifier (p. 550)."""
    if distance_yards <= 2:
        return 0
    thresholds = (3, 5, 7, 10, 15, 20, 30, 50, 70, 100,
                  150, 200, 300, 500, 700, 1000, 1500, 2000,
                  3000, 5000, 7000, 10000, 15000, 20000, 30000,
                  50000, 70000, 100000, 150000, 200000)
    for penalty, maximum in enumerate(thresholds, start=1):
        if distance_yards <= maximum:
            return -penalty
    penalty = len(thresholds)
    progression = (3, 5, 7, 10, 15, 20)
    scale = 100000
    while True:
        for factor in progression:
            penalty += 1
            if distance_yards <= factor * scale:
                return -penalty
        scale *= 10


def evaluate_success_roll(target: int, roll: int) -> Dict[str, object]:
    """Evaluate a 3d success roll, including the complete critical rules."""
    if not 3 <= roll <= 18:
        raise ValueError("A 3d roll must be between 3 and 18.")

    critical_success = roll <= 4 or (roll == 5 and target >= 15) or (roll == 6 and target >= 16)
    critical_failure = roll == 18 or (roll == 17 and target <= 15) or roll >= target + 10
    success = critical_success or (roll <= target and not critical_failure)
    return {
        "success": success,
        "critical_success": critical_success,
        "critical_failure": critical_failure,
        "margin": target - roll if success else roll - target,
    }
