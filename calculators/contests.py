"""Pure opposed rolls; Basic Set pp. 348-349. No session mutation."""

from dataclasses import dataclass

from utils.dice_roller import evaluate_success_roll


@dataclass(frozen=True)
class ContestResult:
    attacker_target: int
    defender_target: int
    attacker_margin: int
    defender_margin: int
    winner: str
    margin_of_victory: int


def quick_contest(attacker: int, defender: int, attack_roll: int, defense_roll: int,
                  *, resistance: bool = False, rule_of_16: bool = False) -> ContestResult:
    """Resistance requires attacker success and awards ties to the defender.

    Critical outcomes do not replace the comparison of margins. Spell-specific
    automatic effects on a critical casting success belong to the spell engine.
    """
    if rule_of_16:
        attacker = min(attacker, max(16, defender))
    attack = evaluate_success_roll(attacker, attack_roll)
    evaluate_success_roll(defender, defense_roll)  # Validate explicit 3d rolls.
    am, dm = attacker - attack_roll, defender - defense_roll
    difference = am - dm
    winner = "attacker" if difference > 0 else "defender" if difference < 0 else "tie"
    if resistance and (not attack["success"] or difference <= 0):
        winner = "defender"
    return ContestResult(attacker, defender, am, dm, winner, abs(difference))


def supernatural_target(skill: int, resistance: int, living_or_sapient: bool = True) -> int:
    return min(skill, max(16, resistance)) if living_or_sapient else skill


def long_distance_modifier(distance_yards: float) -> int:
    """Information magic distance bands, B241; round up to the next band."""
    import math
    if not math.isfinite(distance_yards) or distance_yards < 0:
        raise ValueError("invalid_casting_input")
    extra = 0
    while distance_yards > 1_760_000:
        distance_yards /= 10
        extra -= 2
    for limit, penalty in ((200, 0), (880, -1), (1760, -2), (5280, -3),
                           (17600, -4), (52800, -5), (176000, -6),
                           (528000, -7), (1760000, -8)):
        if distance_yards <= limit:
            return penalty + extra
    raise AssertionError("unreachable distance")
