"""Pacote de calculadoras GURPS 4e."""

from .knockback import KnockbackCalculator
from .slam import SlamCalculator
from .falls import FallsCalculator
from .collisions import CollisionsCalculator
from .explosions import ExplosionsCalculator
from .falling_objects import FallingObjectsCalculator
from .combat import CombatCalculator

__all__ = [
    "KnockbackCalculator",
    "SlamCalculator",
    "FallsCalculator",
    "CollisionsCalculator",
    "ExplosionsCalculator",
    "FallingObjectsCalculator",
    "CombatCalculator"
]