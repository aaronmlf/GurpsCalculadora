"""Read-only trauma and hazard references from the Basic Set Revised."""

from calculators.injury import ArmorLoadout, CombatantState, DamagePacket, InjuryEngine, InjuryInput
from utils.dice_roller import evaluate_success_roll
from utils.quick_tables_cards import Card, Field, Result, line


def _integer(key, low, high, default='0'):
    return Field(key, 'qt_hazard_' + key, 'integer', default, minimum=low, maximum=high)


def _number(key, low, high, default='0'):
    return Field(key, 'qt_hazard_' + key, default=default, minimum=low, maximum=high)


def _choice(key, choices):
    return Field(key, 'qt_hazard_' + key, 'choice', choices[0],
                 tuple((option, 'qt_hazard_' + option) for option in choices))


def _bool(key):
    return Field(key, 'qt_hazard_' + key, 'bool', False)


def _line(key, **kwargs):
    return line('qt_hazard_' + key, **kwargs)


def _result(*rows, expression=None):
    return Result(rows, expression)


_DAMAGE_TYPES = ('cr', 'cut', 'imp', 'pi-', 'pi', 'pi+', 'pi++', 'burn', 'cor', 'tox')


def _damage(values):
    # Scope intentionally limited to the verified overlap of the shared
    # injury engine and B378–380: unmodified rigid DR and a normal torso hit.
    hp = values['max_hp']
    result = InjuryEngine().calculate(InjuryInput(
        packet=DamagePacket(values['basic_damage'], values['damage_type']),
        target=CombatantState(max_hp=hp, current_hp=hp, armor=ArmorLoadout(natural_dr=values['rigid_dr'])),
    ))
    if not result.valid:
        raise ValueError('qt_reference_invalid_field')
    rows = [_line('damage_scope'),
            _line('damage_penetration', basic=values['basic_damage'], dr=result.effective_dr,
                  penetrating=result.penetrating_damage),
            _line('damage_injury', multiplier=format(result.wounding_modifier, 'g'), injury=result.injury),
            _line('damage_shock', modifier=-result.state_delta.shock)]
    if result.major_wound:
        rows.append(_line('damage_major'))
    return _result(*rows)


def _vitals(values):
    maximum_hp, hp, maximum_fp, fp = (values[key] for key in ('max_hp', 'hp', 'max_fp', 'fp'))
    if hp > maximum_hp or fp > maximum_fp or fp < -maximum_fp:
        raise ValueError('qt_hazard_invalid_vitals')
    rows = [_line('vitals_current', hp=hp, maximum_hp=maximum_hp, fp=fp, maximum_fp=maximum_fp)]
    if hp <= -5 * maximum_hp:
        rows.append(_line('vitals_dead', limit=-5 * maximum_hp))
        if hp <= -10 * maximum_hp:
            rows.append(_line('vitals_destroyed', limit=-10 * maximum_hp))
        return _result(*rows)
    if 3 * hp < maximum_hp:
        rows.append(_line('vitals_low_hp'))
    if hp <= 0:
        rows.append(_line('vitals_collapse', modifier=-((-hp) // maximum_hp)))
        rows.append(_line('vitals_death_rolls', first=-maximum_hp, second=-2 * maximum_hp,
                          third=-3 * maximum_hp, fourth=-4 * maximum_hp))
    if 3 * fp < maximum_fp:
        rows.append(_line('vitals_low_fp'))
    if fp <= 0:
        rows.append(_line('vitals_spillover'))
        rows.append(_line('vitals_fp_unconscious' if fp == -maximum_fp else 'vitals_will'))
    if len(rows) == 1:
        rows.append(_line('vitals_no_thresholds'))
    return _result(*rows)


# Upper inclusive TL, treatment time per victim, add to 1d. B424.
_FIRST_AID = ((1, 30, -4), (3, 30, -3), (4, 30, -2), (5, 20, -2), (7, 20, -1), (8, 10, 0), (99, 10, 1))


def _first_aid(values):
    tl, hp, die = (values[key] for key in ('tl', 'max_hp', 'aid_die'))
    minutes, adds = next((minutes, adds) for upper, minutes, adds in _FIRST_AID if tl <= upper)
    multiplier = max(1, hp // 10)
    expression = '1d6' + (f'{adds:+d}' if adds else '')
    rows = [_line('aid_bandage', amount=multiplier),
            _line('aid_treatment', time=minutes, expression=expression, minimum=max(1, 1 + adds) * multiplier,
                  maximum=(6 + adds) * multiplier),
            _line('aid_critical', maximum=(6 + adds) * multiplier),
            _line('aid_optional_bleeding')]
    if multiplier > 1:
        rows.append(_line('aid_high_hp', multiplier=multiplier))
    if die is not None:
        total = max(1, die + adds) * multiplier
        rows.append(_line('aid_success_roll', roll=die, total=total, extra=total - multiplier))
    return _result(*rows)


def _bleeding(values):
    rows = [_line('bleed_optional')]
    if values['bleed_successes'] == 3:
        return _result(*rows, _line('bleed_prior_stop'))
    penalty = -(values['lost_hp'] // 5)
    target = values['ht'] + penalty
    rows.append(_line('bleed_check', modifier=penalty, target=target))
    roll = values['bleed_roll']
    if roll is None:
        rows.append(_line('bleed_outcomes'))
    else:
        outcome = evaluate_success_roll(target, roll)
        if outcome['critical_success']:
            rows.append(_line('bleed_stop'))
        elif not outcome['success']:
            rows.append(_line('bleed_hit', amount=3 if outcome['critical_failure'] else 1))
        elif values['bleed_successes'] == 2:
            rows.append(_line('bleed_prior_stop'))
        else:
            rows.append(_line('bleed_continue', successes=values['bleed_successes'] + 1))
    return _result(*rows)


def _fire(values):
    rows = [_line(values['fire_exposure'] + '_result'), _line('fire_large_area')]
    if values['fire_damage'] is not None:
        damage = values['fire_damage'] / (10 if values['fire_tight_beam'] else 1)
        rows.append(_line('fire_clothing_scope', damage=format(damage, 'g')))
        if damage >= 10:
            rows.append(_line('fire_full_clothes'))
        elif damage >= 3:
            rows.append(_line('fire_partial_clothes'))
        else:
            rows.append(_line('fire_no_clothes'))
    return _result(*rows)


def _suffocation(values):
    fp, maximum_fp = values['fp'], values['max_fp']
    if not -maximum_fp <= fp <= maximum_fp:
        raise ValueError('qt_hazard_invalid_vitals')
    seconds = values['airless_seconds']
    elapsed = min(seconds, 240)
    remaining_fp = max(-maximum_fp, fp - elapsed)
    damage = max(0, elapsed - max(0, fp))
    rows = [_line('airless_scope'), _line('airless_result', fp=remaining_fp, damage=damage)]
    if seconds >= 240:
        rows.append(_line('airless_death'))
    else:
        if remaining_fp <= 0:
            rows.append(_line('airless_unconscious' if remaining_fp == -maximum_fp else 'airless_will'))
        if seconds > 120:
            rows.append(_line('airless_brain'))
    return _result(*rows)


# Cited band upper thresholds and table codes are data, not resolved ailments.
_RADIATION_BANDS = (
    (10, 0, '–/–/A/B'), (20, 0, '–/A/B/C'), (40, 0, 'A/B/C/D'), (80, -1, 'A/B/C/D'),
    (160, -3, 'A/B/C/D'), (800, -4, 'A/B/C/D'), (4000, -5, 'C/D/E/E'), (float('inf'), -5, 'D/E/E/E'),
)


def _radiation(values):
    dose = values['incoming_rads'] / values['protection_factor']
    permanent = dose / 10
    remaining = max(permanent, dose - 10 * max(0, values['dose_days'] - 30))
    accumulated = remaining + values['other_rads']
    rows = [_line('rad_result', dose=format(dose, '.10g'), remaining=format(remaining, '.10g'),
                  permanent=format(permanent, '.10g'), accumulated=format(accumulated, '.10g')),
            _line('rad_scope')]
    if accumulated < 1:
        rows.append(_line('rad_below_table'))
    elif accumulated == 800:
        # The revised printing lists both 161–800 and 800–4,000. Let the
        # GM decide which applies instead of silently choosing either outcome.
        rows.append(_line('rad_ambiguous'))
    else:
        modifier, effects = next((modifier, codes) for upper, modifier, codes in _RADIATION_BANDS
                                 if accumulated <= upper)
        rows.append(_line('rad_band', modifier=f'{modifier:+d}', effects=effects))
    return _result(*rows)


def _guide(key):
    return lambda _values: _result(_line(key))


CARDS = (
    Card('direct_injury', 'trauma', 'qt_hazard_damage_title', '378–380, 419–420',
         (_integer('basic_damage', 0, 1_000_000, '8'), _integer('rigid_dr', 0, 100_000, '3'),
          _integer('max_hp', 1, 100_000, '10'),
          Field('damage_type', 'qt_hazard_damage_type', 'choice', 'cut',
                tuple((kind, 'qt_hazard_damage_' + kind) for kind in _DAMAGE_TYPES))),
         _damage, tool=7),
    Card('vitals', 'trauma', 'qt_hazard_vitals_title', '419, 426',
         (_integer('max_hp', 1, 100_000, '10'), _integer('hp', -1_000_000, 100_000, '10'),
          _integer('max_fp', 1, 100_000, '10'), _integer('fp', -100_000, 100_000, '10')),
         _vitals, tool=7),
    Card('first_aid', 'trauma', 'qt_hazard_aid_title', '420, 424',
         (_integer('tl', 0, 99, '8'), _integer('max_hp', 1, 100_000, '10'), _integer('aid_die', 1, 6, '')),
         _first_aid, roll=('aid_die', 1, 6)),
    Card('bleeding', 'trauma', 'qt_hazard_bleed_title', '420, 424',
         (_integer('ht', 1, 100_000, '10'), _integer('lost_hp', 1, 1_000_000, '5'),
          _integer('bleed_successes', 0, 3), _integer('bleed_roll', 3, 18, '')),
         _bleeding, roll=('bleed_roll', 3, 6), tool=7),
    Card('fire', 'hazards', 'qt_hazard_fire_title', '378, 400, 433–434',
         (_choice('fire_exposure', ('fire_partial_turn', 'fire_full_turn', 'fire_intense')),
          _integer('fire_damage', 0, 1_000_000, ''), _bool('fire_tight_beam')),
         _fire, tool=7),
    Card('suffocation', 'hazards', 'qt_hazard_airless_title', '425–427, 436–437',
         (_integer('max_fp', 1, 100_000, '10'), _integer('fp', -100_000, 100_000, '10'),
          _integer('airless_seconds', 0, 86_400, '10')),
         _suffocation),
    Card('radiation', 'hazards', 'qt_hazard_rad_title', '435–436',
         (_number('incoming_rads', 0, 1_000_000_000, '200'), _number('protection_factor', 1, 1_000_000, '1'),
          _integer('dose_days', 0, 1_000_000, '48'), _number('other_rads', 0, 1_000_000_000)),
         _radiation),
    Card('cold', 'hazards', 'qt_hazard_cold_title', '430', (), _guide('cold_guide')),
    Card('heat', 'hazards', 'qt_hazard_heat_title', '434', (), _guide('heat_guide')),
    Card('electricity', 'hazards', 'qt_hazard_electricity_title', '432–433', (), _guide('electricity_guide')),
    Card('poison', 'hazards', 'qt_hazard_poison_title', '416, 428–429, 437–441', (), _guide('poison_guide')),
    Card('falls', 'hazards', 'qt_hazard_falls_title', '430–431', (), _guide('falls_guide'), tool=2),
    Card('collisions', 'hazards', 'qt_hazard_collisions_title', '430–432', (), _guide('collisions_guide'), tool=3),
    Card('explosions', 'hazards', 'qt_hazard_explosions_title', '414–415', (), _guide('explosions_guide'), tool=4),
)
