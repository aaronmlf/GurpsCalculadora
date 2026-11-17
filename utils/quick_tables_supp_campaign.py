"""Optional, read-only references for social play, mass combat and horror."""

from decimal import Decimal

from calculators.campaign import MassCombatEngine, SocialEngineeringEngine
from utils.dice_roller import evaluate_success_roll
from utils.quick_tables_cards import Card, Field, Result, label, line


SOCIAL = 'GURPS Social Engineering'
PULLING_RANK = 'GURPS Social Engineering: Pulling Rank'
MASS_COMBAT = 'GURPS Mass Combat'
HORROR = 'GURPS Horror'
PREFIX = 'qt_scamp_'
ROLL = ('roll', 3, 6)


def _line(key, **arguments):
    return line(PREFIX + key, **arguments)


def _label(key):
    return label(PREFIX + key)


def _result(*lines, expression=None, allows_roll=True):
    return Result(lines, expression=expression, allows_roll=allows_roll)


def _int(key, default='0', minimum=None, maximum=None, title=None):
    return Field(key, PREFIX + (title or key), 'integer', default, minimum=minimum, maximum=maximum)


def _number(key, default='0'):
    return Field(key, PREFIX + key, default=default, minimum=0)


def _choice(key, default, options, option_prefix='', title=None):
    return Field(key, PREFIX + (title or key), 'choice', default,
                 tuple((option, PREFIX + option_prefix + option) for option in options))


def _bool(key):
    return Field(key, PREFIX + key, 'bool', False)


def _card(key, section, source, requirement, pages, fields, calculate, *, tool=None, roll=None):
    return Card('scamp_' + key, section, PREFIX + key + '_title', pages, fields, calculate,
                tool=tool, roll=roll, source=source, requirement=PREFIX + requirement)


def _signed(value):
    return f'{value:+}'


def _outcome(check):
    if check['critical_success']:
        return _label('critical_success')
    if check['critical_failure']:
        return _label('critical_failure')
    return _label('success' if check['success'] else 'failure')


def _check_line(check, roll):
    return _line('check_result', roll=roll, outcome=_outcome(check), margin=check['margin'])


REACTION_CONTEXTS = (
    'general', 'combat', 'authority', 'admission', 'commerce', 'hiring',
    'aid', 'request_info', 'response_info', 'recreation', 'seduction', 'loyalty',
)
REACTION_PAGES = dict(zip(REACTION_CONTEXTS, (74,) * 3 + (75,) * 5 + (76,) * 4))


def _reaction(v):
    context = _line('reaction_reference', context=_label('context_' + v['context']),
                    page=REACTION_PAGES[v['context']])
    if v['roll'] is None:
        return _result(context, _line('reaction_bands'))
    total = v['roll'] + v['modifier']
    band = SocialEngineeringEngine.reaction_band(total)
    return _result(_line('reaction_result', roll=v['roll'], modifier=_signed(v['modifier']),
                         total=total, band=_label('band_' + band)), context)


def _rank(v):
    # Pulling Rank pp. 5–6, full ranks. Rank evaluated before a situational cap.
    reference_rank = v['patron'] // v['rank_cost']
    steps = v['rank'] - reference_rank
    base = 9 + (2 * steps if steps < 0 else steps)
    target = base - v['previous'] + v['modifier']
    lines = [_line('rank_target', rank=reference_rank, base=base, repeated=-v['previous'],
                   modifier=_signed(v['modifier']), target=target)]
    if target < 3:
        lines.append(_line('rank_blocked'))
    elif v['roll'] is not None:
        check = evaluate_success_roll(target, v['roll'])
        lines.extend((_check_line(check, v['roll']),
                      _line('rank_aid' if check['success'] else 'rank_no_aid')))
    return _result(*lines, _line('rank_guide'), allows_roll=target >= 3)


def _odds_str(value):
    return f'{value:.4g}'


def _mass_strength(v):
    a, b = map(lambda k: Decimal(str(v[k])), ('ts_a', 'ts_b'))
    if not a or not b:
        return _result(_line('strength_required'))
    odds = max(a, b) / min(a, b)
    bonus = MassCombatEngine._relative_ts_bonus(odds)
    return _result(_line('strength_result', odds=_odds_str(odds),
                         a=bonus if a > b else 0, b=bonus if b > a else 0),
                   _line('strength_guide'))


CLASSES = ('air', 'armor', 'artillery', 'c3i', 'cavalry', 'fire', 'engineering', 'naval', 'recon')


def _mass_class(v):
    a, b, neutral_a, neutral_b, opposing = (
        Decimal(str(v[k])) for k in ('class_a', 'class_b', 'neutral_a', 'neutral_b', 'opposing_ts')
    )
    if a < b:
        a = min(b, a + neutral_a)
    elif b < a:
        b = min(a, b + neutral_b)
    lines = [_line('class_totals', a=_odds_str(a), b=_odds_str(b))]
    major = max(a, b)
    if a == b:
        lines.append(_line('class_none'))
    elif not opposing:
        lines.append(_line('class_opposing_required', side='B' if a > b else 'A'))
    elif major * 100 < opposing:
        lines.append(_line('class_insignificant'))
    else:
        minor = min(a, b)
        band = int(major / minor) if minor else 5
        bonus = 3 if band >= 5 else 2 if band >= 3 else 1 if band >= 2 else 0
        if v['encounter'] and v['class'] in ('air', 'artillery', 'c3i'):
            bonus = max(0, bonus - 1)
        lines.append(_line('class_recon_result' if v['class'] == 'recon' else 'class_result',
                           cls=_label('cls_' + v['class']),
                           a=bonus if a > b else 0, b=bonus if b > a else 0))
    return _result(*lines, _line('class_guide'))


def _mass_length(v):
    small = min(v['elements_a'], v['elements_b'])
    minutes = 15 if small < 10 else 30 if small < 100 else 60 if small < 1_000 else 120 if small < 10_000 else 240
    return _result(_line('length_result', count=small, minutes=minutes), _line('length_guide'))


ATTACK_STRATEGIES = frozenset(('all_out_attack', 'attack', 'deliberate_attack', 'indirect_attack'))
RETREAT_STRATEGIES = frozenset(('fighting_retreat', 'full_retreat'))
RAID_STRATEGIES = frozenset(('raid', 'skirmish'))


def _mass_strategy(v):
    strategy = v['strategy']
    if strategy in ATTACK_STRATEGIES:
        category = 'attack'
    elif strategy in RETREAT_STRATEGIES:
        category = 'retreat'
    elif strategy in RAID_STRATEGIES:
        category = 'raid'
    else:
        category = 'defense'
    base = MassCombatEngine.STRATEGY_MODIFIERS[strategy]
    results = [_line('strategy_result', category=_label('category_' + category), modifier=_signed(base)),
               _line('guide_' + strategy)]
    if v['strategy_extra'] == 'desperate':
        if strategy in ('deliberate_attack', 'deliberate_defense', 'skirmish'):
            results.append(_line('strategy_desperate_invalid'))
        elif v['casualty_gap'] < 25:
            results.append(_line('strategy_desperate_minimum', gap=v['casualty_gap']))
        else:
            results.append(_line('strategy_desperate_result', total=_signed(base + 4)))
    return _result(*results, _line('strategy_guide'))


def _mass_result(v):
    margin = v['margin']
    loser, winner, shift = MassCombatEngine._combat_results(margin)
    if not margin:
        return _result(_line('battle_tie', percent=winner), _line('battle_base'))
    shift_key = {'attack': 'battle_shift', 'raid': 'battle_raid', 'other': 'battle_no_shift'}[v['winner_action']]
    return _result(_line('battle_result', winner=winner, loser=loser), _line(shift_key, shift=shift),
                   _line('battle_base'))


def _mass_risk(v):
    kind = v['risk_kind']
    if kind == 'misfortune':
        # Appendix B lists multiples of 5 beginning at 5%, not a 0% outcome.
        round_loss = v['round_loss']
        if round_loss == 0 or round_loss % 5:
            return _result(_line('risk_unlisted', loss=round_loss), _line('risk_guide'), allows_roll=False)
        base = 5 if round_loss == 5 else 6 if round_loss < 20 else 7 if round_loss < 30 else 8 if round_loss < 40 else 9
        context = int(v['desperate'])
    else:
        base = 5
        context = int(v['useful']) + int(v['unit_leader'])
    extra = context + int(v['fanatic']) - int(v['support'])
    target = base + v['risk'] + extra
    lines = [_line('risk_target', base=base, risk=_signed(v['risk']), modifier=_signed(extra), target=target)]
    expression = None
    if target < 3:
        lines.append(_line('risk_too_low'))
    elif v['roll'] is not None:
        result = evaluate_success_roll(target, v['roll'])
        lines.append(_check_line(result, v['roll']))
        if kind == 'heroism':
            bonus = 2 if result['critical_success'] else 1 if result['success'] else -1 if result['critical_failure'] else 0
            lines.append(_line('risk_heroism_result', bonus=_signed(bonus)))
        elif result['critical_success']:
            lines.append(_line('risk_bad_critical'))
            expression = '6d6'
        elif result['success']:
            lines.append(_line('risk_bad'))
            expression = '2d6-1'
        else:
            lines.append(_line('risk_intact'))
    return _result(*lines, _line('risk_guide'), expression=expression, allows_roll=target >= 3)


def _mass_aftermath(v):
    winner = v['winner_loss']
    loser = v['loser_loss']
    results = []
    if winner == loser == 100:
        results.append(_line('after_mutual'))
        winner = loser = 50
    else:
        if winner == 100:
            return _result(_line('after_no_winner'), _line('after_guide'))
        action = v['aftermath']
        if action != 'none' and (not v['retreated'] or loser >= 100):
            return _result(_line('after_not_retreat'), _line('after_guide'))
        if action == 'pursue':
            delta = 5 * (1 + int(v['air_edge']) + int(v['cavalry_edge']))
            loser += delta
            results.append(_line('after_pursuit', increase=delta))
        elif action == 'hold':
            winner = max(0, winner - 5)
            results.append(_line('after_holding'))
        # Halve then round down to the nearest 5%.
        winner = winner // 10 * 5
    return _result(*results, _line('after_final', winner=winner, loser=min(100, loser)),
                   _line('after_guide'))


SIZES = {'small': 1, 'human': 0, 'large': -1, 'huge': -3, 'vast': -6}
APPEARANCES = {'normal': 0, 'disgusting': -1, 'alien': -2, 'impossible': -3}


def _horror_fright(v):
    method = v['fright_method']
    if method == 'ad_hoc':
        return _result(_line('fright_ad_hoc'), expression='1d6', allows_roll=False)
    if method == 'alternatives':
        return _result(_line('fright_alternatives'), allows_roll=False)
    size, appearance = SIZES[v['size']], APPEARANCES[v['appearance']]
    adjusted = v['will'] + v['intrinsic'] + size + appearance + v['modifier']
    target = min(13, adjusted)
    lines = [_line('fright_modifiers', size=_signed(size), appearance=_signed(appearance), target=adjusted),
             _line('fright_limit', target=target), _line('fright_scene_guide')]
    if target < 3:
        lines.append(_line('fright_too_low'))
    elif v['roll'] is not None:
        check = evaluate_success_roll(target, v['roll'])
        lines.append(_check_line(check, v['roll']))
        if not check['success']:
            lines.append(_line('fright_table_check', margin=check['margin']))
            return _result(*lines, expression=f"3d6+{check['margin']}")
    return _result(*lines, allows_roll=target >= 3)


def _horror_cumulative(v):
    before = v['fear_load']
    situation = v['fear_event']
    after = before + 1 if situation == 'failure' else max(0, before - 1) if situation == 'success' else before
    return _result(_line('fear_cumulative_result', current=-before, next=-after),
                   _line('fear_cumulative_guide'))


def _horror_stress(v):
    will, stress, deranged = v['will'], v['stress'], v['deranged']
    if stress > will or deranged > will:
        return _result(_line('stress_limits', limit=will))
    event = v['stress_event']
    increase = 3 if event == 'critical_failure' else 1 if event == 'failure' else 0
    add_stress = 0 if v['blast'] else min(increase, will - stress)
    add_deranged = increase - add_stress
    stress += add_stress
    permanent = max(0, deranged + add_deranged - will)
    deranged = min(will, deranged + add_deranged)
    penalty = -((stress + 1) // 2 + deranged if v['stress_only'] else (stress + deranged + 1) // 2)
    return _result(_line('stress_result', stress=-stress, deranged=-deranged, penalty=penalty, permanent=permanent),
                   _line('stress_guide'))


SIGNED = _int('modifier')
ROLL_FIELD = _int('roll', '', 3, 18)
WILL = _int('will', '10', 1)
LOSS = _int('round_loss', '10', 0, 100)

PACKS = {
    'social': (
        _card('reaction', 'social', SOCIAL, 'requires_reaction', '74–76', (
            _choice('context', 'general', REACTION_CONTEXTS, 'context_'), SIGNED, ROLL_FIELD,
        ), _reaction, tool=13, roll=ROLL),
        _card('rank', 'social', PULLING_RANK, 'requires_rank', '5–6, 9–12', (
            _int('rank', '2', 0), _int('patron', '10', 1), _int('rank_cost', '4', 1),
            _int('previous', '0', 0), SIGNED, ROLL_FIELD,
        ), _rank, tool=13, roll=ROLL),
    ),
    'mass_combat': (
        _card('strength', 'battles', MASS_COMBAT, 'requires_mass', '26–27, 31, 46', (
            _number('ts_a', '75.5'), _number('ts_b', '120'),
        ), _mass_strength, tool=14),
        _card('class', 'battles', MASS_COMBAT, 'requires_class', '31–32, 46', (
            _choice('class', 'fire', CLASSES, 'cls_'), _number('class_a', '9'), _number('class_b', '4'),
            _number('neutral_a'), _number('neutral_b'), _number('opposing_ts', '75.5'), _bool('encounter'),
        ), _mass_class, tool=14),
        _card('length', 'battles', MASS_COMBAT, 'requires_mass', '32, 46', (
            _int('elements_a', '12', 1), _int('elements_b', '20', 1),
        ), _mass_length, tool=14),
        _card('strategy', 'battles', MASS_COMBAT, 'requires_strategy', '34–36, 46', (
            _choice('strategy', 'attack', tuple(MassCombatEngine.STRATEGY_MODIFIERS), 'strategy_'),
            _choice('strategy_extra', 'none', ('none', 'desperate'), 'extra_'),
            _int('casualty_gap', '0', -100, 100),
        ), _mass_strategy, tool=14),
        _card('battle', 'battles', MASS_COMBAT, 'requires_mass', '36–37, 47', (
            _int('margin', '3', 0), _choice('winner_action', 'attack', ('attack', 'raid', 'other'), 'winner_'),
        ), _mass_result, tool=14),
        _card('risk', 'battles', MASS_COMBAT, 'requires_risk', '33, 36–38, 47', (
            _choice('risk_kind', 'misfortune', ('misfortune', 'heroism'), 'risk_'), _int('risk', '0', -3, 3),
            LOSS, _bool('desperate'), _bool('useful'), _bool('unit_leader'), _bool('fanatic'),
            _bool('support'), ROLL_FIELD,
        ), _mass_risk, tool=14, roll=ROLL),
        _card('after', 'battles', MASS_COMBAT, 'requires_aftermath', 38, (
            _int('winner_loss', '35', 0, 100), _int('loser_loss', '15', 0, 100),
            _bool('retreated'), _choice('aftermath', 'none', ('none', 'pursue', 'hold'), 'after_'),
            _bool('air_edge'), _bool('cavalry_edge'),
        ), _mass_aftermath, tool=14),
    ),
    'horror': (
        _card('fright', 'hazards', HORROR, 'requires_fright', '139–141; Basic Set B360–361', (
            _choice('fright_method', 'standard', ('standard', 'ad_hoc', 'alternatives'), 'fright_option_'),
            WILL, _int('intrinsic', '-1'), _choice('size', 'human', tuple(SIZES), 'size_'),
            _choice('appearance', 'normal', tuple(APPEARANCES), 'appearance_'), SIGNED, ROLL_FIELD,
        ), _horror_fright, roll=ROLL),
        _card('fear', 'hazards', HORROR, 'requires_fear', 140, (
            _int('fear_load', '0', 0), _choice('fear_event', 'none', ('none', 'failure', 'success'), 'event_'),
        ), _horror_cumulative),
        _card('stress', 'hazards', HORROR, 'requires_stress', '141–142', (
            WILL, _int('stress', '0', 0), _int('deranged', '0', 0),
            _choice('stress_event', 'none', ('none', 'failure', 'critical_failure'), 'event_'),
            _bool('blast'), _bool('stress_only'),
        ), _horror_stress),
    ),
}
