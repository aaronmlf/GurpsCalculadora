"""
Utilitário para rolagem de dados no sistema GURPS
"""
import random
import re
from typing import Tuple, List


def roll_dice(expression: str) -> Tuple[int, List[int]]:
    """
    Rola dados com base em uma expressão GURPS.
    
    Formatos suportados:
    - "3d6" = 3 dados de 6 lados
    - "2d+1" = 2 dados de 6 + 1
    - "1d-2" = 1 dado de 6 - 2
    - "4d×2" = 4 dados de 6 × 2
    - "6d×1.5" = 4 dados de 6 × 1.5
    
    Retorna: (total, lista_de_resultados)
    """
    expression = expression.strip().lower().replace('×', '*').replace('x', '*')
    
    # Padrão para expressão de dados: XdY(+/-Z)(*(W))
    # Exemplos: 3d6, 2d+1, 1d-2, 6d*2, 1d, 4d-3*2
    pattern = r'(\d+)d(\d*)(?:([+-])(\d+))?(?:\*(\d+(?:\.\d+)?))?'
    match = re.match(pattern, expression)
    
    if not match:
        raise ValueError(f"Expressão inválida: {expression}")
    
    num_dice = int(match.group(1))
    sides_str = match.group(2)
    sides = int(sides_str) if sides_str else 6  # "1d" = 1d6
    sign = match.group(3)
    mod_value = int(match.group(4)) if match.group(4) else 0
    modifier = -mod_value if sign == '-' else mod_value
    multiplier = float(match.group(5)) if match.group(5) else 1.0
    
    # Rola os dados
    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    sum_rolls = sum(rolls)
    
    # Aplica modificadores
    result = sum_rolls + modifier
    result = int(result * multiplier)
    
    return result, rolls


def roll_3d6() -> Tuple[int, List[int]]:
    """
    Rola 3d6 padrão GURPS.
    
    Retorna: (total, lista_de_resultados)
    """
    rolls = [random.randint(1, 6) for _ in range(3)]
    return sum(rolls), rolls


def roll_1d6() -> int:
    """Rola 1d6."""
    return random.randint(1, 6)


def roll_2d6() -> int:
    """Rola 2d6."""
    return random.randint(1, 6) + random.randint(1, 6)


def get_damage_dice(st: int) -> Tuple[str, str]:
    """
    Retorna os dados de dano com base no ST.
    
    Retorna: (thrust_damage, swing_damage)
    """
    damage_table = {
        1: ("1d-6", "1d-5"),
        2: ("1d-6", "1d-4"),
        3: ("1d-5", "1d-4"),
        4: ("1d-5", "1d-3"),
        5: ("1d-4", "1d-3"),
        6: ("1d-4", "1d-2"),
        7: ("1d-3", "1d-2"),
        8: ("1d-3", "1d-1"),
        9: ("1d-2", "1d"),
        10: ("1d-1", "1d+1"),
        11: ("1d", "1d+2"),
        12: ("1d+1", "2d-1"),
        13: ("1d+2", "2d"),
        14: ("2d-1", "2d+1"),
        15: ("2d", "2d+2"),
        16: ("2d+1", "3d-1"),
        17: ("2d+2", "3d"),
        18: ("3d-1", "3d+1"),
        19: ("3d", "3d+2"),
        20: ("3d+1", "4d-1"),
        21: ("3d+2", "4d"),
        22: ("4d-1", "4d+1"),
        23: ("4d", "4d+2"),
        24: ("4d+1", "5d-1"),
        25: ("4d+2", "5d"),
    }
    
    # Para ST acima de 25 (GURPS B16)
    # Thrust: ciclo [+2, -1, 0, +1], base=4 + (extra+3)//4
    # Swing: 1 die acima de thrust, mod = thrust_mod no passo anterior
    if st > 25:
        extra = st - 25
        thrust_cycle = [2, -1, 0, 1]
        thrust_mod = thrust_cycle[extra % 4]
        thrust_dice = 4 + (extra + 3) // 4
        # Swing: mod é o thrust mod do passo anterior (extra 0 → mod 0)
        swing_mod = 0 if extra == 0 else thrust_cycle[(extra - 1) % 4]
        swing_dice = 5 + (extra + 2) // 4
        thrust_mod_str = f"+{thrust_mod}" if thrust_mod > 0 else (str(thrust_mod) if thrust_mod < 0 else "")
        swing_mod_str = f"+{swing_mod}" if swing_mod > 0 else (str(swing_mod) if swing_mod < 0 else "")
        thrust = f"{thrust_dice}d{thrust_mod_str}"
        swing = f"{swing_dice}d{swing_mod_str}"
        return thrust, swing
    
    return damage_table.get(st, ("1d", "1d+1"))


def get_falling_velocity(distance_yards: int) -> int:
    """
    Retorna a velocidade de queda com base na distância em jardas.
    Baseado na tabela de velocidade de queda do GURPS 4e.
    """
    falling_table = {
        1: 5, 2: 7, 3: 8, 4: 9, 5: 10,
        6: 11, 7: 12, 8: 13, 9: 14, 10: 15,
        11: 15, 12: 16, 13: 17, 14: 17, 15: 18,
        16: 19, 17: 19, 18: 20, 19: 20, 20: 21,
        21: 21, 22: 22, 23: 22, 24: 23, 25: 23,
        26: 24, 27: 24, 28: 25, 29: 25, 30: 26,
        31: 26, 32: 26, 33: 27, 34: 27, 35: 28,
        36: 28, 37: 28, 38: 29, 39: 29, 40: 30,
        41: 30, 42: 30, 43: 31, 44: 31, 45: 31,
        46: 32, 47: 32, 48: 32, 49: 33, 50: 33,
        51: 33, 52: 34, 53: 34, 54: 34, 55: 35,
        56: 35, 57: 35, 58: 36, 59: 36, 60: 36,
        61: 37, 62: 37, 63: 37, 64: 38, 65: 38,
        66: 38, 67: 39, 68: 39, 69: 39, 70: 40,
        71: 40, 72: 40, 73: 41, 74: 41, 75: 41,
        76: 42, 77: 42, 78: 42, 79: 43, 80: 43,
        81: 43, 82: 44, 83: 44, 84: 44, 85: 45,
        86: 45, 87: 45, 88: 46, 89: 46, 90: 46,
        91: 47, 92: 47, 93: 47, 94: 48, 95: 48,
        96: 48, 97: 49, 98: 49, 99: 49, 100: 50,
        101: 50, 102: 50, 103: 51, 104: 51, 105: 51,
        106: 52, 107: 52, 108: 52, 109: 53, 110: 53,
        111: 53, 112: 54,
    }
    
    if distance_yards in falling_table:
        return falling_table[distance_yards]
    elif distance_yards > 112:
        # Fórmula ajustada: √(25.8 × distância) baseado na tabela B431
        return int((25.8 * distance_yards) ** 0.5)
    else:
        return 5


def calculate_collision_damage(hp: int, velocity: int) -> Tuple[int, str]:
    """
    Calcula dano de colisão: (HP × velocidade) / 100
    
    Retorna: (dano_total, expressão_de_dados)
    """
    raw_damage = (hp * velocity) / 100
    
    # Trata frações menores que 1d
    if raw_damage < 1:
        if raw_damage <= 0.25:
            return 1, "1d-3"
        elif raw_damage <= 0.5:
            return 1, "1d-2"
        else:
            return 1, "1d-1"
    
    # Arredonda para o dado mais próximo
    dice = int(raw_damage + 0.5)
    return dice, f"{dice}d"