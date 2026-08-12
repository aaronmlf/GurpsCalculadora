"""Pacote de utilitários GURPS 4e."""

from .dice_roller import roll_dice, roll_3d6, roll_1d6, roll_2d6, get_damage_dice, get_falling_velocity, calculate_collision_damage
from .i18n import I18n, get_i18n, t

__all__ = [
    "roll_dice",
    "roll_3d6",
    "roll_1d6",
    "roll_2d6",
    "get_damage_dice",
    "get_falling_velocity",
    "calculate_collision_damage",
    "I18n",
    "get_i18n",
    "t"
]