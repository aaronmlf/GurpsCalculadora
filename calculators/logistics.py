"""Monthly logistics, Mass Combat pp. 13-14. Money is in $, LS in $1,000."""
from dataclasses import dataclass, field, replace
import math
from utils.dice_roller import evaluate_success_roll, roll_3d6


@dataclass
class SupplyGroup:
    identifier: str
    monthly_cost: float
    domain: str = 'land'
    tl: int = 8
    terrain: str = 'clear'
    terrain_feature: bool = False
    transport_network: bool = False
    readiness: str = 'full'
    # A reduced force remains at half TS during its first month of full funding.
    recovering: bool = False


@dataclass
class LogisticsInput:
    groups: list[SupplyGroup] = field(default_factory=list)
    strengths: dict[str, float] = field(default_factory=dict)
    logistic_tl: dict[str, int] = field(default_factory=dict)
    # Explicit allocation to this force; do not automatically reuse shared LS.
    land_supply_line: bool = True
    naval_base: bool = False
    airbase: bool = False
    land_via_port: bool = False
    inland_sea_supply: bool = False
    campaign_season: bool = False
    rural: bool = False
    administration: int = 10
    administration_roll: int | None = None
    funds: float = 0
    replacement_raise_cost: float = 0
    replacement_raise_days: float = 0
    replacement_percent: float = 0


@dataclass
class LogisticsResult:
    complete: bool = False
    errors: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    roll: int | None = None
    administration_factor: float = 1
    raise_costs: dict = field(default_factory=dict)
    logistic_costs: dict = field(default_factory=dict)
    group_costs: dict = field(default_factory=dict)
    required_capacity: dict = field(default_factory=dict)
    capacity_shortfall: float = 0
    logistic_funding_shortfall: float = 0
    combat_funding_shortfall: float = 0
    replacement_cost: float = 0
    replacement_days: float = 0
    total_cost: float = 0
    funds_remaining: float = 0
    effects: dict = field(default_factory=dict)
    breakdown: list = field(default_factory=list)
    source: str = 'Mass Combat'
    pages: str = '13-14'


class LogisticsEngine:
    DOMAINS = {'land', 'naval', 'air'}
    TERRAINS = {'clear', 'arctic', 'desert', 'jungle', 'mountain', 'swampland', 'woodlands'}

    @staticmethod
    def _number(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    def validate(self, data):
        if (not isinstance(data.strengths, dict) or set(data.strengths) - self.DOMAINS or
                any(not self._number(v) for v in data.strengths.values()) or
                not isinstance(data.logistic_tl, dict) or set(data.logistic_tl) - self.DOMAINS or
                any(type(v) is not int or v < 0 for v in data.logistic_tl.values())):
            raise ValueError('invalid_logistic_state')
        if (not isinstance(data.groups, list) or any(not isinstance(g, SupplyGroup) for g in data.groups) or
                type(data.administration) is not int or any(type(v) is not bool for v in
                (data.land_supply_line, data.naval_base, data.airbase, data.land_via_port,
                 data.inland_sea_supply, data.campaign_season, data.rural))):
            raise ValueError('invalid_logistic_input')
        ids = set()
        for g in data.groups:
            if (not isinstance(g.identifier, str) or not g.identifier or g.identifier in ids or
                    not self._number(g.monthly_cost) or g.domain not in self.DOMAINS or
                    type(g.tl) is not int or g.tl < 0 or g.terrain not in self.TERRAINS or
                    g.readiness not in ('full', 'low', 'none') or
                    any(type(v) is not bool for v in (g.terrain_feature, g.transport_network, g.recovering))):
                raise ValueError('invalid_logistic_input')
            ids.add(g.identifier)
        if (any(not self._number(v) for v in (data.funds, data.replacement_raise_cost,
                data.replacement_raise_days, data.replacement_percent)) or data.replacement_percent > 100 or
                data.land_via_port and data.inland_sea_supply):
            raise ValueError('invalid_logistic_input')
        if data.administration_roll is not None and (type(data.administration_roll) is not int or
                                                     not 3 <= data.administration_roll <= 18):
            raise ValueError('invalid_logistic_roll')

    def calculate(self, data):
        self.validate(data)
        result = LogisticsResult(roll=data.administration_roll)
        if data.administration_roll is not None:
            check = evaluate_success_roll(data.administration, data.administration_roll)
            result.administration_factor = (0.85 if check['critical_success'] else
                1.15 if check['critical_failure'] else 1.1 if not check['success'] else
                0.9 if data.administration - data.administration_roll >= 5 else 1)
        else:
            result.pending.append('administration_roll')
        factor = result.administration_factor
        season = data.campaign_season and data.rural
        for kind, multiple in (('land', 1), ('naval', 2), ('air', 4)):
            raising = data.strengths.get(kind, 0) * 5000 * multiple
            discount = 0.5 if season and kind != 'naval' and data.logistic_tl.get(kind, 8) <= 5 else 1
            result.raise_costs[kind] = raising
            result.logistic_costs[kind] = raising * 0.1 * discount * factor
        demand = {kind: 0 for kind in self.DOMAINS}
        for g in data.groups:
            terrain = 1
            if g.domain == 'land' and not g.transport_network and g.terrain != 'clear':
                terrain = 1.5 if g.terrain == 'woodlands' else 2
                terrain -= 0.5 if g.terrain_feature else 0
            seasonal = 0.5 if season and g.domain != 'naval' and g.tl <= 5 else 1
            readiness = {'full': 1, 'low': 0.5, 'none': 0}[g.readiness]
            # LS supports the cost to maintain combat troops, in thousands of $.
            delivery = g.monthly_cost * terrain * seasonal * readiness * factor
            demand[g.domain] += delivery / 1000
            result.group_costs[g.identifier] = delivery
            result.effects[g.identifier] = {
                'ts_multiplier': 0.5 if g.readiness != 'full' or g.recovering else 1,
                'casualties': 5 if g.readiness == 'none' else 0,
                'recovering_next_month': g.readiness != 'full',
            }
            result.breakdown.append({'group': g.identifier, 'terrain': terrain, 'season': seasonal,
                                     'readiness': readiness, 'delivery_ls': delivery / 1000})
        result.required_capacity = demand
        land = data.strengths.get('land', 0) if data.land_supply_line else 0
        naval = data.strengths.get('naval', 0) if data.naval_base else 0
        air = data.strengths.get('air', 0) if data.airbase else 0
        # Allocate the restricted channels first, then universal air support.
        naval_used = min(naval, demand['naval'])
        naval -= naval_used
        if data.land_via_port:
            land_delivered = min(naval, demand['land'])
        elif data.inland_sea_supply:
            land_delivered = min(land, naval, demand['land'])
        else:
            land_delivered = min(land, demand['land'])
        remaining = demand['air'] + demand['naval'] - naval_used + demand['land'] - land_delivered
        result.capacity_shortfall = max(0, remaining - air)
        logistics = sum(result.logistic_costs.values())
        combat = sum(result.group_costs.values())
        result.logistic_funding_shortfall = max(0, logistics - data.funds)
        result.combat_funding_shortfall = max(0, combat - max(0, data.funds - logistics))
        result.replacement_cost = data.replacement_raise_cost * data.replacement_percent / 100
        result.replacement_days = data.replacement_raise_days * data.replacement_percent / 100
        result.total_cost = logistics + combat + result.replacement_cost
        result.funds_remaining = max(0, data.funds - result.total_cost)
        if result.capacity_shortfall > 1e-9:
            result.errors.append('logistic_capacity_shortfall')
        if data.funds + 1e-9 < result.total_cost:
            result.errors.append('logistic_funding_shortfall')
        result.complete = not result.errors and not result.pending
        return result

    def resolve(self, data):
        self.validate(data)
        explicit = replace(data, administration_roll=roll_3d6()[0]) if data.administration_roll is None else data
        return self.calculate(explicit)
