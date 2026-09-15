"""Explicit element replacements, Mass Combat p. 14; no automatic time passage."""
from dataclasses import dataclass, asdict
import math


@dataclass
class ReplacementOrder:
    force_id: str
    element_id: str
    full_strength: float
    full_cost: float
    full_days: float
    percent: float
    elapsed_days: float = 0

    def validate(self):
        if (not isinstance(self.force_id,str) or not self.force_id or
                not isinstance(self.element_id,str) or not self.element_id or
                any(type(v) not in (int,float) or not math.isfinite(v) or v < 0 for v in
                    (self.full_strength,self.full_cost,self.full_days,self.percent,self.elapsed_days)) or
                self.full_strength <= 0 or not 0 < self.percent <= 100):
            raise ValueError('invalid_replacement')

    @property
    def cost(self): return self.full_cost*self.percent/100

    @property
    def days(self): return self.full_days*self.percent/100

    @property
    def strength(self): return self.full_strength*self.percent/100


def start_replacement(session, order, snapshot):
    from copy import deepcopy
    order.validate()
    if session.to_dict()!=snapshot:raise ValueError('stale_battle_result')
    if order.elapsed_days != 0:raise ValueError('invalid_replacement')
    if order.force_id in session.battle_casualties:raise ValueError('logistic_active_battle')
    force=session.forces.get(order.force_id)
    if force is None:raise ValueError('invalid_replacement')
    elements=[e for e in force.elements if e.identifier==order.element_id]
    if (len(elements)!=1 or any(j['force_id']==order.force_id and j['element_id']==order.element_id
                              for j in session.replacement_orders) or
            elements[0].troop_strength+order.strength > order.full_strength+1e-9):
        raise ValueError('invalid_replacement')
    if order.cost > force.resources:raise ValueError('logistic_funding_shortfall')
    candidate=deepcopy(session)
    candidate.forces[order.force_id].resources-=order.cost
    candidate.replacement_orders.append(asdict(order))
    candidate.history.append({'label':'replacement_started','order':asdict(order)})
    session._commit(candidate)


def advance_replacement(session, force_id, element_id, days, snapshot):
    from copy import deepcopy
    if session.to_dict()!=snapshot:raise ValueError('stale_battle_result')
    if type(days) not in (int,float) or not math.isfinite(days) or days < 0:
        raise ValueError('invalid_replacement')
    if force_id in session.battle_casualties:raise ValueError('logistic_active_battle')
    indices=[i for i,j in enumerate(session.replacement_orders) if j['force_id']==force_id and j['element_id']==element_id]
    if len(indices)!=1:raise ValueError('invalid_replacement')
    candidate=deepcopy(session)
    index=indices[0]
    order=ReplacementOrder(**candidate.replacement_orders[index])
    order.elapsed_days+=days
    completed=order.elapsed_days>=order.days
    if completed:
        elements=[e for e in candidate.forces[force_id].elements if e.identifier==element_id]
        if len(elements)!=1 or elements[0].troop_strength+order.strength>order.full_strength+1e-9:
            raise ValueError('invalid_replacement')
        elements[0].troop_strength+=order.strength
        candidate.replacement_orders.pop(index)
    else:
        candidate.replacement_orders[index]=asdict(order)
    candidate.history.append({'label':'replacement_completed' if completed else 'replacement_progress','order':asdict(order)})
    session._commit(candidate)
    return completed
