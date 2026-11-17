"""Optional Dungeon Fantasy references (Wilderness Adventures and Treasure Tables)."""
from decimal import Decimal

from utils.dice_roller import evaluate_success_roll
from utils.quick_tables_cards import Card, Field, Result, label, line, measure


_T = 'qt_sfant_'
_WILDERNESS = 'GURPS Dungeon Fantasy 16: Wilderness Adventures'
_TREASURE = 'GURPS Dungeon Fantasy 8: Treasure Tables'


def _field(key, default='0', lo=0, hi=1_000_000, kind='number'):
    return Field(key, _T + key, kind, default, minimum=lo, maximum=hi)


def _choice(key, default, keys):
    return Field(key, _T + key, 'choice', default, tuple((value, _T + value) for value in keys))


def _row(key, **values):
    return line(_T + key, **values)


# Chapter 2, p. 23. A no-sleep group may still need breaks; not the
# same thing as an untiring vehicle/group that can drive all day.
_TRAVEL_HOURS = {
    'pace_regular': 8, 'pace_survival': 12, 'pace_sleepless': 14,
    'pace_sleepless_survival': 19, 'pace_untiring': 24,
}


def _travel(values):
    hours = _TRAVEL_HOURS[values['pace']] - values['time_stopped']
    if hours < 0:
        raise ValueError(_T + 'stops_beyond_hours')
    # Supply the member's encumbered Move (or conveyance Top Speed) and
    # choose the slowest computed member. Never defer to a Basic card setting.
    move = values['encumbered_move'] * (0.5 if values['low_hp_or_fp'] else 1)
    adjusted = move * values['terrain_factor'] * (1 + values['conditions_percent'] / 100)
    distance = adjusted * 0.5 * hours
    rows = [_row('travel_adjusted', move=f'{move:g}', hours=f'{hours:g}'),
            _row('travel_distance', distance=measure(distance, 'miles')),
            _row('travel_group')]
    if distance < 0:
        rows.append(_row('travel_negative'))
    return Result(tuple(rows))


_FORAGING_TIME = {
    'forage_half_hour': -5, 'forage_hour': 0, 'forage_two_hours': 1,
    'forage_four_hours': 2, 'forage_eight_hours': 3, 'forage_all_day': 4,
}
_FORAGING_METHOD = (
    'forage_gather', 'forage_fish', 'forage_fish_improvised', 'forage_hunt',
    'forage_spear', 'forage_trap_survival', 'forage_trap_skill',
)


def _forage(values):
    method = values['forage_method']
    time = _FORAGING_TIME[values['forage_time']]
    technique = {'forage_fish_improvised': -2, 'forage_hunt': values['weapon_acc'] - 4,
                 'forage_trap_skill': -5}.get(method, 0)
    target = values['forage_skill'] + time + technique + values['forage_terrain']
    rows = [_row('forage_target', skill=target, time=time, method=technique,
                 terrain=values['forage_terrain']), _row('forage_scope')]
    if target < 3:
        return Result(tuple(rows) + (_row('forage_no_test'),))
    roll = values['roll']
    expression = None
    if roll is not None:
        result = evaluate_success_roll(target, roll)
        if result['critical_failure']:
            rows.append(_row('forage_spear_harm' if method == 'forage_spear' else 'forage_harm'))
            if method == 'forage_spear':
                expression = '1d6'
        else:
            meals = 2 if result['critical_success'] else int(result['success'])
            rows.append(_row('forage_meals', count=meals, weight=measure(meals * 0.5, 'pounds')))
        if method == 'forage_hunt':
            rows.append(_row('forage_ammo'))
    return Result(tuple(rows), expression)


def _treasure_cost(values):
    original = Decimal(str(values['total_cf']))
    cf = max(Decimal('-0.8'), original)
    factor = 1 + cf
    cost = (Decimal(str(values['base_price'])) * factor
            + Decimal(str(values['flat_price'])) + Decimal(str(values['enchantments'])))
    rows = [_row('cost_factor_result', cf=format(cf, '+f'), factor=format(factor, 'f')),
            _row('cost_total_result', value=format(cost, '.2f')), _row('cost_scope')]
    if cf != original:
        rows.append(_row('cost_floor'))
    return Result(tuple(rows))


def _treasure_budget(values):
    town = values['people'] * values['town_weeks'] * 150
    food = values['people'] * values['days_away'] * 6
    other = values['extra_expenses']
    return Result((_row('budget_split', town=town, food=food, other=f'{other:.2f}'),
                   _row('budget_total', total=f'{town + food + other:.2f}'),
                   _row('budget_scope')))


def _ordered_treasure(values):
    dice = tuple(values[f'treasure_die_{index}'] for index in (1, 2, 3))
    rows = [_row('ordered_dice_guide')]
    if all(value is not None for value in dice):
        rows.append(_row('ordered_dice_key', first=dice[0], second=dice[1], third=dice[2]))
    return Result(tuple(rows), '3d6')


PACKS = {
    'wilderness': (
        Card('sup_df_overland', 'travel', _T + 'travel_title', '21–23', (
            _field('encumbered_move', '5', 0, 10_000),
            _choice('pace', 'pace_survival', _TRAVEL_HOURS),
            _field('terrain_factor', '1', 0, 10),
            _field('conditions_percent', '0', -1000, 1000),
            _field('time_stopped', '0', 0, 24),
            Field('low_hp_or_fp', _T + 'low_hp_or_fp', 'bool', False),
        ), _travel, source=_WILDERNESS, requirement=_T + 'wilderness_context'),
        Card('sup_df_foraging', 'travel', _T + 'forage_title', '22, 42–43', (
            _field('forage_skill', '12', 0, 1000, 'integer'),
            _choice('forage_method', 'forage_gather', _FORAGING_METHOD),
            _choice('forage_time', 'forage_hour', _FORAGING_TIME),
            _field('forage_terrain', '0', -30, 30, 'integer'),
            _field('weapon_acc', '0', 0, 50, 'integer'),
            _field('roll', '', 3, 18, 'integer'),
        ), _forage, roll=('roll', 3, 6), source=_WILDERNESS, requirement=_T + 'wilderness_context'),
    ),
    'treasure': (
        Card('sup_df_treasure_cost', 'objects', _T + 'cost_title', '6', (
            _field('base_price', '100'), _field('total_cf', '0', -1000, 1000),
            _field('flat_price'), _field('enchantments'),
        ), _treasure_cost, source=_TREASURE, requirement=_T + 'treasure_context'),
        Card('sup_df_treasure_budget', 'travel', _T + 'budget_title', '4–5', (
            _field('people', '4', 1, 1000, 'integer'), _field('town_weeks', '1', 0, 520, 'integer'),
            _field('days_away', '7', 0, 3650, 'integer'), _field('extra_expenses'),
        ), _treasure_budget, source=_TREASURE, requirement=_T + 'treasure_context'),
        Card('sup_df_treasure_order', 'objects', _T + 'ordered_dice_title', '6–10', (
            *(_field(f'treasure_die_{index}', '', 1, 6, 'integer') for index in (1, 2, 3)),
        ), _ordered_treasure, source=_TREASURE, requirement=_T + 'treasure_context'),
    ),
}
