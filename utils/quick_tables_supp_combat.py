"""Opt-in combat supplement references; never modify Basic Set or session state."""

import math

from utils.dice_roller import ceil_range_distance, get_range_modifier, same_range_boundary
from utils.quick_tables_cards import Card, Field, Result, label, line, measure


_PREFIX = 'qt_scombat_'
_TS = 'GURPS Tactical Shooting'
_EC = 'GURPS Tactical Shooting: Extreme Conditions'
_MA = 'GURPS Martial Arts'
_ACTION = 'GURPS Action 2: Exploits'


def _line(key, **values):
    return line(_PREFIX + key, **values)


def _label(key):
    return label(_PREFIX + key)


def _choice(key, default, options, category=None):
    category = category or key
    return Field(key, _PREFIX + key, kind='choice', default=default,
                 options=tuple((value, _PREFIX + category + '_' + value) for value in options))


def _integer(key, default='0', minimum=0, maximum=None):
    return Field(key, _PREFIX + key, kind='integer', default=default, minimum=minimum, maximum=maximum)


def _number(key, default='0', minimum=0, maximum=None, unit=None):
    return Field(key, _PREFIX + key, default=default, minimum=minimum, maximum=maximum, unit=unit)


def _check(key, default=False):
    return Field(key, _PREFIX + key, kind='bool', default=default)


def _card(key, section, pages, fields, calculate, source, requirement):
    return Card(key, section, _PREFIX + key + '_title', pages, fields, calculate,
                source=source, requirement=_PREFIX + 'requires_' + requirement)


def _shooting_method(v):
    method, gear = v['shooting_method'], v['sight_gear']
    if method != 'unsighted' and (v['hip_shot'] or gear == 'goggles'):
        return Result((_line('sights_no_sighted'),))
    if method == 'unsighted' and gear == 'weapon_night_sight':
        return Result((_line('sights_no_weapon_night_sight'),))
    if v['target_not_visible']:
        return Result((_line('sights_no_visibility'), _line('sights_' + method)))
    near = v['distance'] <= v['perception'] or same_range_boundary(v['distance'], v['perception'])
    relief = 1 if method == 'unsighted' and near and v['darkness'] < 0 else 0
    gear_penalty = (-1 if method == 'unsighted' else -4) if gear == 'mask' else -3 if gear == 'goggles' else 0
    return Result((
        _line('sights_' + method),
        _line('sights_modifiers', darkness=v['darkness'], relief=relief, gear=gear_penalty,
              modifier=v['darkness'] + relief + gear_penalty),
        _line('sights_scope'),
    ))


def _tactical_cover(v):
    # Attacks on the shooter bypassing cover, and shooter firing around cover.
    incoming, outgoing = {'very_light': (-1, 0), 'light': (-2, 0),
                          'medium': (-3, -2), 'heavy': (-4, -4)}[v['cover_grade']]
    if v['braced_and_aimed']:
        outgoing = 0
    return Result((_line('cover_pair', incoming=incoming, outgoing=outgoing), _line('cover_scope')))


def _rangefinding(v):
    mode = v['range_source']
    exact = mode in ('measured', 'landmark')
    modifier = (3 if v['sights_set'] else 0) if exact else 1 if mode == 'near_landmark' else 0
    lines = [_line('rangefinding_acc', modifier=modifier)]
    if exact and not v['sights_set']:
        lines.append(_line('rangefinding_set_sights'))
    lines.append(_line('rangefinding_scope'))
    return Result(tuple(lines))


# (Minimum and maximum increments in yards, precipitation flag).
_OBSCURATION = {
    'haze': (200, 550, True), 'mist': (100, 200, True), 'fog': (70, 100, True),
    'dense_fog': (45, 70, True), 'pea_soup': (None, 10, True),
    'light_drizzle': (90, None, True), 'drizzle': (45, 90, True), 'heavy_drizzle': (25, 45, True),
    'light_rain': (15, 25, True), 'rain': (8, 15, True), 'heavy_rain': (None, 8, True),
    'very_light_snow': (45, 90, True), 'light_snow': (25, 45, True),
    'moderate_snow': (15, 25, True), 'heavy_snow': (8, 15, True), 'blizzard': (None, 8, True),
    'sparse': (11, None, False), 'normal': (8, 10, False), 'thick': (5, 7, False),
    'dense': (2, 4, False), 'impenetrable': (None, 1, False),
}


def _obscuration(v):
    low, high, precipitation = _OBSCURATION[v['obscuration']]
    base = v['chosen_increment']
    shelter = 2 if precipitation and v['beneath_vegetation'] else 1
    if low is None:
        parts = [_line('increment_at_most', high=measure(high, 'yards'))]
    elif high is None:
        parts = [_line('increment_at_least', low=measure(low, 'yards'))]
    else:
        parts = [_line('increment_interval', low=measure(low, 'yards'), high=measure(high, 'yards'))]
    if base is None:
        parts.append(_line('increment_select'))
    else:
        if ((low is not None and base < low and not same_range_boundary(base, low))
                or (high is not None and base > high and not same_range_boundary(base, high))):
            raise ValueError(_PREFIX + 'invalid_increment')
        effective = base * shelter
        steps = v['affected_distance'] / effective
        nearest = round(steps)
        full_steps = nearest if same_range_boundary(steps, nearest) else math.floor(steps)
        parts.append(_line('increment_result', modifier=-full_steps, effective=measure(effective, 'yards')))
    if shelter == 2:
        parts.append(_line('increment_shelter'))
    parts.append(_line('increment_scope'))
    return Result(tuple(parts))


def _crosswind(v):
    threshold = 300
    range_penalty = get_range_modifier(ceil_range_distance(v['distance']))
    steps = max(0, get_range_modifier(threshold) - range_penalty)
    multiplier = {'none': 0, 'significant': 1, 'strong': 2}[v['crosswind']]
    penalty = steps * multiplier
    correction = min(penalty, 2 * v['aiming_successes'])
    return Result((_line('crosswind_result', modifier=correction - penalty, steps=steps,
                         threshold=measure(threshold, 'yards'), wind=-penalty, correction=correction),
                   _line('crosswind_scope')))


def _martial_maneuver(v):
    maneuver = v['martial_maneuver']
    if maneuver == 'telegraphic':
        return Result((_line('maneuver_telegraphic'), _line('maneuver_telegraphic_limits')))
    if not v['ready_melee']:
        return Result((_line('maneuver_not_ready'),))
    dice = v['damage_dice']
    if maneuver == 'defensive':
        return Result((_line('maneuver_defensive', damage=-max(2, dice)), _line('maneuver_defensive_limits')))
    hit = (2 if maneuver == 'determined' else 0) - (2 if v['second_step'] else 0)
    damage = 0
    if maneuver == 'strong' and v['st_based']:
        damage = max(1, dice // 2) if v['scale_strong'] else 1
    return Result((_line('maneuver_committed', hit=hit, damage=damage,
                         steps=2 if v['second_step'] else 1), _line('maneuver_committed_limits')))


def _martial_grip(v):
    grip, swing = v['martial_grip'], v['swing']
    side = v['side_attack']
    penalty = -max(2, v['damage_dice'])
    if grip == 'reversed':
        attack, damage, parry = 0, penalty if swing else 1, -2
    elif grip == 'defensive_one':
        attack, damage, parry = -2, 1, -1 if side else 1
    else:
        attack, damage, parry = 0, penalty if swing else 0, -1 if side else 1
    return Result((
        _line('grip_result', attack=attack, damage=damage, parry=parry),
        _line('grip_reversed_scope' if grip == 'reversed' else 'grip_defensive_scope'),
    ))


def _martial_step(v):
    if not v['standing_and_space']:
        return Result((_line('slip_unavailable'),))
    sideways = v['defensive_step'] == 'sideslip'
    retreat = 3 if v['mobile_defense'] else 1
    modifier = retreat - (1 if sideways else 2) - (1 if not sideways and v['stop_thrust'] else 0)
    return Result((_line('slip_result', modifier=modifier),
                   _line('slip_side_scope' if sideways else 'slip_toward_scope'), _line('slip_scope')))


def _severe_bleeding(v):
    wound, damage = v['bleeding_wound'], v['wound_damage']
    injury = v['bleeding_injury']
    if not injury:
        return Result((_line('bleed_no_injury'),))
    extra, seconds = 0, 60
    surgery = wound in ('neck', 'skull_eye', 'artery', 'vitals')
    if wound == 'neck' and damage in ('cut', 'imp', 'piercing'):
        extra, seconds = -2, 30
    elif wound == 'skull_eye' and damage in ('cut', 'imp', 'piercing', 'tight_beam'):
        seconds = 30
    elif wound == 'artery':
        if damage not in ('cut', 'imp', 'piercing', 'tight_beam'):
            return Result((_line('bleed_artery_ineligible'),))
        extra, seconds = (-4 if damage == 'cut' else -3), 30
    elif wound == 'vitals':
        extra, seconds = -4, 30
    elif wound in ('superficial', 'extremity', 'limb'):
        extra = {'superficial': -1, 'extremity': -2, 'limb': -3}[wound]
        if damage == 'cut' and wound != 'superficial':
            extra -= 1
        seconds = 30 if wound == 'limb' else 60
    ordinary = -(injury // 5)
    parts = [_line('bleed_result', modifier=ordinary + extra, size=ordinary, extra=extra, seconds=seconds),
             _line('bleed_surgery_scope' if surgery else 'bleed_first_aid_scope'), _line('bleed_scope')]
    if wound in ('neck', 'skull_eye', 'artery', 'vitals'):
        parts.append(_line('bleed_lasting_scope'))
    return Result(tuple(parts))


def _bad(v):
    magnitude = v['enemy_value'] // 4 if v['bad_method'] == 'enemy' else v['bad_value']
    apply = v['bad_context'] == 'phase' and not v['bad_npc_alternative']
    parts = [_line('bad_selected', bad=-magnitude)]
    if apply:
        parts.append(_line('bad_effective', target=v['task_skill'] + v['personal_adjustments'] - magnitude))
    else:
        parts.append(_line('bad_not_applied'))
    if v['bad_npc_alternative']:
        parts.append(_line('bad_npc_skill', skill=10 + magnitude))
    parts.append(_line('bad_scope'))
    return Result(tuple(parts))


_CHASE = dict(zip(('close', 'short', 'medium', 'long', 'extreme'), (0, -3, -7, -11, -15)))


def _chase(v):
    if v['chase_method'] == 'distance':
        distance = ceil_range_distance(v['distance'])
        bands = tuple(_CHASE)
        index = sum(distance > threshold for threshold in (5, 20, 100, 500))
        band = bands[index]
    else:
        band = v['chase_band']
    parts = [_line('chase_result', band=_label('chase_band_' + band), modifier=_CHASE[band])]
    static = v['static_parties']
    margin = v['victory_margin']
    if static == 'both':
        parts.append(_line('chase_both_static'))
    elif static == 'one':
        parts.append(_line('chase_one_static'))
    elif margin is not None:
        parts.append(_line('chase_steps', steps=2 if margin >= 10 else 1 if margin >= 5 else 0))
    parts.append(_line('chase_scope'))
    return Result(tuple(parts))


PACKS = {
    'tactical': (
        _card('ts_sights', 'combat', (13, 14, 19, 20), (
            _choice('shooting_method', 'unsighted', ('unsighted', 'sighted', 'aimed')),
            _choice('sight_gear', 'standard', ('standard', 'mask', 'goggles', 'weapon_night_sight')),
            _number('distance', '10', maximum=1e9, unit='yards'), _integer('perception', '10', maximum=100),
            _integer('darkness', '-2', minimum=-10, maximum=0),
            _check('hip_shot'), _check('target_not_visible'),
        ), _shooting_method, _TS, 'sights'),
        _card('ts_cover', 'combat', (28,), (
            _choice('cover_grade', 'medium', ('very_light', 'light', 'medium', 'heavy')),
            _check('braced_and_aimed'),
        ), _tactical_cover, _TS, 'cover'),
        _card('ts_rangefinding', 'combat', (27,), (
            _choice('range_source', 'measured', ('unknown', 'measured', 'landmark', 'near_landmark')),
            _check('sights_set'),
        ), _rangefinding, _TS, 'rangefinding'),
        _card('ts_obscuration', 'senses', (6, 7), (
            _choice('obscuration', 'fog', _OBSCURATION),
            _number('chosen_increment', '', minimum=.01, maximum=1e7, unit='yards'),
            _number('affected_distance', '100', maximum=1e9, unit='yards'), _check('beneath_vegetation'),
        ), _obscuration, _EC, 'obscuration'),
        _card('ts_crosswind', 'combat', (7,), (
            _number('distance', '1000', maximum=1e9, unit='yards'),
            _choice('crosswind', 'significant', ('none', 'significant', 'strong')),
            _integer('aiming_successes', maximum=100),
        ), _crosswind, _EC, 'wind'),
    ),
    'martial_arts': (
        _card('ma_maneuvers', 'combat', (99, 100, 113), (
            _choice('martial_maneuver', 'determined', ('determined', 'strong', 'defensive', 'telegraphic')),
            _check('ready_melee', True), _check('second_step'), _check('st_based', True),
            _check('scale_strong'), _integer('damage_dice', '2', maximum=10000),
        ), _martial_maneuver, _MA, 'maneuvers'),
        _card('ma_grips', 'combat', (109, 111, 112), (
            _choice('martial_grip', 'defensive_one', ('defensive_one', 'defensive_two', 'reversed')),
            _check('swing'), _check('side_attack'), _integer('damage_dice', '2', maximum=10000),
        ), _martial_grip, _MA, 'grips'),
        _card('ma_defensive_step', 'combat', (124,), (
            _choice('defensive_step', 'sideslip', ('sideslip', 'slip')),
            _check('standing_and_space', True), _check('mobile_defense'), _check('stop_thrust'),
        ), _martial_step, _MA, 'step'),
        _card('ma_severe_bleeding', 'trauma', (137, 138), (
            _choice('bleeding_wound', 'neck', ('neck', 'skull_eye', 'artery', 'vitals',
                                              'superficial', 'extremity', 'limb', 'ordinary')),
            _choice('wound_damage', 'cut', ('cut', 'imp', 'piercing', 'tight_beam', 'other')),
            _integer('bleeding_injury', '10', maximum=100000),
        ), _severe_bleeding, _MA, 'bleeding'),
    ),
    'action': (
        _card('action_bad', 'combat', (4, 5), (
            _choice('bad_method', 'manual', ('manual', 'enemy')),
            _integer('bad_value', '5', maximum=10), _integer('enemy_value', '20', maximum=40),
            _choice('bad_context', 'phase', ('phase', 'detailed', 'combat', 'chase')),
            _integer('task_skill', '12', maximum=100), _integer('personal_adjustments', minimum=-100, maximum=100),
            _check('bad_npc_alternative'),
        ), _bad, _ACTION, 'bad'),
        _card('action_chases', 'travel', (31, 34, 35), (
            _choice('chase_method', 'distance', ('distance', 'band')),
            _number('distance', '30', maximum=1e9, unit='yards'), _choice('chase_band', 'medium', _CHASE),
            _integer('victory_margin', '', maximum=100), _choice('static_parties', 'neither', ('neither', 'one', 'both')),
        ), _chase, _ACTION, 'chases'),
    ),
}
