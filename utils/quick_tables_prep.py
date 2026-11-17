"""Read-only Basic Set Revised references for equipment and preparation."""

import math

from calculators.contests import long_distance_modifier
from utils.dice_roller import ceil_range_distance, collision_damage_expression, evaluate_success_roll
from utils.quick_tables_cards import Card, Field, Result, label, line, measure


def _options(*keys):
    return tuple((key, 'qt_prep_' + key) for key in keys)


def _ceil_scaled_cube_root(value, scale, divisor=1):
    """Round up, without promoting exact thresholds (e.g. 8 lb -> 8 HP)."""
    estimate = math.ceil(scale * math.cbrt(value / divisor))
    numerator, denominator = value.as_integer_ratio()
    threshold = scale ** 3 * numerator
    denominator *= divisor
    while estimate > 1 and (estimate - 1) ** 3 * denominator >= threshold:
        estimate -= 1
    while estimate ** 3 * denominator < threshold:
        estimate += 1
    return estimate


def _object_hp(v):
    weight, model = v['weight'], v['model']
    scale = {'unliving': 4, 'homogenous': 8, 'diffuse': 8, 'building': 100}[model]
    divisor = 2000 if model == 'building' else 1  # Short tons for B558's building formula.
    hp = _ceil_scaled_cube_root(weight, scale, divisor)
    return Result((line('qt_prep_hp_result', hp=hp, weight=measure(weight, 'pounds')),
                   line('qt_prep_hp_guide')))


# Cover ratings, not an object's intrinsic DR or HP (B559).
_COVER_RATINGS = {
    'aluminum': (20, 30), 'brick': (5, 8), 'concrete': (6, 9),
    'reinforced_concrete': (10, 12), 'window_glass': (5, 8),
    'ballistic_glass': (10, 20), 'iron': (40, 60), 'sandbags': (3, 3),
    'mild_steel': (50, 60), 'hard_steel': (60, 70), 'stone': (8, 13), 'wood': (0.5, 1),
}

_ERODING_COVER = frozenset({'brick', 'concrete', 'reinforced_concrete', 'stone', 'wood'})


def _material_cover(v):
    mat, thickness = v['material'], v['thickness']
    low, high = _COVER_RATINGS[mat]
    result = [line('qt_prep_material_result', low=round(low * thickness * 36, 6),
                   high=round(high * thickness * 36, 6), thickness=measure(thickness, 'yards')),
              line('qt_prep_material_guide')]
    if mat in _ERODING_COVER:
        result.append(line('qt_prep_material_wear'))
    return Result(tuple(result))


def _barrier_cover(v):
    added_hp = {'slab': 0, 'homogenous': v['hp'] // 4, 'unliving': v['hp'] // 2}[v['model']]
    return Result((line('qt_prep_cover_result', total=v['dr'] + added_hp,
                        dr=v['dr'], hp=added_hp), line('qt_prep_cover_guide')))


def _artifact_condition(v):
    hp, current = v['hp'], v['current_hp']
    building = v['model'] == 'building'
    if current <= -5 * hp:
        state = 'collapse' if building else 'destroyed'
    elif current <= -hp:
        state = 'collapse_check' if building else 'destruction_check'
    elif current <= 0:
        state = 'building_disable_check' if building else 'stress_check' if v['stressed'] else 'wait_for_stress'
    elif 3 * current < hp:
        state = 'impaired'
    else:
        state = 'above_thresholds'
    return Result((line('qt_prep_artifact_hp_result', current=current, hp=hp),
                   line('qt_prep_artifact_' + state), line('qt_prep_artifact_guide')))


def _fixed_obstacle(v):
    raw = v['hp'] * v['velocity'] / 100
    if not raw:
        return Result((line('qt_prep_collision_none'),))
    incoming_raw = raw * (2 if v['surface'] == 'hard' else 1)
    outgoing = collision_damage_expression(raw)[1]
    incoming = collision_damage_expression(incoming_raw)[1]
    result = [line('qt_prep_collision_dice', incoming=incoming, outgoing=outgoing)]
    if v['breakable']:
        result.append(line('qt_prep_collision_cap', cap=v['obstacle_hp'] + v['dr']))
    if v['surface'] == 'elastic':
        result.append(line('qt_prep_collision_elastic', dr=v['elastic_dr']))
    result.append(line('qt_prep_collision_guide'))
    return Result(tuple(result))


# B554 codes preserve case, notably small/large windows and superstructures.
_VEHICLE_LOCATIONS = {
    'body': ('hull', 0), 'vitals': ('vital_area', -3), 'A': ('arm_mount', -2),
    'C': ('tracks', -2), 'D': ('draft_animal', None), 'E': ('exposed_rider', 0),
    'G': ('large_window', -3), 'g': ('small_window', -7), 'H': ('rotor', -2),
    'M': ('mast', -2), 'O': ('open_cabin', -3), 'R': ('runner', -4),
    'S': ('large_structure', -2), 's': ('small_structure', -5),
    'T': ('main_turret', -2), 't': ('independent_turret', -5),
    'W': ('wheel', -4), 'Wi': ('wing', -2), 'X': ('exposed_weapon', -7),
}
_VEHICLE_BANDS = (
    (4, ('g', 'X')), (5, ('s', 't')), (7, ('C', 'D', 'H', 'M', 'Wi')),
    (8, ('A', 'S', 'T')), (9, ('body', 'E')), (10, ('body',)),
    (11, ('G', 'O')), (12, ('A', 'S', 'T')), (14, ('C', 'D', 'H', 'M', 'Wi')),
    (16, ('R', 'W')), (18, ('vitals',)),
)


def _vehicle_name(code):
    return label('qt_prep_' + _VEHICLE_LOCATIONS[code][0])


def _vehicle_hit(v):
    roll, confirmed = v['roll'], v['location']
    if roll is None:
        return Result((line('qt_prep_vehicle_guide'),))
    candidates = next(codes for limit, codes in _VEHICLE_BANDS if roll <= limit)
    if candidates == ('body',):
        chosen = 'body'
    elif confirmed in candidates:
        chosen = confirmed
    elif confirmed == 'no_candidate':
        chosen = 'body'
    else:
        return Result((line('qt_prep_vehicle_pending', roll=roll),
                       *(line('qt_prep_vehicle_candidate', part=_vehicle_name(code)) for code in candidates),
                       line('qt_prep_vehicle_guide')))
    result = [line('qt_prep_vehicle_result', roll=roll, part=_vehicle_name(chosen))]
    penalty = _VEHICLE_LOCATIONS[chosen][1]
    result.append(line('qt_prep_vehicle_animal' if penalty is None else 'qt_prep_vehicle_penalty',
                       **({} if penalty is None else {'penalty': penalty})))
    return Result(tuple(result))


_MANA = tuple((key, 'magic_mana_' + key) for key in ('no_mana', 'low', 'normal', 'high', 'very_high'))


def _can_cast(mana, mage):
    if mana == 'no_mana':
        return 'qt_prep_magic_no_mana'
    if mana in ('low', 'normal') and not mage:
        return 'qt_prep_magic_need_magery'
    return None


def _casting_preparation(v):
    mana, mage = v['mana'], v['mage']
    blocked = _can_cast(mana, mage)
    if blocked:
        return Result((line(blocked),))
    mana_mod = -5 if mana == 'low' else 0
    skill = v['skill'] + mana_mod
    kind, seconds = v['kind'], v['time']
    reduction = max(0, (skill - 10) // 5) if kind != 'blocking' else 0
    ritual = ('ritual_large' if skill <= 9 else 'ritual_words_gesture' if skill <= 14
              else 'ritual_words_or_gesture' if skill <= 19 else 'ritual_none')
    if kind == 'blocking':
        seconds = 0
    elif skill <= 9:
        seconds *= 2
    elif skill >= 20 and kind != 'missile':
        divisor = 2 ** ((skill - 15) // 5)
        seconds = max(1, -(-seconds // divisor))
    result = [line('qt_prep_magic_skill', skill=skill, mod=mana_mod),
              line('qt_prep_magic_effect', cost=max(0, v['cost'] - reduction),
                   reduction=reduction, seconds=seconds),
              line('qt_prep_magic_ritual', ritual=label('qt_prep_' + ritual))]
    if v['maintenance'] is not None and kind != 'blocking':
        result.append(line('qt_prep_magic_maintenance_cost', cost=max(0, v['maintenance'] - reduction)))
    if mana == 'very_high':
        result.append(line('qt_prep_magic_very_high'))
        if mage:
            result.append(line('qt_prep_magic_very_high_recovery'))
    elif mana == 'low':
        result.append(line('qt_prep_magic_low_effect'))
    result.append(line('qt_prep_magic_guide'))
    return Result(tuple(result))


def _spell_range(v):
    mode, yards = v['mode'], v['yards']
    if mode == 'long_distance':
        return Result((line('qt_prep_spell_range_long', mod=long_distance_modifier(yards)),
                       line('qt_prep_spell_range_long_guide')))
    reach = 0 if v['touch'] else ceil_range_distance(yards)
    unseen = -5 if not v['touch'] and not v['see'] else 0
    return Result((line('qt_prep_spell_range_result', mod=-reach + unseen, range=-reach, unseen=unseen),
                   line('qt_prep_spell_range_guide_' + mode)))


def _spell_check(v):
    mana, roll, target = v['mana'], v['roll'], v['effective_skill']
    blocked = _can_cast(mana, v['mage'])
    if blocked:
        return Result((line(blocked),))
    if target < 3:
        return Result((line('qt_prep_spell_minimum_skill'),))
    if roll is None:
        return Result((line('qt_prep_spell_check_guide'),))
    rolled = evaluate_success_roll(target, roll)
    if rolled['success']:
        outcome = 'critical_success' if rolled['critical_success'] else 'success'
    else:
        outcome = 'critical_failure' if rolled['critical_failure'] or mana == 'very_high' else 'failure'
    result = [line('qt_prep_spell_check_outcome', roll=roll, target=target,
                   outcome=label('gm_dice_check_' + outcome))]
    if outcome == 'critical_failure':
        result.append(line('qt_prep_spell_backfire_reference'))
        if mana == 'very_high':
            result.append(line('qt_prep_magic_very_high'))
        elif mana == 'low':
            result.append(line('qt_prep_magic_low_effect'))
    result.append(line('qt_prep_spell_check_guide'))
    return Result(tuple(result))


_WEALTH_BY_TL = (250, 500, 750, 1000, 2000, 5000, 10_000, 15_000, 20_000, 30_000, 50_000, 75_000, 100_000)
_WEALTH_FACTORS = {'dead_broke': 0, 'poor': 0.2, 'struggling': 0.5,
                   'average': 1, 'comfortable': 2, 'wealthy': 5, 'very_wealthy': 20, 'filthy_rich': 100}
_STATUS_EXPENSES = (100, 300, 600, 1200, 3000, 12_000, 60_000, 600_000, 6_000_000, 60_000_000, 600_000_000)


def _wealth_and_status(v):
    base = _WEALTH_BY_TL[min(v['tl'], 12)]
    starting = int(base * _WEALTH_FACTORS[v['wealth']])
    if v['wealth'] == 'filthy_rich':
        starting *= 10 ** v['multimillionaire']
    movable = starting // 5 if v['settled'] else starting
    return Result((line('qt_prep_wealth_result', base=base, starting=starting),
                   line('qt_prep_wealth_split', movable=movable, settled=starting - movable),
                   line('qt_prep_status_result', monthly=_STATUS_EXPENSES[v['status'] + 2]),
                   line('qt_prep_wealth_guide')))


def _encounter(v):
    result = [] if v['roll'] is None else [line('qt_prep_encounter_slot', slot=v['roll'])]
    result.append(line('qt_prep_encounter_guide'))
    return Result(tuple(result))


CARDS = (
    Card('object_hp', 'objects', 'qt_prep_hp_title', '483, 558', (
        Field('weight', 'qt_prep_weight', default='8', minimum=1e-9, maximum=1e12, unit='pounds'),
        Field('model', 'qt_prep_object_model', 'choice', 'unliving', _options('unliving', 'homogenous', 'diffuse', 'building')),
    ), _object_hp, tool=7),
    Card('cover_material', 'objects', 'qt_prep_material_title', '558–559', (
        Field('material', 'qt_prep_material', 'choice', 'wood', _options(*_COVER_RATINGS)),
        Field('thickness', 'qt_prep_thickness', default='0.0277777777777778', minimum=0, maximum=1000, unit='yards'),
    ), _material_cover, tool=8),
    Card('cover_barrier', 'objects', 'qt_prep_cover_title', '408, 484', (
        Field('model', 'qt_prep_cover_model', 'choice', 'homogenous', _options('homogenous', 'slab', 'unliving')),
        Field('hp', 'qt_prep_hp', 'integer', '20', minimum=1, maximum=1_000_000),
        Field('dr', 'qt_prep_intrinsic_dr', 'integer', '4', minimum=0, maximum=1_000_000),
    ), _barrier_cover, tool=8),
    Card('artifact_condition', 'objects', 'qt_prep_artifact_title', '419, 483–485', (
        Field('model', 'qt_prep_artifact_model', 'choice', 'artifact', _options('artifact', 'building')),
        Field('hp', 'qt_prep_hp', 'integer', '10', minimum=1, maximum=1_000_000),
        Field('current_hp', 'qt_prep_current_hp', 'integer', '4', minimum=-10_000_000, maximum=1_000_000),
        Field('stressed', 'qt_prep_artifact_stressed', 'bool', True),
    ), _artifact_condition, tool=7),
    Card('fixed_obstacle', 'objects', 'qt_prep_collision_title', '430–431, 470', (
        Field('hp', 'qt_prep_mover_hp', 'integer', '10', minimum=1, maximum=1_000_000),
        Field('velocity', 'qt_prep_collision_speed', default='19', minimum=0, maximum=1_000_000, unit='yards_per_second'),
        Field('surface', 'qt_prep_surface', 'choice', 'hard', _options('hard', 'soft', 'elastic')),
        Field('breakable', 'qt_prep_breakable', 'bool', False),
        Field('obstacle_hp', 'qt_prep_obstacle_hp', 'integer', '10', minimum=1, maximum=1_000_000),
        Field('dr', 'qt_prep_intrinsic_dr', 'integer', '0', minimum=0, maximum=1_000_000),
        Field('elastic_dr', 'qt_prep_elastic_dr', 'integer', '5', minimum=0, maximum=1_000_000),
    ), _fixed_obstacle, tool=3),
    Card('vehicle_hit', 'objects', 'qt_prep_vehicle_title', '462–463, 470, 554–555', (
        Field('location', 'qt_prep_vehicle_location', 'choice', 'unconfirmed',
              _options('unconfirmed', 'no_candidate') + tuple(
                  (code, 'qt_prep_' + item[0]) for code, item in _VEHICLE_LOCATIONS.items())),
        Field('roll', 'qt_prep_roll_3d', 'integer', '', minimum=3, maximum=18),
    ), _vehicle_hit, tool=12, roll=('roll', 3, 6)),
    Card('magic_preparation', 'magic', 'qt_prep_magic_title', '235–241', (
        Field('mana', 'qt_prep_mana', 'choice', 'normal', _MANA),
        Field('mage', 'qt_prep_mage', 'bool', True),
        Field('skill', 'qt_prep_base_skill', 'integer', '15', minimum=0, maximum=1000),
        Field('kind', 'qt_prep_spell_kind', 'choice', 'normal_spell', _options('normal_spell', 'missile', 'blocking')),
        Field('cost', 'qt_prep_spell_cost', 'integer', '2', minimum=0, maximum=1_000_000),
        Field('time', 'qt_prep_spell_seconds', 'integer', '1', minimum=1, maximum=1_000_000),
        Field('maintenance', 'qt_prep_spell_maintenance', 'integer', '', minimum=0, maximum=1_000_000),
    ), _casting_preparation, tool=10),
    Card('magic_range', 'magic', 'qt_prep_spell_range_title', '239, 241', (
        Field('mode', 'qt_prep_spell_range_mode', 'choice', 'regular', _options('regular', 'area', 'long_distance')),
        Field('yards', 'qt_prep_spell_distance', default='5', minimum=0, maximum=1e15, unit='yards'),
        Field('touch', 'qt_prep_touch', 'bool', False),
        Field('see', 'qt_prep_see', 'bool', True),
    ), _spell_range, tool=10),
    Card('magic_check', 'magic', 'qt_prep_check_title', '235–236, 241, 345, 348', (
        Field('mana', 'qt_prep_mana', 'choice', 'normal', _MANA),
        Field('mage', 'qt_prep_mage', 'bool', True),
        Field('effective_skill', 'qt_prep_effective_skill', 'integer', '12', minimum=-100, maximum=1000),
        Field('roll', 'qt_prep_roll_3d', 'integer', '', minimum=3, maximum=18),
    ), _spell_check, tool=10, roll=('roll', 3, 6)),
    Card('wealth_and_status', 'magic', 'qt_prep_wealth_title', '25–27, 265', (
        Field('tl', 'qt_prep_tl', 'integer', '8', minimum=0, maximum=100),
        Field('wealth', 'qt_prep_wealth_level', 'choice', 'average', _options(*_WEALTH_FACTORS)),
        Field('multimillionaire', 'qt_prep_multimillionaire', 'integer', '0', minimum=0, maximum=10),
        Field('settled', 'qt_prep_settled', 'bool', True),
        Field('status', 'qt_prep_status', 'integer', '0', minimum=-2, maximum=8),
    ), _wealth_and_status),
    Card('encounter_slot', 'magic', 'qt_prep_encounter_title', '503', (
        Field('roll', 'qt_prep_roll_1d', 'integer', '', minimum=1, maximum=6),
    ), _encounter, roll=('roll', 1, 6)),
)
