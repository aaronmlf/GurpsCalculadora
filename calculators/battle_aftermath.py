"""Mass Combat p. 38: pursuit followed by recovery, without mutating a session."""
from dataclasses import dataclass, field, replace
import math
from utils.dice_roller import evaluate_success_roll, roll_3d6, roll_1d6


@dataclass
class AftermathInput:
    attacker_casualties: float
    defender_casualties: float
    attacker_ts: float
    defender_ts: float
    # Battle victor, NOT necessarily the winner of the last Strategy contest.
    victor: str
    voluntary_retreat: bool = False
    leadership: int = 10
    choice: str = 'hold'
    cavalry_superiority: bool = False
    air_superiority: bool = False
    attacker_logistic_losses: float = 0
    defender_logistic_losses: float = 0
    leadership_roll: int | None = None
    reaction_roll: int | None = None
    logistic_roll: int | None = None
    attacker_id: str = 'gui.mass.attacker'
    defender_id: str = 'gui.mass.defender'


@dataclass
class AftermathResult:
    complete: bool
    pending: list[str] = field(default_factory=list)
    action: str = 'none'
    rolls: dict = field(default_factory=dict)
    final_casualties: dict = field(default_factory=dict)
    remaining_ts: dict = field(default_factory=dict)
    logistic_losses: dict = field(default_factory=dict)
    breakdown: list = field(default_factory=list)
    source: str = 'Mass Combat'
    page: str = '38'


class BattleAftermathEngine:
    @staticmethod
    def validate(data):
        if (not isinstance(data.attacker_id, str) or not data.attacker_id or
                not isinstance(data.defender_id, str) or not data.defender_id or data.attacker_id == data.defender_id):
            raise ValueError('invalid_aftermath_choice')
        for value in (data.attacker_casualties, data.defender_casualties,
                      data.attacker_logistic_losses, data.defender_logistic_losses):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError('invalid_battle_casualties')
        for value in (data.attacker_ts, data.defender_ts):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('force_has_no_troop_strength')
        if data.victor not in ('attacker', 'defender', 'mutual', 'neither') or data.choice not in ('hold', 'pursue'):
            raise ValueError('invalid_aftermath_choice')
        if type(data.leadership) is not int or any(type(v) is not bool for v in
                (data.voluntary_retreat, data.cavalry_superiority, data.air_superiority)):
            raise ValueError('invalid_aftermath_choice')
        for value, low, high in ((data.leadership_roll, 3, 18), (data.reaction_roll, 1, 6), (data.logistic_roll, 1, 6)):
            if value is not None and (type(value) is not int or not low <= value <= high):
                raise ValueError('invalid_aftermath_roll')
        a, d = data.attacker_casualties, data.defender_casualties
        if (data.victor == 'mutual' and (a != 100 or d != 100) or
                a == d == 100 and data.victor != 'mutual' or
                data.victor == 'attacker' and a == 100 or data.victor == 'defender' and d == 100 or
                data.victor == 'neither' and (a == 100 or d == 100) or
                data.voluntary_retreat and data.victor not in ('attacker', 'defender')):
            raise ValueError('invalid_aftermath_choice')

    def calculate(self, data):
        """Use explicit rolls only; unresolved choices return no applicable result."""
        self.validate(data)
        loss = {'attacker': data.attacker_casualties, 'defender': data.defender_casualties}
        logistics = {'attacker': data.attacker_logistic_losses, 'defender': data.defender_logistic_losses}
        result = AftermathResult(False)
        loser = 'defender' if data.victor == 'attacker' else 'attacker'
        pursuit_allowed = data.voluntary_retreat and loss[loser] < 100
        # Rear area destruction precedes recovery, including mutual annihilation.
        for side in loss:
            if loss[side] == 100:
                logistics[side] = 100
        if pursuit_allowed:
            if data.leadership_roll is None:
                result.pending = ['leadership_roll']
                return result
            result.rolls['leadership'] = data.leadership_roll
            success = evaluate_success_roll(data.leadership, data.leadership_roll)['success']
            if success:
                result.action = data.choice
            else:
                if data.reaction_roll is None:
                    result.pending = ['reaction_roll']
                    return result
                result.rolls['reaction'] = data.reaction_roll
                result.action = 'pursue' if data.reaction_roll <= 3 else 'hold'
            if result.action == 'pursue':
                if data.logistic_roll is None:
                    result.pending = ['logistic_roll']
                    return result
                result.rolls['logistics'] = data.logistic_roll
                extra = 5 * (1 + data.cavalry_superiority + data.air_superiority)
                loss[loser] = min(100, loss[loser] + extra)
                logistics[loser] = min(100, logistics[loser] + data.logistic_roll * 5)
                if loss[loser] == 100:
                    logistics[loser] = 100
                result.breakdown.append({'key': 'pursuit', 'side': loser, 'value': extra})
            else:
                loss[data.victor] = max(0, loss[data.victor] - 5)
                result.breakdown.append({'key': 'hold', 'side': data.victor, 'value': -5})
        result.breakdown.append({'key': 'before_recovery', **loss})
        for side in loss:
            if data.victor == side or data.victor == 'mutual':
                loss[side] = math.floor(loss[side] / 10) * 5
        result.final_casualties = loss
        result.logistic_losses = logistics
        # Published example: TS 75.5, 15% final casualties -> TS 64.
        result.remaining_ts = {side: (getattr(data, side + '_ts') if loss[side] == 0 else
                                     math.floor(getattr(data, side + '_ts') * (1 - loss[side] / 100)))
                               for side in loss}
        result.complete = True
        return result

    def resolve(self, data):
        self.validate(data)
        current = replace(data)
        while True:
            result = self.calculate(current)
            if result.complete:
                return result
            needed = result.pending[0]
            setattr(current, needed, roll_3d6()[0] if needed == 'leadership_roll' else roll_1d6())
