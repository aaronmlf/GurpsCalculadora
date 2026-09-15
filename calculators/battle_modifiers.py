"""Mass Combat pp. 31-32, 35-37: numerical modifiers, no session changes."""
import math

CLASSES = ('Air', 'Arm', 'Art', 'C3I', 'Cav', 'F', 'Eng', 'Nav')


def class_superiority(attacker, defender, attacker_total, defender_total, encounter=False):
    """Maps class -> [eligible offensive TS, allocated neutralizing TS].

    The caller selects applicable classes and allocates dual-use elements before
    calling. Totals already include terrain/quality/equipment adjustments.
    """
    bonuses = [{}, {}]
    for values in (attacker, defender):
        if not isinstance(values, dict) or set(values) - set(CLASSES):
            raise ValueError('invalid_class_strength')
        for pair in values.values():
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2 or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in pair)):
                raise ValueError('invalid_class_strength')
    for side, own, enemy, enemy_total in ((0, attacker, defender, defender_total),
                                          (1, defender, attacker, attacker_total)):
        for key in set(attacker) | set(defender):
            attack = own.get(key, (0, 0))[0]
            opposition = sum(enemy.get(key, (0, 0)))
            bonus = 0
            if attack > 0 and attack >= enemy_total * .01:
                ratio = attack / opposition if opposition else math.inf
                bonus = 3 if ratio >= 5 else 2 if ratio >= 3 else 1 if ratio >= 2 else 0
                if encounter and key in ('Air', 'Art', 'C3I'):
                    bonus = max(0, bonus - 1)
            bonuses[side][key] = bonus
    return bonuses


def position_after_round(a_pb, d_pb, a_strategy, d_strategy, margin, shift):
    attack = {'attack', 'all_out_attack', 'deliberate_attack', 'indirect_attack'}
    if margin == 0:
        if a_strategy == 'mobile_defense' and d_strategy != 'mobile_defense':
            balance = a_pb - d_pb - 1
            return max(0, balance), max(0, -balance)
        if d_strategy == 'mobile_defense' and a_strategy != 'mobile_defense':
            balance = a_pb - d_pb + 1
            return max(0, balance), max(0, -balance)
        return a_pb, d_pb
    winner, loser = (a_pb, d_pb) if margin > 0 else (d_pb, a_pb)
    strategy, opposing = (a_strategy, d_strategy) if margin > 0 else (d_strategy, a_strategy)
    movement = shift if strategy in attack or strategy == 'raid' else 0
    if opposing == 'all_out_defense':
        movement = max(0, movement - 1)
    forced = opposing in ('mobile_defense', 'fighting_retreat')
    if forced:
        movement += 1
    if strategy == 'raid' and not forced:
        loser = max(0, loser - movement)
    else:
        balance = winner - loser + movement
        winner, loser = max(0, balance), max(0, -balance)
    return (winner, loser) if margin > 0 else (loser, winner)
