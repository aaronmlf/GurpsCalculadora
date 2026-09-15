"""Social Engineering and Mass Combat calculators with campaign persistence."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from calculators.injury import RuleReference
from calculators.battle_modifiers import class_superiority, position_after_round
from calculators.battle_end import battle_end
from utils.dice_roller import evaluate_success_roll, roll_3d6


@dataclass
class CharacterSocialProfile:
    identifier: str
    name: str
    iq: int = 10
    will: int = 10
    status: int = 0
    rank: int = 0
    appearance_modifier: int = 0
    reputation_modifier: int = 0
    charisma: int = 0
    cultural_familiarity: bool = True
    skills: Dict[str, int] = field(default_factory=dict)


@dataclass
class ReactionInput:
    actor: CharacterSocialProfile
    context: str = "general"
    disposition_modifier: int = 0
    situational_modifier: int = 0
    group_modifier: int = 0
    roll: Optional[int] = None


@dataclass
class ReactionResult:
    total: int
    band: str
    roll: int
    modifiers: int
    breakdown: List[Dict[str, Any]]
    references: List[RuleReference]


@dataclass
class InfluenceInput:
    actor: CharacterSocialProfile
    target: CharacterSocialProfile
    skill: str
    modifier: int = 0
    resistance_attribute: str = "will"
    expanded: bool = False
    actor_roll: Optional[int] = None
    target_roll: Optional[int] = None


@dataclass
class InfluenceResult:
    valid: bool
    errors: List[str]
    actor_target: int
    target_resistance: int
    actor_result: Dict[str, Any]
    target_result: Optional[Dict[str, Any]]
    success: bool
    margin: int
    reaction_shift: int
    pending_effects: List[Dict[str, Any]]
    references: List[RuleReference]
    reaction_band: str = ""


@dataclass
class RelationshipRecord:
    identifier: str
    first_id: str
    second_id: str
    relationship_type: str = "acquaintance"
    intensity: int = 0
    frequency_days: int = 30
    last_contact: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OrganizationRecord:
    identifier: str
    name: str
    size: int = 0
    resources: int = 0
    influence: int = 0
    hierarchy: int = 0
    reputation: int = 0
    contacts: List[str] = field(default_factory=list)
    relationships: Dict[str, int] = field(default_factory=dict)


@dataclass
class ElementRecord:
    identifier: str
    name: str
    troop_strength: float
    classes: List[str]
    quality: str = "average"
    equipment: str = "average"
    mobility: str = "foot"
    cost: float = 0.0
    transport_weight: float = 0.0
    special_classes: List[str] = field(default_factory=list)


@dataclass
class ForceRecord:
    identifier: str
    name: str
    elements: List[ElementRecord]
    commander_strategy: int = 10
    reconnaissance: int = 10
    logistics: int = 10
    morale: int = 10
    resources: float = 0.0
    readiness_multiplier: float = 1.0
    readiness_recovering: bool = False
    maintenance_month: int = 0

    def __post_init__(self):
        if (type(self.readiness_multiplier) not in (int, float) or self.readiness_multiplier not in (0.5, 1) or
                type(self.readiness_recovering) is not bool or type(self.maintenance_month) is not int or self.maintenance_month < 0):
            raise ValueError('invalid_logistic_state')

    @property
    def troop_strength(self) -> float:
        return self.base_troop_strength * self.readiness_multiplier

    @property
    def base_troop_strength(self) -> float:
        quality = {"inferior": 0.5, "average": 1.0, "good": 1.5, "elite": 2.0}
        equipment = {"poor": 0.5, "average": 1.0, "good": 1.5, "fine": 2.0}
        return sum(item.troop_strength * quality.get(item.quality, 1.0) *
                   equipment.get(item.equipment, 1.0) for item in self.elements)


@dataclass
class BattleInput:
    attacker: ForceRecord
    defender: ForceRecord
    attacker_strategy: str = "attack"
    defender_strategy: str = "defense"
    terrain_modifier: int = 0
    intelligence_modifier: int = 0
    attacker_roll: Optional[int] = None
    defender_roll: Optional[int] = None
    attacker_casualties: float = 0
    defender_casualties: float = 0
    attacker_position: int = 0
    defender_position: int = 0
    attacker_classes: Dict[str, List[float]] = field(default_factory=dict)
    defender_classes: Dict[str, List[float]] = field(default_factory=dict)
    encounter_battle: bool = False
    attacker_indirect_uses: int = 0
    defender_indirect_uses: int = 0
    attacker_previous_strategy: str = ''
    defender_previous_strategy: str = ''
    attacker_recon_superiority: bool = False
    defender_recon_superiority: bool = False
    attacker_raid_logistics: bool = False
    defender_raid_logistics: bool = False
    attacker_desperate: bool = False
    defender_desperate: bool = False
    parley_response: str = 'pending'
    attacker_defense_bonus: int = 0
    defender_defense_bonus: int = 0
    round_number: int = 1
    siege: bool = False
    attacker_confused: bool = False
    defender_confused: bool = False
    attacker_mobile: bool = False
    defender_mobile: bool = False
    attacker_started_confused: bool = False
    defender_started_confused: bool = False
    attacker_leadership: int = 10
    defender_leadership: int = 10
    attacker_rally_roll: Optional[int] = None
    defender_rally_roll: Optional[int] = None
    attacker_response_strategy: str = ''
    defender_response_strategy: str = ''


@dataclass
class CampaignStateDelta:
    relationship_changes: Dict[str, int] = field(default_factory=dict)
    organization_resource_changes: Dict[str, float] = field(default_factory=dict)
    force_losses: Dict[str, float] = field(default_factory=dict)
    morale_changes: Dict[str, int] = field(default_factory=dict)
    territory_changes: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    battle_round: bool = False
    battle_positions: Dict[str, int] = field(default_factory=dict)
    logistic_losses: Dict[str, float] = field(default_factory=dict)


@dataclass
class BattleCalculation:
    valid: bool
    errors: List[str]
    attacker_ts: float
    defender_ts: float
    ratio_modifier: int
    attacker_target: int
    defender_target: int
    breakdown: List[Dict[str, Any]]
    # Non-combat events have no Strategy rolls or round state delta (MC36).
    event: str = "combat"


@dataclass
class BattleResult:
    valid: bool
    errors: List[str]
    attacker_ts: float
    defender_ts: float
    ratio_modifier: int
    attacker_result: Dict[str, Any]
    defender_result: Dict[str, Any]
    margin: int
    outcome: str
    attacker_casualty_percent: int
    defender_casualty_percent: int
    state_delta: CampaignStateDelta
    breakdown: List[Dict[str, Any]]
    references: List[RuleReference]
    rally_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    battle_end: Dict[str, Any] = field(default_factory=dict)
    attack_rolls: Dict[str, int] = field(default_factory=dict)


class SocialEngineeringEngine:
    @staticmethod
    def reaction_band(total: int) -> str:
        if total <= 0: return "disastrous"
        if total <= 3: return "very_bad"
        if total <= 6: return "bad"
        if total <= 9: return "poor"
        if total <= 12: return "neutral"
        if total <= 15: return "good"
        if total <= 18: return "very_good"
        return "excellent"

    def resolve_reaction(self, data: ReactionInput, roll: Optional[int] = None) -> ReactionResult:
        value = roll if roll is not None else data.roll
        if value is None:
            value = roll_3d6()[0]
        actor = data.actor
        modifiers = (actor.appearance_modifier + actor.reputation_modifier + actor.charisma +
                     data.disposition_modifier + data.situational_modifier + data.group_modifier)
        if not actor.cultural_familiarity:
            modifiers -= 3
        total = value + modifiers
        return ReactionResult(
            total=total, band=self.reaction_band(total), roll=value, modifiers=modifiers,
            breakdown=[{"key": "appearance", "value": actor.appearance_modifier},
                       {"key": "reputation", "value": actor.reputation_modifier},
                       {"key": "charisma", "value": actor.charisma},
                       {"key": "situation", "value": data.situational_modifier}],
            references=[RuleReference("Basic Set", "494-561"), RuleReference("Social Engineering", "20-39")],
        )

    def resolve_influence(self, data: InfluenceInput, actor_roll: Optional[int] = None,
                          target_roll: Optional[int] = None) -> InfluenceResult:
        errors: List[str] = []
        skill = data.actor.skills.get(data.skill)
        if skill is None:
            errors.append("unknown_influence_skill")
            skill = data.actor.iq - 5
        actor_target = skill + data.modifier
        resistance = getattr(data.target, data.resistance_attribute, None)
        if resistance is None:
            errors.append("invalid_resistance_attribute")
            resistance = data.target.will
        aroll = actor_roll if actor_roll is not None else data.actor_roll
        if aroll is None:
            aroll = roll_3d6()[0]
        actor_result = evaluate_success_roll(actor_target, aroll)
        target_result = None
        margin = int(actor_result["margin"]) if actor_result["success"] else -int(actor_result["margin"])
        success = bool(actor_result["success"])
        # B359: even ordinary Influence is a Quick Contest, not a lone skill roll.
        troll = target_roll if target_roll is not None else data.target_roll
        if troll is None:
            troll = roll_3d6()[0]
        target_result = evaluate_success_roll(resistance, troll)
        opposing = resistance - troll
        margin = actor_target - aroll - opposing
        success = margin > 0
        band = ("very_good" if data.skill == "Sex Appeal" else "good") if success else "bad"
        pending = [{"kind": "gm_social_consequence", "skill": data.skill, "margin": margin}]
        if data.skill == "Diplomacy":
            pending.append({"kind": "take_better_reaction_roll", "influence_band": band})
        return InfluenceResult(
            valid=not errors, errors=errors, actor_target=actor_target, target_resistance=resistance,
            actor_result=actor_result, target_result=target_result, success=success, margin=margin,
            reaction_shift=0, reaction_band=band,
            pending_effects=pending,
            references=[RuleReference("Basic Set", "359"), RuleReference("Social Engineering", "31-39")],
        )


class MassCombatEngine:
    @staticmethod
    def _initiative_choices(data):
        slow={'deliberate_attack','deliberate_defense','parley'}
        original={'attacker':data.attacker_strategy,'defender':data.defender_strategy}
        changes={}
        errors=[]
        for side in ('attacker','defender'):
            choice=getattr(data,side+'_response_strategy')
            if not isinstance(choice,str):
                errors.append('invalid_initiative_response')
                continue
            if not choice:continue
            other='defender' if side=='attacker' else 'attacker'
            allowed=(original[other] in slow and original[side] not in slow and
                     (original[other]!='parley' or data.parley_response=='refuse'))
            if not allowed or choice not in MassCombatEngine.STRATEGY_MODIFIERS:
                errors.append('invalid_initiative_response')
            else:changes[side+'_strategy']=choice
        if errors:return data,errors
        return replace(data,**changes,attacker_response_strategy='',defender_response_strategy=''),[]

    @staticmethod
    def _strategy_superiority_bonus(strategy, bonuses):
        if strategy == 'raid':
            return sum(bonuses.get(key,0)>0 for key in ('Air','Cav','Nav'))
        # MC34-35: these are single +1 adjustments, not the sum of class bonuses.
        eligible = {
            'deliberate_attack': ('Art',),
            'indirect_attack': ('C3I',),
            'deliberate_defense': ('F',),
            'mobile_defense': ('Cav', 'Nav'),
            'skirmish': ('Air', 'Art', 'F'),
        }
        return int(any(bonuses.get(key, 0) > 0 for key in eligible.get(strategy, ())))

    @staticmethod
    def _battle_event(data):
        a, d = data.attacker_strategy, data.defender_strategy
        defenses = {'defense', 'all_out_defense', 'deliberate_defense', 'mobile_defense', 'rally'}
        retreats = {'fighting_retreat', 'full_retreat'}
        if a == d == 'parley':
            return 'parley'
        if 'parley' in (a, d):
            if data.parley_response=='accept':return 'parley'
            if data.parley_response!='refuse':return 'parley_decision_required'
            a='defense' if a=='parley' else a
            d='defense' if d=='parley' else d
        if (a in retreats and d in retreats | defenses or
                d in retreats and a in defenses):
            return 'no_battle'
        return 'combat'

    @staticmethod
    def _battle_choices(data):
        data,_=MassCombatEngine._initiative_choices(data)
        if data.parley_response=='refuse' and (data.attacker_strategy=='parley') != (data.defender_strategy=='parley'):
            data=replace(data,attacker_strategy='defense' if data.attacker_strategy=='parley' else data.attacker_strategy,
                         defender_strategy='defense' if data.defender_strategy=='parley' else data.defender_strategy)
        defenses = {'defense', 'all_out_defense', 'deliberate_defense', 'mobile_defense', 'rally'}
        if data.attacker_strategy in defenses and data.defender_strategy in defenses:
            return replace(data, attacker_strategy='skirmish', defender_strategy='skirmish')
        return data
    STRATEGY_MODIFIERS = {
        "all_out_attack": 2, "all_out_defense": 2, "attack": 0, "defense": 1,
        "deliberate_attack": 1, "deliberate_defense": 1, "fighting_retreat": 3,
        "full_retreat": 8, "indirect_attack": -3, "mobile_defense": 0,
        "parley": 0, "raid": 0, "rally": -2, "skirmish": 2,
    }

    @staticmethod
    def _relative_ts_bonus(odds: float) -> int:
        bonus = 0
        for threshold, value in ((1.5, 2), (2, 4), (3, 6), (5, 8), (7, 10),
                                 (10, 12), (15, 14), (20, 16), (30, 18), (50, 20)):
            if odds >= threshold:
                bonus = value
        return bonus

    @staticmethod
    def _combat_results(margin: int) -> tuple[int, int, int]:
        margin = abs(margin)
        if margin == 0: return 10, 10, 0
        if margin <= 3: return 15, 10, 1
        if margin <= 6: return 20, 10, 2
        if margin <= 9: return 25, 5, 2
        if margin <= 14: return 30, 5, 3
        if margin <= 19: return 35, 0, 3
        return 40, 0, 4

    def calculate(self, data: BattleInput) -> BattleCalculation:
        data,initiative_errors=self._initiative_choices(data)
        event = self._battle_event(data)
        invalid_encounter = data.encounter_battle and any(strategy in ('deliberate_attack','deliberate_defense')
                            for strategy in (data.attacker_strategy,data.defender_strategy))
        context_errors=list(initiative_errors)
        if (type(data.round_number) is not int or data.round_number<1 or type(data.siege) is not bool or
                data.siege and data.encounter_battle):
            context_errors.append('invalid_battle_context')
        for side in ('attacker','defender'):
            leadership=getattr(data,side+'_leadership')
            rally_roll=getattr(data,side+'_rally_roll')
            if (type(leadership) is not int or rally_roll is not None and
                    (type(rally_roll) is not int or not 3<=rally_roll<=18)):
                context_errors.append('invalid_rally_input')
            strategy=getattr(data,side+'_strategy')
            confused=getattr(data,side+'_confused')
            mobile=getattr(data,side+'_mobile')
            started=getattr(data,side+'_started_confused')
            if any(type(v) is not bool for v in (confused,mobile,started)):
                context_errors.append('invalid_battle_context')
            if confused and strategy not in ('rally','full_retreat'):
                context_errors.append('confused_strategy_required')
            if strategy=='rally' and not confused:
                context_errors.append('rally_requires_confusion')
            if strategy in ('deliberate_attack','deliberate_defense') and started:
                context_errors.append('invalid_battle_context')
            if strategy=='deliberate_defense' and not data.siege and (
                    data.round_number!=1 or getattr(data,side+'_defense_bonus')==0):
                context_errors.append('deliberate_defense_context')
            if data.encounter_battle and data.round_number==1 and mobile and strategy in (
                    'defense','all_out_defense','deliberate_defense','parley','rally','full_retreat','fighting_retreat') and not confused:
                context_errors.append('mobile_encounter_strategy')
        a_parley = -1 if data.attacker_strategy=='parley' and data.defender_strategy!='parley' and data.parley_response=='refuse' else 0
        d_parley = -1 if data.defender_strategy=='parley' and data.attacker_strategy!='parley' and data.parley_response=='refuse' else 0
        data = self._battle_choices(data)
        errors: List[str] = []
        errors.extend(context_errors)
        if invalid_encounter:errors.append('invalid_encounter_strategy')
        if data.parley_response not in ('pending','accept','refuse'):
            errors.append('invalid_parley_response')
        if event == 'parley_decision_required':
            errors.append('battle_parley_decision_required')
        for side in ('attacker', 'defender'):
            if type(getattr(data,side+'_defense_bonus')) is not int or getattr(data,side+'_defense_bonus')<0:
                errors.append('invalid_defense_bonus')
            desperate=getattr(data,side+'_desperate')
            other='defender' if side=='attacker' else 'attacker'
            if (type(desperate) is not bool or desperate and (
                    getattr(data,side+'_strategy') in ('deliberate_attack','deliberate_defense','skirmish') or
                    getattr(data,side+'_casualties')-getattr(data,other+'_casualties')<25)):
                errors.append('invalid_desperate_strategy')
            uses = getattr(data, side + '_indirect_uses')
            previous = getattr(data, side + '_previous_strategy')
            if (type(uses) is not int or uses < 0 or previous not in ('', *self.STRATEGY_MODIFIERS) or
                    previous == 'indirect_attack' and uses == 0):
                errors.append('invalid_strategy_history')
            if (type(getattr(data,side+'_recon_superiority')) is not bool or
                    type(getattr(data,side+'_raid_logistics')) is not bool or
                    getattr(data,side+'_raid_logistics') and getattr(data,side+'_strategy')!='raid'):
                errors.append('invalid_battle_strategy')
        ats, dts = data.attacker.troop_strength, data.defender.troop_strength
        if not all(math.isfinite(v) and v > 0 for v in (ats, dts)):
            errors.append("force_has_no_troop_strength")
            return BattleCalculation(False, errors, ats, dts, 0, 0, 0, [])
        if (data.attacker.identifier == data.defender.identifier or
                any(not math.isfinite(v) or not 0 <= v < 100 for v in
                    (data.attacker_casualties, data.defender_casualties))):
            errors.append('invalid_battle_casualties')
        ratio = ats / max(0.001, dts)
        if ratio >= 1:
            ratio_modifier = self._relative_ts_bonus(ratio)
        else:
            ratio_modifier = -self._relative_ts_bonus(1 / max(0.001, ratio))
        a_target = data.attacker.commander_strategy + max(0, ratio_modifier) + data.intelligence_modifier
        d_target = data.defender.commander_strategy + max(0, -ratio_modifier) + data.terrain_modifier
        defenses={'defense','all_out_defense','deliberate_defense','mobile_defense','rally','parley'}
        defense_bonuses={}
        for side in ('attacker','defender'):
            other='defender' if side=='attacker' else 'attacker'
            bonus=getattr(data,side+'_defense_bonus')
            bonus=bonus if type(bonus) is int and bonus>=0 and getattr(data,side+'_strategy') in defenses else 0
            if getattr(data,other+'_strategy')=='deliberate_attack':bonus=math.ceil(bonus/2)
            defense_bonuses[side]=bonus
        a_target+=defense_bonuses['attacker']
        d_target+=defense_bonuses['defender']
        a_target += self.STRATEGY_MODIFIERS.get(data.attacker_strategy, 0)
        d_target += self.STRATEGY_MODIFIERS.get(data.defender_strategy, 0)
        a_repeat = -2 if data.attacker_strategy == data.attacker_previous_strategy == 'indirect_attack' else 0
        d_repeat = -2 if data.defender_strategy == data.defender_previous_strategy == 'indirect_attack' else 0
        a_target += a_repeat
        d_target += d_repeat
        a_target += a_parley
        d_target += d_parley
        a_target += 4 if data.attacker_desperate else 0
        d_target += 4 if data.defender_desperate else 0
        a_confused_retreat=-2 if data.attacker_confused and data.attacker_strategy=='full_retreat' else 0
        d_confused_retreat=-2 if data.defender_confused and data.defender_strategy=='full_retreat' else 0
        a_target+=a_confused_retreat
        d_target+=d_confused_retreat
        a_penalty = -math.floor(data.attacker_casualties / 5) if math.isfinite(data.attacker_casualties) else 0
        d_penalty = -math.floor(data.defender_casualties / 5) if math.isfinite(data.defender_casualties) else 0
        a_target += a_penalty
        d_target += d_penalty
        if (any(type(v) is not int or v < 0 for v in (data.attacker_position, data.defender_position)) or
                data.attacker_position and data.defender_position):
            errors.append('invalid_battle_position')
        if type(data.encounter_battle) is not bool:
            errors.append('invalid_class_strength')
        class_breakdown = []
        try:
            ab, db = class_superiority(data.attacker_classes, data.defender_classes, ats, dts, data.encounter_battle)
            a_target += sum(ab.values())
            d_target += sum(db.values())
            a_strategy_bonus = self._strategy_superiority_bonus(data.attacker_strategy, ab)
            d_strategy_bonus = self._strategy_superiority_bonus(data.defender_strategy, db)
            a_strategy_bonus += int(data.attacker_strategy=='raid' and data.attacker_recon_superiority)
            d_strategy_bonus += int(data.defender_strategy=='raid' and data.defender_recon_superiority)
            a_target += a_strategy_bonus
            d_target += d_strategy_bonus
            class_breakdown = [{'key': 'class_' + key, 'attacker': ab[key], 'defender': db[key],
                               'source': 'Mass Combat', 'page': '31-32'} for key in sorted(ab)]
            class_breakdown.append({'key': 'strategy_superiority', 'attacker': a_strategy_bonus,
                                    'defender': d_strategy_bonus, 'source': 'Mass Combat', 'page': '34-35'})
        except ValueError:
            errors.append('invalid_class_strength')
        a_target += data.attacker_position if type(data.attacker_position) is int else 0
        d_target += data.defender_position if type(data.defender_position) is int else 0
        if data.attacker_strategy not in self.STRATEGY_MODIFIERS or data.defender_strategy not in self.STRATEGY_MODIFIERS:
            errors.append("invalid_battle_strategy")
        return BattleCalculation(not errors, errors, ats, dts, ratio_modifier, a_target, d_target,
            [{"key": "ts_ratio", "value": ratio}, {"key": "ratio_modifier", "value": ratio_modifier},
             {"key": "attacker_casualty_penalty", "value": a_penalty, "source": "Mass Combat", "page": "37"},
             {"key": "defender_casualty_penalty", "value": d_penalty, "source": "Mass Combat", "page": "37"},
             {'key': 'position', 'attacker': data.attacker_position, 'defender': data.defender_position,
              'source': 'Mass Combat', 'page': '37'},
             {'key':'effective_strategies','attacker':data.attacker_strategy,'defender':data.defender_strategy,'source':'Mass Combat','page':'35-36'},
             {'key':'defense_bonus',**defense_bonuses,'source':'Mass Combat','page':'32, 34'},
             {'key':'parley_refusal','attacker':a_parley,'defender':d_parley,'source':'Mass Combat','page':'35'},
             {'key':'confused_retreat','attacker':a_confused_retreat,'defender':d_confused_retreat,'source':'Mass Combat','page':'35'},
             {'key':'strategy_repeat','attacker':a_repeat,'defender':d_repeat,'source':'Mass Combat','page':'35'},
             {'key':'strategy_desperate','attacker':4 if data.attacker_desperate else 0,
              'defender':4 if data.defender_desperate else 0,'source':'Mass Combat','page':'36'},
             {'key':'desperate_misfortune','attacker':int(bool(data.attacker_desperate)),
              'defender':int(bool(data.defender_desperate)),'source':'Mass Combat','page':'36'}] + class_breakdown, event=event)

    def resolve(self, data: BattleInput, attacker_roll: Optional[int] = None,
                defender_roll: Optional[int] = None) -> BattleResult:
        calculation = self.calculate(data)
        data = self._battle_choices(data)
        ats, dts, ratio_modifier = calculation.attacker_ts, calculation.defender_ts, calculation.ratio_modifier
        errors = calculation.errors
        if errors:
            return BattleResult(False, errors, ats, dts, ratio_modifier, {}, {}, 0, 'tie', 0, 0,
                                CampaignStateDelta(), calculation.breakdown, [RuleReference('Mass Combat', '30-38')])
        if calculation.event != 'combat':
            return BattleResult(True, [], ats, dts, ratio_modifier, {}, {}, 0,
                                calculation.event, 0, 0, CampaignStateDelta(),
                                calculation.breakdown, [RuleReference('Mass Combat', '36')])
        a_target, d_target = calculation.attacker_target, calculation.defender_target
        ar = attacker_roll if attacker_roll is not None else data.attacker_roll
        dr = defender_roll if defender_roll is not None else data.defender_roll
        if ar is None: ar = roll_3d6()[0]
        if dr is None: dr = roll_3d6()[0]
        a_result, d_result = evaluate_success_roll(a_target, ar), evaluate_success_roll(d_target, dr)
        a_margin = a_target - ar
        d_margin = d_target - dr
        margin = a_margin - d_margin
        winner_strategy = data.attacker_strategy if margin > 0 else data.defender_strategy
        if winner_strategy == 'indirect_attack':
            prior_uses = data.attacker_indirect_uses if margin > 0 else data.defender_indirect_uses
            margin = (1 if margin >= 0 else -1) * math.ceil(abs(margin) * (1.5 if prior_uses else 2))
        elif winner_strategy == 'skirmish':
            margin = math.trunc(margin / 2)
        outcome = "attacker_decisive" if margin >= 10 else "attacker_wins" if margin > 0 else \
            "tie" if margin == 0 else "defender_wins" if margin > -10 else "defender_decisive"
        loser_loss, winner_loss, _pb_shift = self._combat_results(margin)
        if margin > 0:
            attacker_loss, defender_loss = winner_loss, loser_loss
        elif margin < 0:
            attacker_loss, defender_loss = loser_loss, winner_loss
        else:
            attacker_loss = defender_loss = 10
        # Both sides can choose any strategy; never privilege the UI's side names.
        if data.attacker_strategy in {'all_out_attack', 'all_out_defense'}: attacker_loss *= 2
        if data.defender_strategy in {'all_out_attack', 'all_out_defense'}: defender_loss *= 2
        if data.attacker_strategy == 'all_out_attack' and margin > 0: defender_loss += 5
        if data.defender_strategy == 'all_out_attack' and margin < 0: attacker_loss += 5
        if data.attacker_strategy == 'deliberate_defense' and margin >= 0: defender_loss += 5
        if data.defender_strategy == 'deliberate_defense' and margin <= 0: attacker_loss += 5
        if data.attacker_strategy == 'skirmish' or data.attacker_strategy == 'mobile_defense' and margin <= 0:
            attacker_loss = max(0, attacker_loss - 5)
        if data.defender_strategy == 'skirmish' or data.defender_strategy == 'mobile_defense' and margin >= 0:
            defender_loss = max(0, defender_loss - 5)
        if data.attacker_strategy == 'fighting_retreat': defender_loss //= 2
        if data.defender_strategy == 'fighting_retreat': attacker_loss //= 2
        if data.attacker_strategy == "full_retreat":
            attacker_loss = max(0, attacker_loss - 10)
            defender_loss = 0
        if data.defender_strategy == "full_retreat":
            defender_loss = max(0, defender_loss - 10)
            attacker_loss = 0
        # MC36: automatic extra losses, after normal strategy adjustments.
        attacker_loss += 10 if data.attacker_desperate else 0
        defender_loss += 10 if data.defender_desperate else 0
        attacker_loss, defender_loss = min(100, attacker_loss), min(100, defender_loss)
        logistic_losses = {}
        if data.attacker_strategy=='full_retreat' or data.attacker_strategy=='fighting_retreat' and margin<0:
            logistic_losses[data.attacker.identifier]=attacker_loss
        if data.defender_strategy=='full_retreat' or data.defender_strategy=='fighting_retreat' and margin>0:
            logistic_losses[data.defender.identifier]=defender_loss
        if data.attacker_raid_logistics and margin>0:
            automatic = 10 if data.defender_desperate else 0
            logistic_losses[data.defender.identifier]=max(logistic_losses.get(data.defender.identifier,0),max(0,defender_loss-automatic))
            defender_loss=automatic
        if data.defender_raid_logistics and margin<0:
            automatic = 10 if data.attacker_desperate else 0
            logistic_losses[data.attacker.identifier]=max(logistic_losses.get(data.attacker.identifier,0),max(0,attacker_loss-automatic))
            attacker_loss=automatic
        a_pb, d_pb = position_after_round(data.attacker_position, data.defender_position,
            data.attacker_strategy, data.defender_strategy, margin, _pb_shift)
        rallies={}
        for side,loss in (('attacker',attacker_loss),('defender',defender_loss)):
            if getattr(data,side+'_strategy')=='rally' and getattr(data,side+'_casualties')+loss<100:
                roll=getattr(data,side+'_rally_roll')
                if roll is None:roll=roll_3d6()[0]
                rallies[side]=evaluate_success_roll(getattr(data,side+'_leadership')-2,roll)
                rallies[side].update(roll=roll,target=getattr(data,side+'_leadership')-2)
        delta = CampaignStateDelta(
            force_losses={data.attacker.identifier: attacker_loss, data.defender.identifier: defender_loss},
            battle_round=True,
            logistic_losses=logistic_losses,
            battle_positions={data.attacker.identifier: a_pb, data.defender.identifier: d_pb},
            notes=["Resolve pursuit and named-character consequences separately."],
        )
        calculation.breakdown.append({'key': 'position_next', 'attacker': a_pb, 'defender': d_pb,
                                      'source': 'Mass Combat', 'page': '37'})
        return BattleResult(
            valid=not errors, errors=errors, attacker_ts=ats, defender_ts=dts,
            ratio_modifier=ratio_modifier, attacker_result=a_result, defender_result=d_result,
            margin=margin, outcome=outcome, attacker_casualty_percent=attacker_loss,
            defender_casualty_percent=defender_loss, state_delta=delta,
            breakdown=calculation.breakdown,
            references=[RuleReference("Mass Combat", "30-42")],
            rally_results=rallies,
            battle_end=battle_end(data,margin,attacker_loss,defender_loss),
            attack_rolls={'attacker':ar,'defender':dr},
        )


CAMPAIGN_SCHEMA = "gurps-calculadora.campaign-session.v1"


@dataclass
class CampaignSession:
    characters: Dict[str, CharacterSocialProfile] = field(default_factory=dict)
    relationships: Dict[str, RelationshipRecord] = field(default_factory=dict)
    organizations: Dict[str, OrganizationRecord] = field(default_factory=dict)
    forces: Dict[str, ForceRecord] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    autosave_path: Optional[Path] = field(default=None, repr=False)
    _undo: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    battle_casualties: Dict[str, float] = field(default_factory=dict)
    battle_positions: Dict[str, int] = field(default_factory=dict)
    battle_class_strengths: Dict[str, Dict[str, List[float]]] = field(default_factory=dict)
    battle_encounter: bool = False
    battle_logistic_casualties: Dict[str, float] = field(default_factory=dict)
    force_logistic_strengths: Dict[str, Dict[str, float]] = field(default_factory=dict)
    logistics_plans: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    replacement_orders: List[Dict[str, Any]] = field(default_factory=list)
    battle_strategy_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    battle_round_number: int = 1
    battle_conditions: Dict[str, Dict[str, bool]] = field(default_factory=dict)
    battle_ended: Dict[str, Any] = field(default_factory=dict)
    battle_settings: Dict[str, Any] = field(default_factory=dict)


    def to_dict(self) -> Dict[str, Any]:
        return {"schema": CAMPAIGN_SCHEMA,
                "characters": {key: asdict(value) for key, value in self.characters.items()},
                "relationships": {key: asdict(value) for key, value in self.relationships.items()},
                "organizations": {key: asdict(value) for key, value in self.organizations.items()},
                "forces": {key: asdict(value) for key, value in self.forces.items()},
                "history": self.history[-100:], "battle_casualties": dict(self.battle_casualties),
                'battle_positions': dict(self.battle_positions),
                'battle_class_strengths': deepcopy(self.battle_class_strengths),
                'battle_encounter': self.battle_encounter,
                'battle_logistic_casualties': dict(self.battle_logistic_casualties),
                'force_logistic_strengths': deepcopy(self.force_logistic_strengths),
                'logistics_plans': deepcopy(self.logistics_plans),
                'replacement_orders': deepcopy(self.replacement_orders),
                'battle_strategy_state': deepcopy(self.battle_strategy_state),
                'battle_round_number':self.battle_round_number,
                'battle_conditions':deepcopy(self.battle_conditions),'battle_ended':deepcopy(self.battle_ended),
                'battle_settings':deepcopy(self.battle_settings)}

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], autosave_path: Optional[Path] = None) -> "CampaignSession":
        if raw.get("schema") != CAMPAIGN_SCHEMA:
            raise ValueError("invalid_campaign_schema")
        forces = {}
        for key, value in raw.get("forces", {}).items():
            item = dict(value)
            item["elements"] = [ElementRecord(**element) for element in item.get("elements", [])]
            forces[key] = ForceRecord(**item)
        casualties = raw.get('battle_casualties', {})
        if (not isinstance(casualties, dict) or any(key not in forces or isinstance(value, bool) or
                not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100
                for key, value in casualties.items())):
            raise ValueError('invalid_battle_casualties')
        positions = raw.get('battle_positions', {})
        if (not isinstance(positions, dict) or sum(v > 0 for v in positions.values() if type(v) is int) > 1 or
                any(key not in casualties or type(v) is not int or v < 0 for key, v in positions.items())):
            raise ValueError('invalid_battle_position')
        strengths = raw.get('battle_class_strengths', {})
        if not isinstance(strengths, dict) or set(strengths) - set(casualties) or type(raw.get('battle_encounter', False)) is not bool:
            raise ValueError('invalid_class_strength')
        for values in strengths.values():
            class_superiority(values, {}, 1, 1)
        logistic_losses = raw.get('battle_logistic_casualties', {})
        logistic_strengths = raw.get('force_logistic_strengths', {})
        if (not isinstance(logistic_losses, dict) or not isinstance(logistic_strengths, dict) or
                any(k not in casualties or type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100
                    for k, v in logistic_losses.items())):
            raise ValueError('invalid_logistic_state')
        for key, values in logistic_strengths.items():
            if (key not in forces or not isinstance(values, dict) or set(values) - {'land', 'air', 'naval'} or
                    any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values.values())):
                raise ValueError('invalid_logistic_state')
        plans = raw.get('logistics_plans', {})
        settings=raw.get('battle_settings',{})
        if not isinstance(settings,dict) or settings and (set(settings)!={'siege','attacker_db','defender_db'} or
                type(settings['siege']) is not bool or any(type(settings[k]) is not int or settings[k]<0
                for k in ('attacker_db','defender_db'))):raise ValueError('invalid_battle_context')
        ended=raw.get('battle_ended',{})
        if not isinstance(ended,dict) or ended and (set(ended)!={'victor','voluntary_retreat','reason'} or
                ended['victor'] not in ('attacker','defender','mutual','neither') or
                type(ended['voluntary_retreat']) is not bool or ended['reason'] not in ('casualties','retreat') or not casualties):
            raise ValueError('invalid_battle_context')
        conditions=raw.get('battle_conditions',{})
        if not isinstance(conditions,dict):raise ValueError('invalid_battle_context')
        for key,values in conditions.items():
            if (key not in casualties or not isinstance(values,dict) or set(values)!={'confused','started_confused','mobile'} or
                    any(type(v) is not bool for v in values.values())):
                raise ValueError('invalid_battle_context')
        round_number=raw.get('battle_round_number',1)
        if type(round_number) is not int or round_number<1:raise ValueError('invalid_battle_context')
        strategy_state = raw.get('battle_strategy_state', {})
        if not isinstance(strategy_state,dict): raise ValueError('invalid_strategy_history')
        for key, state in strategy_state.items():
            if (key not in casualties or not isinstance(state,dict) or set(state)!={'uses','previous'} or
                    type(state['uses']) is not int or state['uses'] < 0 or
                    state['previous'] not in MassCombatEngine.STRATEGY_MODIFIERS or
                    state['previous']=='indirect_attack' and state['uses']==0):
                raise ValueError('invalid_strategy_history')
        from calculators.replacements import ReplacementOrder
        orders = raw.get('replacement_orders', [])
        if not isinstance(orders,list): raise ValueError('invalid_replacement')
        seen=set()
        for item in orders:
            if not isinstance(item,dict): raise ValueError('invalid_replacement')
            order=ReplacementOrder(**item)
            order.validate()
            pair=(order.force_id,order.element_id)
            if (order.force_id not in forces or pair in seen or
                    len([e for e in forces[order.force_id].elements if e.identifier==order.element_id])!=1):
                raise ValueError('invalid_replacement')
            seen.add(pair)
        if not isinstance(plans, dict):
            raise ValueError('invalid_logistic_input')
        from calculators.logistics import LogisticsInput, SupplyGroup, LogisticsEngine
        for key, plan in plans.items():
            if key not in forces or not isinstance(plan, dict):
                raise ValueError('invalid_logistic_input')
            parsed = LogisticsInput(**{**plan, 'groups': [SupplyGroup(**g) for g in plan.get('groups', [])]})
            LogisticsEngine().validate(parsed)
            if len(parsed.groups) != 1 or parsed.groups[0].identifier != key:
                raise ValueError('invalid_logistic_input')
        return cls(
            characters={key: CharacterSocialProfile(**value) for key, value in raw.get("characters", {}).items()},
            relationships={key: RelationshipRecord(**value) for key, value in raw.get("relationships", {}).items()},
            organizations={key: OrganizationRecord(**value) for key, value in raw.get("organizations", {}).items()},
            forces=forces, history=list(raw.get("history", []))[-100:], autosave_path=autosave_path,
            battle_casualties=dict(raw.get('battle_casualties', {})), battle_positions=dict(positions),
            battle_class_strengths=deepcopy(strengths), battle_encounter=raw.get('battle_encounter', False),
            battle_logistic_casualties=dict(logistic_losses), force_logistic_strengths=deepcopy(logistic_strengths),
            logistics_plans=deepcopy(plans), replacement_orders=deepcopy(orders),
            battle_strategy_state=deepcopy(strategy_state),battle_round_number=round_number,battle_conditions=deepcopy(conditions),
            battle_ended=deepcopy(ended),battle_settings=deepcopy(settings))

    @classmethod
    def load_or_new(cls, path: Path) -> "CampaignSession":
        from utils.editor_records import read_document
        from uuid import uuid4
        path = Path(path)
        if not path.exists():
            return cls(autosave_path=path)
        try:
            return cls.from_dict(read_document(path), path)
        except (ValueError, TypeError, KeyError, AttributeError):
            diagnostic = path.with_name(path.name + ".invalid-" + uuid4().hex)
            os.replace(path, diagnostic)
            session = cls(autosave_path=path)
            session.recovered_file = diagnostic
            return session

    def save(self) -> None:
        if self.autosave_path is None:
            return
        from utils.editor_records import write_document
        write_document(self.autosave_path, self.to_dict())

    def _commit(self, candidate):
        candidate._undo = (deepcopy(self._undo) + [deepcopy(self.to_dict())])[-100:]
        candidate.history = candidate.history[-100:]
        candidate.save()
        self.__dict__.update(candidate.__dict__)

    def apply_battle_round(self, data: BattleInput, result: BattleResult, expected_snapshot):
        """Commit a resolved round and its starting forces as a single undo step."""
        if self.to_dict() != expected_snapshot:
            raise ValueError('stale_battle_result')
        if self.battle_ended:raise ValueError('battle_already_ended')
        if set(result.attack_rolls)!={'attacker','defender'}:raise ValueError('stale_battle_result')
        explicit=replace(data)
        for side in ('attacker','defender'):
            # Supply every random input before verification; never consume RNG here.
            rr=result.rally_results.get(side,{}).get('roll',getattr(data,side+'_rally_roll'))
            if rr is None:rr=3
            setattr(explicit,side+'_rally_roll',rr)
        verified=MassCombatEngine().resolve(explicit,result.attack_rolls['attacker'],result.attack_rolls['defender'])
        if verified!=result:raise ValueError('stale_battle_result')
        identifiers = {data.attacker.identifier, data.defender.identifier}
        if data.round_number!=self.battle_round_number:raise ValueError('stale_battle_result')
        if (not result.valid or not result.state_delta.battle_round or
                set(result.state_delta.force_losses) != identifiers or
                self.battle_casualties and set(self.battle_casualties) != identifiers):
            raise ValueError('invalid_battle_casualties')
        candidate = deepcopy(self)
        for force, previous in ((data.attacker, data.attacker_casualties),
                                (data.defender, data.defender_casualties)):
            if not math.isfinite(previous) or not 0 <= previous < 100:
                raise ValueError('invalid_battle_casualties')
            existing = candidate.forces.get(force.identifier)
            if existing is not None and asdict(existing) != asdict(force):
                raise ValueError('stale_battle_result')
            if self.battle_casualties and candidate.battle_casualties.get(force.identifier) != previous:
                raise ValueError('stale_battle_result')
            candidate.forces[force.identifier] = deepcopy(force)
            candidate.battle_casualties[force.identifier] = previous
        actual = MassCombatEngine._battle_choices(data)
        for side in ('attacker','defender'):
            key = getattr(data,side).identifier
            uses = getattr(data,side+'_indirect_uses')
            previous = getattr(data,side+'_previous_strategy')
            stored = self.battle_strategy_state.get(key, {'uses':0,'previous':''})
            if stored != {'uses':uses,'previous':previous}:
                raise ValueError('stale_battle_result')
            choice = getattr(actual,side+'_strategy')
            candidate.battle_strategy_state[key] = {'uses':uses+int(choice=='indirect_attack'),'previous':choice}
            current={k:getattr(data,side+'_'+k) for k in ('confused','started_confused','mobile')}
            if key in self.battle_conditions and self.battle_conditions[key]!=current:
                raise ValueError('stale_battle_result')
            current['started_confused']=current['started_confused'] or (data.round_number==1 and current['confused'])
            if side in result.rally_results and result.rally_results[side]['success']:
                current['confused']=False
            candidate.battle_conditions[key]=current
        if self.battle_casualties and (self.battle_positions.get(data.attacker.identifier, 0) != data.attacker_position or
                                     self.battle_positions.get(data.defender.identifier, 0) != data.defender_position):
            raise ValueError('stale_battle_result')
        candidate._apply_delta(result.state_delta, 'battle_round')
        candidate.battle_class_strengths = {data.attacker.identifier: deepcopy(data.attacker_classes),
                                          data.defender.identifier: deepcopy(data.defender_classes)}
        candidate.battle_encounter = data.encounter_battle
        candidate.battle_round_number+=1
        candidate.battle_settings={'siege':data.siege,'attacker_db':data.attacker_defense_bonus,'defender_db':data.defender_defense_bonus}
        candidate.battle_ended=battle_end(actual,result.margin,result.attacker_casualty_percent,result.defender_casualty_percent)
        self._commit(candidate)

    def finalize_battle(self, final_casualties: Dict[str, float], expected_snapshot=None):
        """Apply GM-confirmed post-pursuit/recovery losses once (MC38-39)."""
        if expected_snapshot is not None and self.to_dict() != expected_snapshot:
            raise ValueError('stale_battle_result')
        if (set(final_casualties) != set(self.battle_casualties) or not final_casualties or
                any(not math.isfinite(v) or not 0 <= v <= 100 for v in final_casualties.values())):
            raise ValueError('invalid_battle_casualties')
        candidate = deepcopy(self)
        candidate._apply_delta(CampaignStateDelta(force_losses=final_casualties), 'battle_finalized')
        for key, loss in candidate.battle_logistic_casualties.items():
            candidate.force_logistic_strengths[key] = {kind: value * (1 - loss / 100)
                for kind, value in candidate.force_logistic_strengths.get(key, {}).items()}
        candidate.battle_casualties.clear()
        candidate.battle_positions.clear()
        candidate.battle_class_strengths.clear()
        candidate.battle_strategy_state.clear()
        candidate.battle_conditions.clear()
        candidate.battle_round_number=1
        candidate.battle_ended.clear()
        candidate.battle_settings.clear()
        candidate.battle_logistic_casualties.clear()
        candidate.battle_encounter = False
        self._commit(candidate)

    def end_without_combat(self, data, expected_snapshot):
        if self.to_dict()!=expected_snapshot or self.battle_ended:
            raise ValueError('stale_battle_result')
        calculation=MassCombatEngine().calculate(data)
        if not calculation.valid or calculation.event!='no_battle':
            raise ValueError('invalid_battle_context')
        ids={data.attacker.identifier,data.defender.identifier}
        if self.battle_casualties and set(self.battle_casualties)!=ids:
            raise ValueError('stale_battle_result')
        if data.round_number!=self.battle_round_number:raise ValueError('stale_battle_result')
        candidate=deepcopy(self)
        for side in ('attacker','defender'):
            force=getattr(data,side)
            loss=getattr(data,side+'_casualties')
            existing=self.forces.get(force.identifier)
            if existing is not None and asdict(existing)!=asdict(force):raise ValueError('stale_battle_result')
            if self.battle_casualties and self.battle_casualties[force.identifier]!=loss:
                raise ValueError('stale_battle_result')
            if self.battle_casualties and self.battle_positions.get(force.identifier,0)!=getattr(data,side+'_position'):
                raise ValueError('stale_battle_result')
            candidate.forces[force.identifier]=deepcopy(force)
            candidate.battle_casualties[force.identifier]=loss
            candidate.battle_positions[force.identifier]=getattr(data,side+'_position')
            candidate.battle_class_strengths[force.identifier]=deepcopy(getattr(data,side+'_classes'))
        actual=MassCombatEngine._battle_choices(data)
        candidate.battle_ended=battle_end(actual,0,0,0)
        candidate.battle_settings={'siege':data.siege,'attacker_db':data.attacker_defense_bonus,'defender_db':data.defender_defense_bonus}
        candidate.battle_encounter=data.encounter_battle
        candidate.history.append({'label':'battle_ended_without_combat','input':asdict(data)})
        self._commit(candidate)

    def finalize_aftermath(self, data, result, expected_snapshot):
        """Commit MC38 pursuit/recovery once, including independent logistic losses."""
        from calculators.battle_aftermath import BattleAftermathEngine
        if self.to_dict() != expected_snapshot:
            raise ValueError('stale_battle_result')
        if self.battle_ended and (data.victor!=self.battle_ended['victor'] or
                                 data.voluntary_retreat!=self.battle_ended['voluntary_retreat']):
            raise ValueError('invalid_aftermath_choice')
        if not result.complete:
            raise ValueError('invalid_aftermath_choice')
        explicit = replace(data, leadership_roll=result.rolls.get('leadership', data.leadership_roll),
            reaction_roll=result.rolls.get('reaction', data.reaction_roll),
            logistic_roll=result.rolls.get('logistics', data.logistic_roll))
        if BattleAftermathEngine().calculate(explicit) != result:
            raise ValueError('stale_battle_result')
        ids = {side: getattr(data, side + '_id') for side in ('attacker', 'defender')}
        if set(self.battle_casualties) != set(ids.values()):
            raise ValueError('invalid_battle_casualties')
        candidate = deepcopy(self)
        for side, key in ids.items():
            force = candidate.forces[key]
            if (getattr(data, side + '_casualties') != self.battle_casualties[key] or
                    getattr(data, side + '_ts') != force.troop_strength or
                    getattr(data, side + '_logistic_losses') != self.battle_logistic_casualties.get(key, 0)):
                raise ValueError('stale_battle_result')
            ratio = result.remaining_ts[side] / force.troop_strength if force.troop_strength else 0
            for element in force.elements:
                element.troop_strength *= ratio
            remaining = 1 - result.logistic_losses[side] / 100
            candidate.force_logistic_strengths[key] = {kind: value * remaining
                for kind, value in candidate.force_logistic_strengths.get(key, {}).items()}
        candidate.history.append({'label': 'battle_aftermath', 'input': asdict(explicit), 'result': asdict(result)})
        candidate.battle_settings.clear()
        candidate.battle_conditions.clear()
        candidate.battle_round_number=1
        candidate.battle_ended.clear()
        candidate.battle_strategy_state.clear()
        candidate.battle_casualties.clear()
        candidate.battle_positions.clear()
        candidate.battle_class_strengths.clear()
        candidate.battle_logistic_casualties.clear()
        candidate.battle_encounter = False
        self._commit(candidate)

    def upsert_record(self, record):
        mapping = {CharacterSocialProfile: 'characters', RelationshipRecord: 'relationships',
                   OrganizationRecord: 'organizations', ForceRecord: 'forces'}
        group = mapping.get(type(record))
        if group is None or not isinstance(record.identifier, str) or not record.identifier:
            raise ValueError('invalid_campaign_record')
        candidate = deepcopy(self)
        getattr(candidate, group)[record.identifier] = deepcopy(record)
        candidate.history.append({'label': 'edit_' + group, 'identifier': record.identifier})
        self._commit(candidate)

    def apply_maintenance(self, data, result, expected_snapshot):
        """One funded month, one force, one atomic undo step. No hypothetical changes."""
        from calculators.logistics import LogisticsEngine
        if self.to_dict() != expected_snapshot:
            raise ValueError('stale_battle_result')
        if len(data.groups) != 1 or not result.complete:
            raise ValueError('invalid_logistic_input')
        group = data.groups[0]
        if group.identifier not in self.forces or group.identifier in self.battle_casualties:
            raise ValueError('logistic_active_battle')
        explicit = replace(data, administration_roll=result.roll)
        if LogisticsEngine().calculate(explicit) != result:
            raise ValueError('stale_battle_result')
        force = self.forces[group.identifier]
        if (group.recovering != force.readiness_recovering or
                data.strengths != self.force_logistic_strengths.get(group.identifier, {}) or
                data.funds > force.resources):
            raise ValueError('stale_battle_result')
        # Replacement completion requires the training-time workflow, not a TS gift.
        if data.replacement_percent:
            raise ValueError('logistic_replacement_pending')
        candidate = deepcopy(self)
        force = candidate.forces[group.identifier]
        effect = result.effects[group.identifier]
        force.resources -= result.total_cost
        for element in force.elements:
            element.troop_strength *= 1 - effect['casualties'] / 100
        force.readiness_multiplier = effect['ts_multiplier']
        force.readiness_recovering = effect['recovering_next_month']
        force.maintenance_month += 1
        candidate.history.append({'label':'monthly_maintenance','input':asdict(explicit),'result':asdict(result)})
        self._commit(candidate)

    def configure_logistics(self, force, data, expected_snapshot):
        from calculators.logistics import LogisticsEngine
        if self.to_dict() != expected_snapshot:
            raise ValueError('stale_battle_result')
        LogisticsEngine().validate(data)
        if (len(data.groups) != 1 or data.groups[0].identifier != force.identifier or
                not math.isfinite(force.troop_strength) or force.troop_strength <= 0):
            raise ValueError('invalid_logistic_input')
        if force.identifier in self.battle_casualties:
            raise ValueError('logistic_active_battle')
        existing = self.forces.get(force.identifier)
        if existing is not None and asdict(existing) != asdict(force):
            raise ValueError('stale_battle_result')
        candidate = deepcopy(self)
        candidate.forces[force.identifier] = deepcopy(force)
        candidate.forces[force.identifier].resources = data.funds
        candidate.force_logistic_strengths[force.identifier] = deepcopy(data.strengths)
        candidate.logistics_plans[force.identifier] = asdict(data)
        candidate.history.append({'label':'configure_logistics','force':force.identifier})
        self._commit(candidate)

    def update_battle_context(self, conditions, settings, encounter, expected_snapshot):
        """GM-confirmed external events/corrections, with no new combat round."""
        if self.to_dict()!=expected_snapshot:raise ValueError('stale_battle_result')
        if self.battle_ended or not self.battle_casualties or set(conditions)!=set(self.battle_casualties):
            raise ValueError('invalid_battle_context')
        if type(encounter) is not bool or settings.get('siege') and encounter:
            raise ValueError('invalid_battle_context')
        candidate=deepcopy(self)
        candidate.battle_conditions=deepcopy(conditions)
        candidate.battle_settings=deepcopy(settings)
        candidate.battle_encounter=encounter
        # Apply the same schema validation as saved/imported sessions.
        CampaignSession.from_dict(candidate.to_dict())
        candidate.history.append({'label':'battle_context_confirmed','conditions':deepcopy(conditions),
                                  'settings':deepcopy(settings),'encounter':encounter})
        self._commit(candidate)

    def apply(self, delta: CampaignStateDelta, label: str = "campaign_event") -> None:
        candidate = deepcopy(self)
        candidate._apply_delta(delta, label)
        self._commit(candidate)

    def _apply_delta(self, delta: CampaignStateDelta, label: str) -> None:
        if delta.logistic_losses:
            if (not delta.battle_round or any(k not in self.forces or k not in delta.force_losses or
                    type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100
                    for k,v in delta.logistic_losses.items())):
                raise ValueError('invalid_logistic_state')
            for key, loss in delta.logistic_losses.items():
                self.battle_logistic_casualties[key]=min(100,self.battle_logistic_casualties.get(key,0)+loss)
        if delta.battle_positions:
            if (not delta.battle_round or sum(v > 0 for v in delta.battle_positions.values() if type(v) is int) > 1 or
                    any(k not in delta.force_losses or k not in self.forces or type(v) is not int or v < 0
                        for k, v in delta.battle_positions.items())):
                raise ValueError('invalid_battle_position')
            merged = {**self.battle_positions, **delta.battle_positions}
            if sum(v > 0 for v in merged.values()) > 1:
                raise ValueError('invalid_battle_position')
            self.battle_positions.update(delta.battle_positions)
        for changes, records in ((delta.relationship_changes, self.relationships),
                                 (delta.organization_resource_changes, self.organizations),
                                 (delta.force_losses, self.forces), (delta.morale_changes, self.forces)):
            if any(key not in records or isinstance(value, bool) or not math.isfinite(value)
                   for key, value in changes.items()):
                raise ValueError('invalid_campaign_delta')
        if any(not 0 <= loss <= 100 for loss in delta.force_losses.values()) or delta.territory_changes:
            raise ValueError('invalid_campaign_delta')
        for key, change in delta.relationship_changes.items():
            if key in self.relationships:
                self.relationships[key].intensity += change
        for key, change in delta.organization_resource_changes.items():
            if key in self.organizations:
                self.organizations[key].resources += round(change)
        for key, change in delta.force_losses.items():
            if key in self.forces:
                if delta.battle_round:
                    self.battle_casualties[key] = min(100, self.battle_casualties.get(key, 0) + change)
                    continue
                remaining = max(0.0, 1.0 - change / 100.0)
                for element in self.forces[key].elements:
                    element.troop_strength *= remaining
        for key, change in delta.morale_changes.items():
            if key in self.forces:
                self.forces[key].morale += change
        self.history.append({"label": label, "delta": asdict(delta), "at": datetime.now().isoformat(timespec="seconds")})

    def undo(self) -> bool:
        if not self._undo:
            return False
        restored = CampaignSession.from_dict(self._undo[-1], self.autosave_path)
        restored._undo = deepcopy(self._undo[:-1])
        restored.save()
        self.__dict__.update(restored.__dict__)
        return True
