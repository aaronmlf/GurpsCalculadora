"""Opt-in, read-only magic, powers, psi and spacecraft references."""

from bisect import bisect_left
import math

from calculators.strength import EffortOption, StrengthCalculationInput, StrengthEngine, StrengthProfile
from utils.dice_roller import same_range_boundary
from utils.quick_tables_cards import Card, Field, Result, label, line, measure


def _key(name):
    return 'qt_ssuper_' + name


def _options(*values):
    return tuple((value, _key(value)) for value in values)


def _choice(key, title, default, values):
    return Field(key, _key(title), 'choice', default, _options(*values))


def _int(key, title, default, minimum, maximum):
    return Field(key, _key(title), 'integer', default, minimum=minimum, maximum=maximum)


def _num(key, title, default, minimum, maximum, unit=None):
    return Field(key, _key(title), 'number', default, minimum=minimum, maximum=maximum, unit=unit)


def _bool(key, title, default=False):
    return Field(key, _key(title), 'bool', default)


def _result(name, **arguments):
    return Result((line(_key(name), **arguments),))


def _lookup_3d(v, pending, outcome):
    return _result(pending) if v['roll'] is None else _result(outcome, roll=v['roll'])


def _black_critical(v):
    if not v['failed']:
        return _result('black_not_applicable')
    return _lookup_3d(v, 'black_pending', 'black_ref')


def _calamity(v):
    threshold, before, after = v['threshold'], v['before'], v['after']
    casting = v['event'] == 'casting'
    added_for_maintenance = v['event'] == 'maintenance' and after > before
    if after <= threshold or (before > threshold and not (casting or added_for_maintenance)):
        return _result('calamity_not_applicable')
    excess = after - threshold
    modifier = excess // 5
    lines = [line(_key('calamity_modifier'), excess=excess, mod=modifier)]
    if v['roll'] is not None:
        total = v['roll'] + modifier
        lines.append(line(_key('calamity_ref'), total=total, roll=v['roll']))
        if total >= 29 and casting:
            lines.append(line(_key('calamity_casting_will'), mod=-modifier))
    lines.append(line(_key('calamity_guide')))
    return Result(tuple(lines))


_RPM_EFFECTS = {'sense': 2, 'strengthen': 3, 'restore': 4, 'control': 5,
                'destroy': 5, 'create': 6, 'transform': 8}
_RPM_DURATIONS = ('momentary', '10m', '30m', '1h', '3h', '6h', '12h',
                  '1d', '3d', '1w', '2w', '1mo')
_RPM_WEIGHT_LB = (10, 30, 100, 300, 1000, 3000, 10_000, 30_000, 100_000,
                  300_000, 900_000, 2_700_000)


def _rpm_weight_energy(weight):
    index = bisect_left(_RPM_WEIGHT_LB, weight)
    if index > 0 and same_range_boundary(weight, _RPM_WEIGHT_LB[index - 1]):
        return index - 1
    if index < len(_RPM_WEIGHT_LB):
        return index
    ceiling = _RPM_WEIGHT_LB[-1]
    index = len(_RPM_WEIGHT_LB) - 1
    while weight > ceiling and not same_range_boundary(weight, ceiling):
        ceiling *= 3
        index += 1
    return index


def _rpm_energy(v):
    effect = _RPM_EFFECTS[v['effect']]
    duration = _RPM_DURATIONS.index(v['duration'])
    weight = _rpm_weight_energy(v['weight']) if v['weight'] is not None else 0
    other = v['extras']
    subtotal = effect + duration + weight + other
    multiplier = 1 + 2 * v['greater']
    return Result((line(_key('rpm_breakdown'), effect=effect, duration=duration, weight=weight, other=other),
                   line(_key('rpm_total'), subtotal=subtotal, multiplier=multiplier, total=subtotal * multiplier),
                   line(_key('rpm_guide'))))


def _super_effort(v):
    st, level = v['base_st'], v['levels']
    engine = StrengthEngine()
    result = engine.calculate(StrengthCalculationInput(
        profile=StrengthProfile(st=st), task='two_handed_lift', rules_profile='realistic',
        effort=EffortOption(super_effort_levels=level, super_effort_scope='lifting'),
    ))
    return Result((line(_key('lift_scores'), normal=st + level, bonus=result.effective_st - st,
                        boosted=result.effective_st, cost=result.fp_cost),
                   line(_key('lift_capacity'), basic=measure(result.basic_lift_lb, 'pounds'),
                        capacity=measure(result.capacity_lb, 'pounds')),
                   line(_key('lift_guide'))))


def _awe_confusion(v):
    mode = label(_key(v['mode']))
    if v['margin'] is None:
        return _result('awe_need_failure', mode=mode)
    if v['roll'] is None:
        return _result('awe_need_roll', mode=mode, margin=v['margin'])
    return _result('awe_ref', mode=mode, total=v['roll'] + v['margin'], roll=v['roll'], margin=v['margin'])


def _psi_range(v):
    level = v['level'] + v['offset']
    if level < 1:
        return _result('psi_bad_level', level=level)
    if level >= 79:
        return _result('psi_range_scope', level=level, scope=label(_key('psi_universal')))
    power, offset = divmod(level - 1, 3)
    yards = (1, 2, 5)[offset] * 10 ** power
    lines = [line(_key('psi_range'), level=level, distance=measure(yards, 'yards'))]
    if level >= 23:
        scope = 'psi_system' if level >= 40 else 'psi_global'
        lines.append(line(_key('psi_range_scope'), level=level, scope=label(_key(scope))))
    return Result(tuple(lines))


def _psi_crippling(v):
    if not v['crippled']:
        return _result('psi_cripple_not_applicable')
    return _lookup_3d(v, 'psi_cripple_pending', 'psi_cripple_ref')


# Space travel figures in GURPS Spaceships v1.31, p.37; these are not ephemerides.
# Each row: orbital radius in AU, orbital speed in mi/s, period in years, G, escape mi/s.
_SOLAR_BODIES = {
    'sun': (None, None, None, 28, 383), 'mercury': (0.39, 29.6, 0.24, 0.38, 2.7),
    'venus': (0.72, 21.8, 0.62, 0.91, 6.4), 'earth': (1, 18.5, 1, 1, 6.96),
    'luna': (1, None, None, 0.16, 1), 'mars': (1.5, 15.1, 1.88, 0.38, 3.1),
    'ceres': (2.7, 11.3, 4.6, 0.03, 0.32), 'jupiter': (5.2, 8.1, 11.9, 2.36, 37),
    'saturn': (9.5, 6, 29.5, 0.92, 22), 'uranus': (19, 4.2, 84, 0.89, 13.2),
    'neptune': (30, 3.4, 165, 1.19, 14.6), 'pluto': (40, 2.9, 248, 0.067, 0.68),
    'oort': (10_000, 0.59, 200, None, None),
}


def _solar_body(v):
    radius, speed, period, gravity, escape = _SOLAR_BODIES[v['body']]
    lines = []
    if radius is not None:
        lines.append(line(_key('solar_radius'), radius=radius))
    if speed is not None and period is not None:
        lines.append(line(_key('solar_orbit'), speed=measure(speed, 'miles_per_second'), period=period))
    if gravity is not None and escape is not None:
        lines.append(line(_key('solar_gravity'), gravity=gravity, escape=measure(escape, 'miles_per_second')))
    if v['body'] == 'luna':
        lines.append(line(_key('solar_luna')))
    elif v['body'] == 'oort':
        lines.append(line(_key('solar_oort')))
    lines.append(line(_key('solar_guide')))
    return Result(tuple(lines))


def _reactionless_trip(v):
    acceleration = v['acceleration']
    if v['scale'] == 'short_voyage':
        minutes = 0.423 * math.sqrt(v['miles'] / acceleration)
        peak = 0.18 * minutes * acceleration
        travel = line(_key('voyage_short'), minutes=minutes, distance=measure(v['miles'], 'miles'))
    else:
        hours = 68 * math.sqrt(v['au'] / acceleration)
        peak = 10.9 * hours * acceleration
        travel = line(_key('voyage_long'), hours=hours, days=hours / 24, distance=v['au'])
    if peak >= 186_000:
        return _result('voyage_out_of_model')
    lines = [travel, line(_key('voyage_peak'), peak=measure(peak, 'miles_per_second')),
             line(_key('voyage_guide'))]
    if peak >= 18_600:
        lines.append(line(_key('voyage_relativistic')))
    return Result(tuple(lines))


_SENSOR_RANGES = (0.1, 0.15, 0.2, 0.3, 0.5, 0.7, 1, 1.5, 2, 3, 5, 7, 10, 15, 20, 30, 50, 70)


def _sensors(v):
    distance = _SENSOR_RANGES[v['level'] - 1]
    return Result((line(_key('sensor_range'), level=v['level'], light_seconds=distance,
                        approx=measure(distance * 200_000, 'miles'), au=distance),
                   line(_key('sensor_guide'))))


_COMBAT_RANGE = {
    'rendezvous': ('zero', 'zero', 'zero'),
    'formation_incoming': ('point_blank', 'point_blank', 'point_blank'),
    'collision_course': ('point_blank', 'close_range', 'short_range'),
    'attack_engaged': ('close_range', 'short_range', 'long_range'),
    'neutral': ('short_range', 'long_range', 'extreme_range'),
}
_COMBAT_SCALES = ('close_scale', 'standard_scale', 'distant_scale')


def _combat_range(v):
    category = _COMBAT_RANGE[v['situation']][_COMBAT_SCALES.index(v['scale'])]
    return Result((line(_key('combat_range_result'), category=label(_key(category)),
                        scale=label(_key(v['scale'])), situation=label(_key(v['situation']))),
                   line(_key('combat_range_guide'))))


_ROLL_FIELD = _int('roll', 'roll_3d', '', 3, 18)
_ROLL = ('roll', 3, 6)
MAGIC = 'GURPS Magic'
THAUMATOLOGY = 'GURPS Thaumatology'
RPM = 'GURPS Thaumatology: Ritual Path Magic'
POWERS = 'GURPS Powers'
PSI = 'GURPS Psionic Powers'
SPACESHIPS = 'GURPS Spaceships (v1.31)'


PACKS = {
    'magic': (
        Card('sup_black_critical', 'magic', _key('black_title'), '157', (
            _bool('failed', 'black_confirmed'), _ROLL_FIELD,
        ), _black_critical, roll=_ROLL, source=MAGIC, requirement=_key('black_req')),
        Card('sup_threshold_calamity', 'magic', _key('calamity_title'), '76–78', (
            _int('threshold', 'threshold', '30', 0, 1_000_000),
            _int('before', 'before_tally', '30', 0, 1_000_000),
            _int('after', 'after_tally', '35', 0, 1_000_000),
            _choice('event', 'calamity_event', 'casting', ('casting', 'maintenance', 'other')),
            _ROLL_FIELD,
        ), _calamity, roll=_ROLL, source=THAUMATOLOGY, requirement=_key('calamity_req')),
        Card('sup_rpm_energy', 'magic', _key('rpm_title'), '15–19', (
            _choice('effect', 'rpm_effect', 'sense', _RPM_EFFECTS),
            _choice('duration', 'rpm_duration', 'momentary', _RPM_DURATIONS),
            _num('weight', 'rpm_subject_weight', '', 0, 1e18, 'pounds'),
            _int('extras', 'rpm_other_energy', '0', 0, 1_000_000),
            _int('greater', 'rpm_greater_count', '0', 0, 1000),
        ), _rpm_energy, source=RPM, requirement=_key('rpm_req')),
    ),
    'powers_psi': (
        Card('sup_power_lift', 'powers', _key('lift_title'), '58, 159', (
            _int('base_st', 'lift_base_st', '10', 1, 100000),
            _int('levels', 'lift_special_levels', '20', 1, 40),
        ), _super_effort, tool=9, source=POWERS, requirement=_key('lift_req')),
        Card('sup_awe_confusion', 'powers', _key('awe_title'), '84–85', (
            _choice('mode', 'awe_mode', 'awe', ('awe', 'confusion')),
            _int('margin', 'awe_margin', '', 1, 1000), _ROLL_FIELD,
        ), _awe_confusion, roll=_ROLL, source=POWERS, requirement=_key('awe_req')),
        Card('sup_psi_range', 'powers', _key('psi_range_title'), '22', (
            _int('level', 'psi_level', '5', 1, 1000), _int('offset', 'psi_offset', '0', -1000, 1000),
        ), _psi_range, source=PSI, requirement=_key('psi_range_req')),
        Card('sup_psi_crippling', 'powers', _key('psi_cripple_title'), '6–7', (
            _bool('crippled', 'psi_cripple_confirmed'), _ROLL_FIELD,
        ), _psi_crippling, roll=_ROLL, source=PSI, requirement=_key('psi_cripple_req')),
    ),
    'space': (
        Card('sup_solar_body', 'space', _key('solar_title'), '36–37', (
            _choice('body', 'solar_body', 'earth', _SOLAR_BODIES),
        ), _solar_body, tool=12, source=SPACESHIPS, requirement=_key('solar_req')),
        Card('sup_reactionless_trip', 'space', _key('voyage_title'), '39–40', (
            _choice('scale', 'voyage_scale', 'long_voyage', ('short_voyage', 'long_voyage')),
            _num('miles', 'voyage_short_distance', '240000', 0, 1e12, 'miles'),
            _num('au', 'voyage_long_distance', '1', 0, 1e6),
            _num('acceleration', 'voyage_acceleration', '1', 1e-9, 1e6),
        ), _reactionless_trip, tool=12, source=SPACESHIPS, requirement=_key('voyage_req')),
        Card('sup_sensors_comms', 'space', _key('sensor_title'), '45–46', (
            _int('level', 'sensor_level', '8', 1, len(_SENSOR_RANGES)),
        ), _sensors, tool=12, source=SPACESHIPS, requirement=_key('sensor_req')),
        Card('sup_space_combat_range', 'space', _key('combat_range_title'), '57', (
            _choice('scale', 'combat_scale', 'standard_scale', _COMBAT_SCALES),
            _choice('situation', 'combat_situation', 'neutral', _COMBAT_RANGE),
        ), _combat_range, tool=12, source=SPACESHIPS, requirement=_key('combat_range_req')),
    ),
}
