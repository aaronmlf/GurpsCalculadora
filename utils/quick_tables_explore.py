"""Basic Set Revised quick checks for perception, terrain, and movement.

These lookups advise the GM; they do not roll secretly, consume resources,
decide whether a trail exists, or derive environmental conditions from maps.
"""

from dataclasses import dataclass
import math

from utils.dice_roller import same_range_boundary
from utils.quick_tables_cards import Card, Field, Result, line, measure, label


_PREFIX = 'qt_explore_'


def _line(key, **values):
    return line(_PREFIX + key, **values)


def _choice(key, default, category, options):
    return Field(key, _PREFIX + key, kind='choice', default=default,
                 options=tuple((value, _PREFIX + category + value) for value in options))


def _number(key, default='0', *, minimum=0, maximum=None, unit=None):
    return Field(key, _PREFIX + key, default=default, minimum=minimum, maximum=maximum, unit=unit)


def _integer(key, default='0', *, minimum=0, maximum=None):
    return Field(key, _PREFIX + key, kind='integer', default=default, minimum=minimum, maximum=maximum)


def _check(key, default=False):
    return Field(key, _PREFIX + key, kind='bool', default=default)


# B358 values only. The baselines are exact powers of two in yards.
_HEARING_BASELINES = dict(zip((
    'leaves', 'quiet_conversation', 'conversation', 'light_traffic', 'loud_conversation',
    'noisy_office', 'traffic', 'quiet_rock', 'heavy_traffic', 'jet', 'loud_rock', 'metallica',
), (2.0 ** exponent for exponent in range(-2, 10))))


def calculate_hearing(values):
    baseline = _HEARING_BASELINES[values['sound']]
    distance = values['hearing_distance']
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError(_PREFIX + 'invalid_hearing_distance')
    # A fractional step uses the farther band. frexp gives exact power-of-two
    # boundaries without computing an overflowing distance/baseline ratio.
    _, exponent = math.frexp(distance)
    boundary = math.ldexp(.5, exponent)
    steps = exponent - same_range_boundary(distance, boundary)
    distance_modifier = math.frexp(baseline)[1] - 1 - steps
    parts = [_line('hearing_baseline', distance=measure(baseline, 'yards')),
             _line('hearing_distance_modifier', modifier=distance_modifier)]
    if values['hearing_trait'] == 'deaf':
        parts.append(_line('hearing_deaf'))
    else:
        trait = {'normal': 0, 'discriminatory': 4, 'hard': -4}[values['hearing_trait']]
        if trait:
            parts.append(_line('hearing_trait_modifier', modifier=trait))
        parts.append(_line('sense_target', base=values['sense_base'], acute=values['acute'],
                           modifier=distance_modifier + trait + values['circumstances'],
                           target=values['sense_base'] + values['acute'] + distance_modifier + trait
                           + values['circumstances']))
    parts.append(_line('hearing_notes'))
    return Result(tuple(parts))


def calculate_vision(values):
    if values['vision_unavailable']:
        return Result((_line('vision_no_roll'), _line('sense_comprehension')))
    task = values['vision_task']
    bonus = 0
    if values['actively_watching']:
        if task == 'notice' and values['plain_target']:
            bonus = 10
        elif task == 'detail' and values['located_target']:
            bonus = 20
    ordinary = values['circumstances']
    base = values['sense_base']
    acute = values['acute']
    return Result((
        _line('vision_bonus', bonus=bonus),
        _line('sense_target', base=base, acute=acute, modifier=ordinary + bonus,
              target=base + acute + ordinary + bonus),
        _line('vision_notes'),
        _line('sense_comprehension'),
    ))


def calculate_taste_smell(values):
    sense = label(_PREFIX + 'taste_smell_sense_' + values['taste_smell_sense'])
    trait = values['taste_smell_trait']
    if trait == 'absent':
        return Result((_line('taste_smell_unavailable', sense=sense),))
    base, acute = values['sense_base'], values['acute']
    discrimination = 4 if trait == 'discriminatory' else 0
    net = discrimination + values['circumstances']
    return Result((
        _line('taste_smell_trait_modifier', sense=sense, modifier=discrimination),
        _line('sense_target', base=base, acute=acute, modifier=net, target=base + acute + net),
        _line('taste_smell_notes'),
        _line('sense_comprehension'),
    ))


_HORIZON_MILES = (.4, .5, .6, .8, 1, 1.2, 1.5, 1.75, 2, 2.5, 3, 3.5,
                  4.5, 5.5, 6.5, 8, 9.5, 12, 15, 18, 21)


def _horizon_miles(sm):
    if not -10 <= sm <= 30:
        raise ValueError(_PREFIX + 'invalid_horizon_size')
    tiers = max(0, (sm + 1) // 12)
    return _HORIZON_MILES[sm + 10 - 12 * tiers] * 10 ** tiers


def calculate_horizon(values):
    observer = _horizon_miles(values['observer_sm'])
    source = _horizon_miles(values['signal_sm'])
    maximum = observer + source
    within_horizon = (values['signal_distance'] <= maximum
                      or same_range_boundary(values['signal_distance'], maximum))
    parts = [
        _line('horizon_distance', maximum=measure(maximum, 'miles'),
              observer=measure(observer, 'miles'), source=measure(source, 'miles')),
        _line('horizon_status', status=label(_PREFIX + ('horizon_within' if within_horizon
                                                       else 'horizon_beyond'))),
    ]
    if within_horizon and values['deliberate_signal'] and values['actively_watching']:
        parts.append(_line('horizon_plain'))
    if within_horizon and values['light_signal']:
        parts.append(_line('horizon_light', bonus=-values['darkness']))
    parts.append(_line('horizon_notes'))
    return Result(tuple(parts))


@dataclass(frozen=True, slots=True)
class _Terrain:
    dice: int
    offset: int
    average: int
    tracking: int | None = None
    travel: tuple[float, float, float] | None = None  # minimum, average, maximum
    weather_sensitive_track: bool = False


# B573-574. Travel multipliers are for typical conditions in the named biome,
# not separate adjustments to stack with identical terrain/weather penalties.
_TERRAIN = {
    'arctic': _Terrain(1, -7, -4, -2, (.20, .50, 1), True),
    'desert': _Terrain(1, -7, -4, -2, (.20, .50, 1.25), True),
    'island': _Terrain(2, -7, 0, -2, (.20, .50, 1.25), True),
    'jungle': _Terrain(2, -7, 0, 0, (.20, .20, .20)),
    'mountain': _Terrain(1, -7, -4, -2, (.20, .20, .20)),
    'plains': _Terrain(2, -7, 0, 0, (.50, 1, 1.25)),
    'swamp': _Terrain(2, -7, 0, -4, (.20, .20, .20)),
    'woodlands': _Terrain(2, -7, 0, 0, (.20, .50, 1)),
    'bank': _Terrain(2, -6, 1),
    'ocean_vent': _Terrain(2, -6, 1),
    'reef': _Terrain(2, -6, 1),
    'lagoon': _Terrain(2, -6, 1),
    'lake': _Terrain(2, -7, 0),
    'river': _Terrain(2, -7, 0),
    'ocean': _Terrain(2, -8, -1),
    'sea': _Terrain(2, -8, -1),
}


def calculate_terrain(values):
    terrain_key = values['terrain']
    terrain = _TERRAIN[terrain_key]
    low, high = terrain.dice + terrain.offset, terrain.dice * 6 + terrain.offset
    mode = values['foraging_method']
    if mode == 'roll':
        roll_sum = values['foraging_roll']
        if not terrain.dice <= roll_sum <= 6 * terrain.dice:
            raise ValueError(_PREFIX + 'invalid_foraging_roll')
        modifier = roll_sum + terrain.offset
    else:
        modifier = {'average': terrain.average, 'minimum': low, 'maximum': high}[mode]
    formula = f'{terrain.dice}d6{terrain.offset:+d}'
    parts = [_line('terrain_foraging', modifier=modifier, formula=formula, low=low, high=high),
             _line('terrain_foraging_note')]
    if terrain.travel is None:
        parts.append(_line('terrain_underwater'))
    else:
        assert terrain.tracking is not None
        tracking = terrain.tracking
        conditions = values['track_conditions']
        if terrain.weather_sensitive_track:
            tracking = {'typical': tracking, 'loose_calm': 0, 'loose_wind_water': -4}[conditions]
        elif conditions != 'typical':
            parts.append(_line('terrain_tracking_condition_ignored'))
        travel = values['terrain_travel_surface']
        if travel in ('ski', 'skate'):
            if terrain_key != 'arctic':
                raise ValueError(_PREFIX + 'invalid_terrain_surface')
            multiplier = 1 if travel == 'ski' else 1.25
        else:
            multiplier = terrain.travel[{'slow': 0, 'average': 1, 'fast': 2}[travel]]
        parts.extend((_line('terrain_tracking', modifier=tracking), _line('terrain_travel', factor=multiplier),
                      _line('terrain_mixed')))
    return Result(tuple(parts), expression=f'{terrain.dice}d6')


def calculate_hiking(values):
    move = values['trail_move']
    method = values['hiking_model']
    effective = (move * values['ground_enhancement'] * values['trail_terrain'] * values['trail_weather']
                 * (1.2 if values['hiking_success'] else 1))
    parts = []
    if method == 'basic':
        daily = 10 * effective
        parts.append(_line('hiking_full_day'))
    else:
        hours = 12 if method == 'skilled' else 8
        if values['hiking_foraging_hours'] > hours:
            raise ValueError(_PREFIX + 'invalid_hiking_hours')
        hours -= values['hiking_foraging_hours']
        daily = .5 * effective * hours
        parts.append(_line('hiking_hours', hours=hours))
    parts.extend((_line('hiking_mileage', distance=measure(daily, 'miles')),
                  _line('hiking_move_note'), _line('hiking_fatigue_note')))
    return Result(tuple(parts))


# B349: (task modifier or no roll, regular speed, combat speed). Ladder units
# are rungs/second; all other speeds are retained as feet/second here.
_CLIMBS = {
    'ladder_up': (None, 1, 3), 'ladder_down': (None, 1, 2),
    'tree': (5, 1 / 3, 1), 'mountain': (0, 10 / 60, 1 / 2),
    'stone_wall': (-3, 4 / 60, 1 / 5), 'building': (-3, 2 / 60, 1 / 10),
    'rope_up': (-2, 20 / 60, 1), 'rope_down': (-1, 30 / 60, 2),
    'equipment_down': (-1, 12, 12),
}


def calculate_climbing(values):
    modifier, regular, combat = _CLIMBS[values['climb_kind']]
    speed = combat if values['climb_in_combat'] else regular
    parts = []
    if modifier is None:
        parts.append(_line('climb_ladder_speed', rate=speed, seconds=values['climb_rungs'] / speed))
        parts.append(_line('climb_no_roll'))
    else:
        speed_yps = speed / 3
        parts.append(_line('climb_speed', rate=measure(speed_yps, 'yards_per_second'),
                           seconds=values['climb_distance'] / speed_yps))
        parts.append(_line('climb_modifier', terrain=modifier, encumbrance=values['encumbrance'],
                           total=modifier - values['encumbrance']))
        parts.append(_line('climb_roll_note'))
    if values['climb_in_combat']:
        parts.append(_line('climb_fatigue_note'))
    return Result(tuple(parts))


_ENCUMBRANCE = (1, .8, .6, .4, .2)


def calculate_swimming(values):
    encumbrance = values['encumbrance']
    aquatic = values['aquatic']
    water_move = values['swim_move'] if aquatic else max(1, values['swim_move'] // 5)
    speed = water_move * _ENCUMBRANCE[encumbrance]
    parts = [_line('swim_speed', speed=measure(speed, 'yards_per_second'), distance=measure(10 * speed, 'yards'))]
    if aquatic:
        parts.append(_line('swim_aquatic'))
    else:
        build = {'ordinary': 0, 'overweight': 1, 'fat': 3, 'very_fat': 5}[values['swim_build']]
        entry = 3 if values['swim_intentional'] else 0
        parts.append(_line('swim_entry', modifier=entry + build - 2 * encumbrance))
        parts.append(_line('swim_check_note'))
    parts.append(_line('swim_fatigue', minutes=1 if values['swim_top_speed'] else 30))
    return Result(tuple(parts))


CARDS = (
    Card('hearing', 'senses', _PREFIX + 'hearing_title', (358,), (
        _choice('sound', 'conversation', 'sound_', _HEARING_BASELINES),
        _number('hearing_distance', '1', minimum=.001, unit='yards'),
        _integer('sense_base', '10', maximum=100),
        _integer('acute', maximum=100),
        _choice('hearing_trait', 'normal', 'hearing_trait_', ('normal', 'discriminatory', 'hard', 'deaf')),
        _integer('circumstances', minimum=-100, maximum=100),
    ), calculate_hearing),
    Card('vision_check', 'senses', _PREFIX + 'vision_title', (358, 574), (
        _choice('vision_task', 'notice', 'vision_task_', ('notice', 'detail', 'passive', 'concealment', 'other')),
        _integer('sense_base', '10', maximum=100),
        _integer('acute', maximum=100),
        _integer('circumstances', minimum=-100, maximum=100),
        _check('actively_watching', True), _check('plain_target'), _check('located_target'),
        _check('vision_unavailable'),
    ), calculate_vision),
    Card('taste_smell', 'senses', _PREFIX + 'taste_smell_title', (358,), (
        _choice('taste_smell_sense', 'smell', 'taste_smell_sense_', ('smell', 'taste')),
        _integer('sense_base', '10', maximum=100), _integer('acute', maximum=100),
        _choice('taste_smell_trait', 'normal', 'taste_smell_trait_', ('normal', 'discriminatory', 'absent')),
        _integer('circumstances', minimum=-100, maximum=100),
    ), calculate_taste_smell),
    Card('visual_signals', 'senses', _PREFIX + 'horizon_title', (575,), (
        _integer('observer_sm', minimum=-10, maximum=30),
        _integer('signal_sm', minimum=-10, maximum=30),
        _number('signal_distance', '4', unit='miles'),
        _check('deliberate_signal'), _check('actively_watching', True), _check('light_signal'),
        _integer('darkness', minimum=-10, maximum=0),
    ), calculate_horizon),
    Card('terrain', 'travel', _PREFIX + 'terrain_title', (427, 573, 574), (
        _choice('terrain', 'woodlands', 'terrain_', _TERRAIN),
        _choice('foraging_method', 'average', 'foraging_method_', ('average', 'minimum', 'maximum', 'roll')),
        _integer('foraging_roll', '4', minimum=1, maximum=12),
        _choice('track_conditions', 'typical', 'track_', ('typical', 'loose_calm', 'loose_wind_water')),
        _choice('terrain_travel_surface', 'average', 'surface_', ('slow', 'average', 'fast', 'ski', 'skate')),
    ), calculate_terrain),
    Card('hiking', 'travel', _PREFIX + 'hiking_title', (351, 426, 572), (
        _choice('hiking_model', 'basic', 'hiking_model_', ('basic', 'unskilled', 'skilled')),
        _number('trail_move', '5', maximum=1000), _number('ground_enhancement', '1', minimum=1, maximum=100),
        _number('trail_terrain', '1', maximum=2), _number('trail_weather', '1', maximum=1),
        _check('hiking_success'), _integer('hiking_foraging_hours', maximum=12),
    ), calculate_hiking),
    Card('climbing', 'travel', _PREFIX + 'climb_title', (349,), (
        _choice('climb_kind', 'tree', 'climb_', _CLIMBS),
        _number('climb_distance', '5', maximum=100000, unit='yards'),
        _integer('climb_rungs', '10', maximum=100000),
        _integer('encumbrance', maximum=4), _check('climb_in_combat'),
    ), calculate_climbing),
    Card('swimming', 'travel', _PREFIX + 'swim_title', (354, 355, 426), (
        _integer('swim_move', '5', minimum=1, maximum=1000), _integer('encumbrance', maximum=4),
        _check('aquatic'), _check('swim_intentional'),
        _choice('swim_build', 'ordinary', 'build_', ('ordinary', 'overweight', 'fat', 'very_fat')),
        _check('swim_top_speed', True),
    ), calculate_swimming),
)
