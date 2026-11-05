"""
Calculadora GURPS 4e - Interface Principal

Ferramenta multiuso para cálculos do GURPS 4th Edition (Basic Set Revised).
Inclui calculadoras para: Knockback, Investida, Quedas, Colisões,
Explosões, Queda de Objetos e Cálculos de Combate.

Unidades:
- Interface: metros (m) e metros por segundo (m/s)
- Cálculos internos: jardas (yards) e jardas por segundo (yd/s)
- Conversão: 1 jarda = 0.9144 metros

Referências do Basic Set Revised:
- Damage Table: p. 16
- Combat: p. 364-416
- Knockback: p. 378
- Collisions and Falls: p. 430-431
- Explosions: p. 414-415

Estrutura do projeto:
- main.py: Interface Tkinter (este arquivo)
- calculators/: Módulos de cálculo para cada regra
- utils/: Utilitários (rolagem de dados, i18n)
- i18n/: Arquivos de tradução (pt_BR.json, en_US.json)
"""
import math
import json
import re
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
# typing imports not needed - no type annotations in this file

from calculators.knockback import KnockbackCalculator
from calculators.slam import SlamCalculator
from calculators.falls import FallsCalculator
from calculators.collisions import CollisionsCalculator
from calculators.explosions import ExplosionsCalculator
from calculators.falling_objects import FallingObjectsCalculator
from calculators.combat import CombatCalculator
from calculators.ranged_combat import DamageMode, RangedAttackInput, RangedCombatCalculator, WeaponRecord
from calculators.injury import (
    ArmorLayer,
    ArmorLoadout,
    CombatantState,
    DamagePacket,
    InjuryEngine,
    InjuryInput,
    OptionalInjuryRules,
    StateDelta,
)
from calculators.combat_session import CombatSession
from calculators.combat_library import CombatLibrary
from calculators.melee_combat import (
    GrappleActionInput,
    GrapplingEngine,
    MeleeAttackInput,
    MeleeCombatCalculator,
    MeleeDamageMode,
    MeleeWeaponRecord,
)
from utils.i18n import get_i18n, t
from utils.gui_workspace import install_workspace
from utils.gui_form_state import capture_results, install_form_states, InlineError
from utils.ranged_layout import (Disclosure, FieldError, FieldGrid, RangedWorkbench,
                                 checkbutton as ranged_checkbutton, flow_buttons, wrap_label, wrap_toggle)
from utils.impact_layout import ImpactForm
from utils.ui_preferences import load_ui_preferences
from utils.ui_theme import apply_theme, make_palette
from utils.gui_hub import install_hub, remember_session, confirm_session
from utils.gm_dice_ui import GMDicePanel
from utils.ranged_handoff import RangedHitDraft
from utils.vehicle_combat_ui import VehicleCombatPanel
from utils.gui_editors import VehicleEditor, AbilityEditor, CastingAssistant
from utils.units import UnitSystem
from utils.unit_binding import UnitBinding
from utils.preferences import load_preferences, save_preferences
from utils.dice_roller import roll_3d6
from utils.weapon_catalog import WeaponCatalog
from utils.combat_catalog import ArmorCatalog, MeleeWeaponCatalog, StyleCatalog, TechniqueCatalog
from utils.weapon_catalog import application_data_dir
from calculators.strength import DamageBonusInput, EffortOption, StrengthCalculationInput, StrengthEngine, StrengthProfile
from calculators.magic import MAGIC_SYSTEMS, IMPLEMENTED_MAGIC_SYSTEMS, CastingInput, ResourcePool, ResistanceCheck, SpellcastingEngine
from utils.gui_editors import CeremonialEditor, CampaignEditor
from utils.battle_ui import BattleClassEditor, BattleAftermathEditor
from utils.logistics_ui import LogisticsEditor
from utils.replacements_ui import ReplacementEditor
from calculators.powers import AbilityBuildInput, AbilityEngine, PsionicEngine, PsiUseInput
from calculators.vehicles import VehicleCatalog, VehicleEngine, VehicleMovementInput, VehicleState, VehicleSession
from calculators.campaign import (
    BattleInput, CampaignSession, CharacterSocialProfile, ElementRecord, ForceRecord, InfluenceInput,
    MassCombatEngine, ReactionInput, SocialEngineeringEngine, INFLUENCE_SKILLS,
)
from utils.rules_catalog import ExtendedRulesCatalog, catalog_status
from version import __version__

# ─── Constantes de conversão ────────────────────────────────────────
# 1 jarda = 0.9144 metros (definição internacional)
YARDS_TO_METERS = 0.9144
METERS_TO_YARDS = 1.0 / YARDS_TO_METERS  # ≈ 1.09361


class GURPSCalculator:
    """
    Classe principal da Calculadora GURPS 4e.
    
    Gerencia a interface gráfica e coordena as calculadoras.
    Usa Tkinter para a GUI com suporte completo a internacionalização.
    """

    def __init__(self):
        """Inicializa a aplicação e todos os componentes."""
        self.root = tk.Tk()
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Inicializa calculadoras (lógica de negócio)
        self.knockback_calc = KnockbackCalculator()
        self.slam_calc = SlamCalculator()
        self.falls_calc = FallsCalculator()
        self.collisions_calc = CollisionsCalculator()
        self.explosions_calc = ExplosionsCalculator()
        self.falling_objects_calc = FallingObjectsCalculator()
        self.combat_calc = CombatCalculator()
        self.ranged_calc = RangedCombatCalculator()
        self.weapon_catalog = WeaponCatalog()
        self.injury_calc = InjuryEngine()
        self.melee_calc = MeleeCombatCalculator()
        self.grappling_calc = GrapplingEngine()
        self.melee_weapon_catalog = MeleeWeaponCatalog()
        self.armor_catalog = ArmorCatalog()
        self.technique_catalog = TechniqueCatalog()
        self.style_catalog = StyleCatalog()
        self.combat_session = CombatSession.load_or_new(application_data_dir() / "combat_session.json")
        self.combat_library = CombatLibrary(application_data_dir() / "combat_library.json")
        self._ranged_drafts = {}
        self._injury_ranged_draft = None
        self._injury_draft_resolved = False
        self._injury_manual_form = None
        self.strength_calc = StrengthEngine()
        self.spell_calc = SpellcastingEngine()
        self.ability_calc = AbilityEngine()
        self.psi_calc = PsionicEngine()
        self.vehicle_calc = VehicleEngine()
        self.vehicle_session = VehicleSession.load_or_new(application_data_dir() / "vehicle_session.json")
        self._pending_vehicle_movement = None
        self.social_calc = SocialEngineeringEngine()
        self.mass_combat_calc = MassCombatEngine()
        self.extended_catalog = ExtendedRulesCatalog()
        self.vehicle_catalog = VehicleCatalog(
            Path(__file__).resolve().parent / "data" / "vehicles.json",
            application_data_dir() / "vehicles.json",
        )
        self.campaign_session = CampaignSession.load_or_new(application_data_dir() / "campaign_session.json")
        self._last_melee_result = None
        self._last_grapple_result = None
        self._last_injury_result = None

        # Inicializa sistema de internacionalização
        self.i18n = get_i18n()
        self.preferences_path = application_data_dir() / "preferences.json"
        preferences = load_preferences(self.preferences_path)
        self.i18n.set_language(preferences.get("language", "pt_BR"))
        self.result_units = tk.StringVar(value=preferences.get("units", "metric"))
        self.ui_preferences_path = application_data_dir() / 'ui_preferences.json'
        self.ui_preferences = load_ui_preferences(self.ui_preferences_path)
        self.root.geometry(self.ui_preferences['window'])

        # Variáveis de entrada (preservadas entre rebuilds de UI)
        self._init_variables()

        # Configura tema visual
        self._setup_theme()

        # Cria menu e interface
        self._create_menu()
        self._rebuild_ui()
        self._refresh_session_summary(sync_fields=True)

        # Atualiza título
        self._update_title()

    def _init_variables(self):
        """
        Inicializa todas as variáveis de entrada da interface.
        
        Cada variável tk.IntVar/tk.StringVar/tk.BooleanVar é preservada
        quando a UI é reconstruída (troca de idioma).
        """
        self.gm_dice_expression = tk.StringVar(value='3d6')
        self.gm_dice_last_result = None
        self.gm_dice_error_code = None
        self.gm_dice_page = tk.StringVar(value='1')
        self._gm_dice_current_page = 1
        self._gm_dice_job = None

        # ─── Knockback (p. 378) ─────────────────────────────────────
        self.kb_damage_type = tk.StringVar(value="crushing")
        self.kb_basic_damage = tk.IntVar(value=10)
        self.kb_target_st = tk.IntVar(value=10)
        self.kb_target_hp = tk.IntVar(value=10)
        self.kb_target_dr = tk.IntVar(value=0)
        self.kb_perfect_balance = tk.BooleanVar(value=False)
        self.kb_effective_skill = tk.IntVar(value=10)
        self.kb_roll_result = tk.IntVar(value=11)

        # ─── Slam/Investida (p. 371) ────────────────────────────────
        self.slam_attacker_hp = tk.IntVar(value=10)
        self.slam_attacker_velocity = tk.DoubleVar(value=5)  # m/s
        self.slam_defender_hp = tk.IntVar(value=10)
        self.slam_defender_velocity = tk.DoubleVar(value=0)  # m/s
        self.slam_collision_type = tk.StringVar(value="head_on")
        self.slam_attacker_damage_bonus = tk.IntVar(value=0)

        # ─── Quedas (p. 430-431) ────────────────────────────────────
        self.falls_distance = tk.DoubleVar(value=9)   # metros (~10 jardas)
        self.falls_hp = tk.IntVar(value=10)
        self.falls_dr = tk.IntVar(value=0)
        self.falls_surface = tk.StringVar(value="hard")
        self.falls_acrobatics = tk.BooleanVar(value=False)
        self.falls_swimming = tk.BooleanVar(value=False)

        # ─── Colisões (p. 430-431) ──────────────────────────────────
        self.coll_obj1_hp = tk.IntVar(value=60)
        self.coll_obj1_velocity = tk.DoubleVar(value=23)  # m/s (~25 yd/s)
        self.coll_obj2_hp = tk.IntVar(value=10)
        self.coll_obj2_dr = tk.IntVar(value=0)
        self.coll_obj2_velocity = tk.DoubleVar(value=5)
        self.coll_type = tk.StringVar(value="head_on")
        self.coll_surface = tk.StringVar(value="normal")
        self.coll_immovable = tk.BooleanVar(value=False)
        self.coll_breakable = tk.BooleanVar(value=False)

        # ─── Explosões (p. 414-415) ─────────────────────────────────
        self.exp_basic_damage = tk.IntVar(value=6)
        self.exp_fragmentation = tk.IntVar(value=0)
        self.exp_distance = tk.DoubleVar(value=9)   # metros (~10 jardas)
        self.exp_dr = tk.IntVar(value=0)
        self.exp_direct_hit = tk.BooleanVar(value=False)
        self.exp_target_sm = tk.IntVar(value=0)
        self.exp_posture_modifier = tk.IntVar(value=0)

        # ─── Queda de Objetos (p. 431) ──────────────────────────────
        self.fo_distance = tk.DoubleVar(value=9)
        self.fo_object_hp = tk.IntVar(value=10)
        self.fo_target_hp = tk.IntVar(value=10)
        self.fo_target_sm = tk.IntVar(value=0)
        self.fo_object_sm = tk.IntVar(value=0)
        self.fo_dropping_skill = tk.IntVar(value=15)
        self.fo_target_aware = tk.BooleanVar(value=False)
        self.fo_target_dodge = tk.IntVar(value=8)
        self.fo_aimed = tk.BooleanVar(value=False)

        # ─── Combate (p. 368-376) ───────────────────────────────────
        # Attack Skill: Habilidade usada para acertar (ex: Sword-15)
        # NÃO é o mesmo que ST - são valores separados
        self.combat_attack_skill = tk.IntVar(value=15)
        # Effective Defense: Dodge, Parry ou Block (p. 374-376)
        self.combat_defense = tk.IntVar(value=10)
        # ST: Força do personagem, determina dano (thrust/swing)
        # Referência: Damage Table, p. 16
        self.combat_st = tk.IntVar(value=10)

        # ─── Tiro / Ranged Combat (p. 364, 372-374, 548-550) ───────
        self.ranged_profile_key = "basic"
        self.ranged_maneuver_key = "attack"
        self.ranged_location_key = "torso"
        self.ranged_profile = tk.StringVar()
        self.ranged_search = tk.StringVar()
        self.ranged_weapon = tk.StringVar()
        self.ranged_weapon_name = tk.StringVar()
        self.ranged_acc = tk.StringVar(value="2")
        self.ranged_damage = tk.StringVar(value="2d")
        self.ranged_damage_type = tk.StringVar(value="pi")
        self.ranged_armor_divisor = tk.StringVar(value="1")
        self.ranged_half_damage = tk.StringVar(value="150")
        self.ranged_max_range = tk.StringVar(value="1500")
        self.ranged_rof = tk.StringVar(value="3")
        self.ranged_projectiles = tk.StringVar(value="1")
        self.ranged_shots_stat = tk.StringVar(value="15+1(3)")
        self.ranged_bulk = tk.StringVar(value="-2")
        self.ranged_rcl = tk.StringVar(value="2")
        self.ranged_malf = tk.StringVar(value="17")
        self.ranged_minimum_range = tk.StringVar(value="0")
        self.ranged_required_st = tk.StringVar(value="9")
        self.ranged_skill = tk.StringVar(value="14")
        self.ranged_distance = tk.StringVar(value="25")
        self.ranged_map_hint = tk.StringVar()
        self._map_ranged_transfer = None
        self.ranged_distance.trace_add("write", self._refresh_ranged_map_hint)
        self.ranged_speed = tk.StringVar(value="0")
        self.ranged_sm = tk.StringVar(value="0")
        self.ranged_aim_seconds = tk.StringVar(value="0")
        self.ranged_braced = tk.BooleanVar(value=False)
        self.ranged_aim_lost = tk.BooleanVar(value=False)
        self.ranged_shots_fired = tk.StringVar(value="1")
        self.ranged_maneuver = tk.StringVar()
        self.ranged_location = tk.StringVar()
        self.ranged_dodge = tk.StringVar(value="8")
        self.ranged_target_aware = tk.BooleanVar(value=True)
        self.ranged_dr = tk.StringVar(value="0")
        self.ranged_target_hp = tk.StringVar(value="10")
        self.ranged_shooter_st = tk.StringVar(value="10")
        self.ranged_scope = tk.StringVar(value="0")
        self.ranged_laser = tk.StringVar(value="0")
        self.ranged_targeting = tk.StringVar(value="0")
        self.ranged_cover = tk.StringVar(value="0")
        self.ranged_visibility = tk.StringVar(value="0")
        self.ranged_posture = tk.StringVar(value="0")
        self.ranged_custom_modifier = tk.StringVar(value="0")
        self.ranged_rangefinder = tk.StringVar(value="0")
        self.ranged_precision_aiming = tk.StringVar(value="0")
        self.ranged_follow_up_aim = tk.StringVar(value="0")
        self.ranged_fast_firing = tk.StringVar(value="0")
        self.ranged_cinematic_modifier = tk.StringVar(value="0")
        self.ranged_ammunition_key = "standard"
        self.ranged_ammunition = tk.StringVar()
        self.ranged_minute_of_angle = tk.BooleanVar(value=False)
        self.ranged_cannot_see = tk.BooleanVar(value=False)
        self.ranged_offhand = tk.BooleanVar(value=False)
        self.ranged_advanced_visible = tk.BooleanVar(value=False)

        # ─── Sessão leve compartilhada ──────────────────────────────
        self.session_actor_key, self.session_target_key = self.combat_session.selected_pair()
        self.session_actor = tk.StringVar()
        self.session_target = tk.StringVar()
        self.session_summary = tk.StringVar()
        self.source_basic_set = tk.BooleanVar(value=True)
        self.source_martial_arts = tk.BooleanVar(value=True)
        self.source_low_tech = tk.BooleanVar(value=True)
        self.source_high_tech = tk.BooleanVar(value=True)
        self.source_ultra_tech = tk.BooleanVar(value=True)

        # ─── Corpo a corpo / Melee ──────────────────────────────────
        self.melee_profile_key = "basic"
        self.melee_maneuver_key = "attack"
        self.melee_location_key = "torso"
        self.melee_defense_key = "dodge"
        self.melee_retreat_key = "none"
        self.melee_profile = tk.StringVar()
        self.melee_search = tk.StringVar()
        self.melee_weapon = tk.StringVar()
        self.melee_style = tk.StringVar()
        self.melee_technique = tk.StringVar()
        self.melee_weapon_name = tk.StringVar()
        self.melee_damage = tk.StringVar(value="sw")
        self.melee_damage_type = tk.StringVar(value="cut")
        self.melee_armor_divisor = tk.StringVar(value="1")
        self.melee_reach = tk.StringVar(value="1")
        self.melee_parry = tk.StringVar(value="0")
        self.melee_min_st = tk.StringVar(value="10")
        self.melee_skill = tk.StringVar(value="14")
        self.melee_attacker_st = tk.StringVar(value="10")
        self.melee_distance = tk.StringVar(value="1")
        self.melee_target_hp = tk.StringVar(value="10")
        self.melee_target_ht = tk.StringVar(value="10")
        self.melee_target_dr = tk.StringVar(value="0")
        self.melee_defense_score = tk.StringVar(value="8")
        self.melee_maneuver = tk.StringVar()
        self.melee_location = tk.StringVar()
        self.melee_defense = tk.StringVar()
        self.melee_retreat = tk.StringVar()
        self.melee_rapid_strikes = tk.StringVar(value="1")
        self.melee_deceptive = tk.StringVar(value="0")
        self.melee_custom_modifier = tk.StringVar(value="0")
        self.melee_target_aware = tk.BooleanVar(value=True)
        self.melee_telegraphic = tk.BooleanVar(value=False)
        self.melee_trained_by_master = tk.BooleanVar(value=False)
        self.melee_weapon_master = tk.BooleanVar(value=False)
        self.melee_dual_weapon = tk.BooleanVar(value=False)
        self.melee_offhand = tk.BooleanVar(value=False)
        self.melee_ambidextrous = tk.BooleanVar(value=False)
        self.melee_allow_silly = tk.BooleanVar(value=False)
        self.melee_advanced_visible = tk.BooleanVar(value=False)
        self.melee_grapple_action_key = "grapple"
        self.melee_grapple_action = tk.StringVar()
        self.melee_grapple_resistance = tk.StringVar(value="10")
        self.melee_grapple_two_handed = tk.BooleanVar(value=True)
        self.melee_new_posture_key = "standing"
        self.melee_new_posture = tk.StringVar()

        # ─── Trauma / Injury ────────────────────────────────────────
        self.injury_profile_key = "basic"
        self.injury_location_key = "torso"
        self.injury_direction_key = "front"
        self.injury_profile = tk.StringVar()
        self.injury_basic_damage = tk.StringVar(value="6")
        self.injury_damage_type = tk.StringVar(value="cr")
        self.injury_armor_divisor = tk.StringVar(value="1")
        self.injury_location = tk.StringVar()
        self.injury_direction = tk.StringVar()
        self.injury_target_hp = tk.StringVar(value="10")
        self.injury_target_ht = tk.StringVar(value="10")
        self.injury_natural_dr = tk.StringVar(value="0")
        self.injury_armor_search = tk.StringVar()
        self.injury_armor = tk.StringVar()
        self.injury_chinks = tk.BooleanVar(value=False)
        self.injury_large_area = tk.BooleanVar(value=False)
        self.injury_rule_bleeding = tk.BooleanVar(value=False)
        self.injury_rule_severe_bleeding = tk.BooleanVar(value=False)
        self.injury_rule_accumulated = tk.BooleanVar(value=False)
        self.injury_rule_partial = tk.BooleanVar(value=False)
        self.injury_rule_lasting = tk.BooleanVar(value=False)
        self.injury_rule_gaps = tk.BooleanVar(value=False)
        self.injury_rule_layering = tk.BooleanVar(value=False)
        self.injury_rule_edge = tk.BooleanVar(value=False)
        self.injury_rule_degradation = tk.BooleanVar(value=False)

        # Extended systems (v1.3-v1.6)
        self.strength_st = tk.StringVar(value="10")
        self.strength_lifting = tk.StringVar(value="0")
        self.strength_striking = tk.StringVar(value="0")
        self.strength_super = tk.StringVar(value="0")
        self.strength_task = tk.StringVar(value="basic_lift")
        self.strength_profile = tk.StringVar(value="basic")
        self.strength_all_out = tk.BooleanVar(value=False)
        self.strength_mighty = tk.BooleanVar(value=False)
        self.strength_scope = tk.StringVar(value="lifting")
        self.strength_fp = tk.StringVar(value="10")
        self.strength_max_fp = tk.StringVar(value="10")
        self.strength_will = tk.StringVar(value="10")
        self.strength_extra = tk.StringVar(value="0")
        self.strength_lifting_skill = tk.StringVar(value="")
        self.strength_duration = tk.StringVar(value="1")
        self.strength_continuous = tk.BooleanVar(value=False)
        self.strength_carry = tk.BooleanVar(value=False)
        self.strength_trained_lift = tk.BooleanVar(value=False)
        self.strength_lifting_ht = tk.StringVar(value='10')
        self.strength_power_blow = tk.BooleanVar(value=False)
        self.strength_power_blow_skill = tk.StringVar(value='10')
        self.strength_power_blow_time = tk.StringVar(value='0')
        self.strength_master = tk.BooleanVar(value=False)
        self.strength_triple = tk.BooleanVar(value=False)

        self.magic_spell = tk.StringVar()
        self.magic_system = tk.StringVar(value="standard")
        self.magic_profile = tk.StringVar(value="basic")
        self.magic_skill = tk.StringVar(value="12")
        self.magic_distance = tk.StringVar(value="0")
        self.magic_radius = tk.StringVar(value="1")
        self.magic_fp = tk.StringVar(value="10")
        self.magic_cost_override = tk.StringVar(value="")
        self.magic_time_override = tk.StringVar(value="")
        self.magic_mana = tk.StringVar(value="normal")
        self.magic_is_mage = tk.BooleanVar(value=True)
        self.magic_visible = tk.BooleanVar(value=True)
        self.magic_size = tk.StringVar(value="0")
        self.magic_mod = tk.StringVar(value="0")
        self.magic_reserve = tk.StringVar(value="0")
        self.magic_external = tk.StringVar(value="0")
        self.magic_cycles = tk.StringVar(value="0")
        self.magic_healing_attempts = tk.StringVar(value="0")
        self.magic_physician = tk.StringVar(value="0")
        self.magic_magery = tk.StringVar(value="0")
        self.magic_target_mr = tk.StringVar(value="0")
        self.magic_waives_resistance = tk.BooleanVar(value=False)
        self.magic_use_session = tk.BooleanVar(value=False)
        self.magic_session_reserve = tk.StringVar()

        self.power_advantage = tk.StringVar()
        self.power_levels = tk.StringVar(value="1")
        self.power_psi = tk.StringVar()
        self.power_skill = tk.StringVar(value="12")
        self.power_distance = tk.StringVar(value="0")
        self.power_level = tk.StringVar(value="1")
        self.power_contact = tk.StringVar(value="skin")
        self.power_talent = tk.StringVar(value="0")
        self.power_repeats = tk.StringVar(value="0")
        self.power_repeat_cost = tk.BooleanVar(value=True)
        self.power_fp = tk.StringVar(value="10")
        self.power_reserve = tk.StringVar(value="0")
        self.power_target_willing = tk.BooleanVar(value=False)
        self.power_target_restrained = tk.BooleanVar(value=False)
        self.power_disadvantage_points = tk.StringVar(value="5")
        self.power_use_session = tk.BooleanVar(value=False)
        self.power_session_reserve = tk.StringVar()
        self._session_reserve_maps = {}
        self._session_reserve_actor = self.session_actor_key
        self._supernatural_drafts = {}
        for prefix in ("magic", "power"):
            setattr(self, prefix + "_resisted", tk.BooleanVar(value=False))
            setattr(self, prefix + "_resistance", tk.StringVar(value="10"))
            setattr(self, prefix + "_living_target", tk.BooleanVar(value=True))

        self.vehicle_selected = tk.StringVar()
        self.vehicle_duration = tk.StringVar(value="1")
        self.vehicle_environment = tk.StringVar(value="road")

        self.social_skill = tk.StringVar(value="diplomacy")
        self.social_skill_level = tk.StringVar(value="12")
        self.social_target_will = tk.StringVar(value="10")
        self.social_modifier = tk.StringVar(value="0")

        self.mass_attacker_ts = tk.StringVar(value="100")
        self.mass_defender_ts = tk.StringVar(value="100")
        self.mass_attacker_strategy = tk.StringVar(value="12")
        self.mass_defender_strategy = tk.StringVar(value="12")
        self.mass_attacker_casualties = tk.StringVar(value="0")
        self.mass_defender_casualties = tk.StringVar(value="0")
        self.mass_attacker_position = tk.StringVar(value='0')
        self.mass_defender_position = tk.StringVar(value='0')
        self.mass_encounter = tk.BooleanVar(value=False)
        self.mass_attacker_choice = tk.StringVar(value='attack')
        self.mass_defender_choice = tk.StringVar(value='defense')
        self.mass_parley_response = tk.StringVar(value='pending')
        self.mass_initiative_response={side:tk.StringVar(value='') for side in ('attacker','defender')}
        self.mass_defense_bonus = {side:tk.StringVar(value='0') for side in ('attacker','defender')}
        self.mass_context_flags={side+'_'+key:tk.BooleanVar(value=False) for side in ('attacker','defender')
                                 for key in ('confused','started_confused','mobile')}
        self.mass_context_flags['siege']=tk.BooleanVar(value=False)
        self.mass_rally_values={side+'_'+key:tk.StringVar(value='10' if key=='leadership' else '')
                               for side in ('attacker','defender') for key in ('leadership','rally_roll')}
        self.mass_raid_flags = {side: {key: tk.BooleanVar(value=False) for key in ('recon_superiority','raid_logistics','desperate')}
                               for side in ('attacker','defender')}
        self._mass_classes = {}
        self._pending_mass_round = None
        self._pending_mass_end = None
        self._sync_mass_fields()

    def _setup_theme(self):
        """Apply the selected Oficina palette to Tk's existing widget set."""
        self.colors = make_palette(self.ui_preferences['theme'], self.ui_preferences.get('theme_colors'))
        apply_theme(self.root, self.colors)

    def _create_menu(self):
        """Cria menu principal da aplicação."""
        self.menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=self.menubar)
        self._build_menu()

    def _build_menu(self):
        """Reconstroi o menu com o idioma atual."""
        self.menubar.delete(0, tk.END)
        for child in self.menubar.winfo_children():
            child.destroy()

        # Menu Arquivo
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t("menu_file"), menu=file_menu)
        file_menu.add_command(label=t("menu_exit"), command=self.root.quit)

        # Menu Idioma
        lang_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t("menu_language"), menu=lang_menu)
        lang_menu.add_command(label=t("menu_portuguese"),
                              command=lambda: self._change_language("pt_BR"))
        lang_menu.add_command(label=t("menu_english"),
                              command=lambda: self._change_language("en_US"))
        units_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=t("menu_result_units"), menu=units_menu)
        for key in ("metric", "imperial"):
            units_menu.add_radiobutton(label=t("units_" + key), variable=self.result_units, value=key,
                                      command=self._change_units)

    def _save_preferences(self):
        try:
            save_preferences(self.preferences_path, self.i18n.get_language(), self.result_units.get())
        except OSError as exc:
            messagebox.showwarning(t("common_error_title"), t("preferences_save_error", error=str(exc)))

    def _change_units(self):
        self._rebuild_ui()
        self._save_preferences()

    def _rebuild_ui(self):
        """
        Reconstrói toda a interface com o idioma atual.
        
        Chamado quando o usuário troca de idioma.
        Preserva valores das variáveis de entrada.
        """
        active = self.notebook.index(self.notebook.select()) if hasattr(self, 'notebook') else 0
        self._session_boxes = []
        self._session_reserve_boxes = {}
        self.refresh_home_session = lambda: None
        if getattr(self, "_combat_prep_window", None) is not None and self._combat_prep_window.winfo_exists():
            self._combat_prep_window.destroy()
        saved_results = capture_results(self)
        for binding in getattr(self, '_unit_bindings', []):
            binding.close()
        self._unit_bindings = []
        # Remove frame principal anterior (se existir)
        if hasattr(self, 'main_frame'):
            self.main_frame.destroy()

        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Cria todas as abas
        self._create_knockback_tab()
        self._create_slam_tab()
        self._create_falls_tab()
        self._create_collisions_tab()
        self._create_explosions_tab()
        self._create_falling_objects_tab()
        self._create_combat_tab()
        self._create_injury_tab()
        self._create_ranged_tab()
        self._create_strength_tab()
        self._create_magic_tab()
        self._create_powers_tab()
        self._create_vehicles_tab()
        self._create_social_tab()
        self._create_mass_combat_tab()
        self._create_gm_dice_tab()
        self._create_battle_map_tab()
        self._bind_unit_inputs()
        install_workspace(self, active)
        install_form_states(self, saved_results)
        self._build_menu()
        install_hub(self)
        player = getattr(self, "_battle_map_player", None)
        if player is not None and player.winfo_exists():
            self._ensure_battle_map_panel()
            self._battle_map_changed()

    def _create_battle_map_tab(self):
        self.battle_map_tab = ttk.Frame(self.notebook)
        self.battle_map_panel = None
        self.notebook.add(self.battle_map_tab, text=t("tab_battle_map"))
        self.battle_map_tab.bind("<Map>", lambda _event: self._ensure_battle_map_panel(), add="+")

    def _ensure_battle_map_panel(self):
        if self.battle_map_panel is None:
            from utils.battle_map_ui import BattleMapPanel
            self.battle_map_panel = BattleMapPanel(self.battle_map_tab, self)
            self.battle_map_panel.pack(fill=tk.BOTH, expand=True)
        return self.battle_map_panel

    def _battle_map_changed(self):
        self._refresh_ranged_map_hint()
        panel = getattr(self, "battle_map_panel", None)
        if panel is not None and self.battle_map_tab.winfo_exists():
            panel.refresh_from_session()

    def _create_gm_dice_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=t('tab_gm_dice'))
        self.gm_dice_panel = GMDicePanel(tab, self)

    def _oficina_tab(self, tab_key, title_key, subtitle_key=None):
        """Use the same responsive workspace for independent calculators."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=t(tab_key))
        layout = RangedWorkbench(tab, self.colors['bg'])
        layout.WIDE = max(720, 48 * self.ui_preferences['font_size'])
        wrap_label(ttk.Label(layout.header, text=t(title_key), style='PageTitle.TLabel')).pack(fill=tk.X)
        if subtitle_key:
            wrap_label(ttk.Label(layout.header, text=t(subtitle_key), style='Muted.TLabel')).pack(
                fill=tk.X, pady=(4, 0))
        layout.inputs.oficina = layout
        return layout

    def _oficina_result(self, layout, title_key='ui_result_title', height=10):
        panel = ttk.LabelFrame(layout.result, text=t(title_key), padding=10, style='Result.TLabelframe')
        panel.pack(fill=tk.BOTH, expand=True)
        box = tk.Text(panel, height=height, width=1, wrap=tk.WORD, padx=9, pady=8,
                      font=('Consolas', 10), bg=self.colors['panel'], fg=self.colors['panel_fg'])
        box.pack(fill=tk.BOTH, expand=True)
        box.oficina_layout = layout
        box.oficina_card = True
        box.oficina_scrollbar = ttk.Scrollbar(panel, orient=tk.VERTICAL, command=box.yview)
        box.configure(yscrollcommand=box.oficina_scrollbar.set)
        layout.bind_scrolling()
        return box

    def _bind_unit_inputs(self):
        imperial = self.result_units.get() == "imperial"
        enum_fields = {str(getattr(self, name)): getattr(self, name) for name in (
            "strength_task", "strength_profile", "magic_system", "magic_profile", "vehicle_environment")}
        self._enum_displays = []
        fields = {}
        for name in ("slam_attacker_velocity", "slam_defender_velocity", "coll_obj1_velocity",
                     "coll_obj2_velocity", "ranged_speed", "falls_distance", "exp_distance",
                     "fo_distance", "ranged_distance", "vehicle_combat_distance"):
            speed = "velocity" in name or name == "ranged_speed"
            fields[str(getattr(self, name))] = (getattr(self, name), 1 / 0.9144 if imperial else 1,
                                              ("yd/s" if speed else "yd") if imperial else ("m/s" if speed else "m"))
        for name in ("melee_distance", "magic_distance", "magic_radius", "power_distance",
                     "ranged_half_damage", "ranged_max_range", "ranged_minimum_range"):
            fields[str(getattr(self, name))] = (getattr(self, name), 1 if imperial else 0.9144, "yd" if imperial else "m")
        for name in ("vehicle_combat_speed_first", "vehicle_combat_speed_second"):
            fields[str(getattr(self, name))] = (getattr(self, name), 1 if imperial else 0.9144,
                                                "yd/s" if imperial else "m/s")
        def visit(parent):
            for child in parent.winfo_children():
                if isinstance(child, ttk.Combobox):
                    canonical = enum_fields.get(str(child.cget("textvariable")))
                    if canonical is not None:
                        choices = {t("value_" + key): key for key in child.cget("values")}
                        display = tk.StringVar(value=t("value_" + canonical.get()))
                        self._enum_displays.append(display)
                        child.configure(textvariable=display, values=tuple(choices))
                        child.bind("<<ComboboxSelected>>", lambda event, c=canonical, d=display, m=choices: c.set(m[d.get()]))
                if isinstance(child, (ttk.Entry, ttk.Spinbox)) and not isinstance(child, ttk.Combobox):
                    record = fields.get(str(child.cget("textvariable")))
                    if record:
                        variable, factor, symbol = record
                        self._unit_bindings.append(UnitBinding(child, variable, factor, symbol))
                        grid = child.grid_info()
                        label = getattr(child, 'unit_label', None)
                        labels = (label,) if label is not None else (
                            parent.grid_slaves(row=int(grid['row']), column=int(grid['column']) - 1)
                            if grid else ())
                        for label in labels:
                            if isinstance(label, ttk.Label):
                                text = re.sub(r'\s*\((?:m/s|m|yd/s|yd|yards|jardas|meters|metros)\)', '', str(label.cget('text')))
                                if getattr(child, 'unit_label', None) is label and text.endswith(':'):
                                    label.configure(text=f"{text[:-1]} ({symbol}):")
                                else:
                                    label.configure(text=f"{text} ({symbol})")
                visit(child)
        visit(self.main_frame)

    # ═════════════════════════════════════════════════════════════════
    # KNOCKBACK TAB (p. 378)
    # ═════════════════════════════════════════════════════════════════
    def _create_knockback_tab(self):
        layout = self._oficina_tab("tab_knockback", "knockback_title")
        form = ImpactForm(layout, "p. 378")
        damage = form.panel("knockback_damage_type")
        form.choices(damage, self.kb_damage_type,
                     ("knockback_crushing", "crushing"), ("knockback_cutting", "cutting"))

        target = form.panel("impact_target")
        form.spin(target, ("knockback_basic_damage", self.kb_basic_damage, 0, 10000),
                  ("knockback_target_st", self.kb_target_st, 1, 10000),
                  ("knockback_target_hp", self.kb_target_hp, 1, 10000),
                  ("knockback_dr", self.kb_target_dr, 0, 10000), columns=2)
        form.calculate("knockback_calculate", self._calculate_knockback)

        balance = form.panel("impact_resistance")
        form.spin(balance, ("knockback_skill", self.kb_effective_skill, 1, 10000),
                  ("knockback_roll_label", self.kb_roll_result, 3, 18), columns=2)
        form.check(balance, "knockback_perfect_balance", self.kb_perfect_balance)
        form.actions(balance, ("knockback_roll_button", self._roll_knockback),
                     ("knockback_check_button", self._check_knockback_roll))
        self.kb_result_text = self._oficina_result(layout, "knockback_result", height=8)

    # ═════════════════════════════════════════════════════════════════
    # SLAM TAB (p. 371)
    # ═════════════════════════════════════════════════════════════════
    def _create_slam_tab(self):
        layout = self._oficina_tab("tab_slam", "slam_title")
        form = ImpactForm(layout, "p. 371")
        combatants = form.paired()
        attacker = form.panel("slam_attacker", combatants)
        form.spin(attacker, ("slam_hp", self.slam_attacker_hp, 1, 10000),
                  ("slam_velocity", self.slam_attacker_velocity, 0, 10000),
                  ("slam_attacker_damage_bonus", self.slam_attacker_damage_bonus, -100, 100), columns=1)
        defender = form.panel("slam_defender", combatants)
        form.spin(defender, ("slam_hp", self.slam_defender_hp, 1, 10000),
                  ("slam_velocity", self.slam_defender_velocity, 0, 10000), columns=1)

        direction = form.panel("slam_collision_type")
        form.choices(direction, self.slam_collision_type,
                     ("slam_head_on", "head_on"), ("slam_rear_end", "rear_end"), ("slam_side_on", "side_on"))
        form.calculate("slam_calculate", self._calculate_slam)
        self.slam_result_text = self._oficina_result(layout, "slam_result", height=10)

    # ═════════════════════════════════════════════════════════════════
    # FALLS TAB (p. 430-431)
    # ═════════════════════════════════════════════════════════════════
    def _create_falls_tab(self):
        layout = self._oficina_tab("tab_falls", "falls_title")
        form = ImpactForm(layout, "pp. 430–431")
        impact = form.panel("impact_setup")
        form.spin(impact, ("falls_distance", self.falls_distance, 1, 10000),
                  ("falls_hp", self.falls_hp, 1, 10000), ("falls_dr", self.falls_dr, 0, 10000))

        surface = form.panel("falls_surface_type")
        form.choices(surface, self.falls_surface, ("falls_hard", "hard"), ("falls_soft", "soft"),
                     ("falls_elastic", "elastic"), ("falls_water", "water"))
        form.check(surface, "falls_acrobatics", self.falls_acrobatics)
        form.check(surface, "falls_swimming", self.falls_swimming)
        form.calculate("falls_calculate", self._calculate_falls)
        self.falls_result_text = self._oficina_result(layout, "falls_result", height=10)

    # ═════════════════════════════════════════════════════════════════
    # COLLISIONS TAB (p. 430-431)
    # ═════════════════════════════════════════════════════════════════
    def _create_collisions_tab(self):
        layout = self._oficina_tab("tab_collisions", "collisions_title")
        form = ImpactForm(layout, "pp. 430–431")
        bodies = form.paired()
        first = form.panel("collisions_object1", bodies)
        form.spin(first, ("collisions_hp", self.coll_obj1_hp, 1, 10000),
                  ("collisions_velocity", self.coll_obj1_velocity, 0, 10000), columns=1)
        second = form.panel("collisions_object2", bodies)
        form.spin(second, ("collisions_hp", self.coll_obj2_hp, 1, 10000),
                  ("collisions_velocity", self.coll_obj2_velocity, 0, 10000),
                  ("collisions_dr", self.coll_obj2_dr, 0, 10000), columns=1)

        direction = form.panel("collisions_type")
        form.choices(direction, self.coll_type, ("collisions_head_on", "head_on"),
                     ("collisions_rear_end", "rear_end"), ("collisions_side_on", "side_on"))
        obstacle = form.panel("collisions_surface")
        form.check(obstacle, "collisions_immovable", self.coll_immovable)
        form.choices(obstacle, self.coll_surface, ("collisions_surface_normal", "normal"),
                     ("collisions_surface_hard", "hard"), ("collisions_surface_elastic", "elastic"))
        form.check(obstacle, "collisions_breakable", self.coll_breakable)
        form.calculate("collisions_calculate", self._calculate_collisions)
        self.coll_result_text = self._oficina_result(layout, "collisions_result", height=10)

    # ═════════════════════════════════════════════════════════════════
    # EXPLOSIONS TAB (p. 414-415)
    # ═════════════════════════════════════════════════════════════════
    def _create_explosions_tab(self):
        layout = self._oficina_tab("tab_explosions", "explosions_title")
        form = ImpactForm(layout, "pp. 414–415")
        explosive = form.panel("impact_explosive")
        form.spin(explosive, ("explosions_basic_damage", self.exp_basic_damage, 1, 10000),
                  ("explosions_fragmentation", self.exp_fragmentation, 0, 10000), columns=2)
        target = form.panel("impact_target")
        form.spin(target, ("explosions_distance", self.exp_distance, 0, 10000),
                  ("explosions_dr", self.exp_dr, 0, 10000),
                  ("explosions_target_sm", self.exp_target_sm, -100, 100),
                  ("explosions_posture_modifier", self.exp_posture_modifier, -10, 10), columns=2)
        form.check(target, "explosions_direct_hit", self.exp_direct_hit)
        form.calculate("explosions_calculate", self._calculate_explosions)
        self.exp_result_text = self._oficina_result(layout, "explosions_result", height=10)

    # ═════════════════════════════════════════════════════════════════
    # FALLING OBJECTS TAB (p. 431)
    # ═════════════════════════════════════════════════════════════════
    def _create_falling_objects_tab(self):
        layout = self._oficina_tab("tab_falling_objects", "falling_objects_title")
        form = ImpactForm(layout, "p. 431")
        falling = form.panel("impact_object")
        form.spin(falling, ("falling_objects_distance", self.fo_distance, 1, 10000),
                  ("falling_objects_object_hp", self.fo_object_hp, 1, 10000),
                  ("falling_objects_object_sm", self.fo_object_sm, -100, 100))
        attack = form.panel("impact_attack")
        form.spin(attack, ("falling_objects_dropping_skill", self.fo_dropping_skill, 1, 100))
        form.check(attack, "falling_objects_aimed", self.fo_aimed)
        target = form.panel("impact_target")
        form.spin(target, ("falling_objects_target_hp", self.fo_target_hp, 1, 10000),
                  ("falling_objects_target_sm", self.fo_target_sm, -100, 100),
                  ("falling_objects_target_dodge", self.fo_target_dodge, 1, 100))
        form.check(target, "falling_objects_target_aware", self.fo_target_aware)
        form.calculate("falling_objects_calculate", self._calculate_falling_objects)
        self.fo_result_text = self._oficina_result(layout, "falling_objects_result", height=10)

    # ═════════════════════════════════════════════════════════════════
    # COMBAT TAB (p. 368-376)
    # ═════════════════════════════════════════════════════════════════
    def _scrollable_tab(self, label_key):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=t(label_key))
        canvas = tk.Canvas(frame, bg=self.colors["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        horizontal = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=canvas.xview)
        content = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=content, anchor=tk.NW)
        content.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=max(event.width, content.winfo_reqwidth())))
        canvas.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        horizontal.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return content

    def _session_labels(self):
        return {
            f"{position:02d} · {self.combat_session.combatants[key].name}": key
            for position, key in enumerate(self.combat_session.combatant_order, 1)
        }

    def _create_session_panel(self, parent):
        panel = ttk.LabelFrame(parent, text=t("session_title"), padding=8)
        panel.pack(fill=tk.X, padx=14, pady=5)
        panel.columnconfigure(5, weight=1)
        labels = self._session_labels()
        reverse = {value: key for key, value in labels.items()}
        self.session_actor.set(reverse.get(self.session_actor_key, next(iter(labels))))
        self.session_target.set(reverse.get(self.session_target_key, next(iter(labels))))
        ttk.Label(panel, text=t("session_actor")).grid(row=0, column=0, sticky=tk.W, padx=3)
        actor_box = ttk.Combobox(panel, textvariable=self.session_actor, values=list(labels), state="readonly", width=22)
        actor_box.grid(row=0, column=1, sticky=tk.W, padx=3)
        ttk.Label(panel, text=t("session_target")).grid(row=0, column=2, sticky=tk.W, padx=3)
        target_box = ttk.Combobox(panel, textvariable=self.session_target, values=list(labels), state="readonly", width=22)
        target_box.grid(row=1, column=1, sticky=tk.W, padx=3)
        for label in panel.grid_slaves(row=0, column=2):
            label.grid_configure(row=1, column=0)
        self._session_boxes.extend((actor_box, target_box))
        actor_box.bind("<<ComboboxSelected>>", lambda _event: self._change_session_roles(self._session_labels(), True))
        target_box.bind("<<ComboboxSelected>>", lambda _event: self._change_session_roles(self._session_labels(), False))
        ttk.Button(panel, text=t("session_advance_30"), command=lambda: self._advance_session_time(30)).grid(row=2, column=0, padx=2, pady=6)
        ttk.Button(panel, text=t("session_advance_60"), command=lambda: self._advance_session_time(60)).grid(row=2, column=1, padx=2)
        ttk.Button(panel, text=t("session_undo"), command=self._undo_session).grid(row=2, column=2, padx=2)
        from utils.gui_hub import session_window
        ttk.Button(panel, text=t("combat_prep_title"), command=lambda: session_window(self)).grid(row=2, column=3, padx=2)
        ttk.Label(panel, textvariable=self.session_summary, style="Subtitle.TLabel", wraplength=600).grid(
            row=3, column=0, columnspan=6, sticky=tk.W, padx=3, pady=(6, 0))
        self._refresh_session_summary(sync_fields=False)
        if self.combat_session.load_warning:
            ttk.Label(panel, text=t("local_data_warning", path=self.combat_session.load_warning),
                      wraplength=600).grid(row=4, column=0, columnspan=6, sticky=tk.W, padx=3)

    def _create_combat_tab(self):
        content = self._scrollable_tab("tab_combat")
        ttk.Label(content, text=t("melee_title"), style="PageTitle.TLabel").pack(anchor=tk.W, padx=14, pady=(10, 4))
        ttk.Label(content, text=t("melee_subtitle"), style="Subtitle.TLabel").pack(anchor=tk.W, padx=14, pady=(0, 6))
        self._create_session_panel(content)

        selection = ttk.LabelFrame(content, text=t("melee_section_catalog"), padding=8)
        selection.pack(fill=tk.X, padx=14, pady=5)
        selection.columnconfigure(1, weight=1)
        profile_labels = {
            t("rules_profile_basic"): "basic", t("rules_profile_realistic"): "realistic",
            t("rules_profile_cinematic"): "cinematic",
        }
        self._melee_profile_labels = profile_labels
        self.melee_profile.set({value: key for key, value in profile_labels.items()}[self.melee_profile_key])
        ttk.Label(selection, text=t("rules_profile")).grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
        profile_box = ttk.Combobox(selection, textvariable=self.melee_profile, values=list(profile_labels), state="readonly")
        profile_box.grid(row=0, column=1, sticky=tk.EW, padx=3, pady=3)
        profile_box.bind("<<ComboboxSelected>>", self._change_melee_profile)
        ttk.Label(selection, text=t("melee_search")).grid(row=1, column=0, sticky=tk.W, padx=3, pady=3)
        search = ttk.Entry(selection, textvariable=self.melee_search)
        search.grid(row=1, column=1, sticky=tk.EW, padx=3, pady=3)
        ttk.Button(selection, text=t("common_search"), command=self._filter_melee_weapons).grid(row=1, column=2, padx=3)
        ttk.Label(selection, text=t("melee_weapon")).grid(row=2, column=0, sticky=tk.W, padx=3, pady=3)
        self.melee_weapon_box = ttk.Combobox(selection, textvariable=self.melee_weapon, state="readonly")
        self.melee_weapon_box.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=3, pady=3)
        self.melee_weapon_box.bind("<<ComboboxSelected>>", self._load_selected_melee_weapon)
        preset_buttons = ttk.Frame(selection)
        preset_buttons.grid(row=2, column=3, sticky=tk.E, padx=3)
        ttk.Button(preset_buttons, text=t("common_import"), command=self._import_melee_presets).pack(side=tk.LEFT, padx=2)
        ttk.Button(preset_buttons, text=t("common_export"), command=self._export_melee_presets).pack(side=tk.LEFT, padx=2)
        ttk.Label(selection, text=t("melee_style")).grid(row=3, column=0, sticky=tk.W, padx=3, pady=3)
        self.melee_style_box = ttk.Combobox(selection, textvariable=self.melee_style, state="readonly")
        self.melee_style_box.grid(row=3, column=1, sticky=tk.EW, padx=3, pady=3)
        ttk.Label(selection, text=t("melee_technique")).grid(row=4, column=0, sticky=tk.W, padx=3, pady=3)
        self.melee_technique_box = ttk.Combobox(selection, textvariable=self.melee_technique, state="readonly")
        self.melee_technique_box.grid(row=4, column=1, sticky=tk.EW, padx=3, pady=3)
        ttk.Checkbutton(selection, text=t("melee_allow_silly"), variable=self.melee_allow_silly,
                        command=self._populate_melee_techniques).grid(row=4, column=2, sticky=tk.W, padx=3)
        self._create_source_filter(selection, 5)
        search.bind("<Return>", lambda _event: self._filter_melee_weapons())

        stats = self._extended_options(content, 'melee_stats', 'melee_section_stats')
        for column in (1, 3, 5):
            stats.columnconfigure(column, weight=1)
        self._grid_field(stats, 0, 0, "melee_weapon_name", self.melee_weapon_name)
        self._grid_field(stats, 0, 2, "melee_damage", self.melee_damage)
        self._grid_field(stats, 0, 4, "melee_damage_type", self.melee_damage_type)
        self._grid_field(stats, 1, 0, "melee_armor_divisor", self.melee_armor_divisor)
        self._grid_field(stats, 1, 2, "melee_reach", self.melee_reach)
        self._grid_field(stats, 1, 4, "melee_parry", self.melee_parry)
        self._grid_field(stats, 2, 0, "melee_min_st", self.melee_min_st)

        situation = ttk.LabelFrame(content, text=t("melee_section_situation"), padding=8)
        situation.pack(fill=tk.X, padx=14, pady=5)
        for column in (1, 3, 5):
            situation.columnconfigure(column, weight=1)
        self._grid_field(situation, 0, 0, "melee_skill", self.melee_skill)
        self._grid_field(situation, 0, 2, "melee_attacker_st", self.melee_attacker_st)
        self._grid_field(situation, 0, 4, "melee_distance", self.melee_distance)
        self._grid_field(situation, 1, 0, "melee_target_hp", self.melee_target_hp)
        self._grid_field(situation, 1, 2, "melee_target_ht", self.melee_target_ht)
        self._grid_field(situation, 1, 4, "melee_target_dr", self.melee_target_dr)

        maneuver_keys = [
            "attack", "all_out_determined", "all_out_strong", "all_out_double", "move_and_attack",
            "committed_determined", "committed_strong", "defensive_attack", "evaluate", "feint",
            "ready", "change_posture", "do_nothing", "wait",
        ]
        self._melee_maneuver_labels = {t("melee_maneuver_" + key): key for key in maneuver_keys}
        self.melee_maneuver.set({value: key for key, value in self._melee_maneuver_labels.items()}[self.melee_maneuver_key])
        ttk.Label(situation, text=t("melee_maneuver")).grid(row=2, column=0, sticky=tk.W, padx=3, pady=3)
        maneuver_box = ttk.Combobox(situation, textvariable=self.melee_maneuver,
                                    values=list(self._melee_maneuver_labels), state="readonly")
        maneuver_box.grid(row=2, column=1, sticky=tk.EW, padx=3, pady=3)
        maneuver_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "melee_maneuver_key", self._melee_maneuver_labels[self.melee_maneuver.get()]))
        locations = ["torso", "vitals", "skull", "eye", "face", "jaw", "neck", "groin", "arm", "leg",
                     "hand", "foot", "neck_artery", "limb_artery", "elbow", "knee", "shoulder", "hip", "nose", "ear", "spine"]
        self._melee_location_labels = {t("injury_location_" + key): key for key in locations}
        self.melee_location.set({value: key for key, value in self._melee_location_labels.items()}[self.melee_location_key])
        ttk.Label(situation, text=t("melee_hit_location")).grid(row=2, column=2, sticky=tk.W, padx=3, pady=3)
        location_box = ttk.Combobox(situation, textvariable=self.melee_location,
                                    values=list(self._melee_location_labels), state="readonly")
        location_box.grid(row=2, column=3, sticky=tk.EW, padx=3, pady=3)
        location_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "melee_location_key", self._melee_location_labels[self.melee_location.get()]))
        defense_labels = {t("melee_defense_dodge"): "dodge", t("melee_defense_parry"): "parry", t("melee_defense_block"): "block"}
        self._melee_defense_labels = defense_labels
        self.melee_defense.set({value: key for key, value in defense_labels.items()}[self.melee_defense_key])
        ttk.Label(situation, text=t("melee_defense")).grid(row=2, column=4, sticky=tk.W, padx=3, pady=3)
        defense_box = ttk.Combobox(situation, textvariable=self.melee_defense, values=list(defense_labels), state="readonly")
        defense_box.grid(row=2, column=5, sticky=tk.EW, padx=3, pady=3)
        defense_box.bind("<<ComboboxSelected>>", self._change_melee_defense)
        self._grid_field(situation, 3, 0, "melee_defense_score", self.melee_defense_score)
        ttk.Checkbutton(situation, text=t("melee_target_aware"), variable=self.melee_target_aware).grid(
            row=3, column=2, columnspan=2, sticky=tk.W, padx=3, pady=3)

        advanced_toggle = ttk.Checkbutton(content, text=t("melee_advanced"), variable=self.melee_advanced_visible)
        advanced_toggle.pack(anchor=tk.W, padx=18, pady=(3, 0))
        advanced = ttk.LabelFrame(content, text=t("melee_section_advanced"), padding=8)
        for column in (1, 3, 5):
            advanced.columnconfigure(column, weight=1)
        self._grid_field(advanced, 0, 0, "melee_rapid_strikes", self.melee_rapid_strikes)
        self._grid_field(advanced, 0, 2, "melee_deceptive", self.melee_deceptive)
        self._grid_field(advanced, 0, 4, "melee_custom_modifier", self.melee_custom_modifier)
        ttk.Checkbutton(advanced, text=t("melee_telegraphic"), variable=self.melee_telegraphic).grid(row=1, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(advanced, text=t("melee_trained_by_master"), variable=self.melee_trained_by_master).grid(row=1, column=2, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(advanced, text=t("melee_weapon_master"), variable=self.melee_weapon_master).grid(row=1, column=4, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(advanced, text=t("melee_dual_weapon"), variable=self.melee_dual_weapon).grid(row=2, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(advanced, text=t("melee_offhand"), variable=self.melee_offhand).grid(row=2, column=2, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(advanced, text=t("melee_ambidextrous"), variable=self.melee_ambidextrous).grid(row=2, column=4, columnspan=2, sticky=tk.W)
        retreat_labels = {t("melee_retreat_none"): "none", t("melee_retreat_standard"): "retreat"}
        self._melee_retreat_labels = retreat_labels
        self.melee_retreat.set({value: key for key, value in retreat_labels.items()}[self.melee_retreat_key])
        ttk.Label(advanced, text=t("melee_retreat")).grid(row=3, column=0, sticky=tk.W, pady=3)
        retreat_box = ttk.Combobox(advanced, textvariable=self.melee_retreat, values=list(retreat_labels), state="readonly")
        retreat_box.grid(row=3, column=1, sticky=tk.EW)
        retreat_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "melee_retreat_key", retreat_labels[self.melee_retreat.get()]))
        posture_keys = ["standing", "crouching", "kneeling", "sitting", "crawling", "prone"]
        self._melee_posture_labels = {t("melee_posture_" + key): key for key in posture_keys}
        self.melee_new_posture.set(
            {value: key for key, value in self._melee_posture_labels.items()}[self.melee_new_posture_key]
        )
        ttk.Label(advanced, text=t("melee_new_posture")).grid(row=3, column=2, sticky=tk.W, pady=3)
        posture_box = ttk.Combobox(
            advanced, textvariable=self.melee_new_posture,
            values=list(self._melee_posture_labels), state="readonly",
        )
        posture_box.grid(row=3, column=3, sticky=tk.EW)
        posture_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "melee_new_posture_key", self._melee_posture_labels[self.melee_new_posture.get()]
        ))
        def toggle_advanced():
            if self.melee_advanced_visible.get():
                advanced.pack(fill=tk.X, padx=14, pady=5, after=advanced_toggle)
            else:
                advanced.pack_forget()
        advanced_toggle.configure(command=toggle_advanced)
        if self.melee_advanced_visible.get():
            toggle_advanced()

        grappling = self._extended_options(content, 'melee_grappling', 'grapple_section')
        grappling.columnconfigure(1, weight=1)
        grapple_keys = [
            "grapple", "shift_grip", "break_free", "takedown", "pin", "choke", "strangle",
            "arm_lock", "leg_lock", "neck_lock", "throw", "wrench", "shove",
        ]
        self._grapple_action_labels = {t("grapple_action_" + key): key for key in grapple_keys}
        self.melee_grapple_action.set(
            {value: key for key, value in self._grapple_action_labels.items()}[self.melee_grapple_action_key]
        )
        ttk.Label(grappling, text=t("grapple_action")).grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
        grapple_box = ttk.Combobox(
            grappling, textvariable=self.melee_grapple_action,
            values=list(self._grapple_action_labels), state="readonly",
        )
        grapple_box.grid(row=0, column=1, sticky=tk.EW, padx=3, pady=3)
        grapple_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "melee_grapple_action_key", self._grapple_action_labels[self.melee_grapple_action.get()]
        ))
        self._grid_field(grappling, 0, 2, "grapple_resistance", self.melee_grapple_resistance)
        ttk.Checkbutton(
            grappling, text=t("grapple_two_handed"), variable=self.melee_grapple_two_handed,
        ).grid(row=0, column=4, sticky=tk.W, padx=3)
        ttk.Button(grappling, text=t("grapple_resolve"), command=self._run_grapple).grid(row=0, column=5, padx=3)
        ttk.Button(grappling, text=t("grapple_apply"), command=self._apply_grapple_result).grid(row=0, column=6, padx=3)

        buttons = self._extended_actions(content, (
            ("common_calculate", lambda: self._run_melee("calculate")),
            ("melee_roll_attack", lambda: self._run_melee("attack")),
            ("melee_resolve", lambda: self._run_melee("resolve")),
            ("session_apply", self._apply_melee_result),
            ("melee_save_preset", self._save_melee_preset),
        ))
        buttons.pack_configure(before=advanced_toggle, padx=14)
        result_frame = ttk.LabelFrame(content, text=t("melee_result"), padding=8, style='Result.TLabelframe')
        result_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 8), before=advanced_toggle)
        self.melee_result_text = tk.Text(result_frame, height=12, width=1, bg=self.colors["panel"],
                                         fg=self.colors["fg"], font=("Consolas", 10), wrap=tk.WORD)
        self.melee_result_text.oficina_card = True
        self.melee_result_text.pack(fill=tk.BOTH, expand=True)
        self.combat_result_text = self.melee_result_text
        self._filter_melee_weapons()
        self._populate_melee_styles()
        self._populate_melee_techniques()

    def _grid_field(self, parent, row, column, label_key, variable, width=13):
        ttk.Label(parent, text=t(label_key)).grid(row=row, column=column, sticky=tk.W, padx=3, pady=3)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(
            row=row, column=column + 1, sticky=tk.EW, padx=3, pady=3)
        if label_key not in {'melee_weapon_name', 'melee_damage', 'melee_damage_type', 'melee_reach', 'melee_parry', 'injury_damage_type'}:
            entry.numeric_spec = {'integer': label_key not in {'melee_armor_divisor', 'injury_armor_divisor', 'melee_distance'}, 'optional': True}
            entry.validation_label = InlineError(entry)
        return entry

    def _create_source_filter(self, parent, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, columnspan=7, sticky=tk.W, padx=3, pady=3)
        ttk.Label(frame, text=t("equipment_sources")).pack(side=tk.LEFT, padx=(0, 5))
        sources = [
            ("Basic Set", self.source_basic_set),
            ("Martial Arts", self.source_martial_arts),
            ("Low-Tech", self.source_low_tech),
            ("High-Tech", self.source_high_tech),
            ("Ultra-Tech", self.source_ultra_tech),
        ]
        for label, variable in sources:
            ttk.Checkbutton(
                frame, text=label, variable=variable, command=self._refilter_equipment,
            ).pack(side=tk.LEFT, padx=3)

    def _selected_sources(self):
        return [
            label for label, variable in (
                ("Basic Set", self.source_basic_set),
                ("Martial Arts", self.source_martial_arts),
                ("Low-Tech", self.source_low_tech),
                ("High-Tech", self.source_high_tech),
                ("Ultra-Tech", self.source_ultra_tech),
            ) if variable.get()
        ]

    def _refilter_equipment(self):
        if hasattr(self, "melee_weapon_box"):
            self._filter_melee_weapons()
        if hasattr(self, "injury_armor_box"):
            self._filter_armor()

    # ═════════════════════════════════════════════════════════════════
    # INJURY TAB (Basic Set pp. 377-424; Martial Arts pp. 136-139)
    # ═════════════════════════════════════════════════════════════════
    def _create_injury_tab(self):
        content = self._scrollable_tab("tab_injury")
        ttk.Label(content, text=t("injury_title"), style="PageTitle.TLabel").pack(anchor=tk.W, padx=14, pady=(10, 4))
        ttk.Label(content, text=t("injury_subtitle"), style="Subtitle.TLabel").pack(anchor=tk.W, padx=14, pady=(0, 6))
        self._create_session_panel(content)
        self._injury_scroll_canvas = content.master
        self._injury_handoff_banner = ttk.Frame(content.master.master, padding=(10, 4))
        self._injury_handoff_message = wrap_label(ttk.Label(self._injury_handoff_banner, width=1, wraplength=320))
        self._injury_handoff_message.pack(fill=tk.X)
        self._injury_handoff_button = ttk.Button(self._injury_handoff_banner, text=t("handoff_clear"),
                                                  command=self._clear_ranged_draft)
        self._injury_handoff_button.pack(anchor=tk.W, pady=(3, 0))
        packet = ttk.LabelFrame(content, text=t("injury_section_packet"), padding=8)
        packet.pack(fill=tk.X, padx=14, pady=5)
        for column in (1, 3, 5):
            packet.columnconfigure(column, weight=1)
        profile_labels = {
            t("rules_profile_basic"): "basic", t("rules_profile_realistic"): "realistic",
            t("rules_profile_cinematic"): "cinematic",
        }
        self._injury_profile_labels = profile_labels
        self.injury_profile.set({value: key for key, value in profile_labels.items()}[self.injury_profile_key])
        ttk.Label(packet, text=t("rules_profile")).grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
        profile_box = ttk.Combobox(packet, textvariable=self.injury_profile, values=list(profile_labels), state="readonly")
        profile_box.grid(row=0, column=1, sticky=tk.EW, padx=3, pady=3)
        profile_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "injury_profile_key", profile_labels[self.injury_profile.get()]))
        self._injury_locked_entries = [
            self._grid_field(packet, row, col, key, getattr(self, key))
            for row, col, key in (
                (0, 2, "injury_basic_damage"), (0, 4, "injury_damage_type"),
                (1, 0, "injury_armor_divisor"), (1, 2, "injury_target_hp"),
                (1, 4, "injury_target_ht"), (2, 0, "injury_natural_dr"),
            )
        ]
        locations = list(self._melee_location_labels.values()) if hasattr(self, "_melee_location_labels") else ["torso", "vitals", "skull", "eye", "face", "neck", "groin", "arm", "leg", "hand", "foot"]
        self._injury_location_labels = {t("injury_location_" + key): key for key in locations}
        self.injury_location.set({value: key for key, value in self._injury_location_labels.items()}[self.injury_location_key])
        ttk.Label(packet, text=t("injury_hit_location")).grid(row=2, column=2, sticky=tk.W, padx=3, pady=3)
        location_box = ttk.Combobox(packet, textvariable=self.injury_location,
                                    values=list(self._injury_location_labels), state="readonly")
        location_box.grid(row=2, column=3, sticky=tk.EW, padx=3, pady=3)
        location_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "injury_location_key", self._injury_location_labels[self.injury_location.get()]))
        self._injury_locked_boxes = (profile_box, location_box)
        direction_labels = {t("injury_direction_front"): "front", t("injury_direction_back"): "back", t("injury_direction_side"): "side"}
        self._injury_direction_labels = direction_labels
        self.injury_direction.set({value: key for key, value in direction_labels.items()}[self.injury_direction_key])
        ttk.Label(packet, text=t("injury_direction")).grid(row=2, column=4, sticky=tk.W, padx=3, pady=3)
        direction_box = ttk.Combobox(packet, textvariable=self.injury_direction, values=list(direction_labels), state="readonly")
        direction_box.grid(row=2, column=5, sticky=tk.EW, padx=3, pady=3)
        direction_box.bind("<<ComboboxSelected>>", lambda _event: setattr(
            self, "injury_direction_key", direction_labels[self.injury_direction.get()]))
        ttk.Checkbutton(packet, text=t("injury_chinks"), variable=self.injury_chinks).grid(row=3, column=0, columnspan=2, sticky=tk.W)
        self._injury_large_area_box = ttk.Checkbutton(packet, text=t("injury_large_area"), variable=self.injury_large_area)
        self._injury_large_area_box.grid(row=3, column=2, columnspan=2, sticky=tk.W)
        self._refresh_ranged_draft()

        armor = ttk.LabelFrame(content, text=t("injury_section_armor"), padding=8)
        armor.pack(fill=tk.X, padx=14, pady=5)
        armor.columnconfigure(1, weight=1)
        ttk.Label(armor, text=t("injury_armor_search")).grid(row=0, column=0, sticky=tk.W, padx=3)
        armor_search = ttk.Entry(armor, textvariable=self.injury_armor_search)
        armor_search.grid(row=0, column=1, sticky=tk.EW, padx=3)
        ttk.Button(armor, text=t("common_search"), command=self._filter_armor).grid(row=0, column=2, padx=3)
        ttk.Label(armor, text=t("injury_armor_item")).grid(row=1, column=0, sticky=tk.W, padx=3, pady=3)
        self.injury_armor_box = ttk.Combobox(armor, textvariable=self.injury_armor, state="readonly")
        self.injury_armor_box.grid(row=1, column=1, sticky=tk.EW, padx=3, pady=3)
        ttk.Button(armor, text=t("injury_equip_armor"), command=self._equip_selected_armor).grid(row=1, column=2, padx=3)
        ttk.Button(armor, text=t("injury_clear_armor"), command=self._clear_target_armor).grid(row=1, column=3, padx=3)
        ttk.Button(armor, text=t("common_import"), command=self._import_armor_presets).grid(row=0, column=3, padx=3)
        ttk.Button(armor, text=t("common_export"), command=self._export_selected_armor).grid(row=0, column=4, padx=3)
        self.injury_armor_summary = tk.StringVar()
        ttk.Label(armor, textvariable=self.injury_armor_summary, style="Subtitle.TLabel").grid(
            row=2, column=0, columnspan=4, sticky=tk.W, padx=3, pady=3)
        self._create_source_filter(armor, 3)
        armor_search.bind("<Return>", lambda _event: self._filter_armor())
        self._filter_armor()

        buttons = self._extended_actions(content, (
            ("common_calculate", lambda: self._run_injury("calculate")),
            ("injury_resolve_checks", lambda: self._run_injury("resolve")),
            ("session_apply", self._apply_injury_result),
        ))
        buttons.pack_configure(padx=14)
        result_frame = ttk.LabelFrame(content, text=t("injury_result"), padding=8, style='Result.TLabelframe')
        result_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(2, 8))
        self.injury_result_text = tk.Text(result_frame, height=12, width=1, bg=self.colors["panel"],
                                          fg=self.colors["fg"], font=("Consolas", 10), wrap=tk.WORD)
        self.injury_result_text.oficina_card = True
        self.injury_result_text.pack(fill=tk.BOTH, expand=True)

        optional = self._extended_options(content, 'injury_rules', 'injury_section_optional')
        option_vars = [
            ("injury_rule_bleeding", self.injury_rule_bleeding),
            ("injury_rule_severe_bleeding", self.injury_rule_severe_bleeding),
            ("injury_rule_accumulated", self.injury_rule_accumulated),
            ("injury_rule_partial", self.injury_rule_partial),
            ("injury_rule_lasting", self.injury_rule_lasting),
            ("injury_rule_gaps", self.injury_rule_gaps),
            ("injury_rule_layering", self.injury_rule_layering),
            ("injury_rule_edge", self.injury_rule_edge),
            ("injury_rule_degradation", self.injury_rule_degradation),
        ]
        for index, (key, variable) in enumerate(option_vars):
            ttk.Checkbutton(optional, text=t(key), variable=variable).grid(
                row=index // 3, column=index % 3, sticky=tk.W, padx=6, pady=2)

        self._refresh_session_summary(sync_fields=True)

    # ═════════════════════════════════════════════════════════════════
    # RANGED COMBAT TAB (Basic Set p. 364, 372-374, 548-550)
    # ═════════════════════════════════════════════════════════════════
    def _create_ranged_tab(self):
        """Oficina de tiro: entradas essenciais, ações e resultado no mesmo espaço."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=t("tab_ranged"))
        layout = self.ranged_layout = RangedWorkbench(tab, self.colors["bg"])
        wrap_label(ttk.Label(layout.header, text=t("ranged_title"), style="PageTitle.TLabel")).pack(
            fill=tk.X, pady=(0, 4))
        wrap_label(ttk.Label(layout.header, text=t("ranged_subtitle"), style="Subtitle.TLabel")).pack(fill=tk.X)
        map_note = ttk.Frame(layout.inputs)
        map_note.pack(fill=tk.X)
        self.ranged_map_hint_label = wrap_label(ttk.Label(map_note, textvariable=self.ranged_map_hint))
        self._refresh_ranged_map_hint()

        def labeled(parent, key):
            cell = ttk.Frame(parent)
            cell.columnconfigure(0, weight=1)
            label = wrap_label(ttk.Label(cell, text=t(key)))
            label.grid(row=0, column=0, sticky=tk.EW, pady=(0, 2))
            return cell, label

        def combo(parent, label_key, variable, choices=None, key_attr=None):
            cell, label = labeled(parent, label_key)
            label.grid_configure(columnspan=2)
            box = ttk.Combobox(cell, textvariable=variable, state="readonly", width=1)
            box.grid(row=1, column=0, sticky=tk.EW)
            if choices is not None:
                labels = {t(key): value for key, value in choices}
                reverse = {value: key for key, value in labels.items()}
                variable.set(reverse[getattr(self, key_attr)])
                box.configure(values=tuple(labels))
                box.bind("<<ComboboxSelected>>", lambda _event: setattr(self, key_attr, labels[variable.get()]))
            return cell, box

        selection = ttk.LabelFrame(layout.inputs, text=t("ranged_section_weapon"), padding=8)
        selection.pack(fill=tk.X, pady=(0, 8))
        profile, _profile_box = combo(selection, "ranged_profile", self.ranged_profile, (
            ("ranged_profile_basic", "basic"),
            ("ranged_profile_realistic", "realistic"),
            ("ranged_profile_cinematic", "cinematic"),
        ), "ranged_profile_key")
        profile.pack(fill=tk.X, padx=4, pady=(0, 5))

        search, search_label = labeled(selection, "ranged_search")
        search.pack(fill=tk.X, padx=4, pady=(0, 5))
        search_label.grid_configure(columnspan=2)
        search_entry = ttk.Entry(search, textvariable=self.ranged_search, width=1)
        search_entry.grid(row=1, column=0, sticky=tk.EW)
        ttk.Button(search, text=t("ranged_search_button"), command=self._filter_ranged_weapons).grid(
            row=1, column=1, padx=(6, 0))
        search_entry.bind("<Return>", lambda _event: self._filter_ranged_weapons())

        weapon, self.ranged_weapon_box = combo(selection, "ranged_weapon", self.ranged_weapon)
        weapon.pack(fill=tk.X, padx=4)
        self.ranged_weapon_box.bind("<<ComboboxSelected>>", self._load_selected_weapon)
        self._populate_ranged_weapon_box(self.weapon_catalog.search())
        if self.weapon_catalog.load_warning:
            wrap_label(ttk.Label(selection, text=t("local_data_warning", path=self.weapon_catalog.load_warning))).pack(fill=tk.X)

        def fields(parent, keys, reveal=None):
            for name in keys:
                label_key = "ranged_" + name
                variable = getattr(self, label_key)
                cell, label = labeled(parent, label_key)
                entry = ttk.Entry(cell, textvariable=variable, width=1)
                entry.grid(row=1, column=0, sticky=tk.EW)
                entry.unit_label = label
                if name not in {"weapon_name", "damage", "damage_type", "shots_stat"}:
                    entry.numeric_spec = {
                        "integer": name not in {"armor_divisor", "rof", "half_damage", "max_range",
                                                "minimum_range", "distance", "speed"},
                        "optional": True,
                    }
                    entry.validation_label = FieldError(entry, reveal)
                parent.add(cell)

        essential = FieldGrid(layout.inputs, columns=2)
        essential.pack(fill=tk.X, pady=(0, 4))
        fields(essential, ("skill", "distance", "aim_seconds", "shots_fired"))

        result_frame = ttk.LabelFrame(layout.result, padding=8)
        result_frame.pack(fill=tk.BOTH, expand=True)
        wrap_label(ttk.Label(result_frame, text=t("ranged_result"), style="Subtitle.TLabel")).pack(fill=tk.X, pady=(0, 4))
        layout.create_metrics(result_frame)
        layout.set_metrics(getattr(self, '_ranged_metrics', None))
        handoff = ttk.Frame(result_frame)
        handoff.pack(fill=tk.X, pady=(0, 5))
        self._handoff_selected = tk.StringVar()
        self._handoff_picker = ttk.Combobox(handoff, textvariable=self._handoff_selected, state="readonly", width=5)
        self._handoff_button = ttk.Button(handoff, text=t("handoff_send"), command=self._open_ranged_draft)
        flow_buttons(handoff, [ttk.Label(handoff, text=t("handoff_hit")), self._handoff_picker, self._handoff_button])
        self._refresh_handoff_choices()
        result_content = ttk.Frame(result_frame)
        result_content.pack(fill=tk.BOTH, expand=True)
        self.ranged_result_text = tk.Text(result_content, width=1, height=14, bg=self.colors["panel"],
                                          fg=self.colors["fg"], font=("Consolas", 10), wrap=tk.WORD,
                                          padx=8, pady=6, borderwidth=0)
        self.ranged_result_text.responsive_toolbar = True
        self.ranged_result_text.oficina_card = True
        result_scrollbar = ttk.Scrollbar(result_content, orient=tk.VERTICAL, command=self.ranged_result_text.yview)
        result_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ranged_result_text.configure(yscrollcommand=result_scrollbar.set)
        self.ranged_result_text.oficina_scrollbar = result_scrollbar
        self.ranged_result_text.pack(fill=tk.BOTH, expand=True)

        def run(operation):
            self._run_ranged(operation)
            if not layout.wide and self.ranged_result_text.edit_modified():
                layout.after_idle(lambda: layout.reveal(result_frame, align_top=True))

        actions = ttk.Frame(layout.inputs)
        actions.pack(fill=tk.X, pady=(0, 8))
        flow_buttons(actions, [
            ttk.Button(actions, text=t(key), command=lambda operation=operation: run(operation),
                       style="Primary.TButton" if operation == "calculate" else "TButton")
            for key, operation in (("ranged_calculate", "calculate"), ("ranged_roll_attack", "attack"),
                                   ("ranged_resolve", "resolve"))
        ])

        if not hasattr(self, "_ranged_disclosure_state"):
            self._ranged_disclosure_state = {"stats": False, "situation": False}

        def section(key, caption):
            def show(visible):
                self._ranged_disclosure_state[key] = visible
                disclosure.show(visible)

            disclosure = Disclosure(layout.inputs, t(caption), lambda: show(not disclosure.expanded))
            disclosure.pack(fill=tk.X, pady=(0, 5))
            show(self._ranged_disclosure_state[key])
            return disclosure.section, lambda: show(True) if not disclosure.expanded else None

        stats, reveal_stats = section("stats", "ranged_show_stats")
        stats_fields = FieldGrid(stats)
        stats_fields.pack(fill=tk.X)
        fields(stats_fields, (
            "weapon_name", "acc", "damage", "damage_type", "armor_divisor", "half_damage",
            "max_range", "rof", "projectiles", "shots_stat", "bulk", "rcl", "malf",
            "minimum_range", "required_st",
        ), reveal_stats)
        preset_actions = ttk.Frame(stats)
        preset_actions.pack(fill=tk.X, pady=(4, 0))
        flow_buttons(preset_actions, [
            ttk.Button(preset_actions, text=t(key), command=command) for key, command in (
                ("ranged_save_preset", self._save_ranged_preset),
                ("ranged_import", self._import_ranged_presets),
                ("ranged_export", self._export_ranged_presets),
            )
        ])

        situation, reveal_situation = section("situation", "ranged_show_situation")
        situation_fields = FieldGrid(situation)
        situation_fields.pack(fill=tk.X)
        fields(situation_fields, ("speed", "sm", "dodge", "dr", "target_hp", "shooter_st"), reveal_situation)
        maneuver, _maneuver_box = combo(situation, "ranged_maneuver", self.ranged_maneuver, (
            ("ranged_maneuver_attack", "attack"),
            ("ranged_maneuver_all_out", "all_out_determined"),
            ("ranged_maneuver_move_attack", "move_and_attack"),
            ("ranged_maneuver_pop_up", "pop_up"),
        ), "ranged_maneuver_key")
        maneuver.pack(fill=tk.X, padx=4, pady=3)
        location, _location_box = combo(situation, "ranged_hit_location", self.ranged_location, (
            ("ranged_location_" + key, key) for key in
            ("torso", "vitals", "skull", "face", "eye", "groin", "arm", "leg", "hand", "foot", "weapon")
        ), "ranged_location_key")
        location.pack(fill=tk.X, padx=4, pady=3)
        for name in ("braced", "target_aware"):
            key = "ranged_" + name
            ranged_checkbutton(situation, t(key), getattr(self, key)).pack(fill=tk.X, padx=4, pady=3)

        def show_advanced(visible):
            self.ranged_advanced_visible.set(visible)
            self._toggle_ranged_advanced()

        self._ranged_advanced_disclosure = Disclosure(
            layout.inputs, t("ranged_advanced"), lambda: show_advanced(not self.ranged_advanced_visible.get()))
        self._ranged_advanced_disclosure.pack(fill=tk.X, pady=(0, 5))
        self.ranged_advanced_frame = self._ranged_advanced_disclosure.section
        advanced = FieldGrid(self.ranged_advanced_frame)
        advanced.pack(fill=tk.X)
        fields(advanced, (
            "scope", "laser", "targeting", "cover", "visibility", "posture", "custom_modifier",
            "rangefinder", "precision_aiming", "follow_up_aim", "fast_firing", "cinematic_modifier",
        ), lambda: show_advanced(True) if not self.ranged_advanced_visible.get() else None)
        ammunition, _ammunition_box = combo(
            self.ranged_advanced_frame, "ranged_ammunition", self.ranged_ammunition, (
                ("ranged_ammunition_standard", "standard"),
                ("ranged_ammunition_match", "match"),
                ("ranged_ammunition_hollow_point", "hollow_point"),
                ("ranged_ammunition_aphc", "aphc"),
                ("ranged_ammunition_apds", "apds"),
            ), "ranged_ammunition_key",
        )
        ammunition.pack(fill=tk.X, padx=4, pady=3)
        for name in ("cannot_see", "offhand", "minute_of_angle", "aim_lost"):
            key = "ranged_" + name
            ranged_checkbutton(self.ranged_advanced_frame, t(key), getattr(self, key)).pack(fill=tk.X, padx=4, pady=3)
        self._toggle_ranged_advanced()
        layout.bind_scrolling()

    def _toggle_ranged_advanced(self):
        self._ranged_advanced_disclosure.show(self.ranged_advanced_visible.get())

    def _populate_ranged_weapon_box(self, records):
        self._ranged_weapon_map = {
            "{} — {} p.{} [{}]".format(record.name, record.source, record.page, record.identifier): record.identifier
            for record in records
        }
        values = list(self._ranged_weapon_map)
        self.ranged_weapon_box.configure(values=values)
        if values and self.ranged_weapon.get() not in values:
            self.ranged_weapon.set(values[0])
            self._load_selected_weapon()

    def _filter_ranged_weapons(self):
        self._populate_ranged_weapon_box(self.weapon_catalog.search(self.ranged_search.get()))

    def _load_selected_weapon(self, _event=None):
        identifier = getattr(self, "_ranged_weapon_map", {}).get(self.ranged_weapon.get())
        weapon = self.weapon_catalog.get(identifier) if identifier else None
        if not weapon:
            return
        self._ranged_base_weapon = weapon
        mode = weapon.damage_modes[0]
        self.ranged_weapon_name.set(weapon.name)
        self.ranged_acc.set(str(weapon.accuracy))
        self.ranged_damage.set(mode.dice)
        self.ranged_damage_type.set(mode.damage_type)
        self.ranged_armor_divisor.set(str(mode.armor_divisor))
        self.ranged_half_damage.set("" if mode.half_damage_range is None else str(mode.half_damage_range))
        self.ranged_max_range.set("" if mode.max_range is None else str(mode.max_range))
        self.ranged_rof.set(str(max(weapon.rate_of_fire_modes or [1])).rstrip("0").rstrip("."))
        self.ranged_projectiles.set(str(weapon.projectiles_per_shot))
        self.ranged_shots_stat.set(weapon.shots_raw)
        self.ranged_bulk.set("" if weapon.bulk is None else str(weapon.bulk))
        self.ranged_rcl.set(str(weapon.recoil))
        self.ranged_malf.set(str(weapon.malfunction))
        self.ranged_minimum_range.set(str(mode.minimum_range))
        self.ranged_required_st.set("" if weapon.strength is None else str(weapon.strength))

    def _extended_form(self, tab_key, title_key):
        layout = self._oficina_tab(tab_key, title_key)
        content = layout.inputs
        form = ttk.LabelFrame(content, text=t("extended_inputs"), padding=8)
        form.pack(fill=tk.X, pady=(0, 6))
        form.columnconfigure(1, weight=1)
        return content, form

    def _extended_options(self, content, key, title_key):
        state = getattr(self, '_oficina_options', None)
        if state is None:
            state = self._oficina_options = {}

        def show(visible):
            state[key] = visible
            disclosure.show(visible)

        disclosure = Disclosure(content, t(title_key), lambda: show(not disclosure.expanded))
        disclosure.pack(fill=tk.X, pady=(3, 6))
        disclosure.section.oficina_reveal = lambda: show(True) if not disclosure.expanded else None
        show(state.get(key, False))
        return disclosure.section

    @staticmethod
    def _extended_actions(parent, commands, *, primary=True):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(3, 6))
        flow_buttons(row, [ttk.Button(row, text=t(key), command=command,
                                      style='Primary.TButton' if primary and index == 0 else 'TButton')
                           for index, (key, command) in enumerate(commands)])
        return row

    @staticmethod
    def _form_entry(form, row, label, variable):
        ttk.Label(form, text=label).grid(row=row, column=0, sticky=tk.W, padx=4, pady=3)
        entry = ttk.Entry(form, textvariable=variable)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=4, pady=3)
        if not hasattr(variable, '_numeric_spec'):
            if label in (t('magic_cost_override'), t('magic_time_override')):
                variable._numeric_spec = {'integer': True, 'optional': True}
            try:
                raw = str(variable.get())
                float(raw)
                variable._numeric_spec = {'integer': '.' not in raw, 'optional': False}
            except (ValueError, tk.TclError):
                pass
        if hasattr(variable, '_numeric_spec'):
            entry.numeric_spec = variable._numeric_spec
            entry.validation_label = ttk.Label(form, text='', style='Error.TLabel', wraplength=180)
            entry.validation_label.grid(row=row, column=2, sticky=tk.W, padx=4)
        return entry

    def _extended_result(self, content):
        def adapt(parent):
            for widget in parent.winfo_children():
                grid = widget.grid_info()
                if grid:
                    if isinstance(widget, ttk.Label):
                        widget.configure(wraplength=245 if int(grid.get('columnspan', 1)) > 1 else 145)
                        widget.grid_configure(sticky='ew')
                        wrap_label(widget)
                    elif isinstance(widget, (ttk.Entry, ttk.Combobox)):
                        widget.configure(width=8)
                    elif isinstance(widget, ttk.Checkbutton):
                        widget.grid_configure(sticky='ew')
                        wrap_toggle(widget)
                adapt(widget)
        adapt(content)
        return self._oficina_result(content.oficina)

    @staticmethod
    def _format_roll(roll):
        if not roll:
            return "-"
        if not isinstance(roll, dict):
            return str(roll)
        return t("summary_roll_details", success=t("common_yes") if roll.get("success") else t("common_no"),
                 margin=roll.get("margin", "-"),
                 critical=t("common_yes") if roll.get("critical_success") or roll.get("critical_failure") else t("common_no"))

    @staticmethod
    def _format_errors(errors):
        rendered = []
        for code in dict.fromkeys(errors):
            key = "engine_error_" + code
            rendered.append(t(key) if t(key) != key else t("engine_diagnostic", code=code))
        return "; ".join(rendered) or "-"

    @staticmethod
    def _show_result(box, lines, *, highlights=()):
        box.oficina_highlights = highlights
        box.delete("1.0", tk.END)
        labels = {name: "summary_" + name.lower().replace(" ", "_") for name in (
            "Valid", "Skill", "Energy", "Time", "Roll", "Errors", "Error", "Base cost",
            "Modifier", "Final cost", "Speed", "Distance", "Fuel", "Delta-V", "Total",
            "Reaction", "Success", "Margin", "Outcome", "Casualties")}
        rendered = []
        for line in lines:
            label, separator, value = str(line).partition(": ")
            if label in labels:
                if value in {"True", "False"}:
                    value = t("common_yes" if value == "True" else "common_no")
                enum_key = "value_" + value
                if t(enum_key) != enum_key:
                    value = t(enum_key)
                line = t(labels[label]) + ": " + value
            rendered.append(str(line))
        box.insert(tk.END, "\n".join(rendered))

    def _create_strength_tab(self):
        content, form = self._extended_form("tab_strength", "strength_title")
        self._form_entry(form, 0, t("strength_st"), self.strength_st)
        self._form_entry(form, 1, t("strength_lifting_st"), self.strength_lifting)
        self._form_entry(form, 2, t("strength_striking_st"), self.strength_striking)
        self._form_entry(form, 3, t("strength_super_effort"), self.strength_super)
        ttk.Label(form, text=t("rules_profile")).grid(row=4, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(form, textvariable=self.strength_profile,
                     values=("basic", "realistic", "cinematic"), state="readonly").grid(row=4, column=1, sticky=tk.EW, padx=4)
        ttk.Label(form, text=t("strength_task")).grid(row=5, column=0, sticky=tk.W, padx=4, pady=3)
        ttk.Combobox(form, textvariable=self.strength_task,
                     values=tuple(StrengthEngine.TASK_MULTIPLIERS) + ("striking", "throwing", "knockback_resistance", "grappling", "choke", "collision"),
                     state="readonly").grid(row=5, column=1, sticky=tk.EW, padx=4)
        self._extended_actions(content, (("common_calculate", self._run_strength),
                                         ("common_resolve", lambda: self._run_strength(True))))
        form = self._extended_options(content, 'strength_extra', 'ui_more_options')
        form.columnconfigure(1, weight=1)
        ttk.Checkbutton(form, text=t("strength_all_out_strong"), variable=self.strength_all_out).grid(row=6, column=0, sticky=tk.W, padx=4)
        ttk.Checkbutton(form, text=t("strength_mighty_blows"), variable=self.strength_mighty).grid(row=6, column=1, sticky=tk.W, padx=4)
        ttk.Label(form, text=t("strength_scope")).grid(row=7, column=0, sticky=tk.W, padx=4)
        self._strength_scope_map = {t("strength_scope_" + key): key for key in ("lifting", "striking", "total")}
        self.strength_scope_display = tk.StringVar(value=next(label for label, key in self._strength_scope_map.items() if key == self.strength_scope.get()))
        scope_box = ttk.Combobox(form, textvariable=self.strength_scope_display,
                                values=tuple(self._strength_scope_map), state="readonly")
        scope_box.grid(row=7, column=1, sticky=tk.EW, padx=4)
        scope_box.bind("<<ComboboxSelected>>", lambda event: self.strength_scope.set(self._strength_scope_map[self.strength_scope_display.get()]))
        for row, key, variable in (
            (8, "strength_fp", self.strength_fp), (9, "strength_max_fp", self.strength_max_fp),
            (10, "strength_will", self.strength_will), (11, "strength_extra", self.strength_extra),
            (12, "strength_lifting_skill", self.strength_lifting_skill),
            (13, "strength_duration", self.strength_duration),
        ):
            self._form_entry(form, row, t(key), variable)
        ttk.Checkbutton(form, text=t("strength_continuous"), variable=self.strength_continuous).grid(row=14, column=0, sticky=tk.W)
        ttk.Checkbutton(form, text=t("strength_carry"), variable=self.strength_carry).grid(row=14, column=1, sticky=tk.W)
        advanced = self._extended_options(content, 'strength_skills', 'ui_strength_skills')
        advanced.columnconfigure(1, weight=1)
        ttk.Checkbutton(advanced, text=t('ui_trained_lifting'), variable=self.strength_trained_lift).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self._form_entry(advanced, 1, t('ui_lifting_ht'), self.strength_lifting_ht)
        ttk.Checkbutton(advanced, text='Power Blow (Basic Set p. 215)', variable=self.strength_power_blow).grid(row=2, column=0, columnspan=2, sticky=tk.W)
        self._form_entry(advanced, 3, t('ui_power_blow_skill'), self.strength_power_blow_skill)
        self._form_entry(advanced, 4, t('ui_power_blow_time'), self.strength_power_blow_time)
        ttk.Checkbutton(advanced, text=t('ui_master_prerequisite'), variable=self.strength_master).grid(row=5, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(advanced, text=t('ui_power_blow_triple'), variable=self.strength_triple).grid(row=6, column=0, columnspan=2, sticky=tk.W)
        self.strength_result_text = self._extended_result(content)

    def _localized_choices(self, form, row, label, canonical, labels):
        ttk.Label(form, text=t(label), wraplength=190).grid(row=row, column=0, sticky=tk.W, padx=4, pady=3)
        display = tk.StringVar(value=next((name for name, key in labels.items() if key == canonical.get()), ""))
        # Keep a reference for the lifetime of this widget and retain the canonical ID on rebuild.
        box = ttk.Combobox(form, textvariable=display, values=list(labels), state="readonly", width=12)
        box.display_var = display
        box.canonical_var = canonical
        box.grid(row=row, column=1, sticky=tk.EW, padx=4, pady=3)
        box.bind("<<ComboboxSelected>>", lambda _event: canonical.set(labels[display.get()]))
        return box

    def _catalog_input(self, form, row, label, variable, collection):
        old_map = getattr(self, "_magic_map" if collection == "spells" else "_psi_map", {})
        previous = old_map.get(variable.get())
        records = sorted(self.extended_catalog.records(collection), key=lambda item: (
            ("calculable", "requires_parameters", "reference_only").index(catalog_status(item)), item.name.casefold()))
        mapping = {
            f"{item.name} · {t('catalog_status_' + catalog_status(item))} — {item.source} p.{item.page}": item
            for item in records
        }
        selected = next((key for key, item in mapping.items() if previous and item.identifier == previous.identifier),
                        next(iter(mapping), ""))
        variable.set(selected)
        ttk.Label(form, text=t(label), wraplength=190).grid(row=row, column=0, sticky=tk.W, padx=4)
        box = ttk.Combobox(form, textvariable=variable, values=list(mapping), state="readonly", width=12)
        box.grid(row=row, column=1, sticky=tk.EW, padx=4, pady=3)
        search = tk.StringVar()
        ttk.Label(form, text=t("ui_catalog")).grid(row=row + 1, column=0, sticky=tk.W, padx=4)
        entry = ttk.Entry(form, textvariable=search, width=12)
        entry.grid(row=row + 1, column=1, sticky=tk.EW, padx=4, pady=3)
        def filter_list(_event):
            words = search.get().casefold().split()
            box["values"] = tuple(key for key in mapping if all(word in key.casefold() for word in words))
        entry.bind("<KeyRelease>", filter_list)
        return mapping, box

    def _session_resource_controls(self, content, prefix):
        from utils.gui_hub import session_window
        frame = ttk.Frame(content)
        frame.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(frame, text=t("supernatural_session_fp"),
                        variable=getattr(self, prefix + "_use_session")).pack(anchor=tk.W)
        ttk.Label(frame, text=t("encounter_session_reserve"), wraplength=350).pack(anchor=tk.W, pady=(4, 1))
        reserve = ttk.Combobox(frame, textvariable=getattr(self, prefix + "_session_reserve"),
                               state="readonly", width=12)
        reserve.pack(fill=tk.X)
        self._session_reserve_boxes[prefix] = reserve
        self._refresh_session_reserves()
        ttk.Button(frame, text=t("combat_prep_title"), command=lambda: session_window(self)).pack(anchor=tk.W, pady=3)
        ttk.Label(frame, textvariable=self.session_summary, wraplength=390).pack(fill=tk.X)

    def _create_magic_tab(self):
        content, form = self._extended_form("tab_magic", "magic_title")
        self._magic_map, spell_box = self._catalog_input(form, 0, "magic_spell", self.magic_spell, "spells")
        self._localized_choices(form, 2, "magic_system", self.magic_system, {
            f"{t('value_' + key)} · {t('catalog_status_calculable' if key in IMPLEMENTED_MAGIC_SYSTEMS else 'catalog_status_reference_only')}": key
            for key in sorted(MAGIC_SYSTEMS, key=lambda key: (key not in IMPLEMENTED_MAGIC_SYSTEMS, key))
        })
        self._localized_choices(form, 3, "rules_profile", self.magic_profile,
                                {t("rules_profile_" + key): key for key in ("basic", "realistic", "cinematic")})
        self._form_entry(form, 4, t("magic_skill"), self.magic_skill)
        self._form_entry(form, 5, t("magic_edge_distance"), self.magic_distance)
        self._form_entry(form, 6, t("magic_radius"), self.magic_radius)
        self._form_entry(form, 7, t("magic_fp"), self.magic_fp)
        self._extended_actions(content, (("common_calculate", lambda: self._run_magic(False)),
                                         ("common_resolve", lambda: self._run_magic(True)),
                                         ("magic_renew", lambda: self._run_magic(True, maintain=True))))
        self._extended_actions(content, (('ui_casting_assistant', lambda: CastingAssistant(self)),
                                         ('ui_ceremony_title', lambda: CeremonialEditor(self)),
                                         ("session_apply", lambda: self._apply_supernatural("magic"))), primary=False)
        options = self._extended_options(content, 'magic_extra', 'ui_more_options')
        costs = ttk.Frame(options)
        costs.pack(fill=tk.X)
        for col in (0, 1):
            costs.columnconfigure(col, weight=1, uniform="casting")
        self._form_entry(costs, 0, t("magic_cost_override"), self.magic_cost_override)
        self._form_entry(costs, 1, t("magic_time_override"), self.magic_time_override)
        self._localized_choices(costs, 2, "magic_mana", self.magic_mana,
                                {t("magic_mana_" + key): key for key in ("no_mana", "low", "normal", "high", "very_high")})
        ttk.Checkbutton(costs, text=t("magic_is_mage"), variable=self.magic_is_mage).grid(row=3, column=0, sticky=tk.W)
        ttk.Checkbutton(costs, text=t("magic_target_visible"), variable=self.magic_visible).grid(row=3, column=1, sticky=tk.W)
        for row, (key, var) in enumerate((
            ("magic_target_sm", self.magic_size), ("magic_custom_mod", self.magic_mod),
            ("supernatural_reserve", self.magic_reserve), ("magic_external", self.magic_external),
            ("magic_cycles", self.magic_cycles), ("magic_healing_attempts", self.magic_healing_attempts),
            ("magic_physician", self.magic_physician), ("magic_magery", self.magic_magery),
            ("magic_target_mr", self.magic_target_mr),
        ), 4):
            self._form_entry(costs, row, t(key), var)
        ttk.Checkbutton(options, text=t("magic_waives_resistance"), variable=self.magic_waives_resistance).pack(anchor=tk.W)
        self._session_resource_controls(options, "magic")
        self._resistance_controls(options, "magic")
        def spell_changed(_event):
            self.magic_cost_override.set("")
            self.magic_time_override.set("")
            self.magic_resisted.set(self._magic_map[self.magic_spell.get()].requires_resistance)
            self._refresh_resistance_label("magic")
        spell_box.bind("<<ComboboxSelected>>", spell_changed)
        self._refresh_resistance_label("magic")
        self.magic_result_text = self._extended_result(content)

    def _create_powers_tab(self):
        content, form = self._extended_form("tab_powers", "powers_title")
        self._advantage_map = {f"{item.name} — {item.source} p.{item.page}": item for item in self.extended_catalog.records("advantages")}
        if not self.power_advantage.get(): self.power_advantage.set(next(iter(self._advantage_map)))
        ttk.Label(form, text=t("powers_advantage")).grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Combobox(form, textvariable=self.power_advantage, values=list(self._advantage_map), state="readonly").grid(row=0, column=1, sticky=tk.EW, padx=4)
        self._form_entry(form, 1, t("powers_levels"), self.power_levels)
        self._extended_actions(content, (('powers_build', self._run_ability),
                                         ('ui_ability_editor', lambda: AbilityEditor(self))))
        form = ttk.LabelFrame(content, text=t('ui_psi_panel'), padding=8)
        form.pack(fill=tk.X, pady=(6, 0))
        form.columnconfigure(1, weight=1)
        self._psi_map, psi_box = self._catalog_input(form, 0, "powers_psi_ability", self.power_psi, "psi_abilities")
        self._form_entry(form, 2, t("powers_skill"), self.power_skill)
        self._form_entry(form, 3, t("common_distance"), self.power_distance)
        self._form_entry(form, 4, t("psi_level"), self.power_level)
        self._localized_choices(form, 5, "psi_contact", self.power_contact,
                                {t("psi_contact_" + key): key for key in ("none", "touch", "skin")})
        self._extended_actions(content, (("common_calculate", lambda: self._run_psi(False)),
                                         ("common_resolve", self._run_psi),
                                         ("session_apply", lambda: self._apply_supernatural("power"))))
        options = self._extended_options(content, 'psi_resistance', 'ui_more_options')
        powers = ttk.Frame(options)
        powers.pack(fill=tk.X)
        for col in (0, 1):
            powers.columnconfigure(col, weight=1, uniform="psi")
        for row, (key, var) in enumerate((
            ("psi_talent", self.power_talent), ("psi_repeats", self.power_repeats),
            ("magic_fp", self.power_fp), ("supernatural_reserve", self.power_reserve),
        )):
            self._form_entry(powers, row, t(key), var)
        ttk.Checkbutton(options, text=t("psi_repeat_cost"), variable=self.power_repeat_cost).pack(anchor=tk.W)
        surgery = ttk.LabelFrame(options, text="Mental Surgery", padding=6)
        surgery.pack(fill=tk.X, pady=3)
        surgery.columnconfigure(1, weight=1)
        ttk.Checkbutton(surgery, text=t("psi_target_willing"), variable=self.power_target_willing).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(surgery, text=t("psi_target_restrained"), variable=self.power_target_restrained).grid(row=1, column=0, sticky=tk.W)
        self._form_entry(surgery, 2, t("psi_disadvantage_points"), self.power_disadvantage_points)
        self._session_resource_controls(options, "power")
        self._resistance_controls(options, "power")
        def psi_changed(_event=None):
            self._refresh_resistance_label("power")
            if self._psi_map[self.power_psi.get()].operational_model == "mental_surgery":
                surgery.pack(fill=tk.X, pady=3, before=options.winfo_children()[-1])
            else:
                surgery.pack_forget()
        psi_box.bind("<<ComboboxSelected>>", psi_changed)
        psi_changed()
        self.powers_result_text = self._extended_result(content)

    def _resistance_controls(self, content, prefix):
        frame = ttk.LabelFrame(content, text=t("ui_resistance_title"), padding=10)
        frame.pack(fill=tk.X, pady=5)
        for col in (0, 1):
            frame.columnconfigure(col, weight=1, uniform="resistance")
        ttk.Checkbutton(frame, text=t("ui_resistance_enabled"),
                        variable=getattr(self, prefix + "_resisted")).grid(row=0, column=0, columnspan=2, sticky=tk.EW)
        self._form_entry(frame, 1, t("ui_resistance_target"), getattr(self, prefix + "_resistance"))
        ttk.Checkbutton(frame, text=t("psi_living_sapient" if prefix == "power" else "ui_resistance_living"),
                        variable=getattr(self, prefix + "_living_target")).grid(row=2, column=0, columnspan=2, sticky=tk.W)
        label = ttk.Label(frame, wraplength=390)
        label.grid(row=3, column=0, columnspan=2, sticky=tk.W)
        setattr(self, "_" + prefix + "_resistance_label", label)

    def _refresh_resistance_label(self, prefix):
        if prefix == "magic":
            record = self._magic_map[self.magic_spell.get()]
            notation = record.resistance_notation
        else:
            record = self._psi_map[self.power_psi.get()]
            notation = record.resist_attribute.upper() if record.resist_attribute else ""
        label = getattr(self, "_" + prefix + "_resistance_label")
        label.configure(text=t("supernatural_resist_as", attribute=notation) if notation else "")

    def _resistance_input(self, prefix, required=False):
        if not required and not getattr(self, prefix + "_resisted").get():
            return None
        return ResistanceCheck(target=int(getattr(self, prefix + "_resistance").get()),
                               living_or_sapient=getattr(self, prefix + "_living_target").get())

    def _resistance_lines(self, result):
        lines = [f"{item['source']} p.{item['page']}: {t('ui_rule_of_16')} {item['value']:+}"
                 for item in result.breakdown if item['key'] == 'rule_of_16']
        check = result.resistance
        if check is not None and check.resisted is not None:
            lines.append(t("ui_resistance_result", attack=check.caster_margin,
                           defense=check.defender_margin,
                           resisted=t("common_yes") if check.resisted else t("common_no")))
        return lines

    def _create_vehicles_tab(self):
        content, form = self._extended_form("tab_vehicles", "vehicles_title")
        # Give both columns a usable width when the optional combat panel is
        # expanded. Otherwise a wide dropdown can collapse the movement labels.
        for col in (0, 1):
            form.columnconfigure(col, weight=1, uniform="vehicle_movement")
        self.vehicle_movement_form = form
        if getattr(self.vehicle_session, 'recovered_file', None):
            ttk.Label(content, text=t('ui_session_recovered', path=str(self.vehicle_session.recovered_file)),
                      wraplength=700).pack(fill=tk.X, padx=14)
        self._vehicle_map = {f"{item.name} — {item.source} p.{item.page}": item for item in self.vehicle_catalog.vehicles}
        if not self.vehicle_selected.get(): self.vehicle_selected.set(next(iter(self._vehicle_map)))
        ttk.Label(form, text=t("vehicles_vehicle")).grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Combobox(form, textvariable=self.vehicle_selected, values=list(self._vehicle_map), state="readonly").grid(row=0, column=1, sticky=tk.EW, padx=4)
        self._form_entry(form, 1, t("vehicles_duration"), self.vehicle_duration)
        ttk.Label(form, text=t("vehicles_environment")).grid(row=2, column=0, sticky=tk.W, padx=4)
        ttk.Combobox(form, textvariable=self.vehicle_environment,
                     values=tuple(VehicleEngine.TERRAIN_MULTIPLIERS), state="readonly").grid(row=2, column=1, sticky=tk.EW, padx=4)
        self._extended_actions(content, (("common_calculate", self._run_vehicle),
                                         ('ui_vehicle_editor', lambda: VehicleEditor(self))))
        self._extended_actions(content, (('ui_vehicle_apply', self._apply_vehicle_movement),
                                         ('ui_vehicle_undo', self._undo_vehicle_movement)), primary=False)
        self.vehicle_combat_panel = VehicleCombatPanel(self, content)
        self.vehicles_result_text = self._extended_result(content)

    def _create_social_tab(self):
        content, form = self._extended_form("tab_social", "social_title")
        ttk.Button(content, text=t('ui_campaign_editor'), command=lambda: CampaignEditor(self)).pack(anchor=tk.W, padx=14, pady=5)
        self._localized_choices(form, 0, "social_skill", self.social_skill,
                                {t("social_skill_" + key): key for key in INFLUENCE_SKILLS})
        self._form_entry(form, 1, t("social_skill_level"), self.social_skill_level)
        self._form_entry(form, 2, t("social_target_will"), self.social_target_will)
        self._form_entry(form, 3, t("social_modifier"), self.social_modifier)
        self._extended_actions(content, (("social_reaction", self._run_reaction),
                                         ("social_influence", self._run_influence)))
        self.social_result_text = self._extended_result(content)

    def _create_mass_combat_tab(self):
        content, form = self._extended_form("tab_mass_combat", "mass_title")
        ttk.Button(content, text=t('ui_campaign_editor'), command=lambda: CampaignEditor(self)).pack(anchor=tk.W, padx=14, pady=5)
        self._form_entry(form, 0, t("mass_attacker_ts"), self.mass_attacker_ts)
        self._form_entry(form, 1, t("mass_defender_ts"), self.mass_defender_ts)
        self._form_entry(form, 2, t("mass_attacker_strategy"), self.mass_attacker_strategy)
        self._form_entry(form, 3, t("mass_defender_strategy"), self.mass_defender_strategy)
        self._form_entry(form, 4, t('mass_prior_attacker_losses'), self.mass_attacker_casualties)
        self._form_entry(form, 5, t('mass_prior_defender_losses'), self.mass_defender_casualties)
        self._form_entry(form, 6, t('mass_attacker_pb'), self.mass_attacker_position)
        self._form_entry(form, 7, t('mass_defender_pb'), self.mass_defender_position)
        ttk.Checkbutton(form, text=t('mass_encounter'), variable=self.mass_encounter).grid(row=8, column=0, columnspan=2, sticky=tk.W)
        ttk.Button(form, text=t('mass_classes_title'), command=lambda: BattleClassEditor(self)).grid(row=9, column=0, columnspan=2, pady=5)
        self._mass_choice_displays = []
        for row, side in enumerate(('attacker', 'defender'), 11):
            canonical = getattr(self, 'mass_' + side + '_choice')
            labels = {t('mass_choice_' + key): key for key in self.mass_combat_calc.STRATEGY_MODIFIERS}
            display = tk.StringVar(value=t('mass_choice_' + canonical.get()))
            self._mass_choice_displays.append(display)
            ttk.Label(form, text=t('mass_choice_' + side)).grid(row=row, column=0, sticky=tk.W)
            box = ttk.Combobox(form, textvariable=display, values=tuple(labels), state='readonly', width=28)
            box.grid(row=row, column=1, sticky=tk.EW, pady=3)
            box.bind('<<ComboboxSelected>>', lambda event, c=canonical, d=display, m=labels: c.set(m[d.get()]))
        self._extended_actions(content, (("common_calculate", lambda: self._run_mass_combat(False)),
                                         ("common_resolve", self._run_mass_combat)))
        self._extended_actions(content, (('mass_apply_round', self._apply_mass_round),
                                         ('ui_campaign_undo', self._undo_mass_campaign)), primary=False)
        form = self._extended_options(content, 'mass_context', 'ui_battle_strategy_panel')
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text=t('mass_choices_help'), wraplength=480).grid(row=13, column=0, columnspan=2, sticky=tk.W, pady=6)
        for row,(side,key) in enumerate(((s,k) for s in ('attacker','defender') for k in ('recon_superiority','raid_logistics','desperate')),14):
            ttk.Checkbutton(form,text=t('mass_'+side+'_'+key),variable=self.mass_raid_flags[side][key]).grid(row=row,column=0,columnspan=2,sticky=tk.W)
        parley_labels={t('mass_parley_'+key):key for key in ('pending','accept','refuse')}
        self.mass_parley_display=tk.StringVar(value=t('mass_parley_'+self.mass_parley_response.get()))
        ttk.Label(form,text=t('mass_parley_response')).grid(row=20,column=0,sticky=tk.W)
        parley_box=ttk.Combobox(form,textvariable=self.mass_parley_display,values=tuple(parley_labels),state='readonly')
        parley_box.grid(row=20,column=1,sticky=tk.EW)
        parley_box.bind('<<ComboboxSelected>>',lambda event:self.mass_parley_response.set(parley_labels[self.mass_parley_display.get()]))
        for row,side in enumerate(('attacker','defender'),21):
            self._form_entry(form,row,t('mass_'+side+'_db'),self.mass_defense_bonus[side])
        for row,(key,var) in enumerate(self.mass_context_flags.items(),23):
            ttk.Checkbutton(form,text=t('mass_context_'+key),variable=var).grid(row=row,column=0,columnspan=2,sticky=tk.W)
        for row,(key,var) in enumerate(self.mass_rally_values.items(),30):
            self._form_entry(form,row,t('mass_'+key),var)
        self.mass_initiative_displays=[]
        for row,side in enumerate(('attacker','defender'),34):
            canonical=self.mass_initiative_response[side]
            choices={t('mass_initiative_keep'):''}
            choices.update({t('mass_choice_'+key):key for key in self.mass_combat_calc.STRATEGY_MODIFIERS})
            display=tk.StringVar(value=t('mass_choice_'+canonical.get()) if canonical.get() else t('mass_initiative_keep'))
            self.mass_initiative_displays.append(display)
            ttk.Label(form,text=t('mass_initiative_'+side)).grid(row=row,column=0,sticky=tk.W)
            box=ttk.Combobox(form,textvariable=display,values=tuple(choices),state='readonly')
            box.grid(row=row,column=1,sticky=tk.EW)
            box.bind('<<ComboboxSelected>>',lambda event,c=canonical,d=display,m=choices:c.set(m[d.get()]))
        ttk.Button(form, text=t('mass_update_context'), command=self._update_mass_context).grid(
            row=36, column=0, columnspan=2, sticky=tk.W, pady=3)
        campaign = self._extended_options(content, 'mass_logistics', 'ui_battle_campaign_panel')
        for commands in (
            (('mass_aftermath_title', self._open_mass_aftermath), ('mass_finish_battle', self._finish_mass_battle)),
            tuple(('log_ui_' + side, lambda s=side: LogisticsEditor(self, s)) for side in ('attacker', 'defender')),
            tuple(('replacement_' + side, lambda s=side: self._open_replacements(s)) for side in ('attacker', 'defender')),
        ):
            self._extended_actions(campaign, commands, primary=False)
        self.mass_result_text = self._extended_result(content)

    def _update_mass_context(self):
        try:
            snapshot=deepcopy(self.campaign_session.to_dict())
            conditions={'gui.mass.'+side:{k:self.mass_context_flags[side+'_'+k].get()
                        for k in ('confused','started_confused','mobile')} for side in ('attacker','defender')}
            settings={'siege':self.mass_context_flags['siege'].get(),
                      **{side+'_db':int(v.get()) for side,v in self.mass_defense_bonus.items()}}
            if not messagebox.askyesno(t('mass_update_context'),t('mass_update_context_confirm'),parent=self.root):return
            self.campaign_session.update_battle_context(conditions,settings,self.mass_encounter.get(),snapshot)
            self._pending_mass_round=None
            self._pending_mass_end=None
            self._sync_mass_fields()
            self._show_result(self.mass_result_text,[t('mass_context_updated')])
        except (ValueError,OSError) as exc:
            self._show_result(self.mass_result_text,[self._format_errors([str(exc)])])

    def _open_replacements(self, side):
        try:
            ReplacementEditor(self, side)
        except (ValueError, OSError) as exc:
            self._show_result(self.mass_result_text, [self._format_errors([str(exc)])])

    def _open_mass_aftermath(self):
        try:
            BattleAftermathEditor(self)
        except (ValueError, OSError) as exc:
            self._show_result(self.mass_result_text, [self._format_errors([str(exc)])])

    def _run_strength(self, resolve=False):
        try:
            profile = StrengthProfile(st=int(self.strength_st.get()), lifting_st=int(self.strength_lifting.get()),
                                      striking_st=int(self.strength_striking.get()), current_fp=int(self.strength_fp.get()),
                                      max_fp=int(self.strength_max_fp.get()), will=int(self.strength_will.get()),
                                      lifting_skill_will=int(self.strength_lifting_skill.get()) if self.strength_lifting_skill.get().strip() else None,
                                      lifting_skill_ht=int(self.strength_lifting_ht.get()), power_blow_level=int(self.strength_power_blow_skill.get()),
                                      trained_by_master=self.strength_master.get())
            effort = EffortOption(super_effort_levels=int(self.strength_super.get()),
                                  super_effort_scope=self.strength_scope.get(),
                                  extra_effort_percent=int(self.strength_extra.get()),
                                  use_lifting_skill=profile.lifting_skill_will is not None,
                                  continuous=self.strength_continuous.get(),
                                  sustained_use="carry" if self.strength_carry.get() else "hold",
                                  mighty_blows=self.strength_mighty.get(), trained_lift=self.strength_trained_lift.get(),
                                  power_blow=self.strength_power_blow.get(), concentration_seconds=int(self.strength_power_blow_time.get()),
                                  triple_strength=self.strength_triple.get())
            data = StrengthCalculationInput(profile=profile, task=self.strength_task.get(),
                rules_profile=self.strength_profile.get(), effort=effort, duration_seconds=int(self.strength_duration.get()))
            result = self.strength_calc.resolve(data) if resolve else self.strength_calc.calculate(data)
            units = UnitSystem(self.result_units.get())
            lines = [t("strength_valid", value=t("common_yes") if result.valid else t("common_no")),
                     f"ST: {result.base_st} -> {result.effective_st}",
                     t("strength_bl_result", value=units.display(result.basic_lift_lb, "pounds")),
                     t("strength_capacity_result", value=units.display(result.capacity_lb, "pounds")),
                     f"Thrust / Swing: {result.thrust} / {result.swing}", f"FP: {result.fp_cost}"]
            if result.required_roll_target is not None:
                lines.append(t("strength_roll_target").format(target=result.required_roll_target))
            if result.success_roll is not None:
                lines.append(t("strength_success", value=t("common_yes") if result.success_roll["success"] else t("common_no")))
            if effort.power_blow and result.success_roll is None:
                lines.append(t('ui_power_blow_preview'))
            for interval in result.intervals:
                lines.append(t('ui_strength_interval', index=interval['index'], seconds=interval['seconds'],
                               target=interval['target'], fp=interval['fp_cost'],
                               success=t('common_yes') if interval['success'] else t('common_no')))
            damage = self.strength_calc.calculate_damage(DamageBonusInput(
                profile=profile, rules_profile=self.strength_profile.get(),
                effort=EffortOption(super_effort_levels=effort.super_effort_levels,
                                    super_effort_scope=effort.super_effort_scope, mighty_blows=effort.mighty_blows,
                                    power_blow=effort.power_blow, triple_strength=effort.triple_strength,
                                    concentration_seconds=effort.concentration_seconds,
                                    power_blow_roll=result.success_roll.get('roll') if effort.power_blow and result.success_roll else None),
                maneuver="all_out_strong" if self.strength_all_out.get() else "attack"))
            lines += [t("strength_damage_result", original=damage.original_damage, final=damage.final_damage),
                      t("strength_errors", value=self._format_errors(result.errors + damage.errors))]
            self._show_result(self.strength_result_text, lines, highlights=(lines[1], lines[3]) if result.valid else ())
        except ValueError as exc:
            self._show_result(self.strength_result_text, [t("strength_errors", value=str(exc))])

    def _selected_session_reserve(self, prefix):
        value = getattr(self, prefix + "_session_reserve").get()
        return self._session_reserve_maps.get(prefix, {}).get(value)

    def _refresh_session_reserves(self):
        actor = self.combat_session.combatants[self.session_actor_key]
        same_actor = self._session_reserve_actor == self.session_actor_key
        entries = {t("encounter_reserve_manual"): None}
        entries.update({f"{pool['label']} · {pool['current']}/{pool['maximum']} [{identifier}]": identifier
                        for identifier, pool in actor.resource_pools.items()})
        # Refresh even a not-yet-built tab's display so a role change
        # cannot carry a choice over to a different participant.
        for prefix in ("magic", "power"):
            selected = self._selected_session_reserve(prefix) if same_actor else None
            self._session_reserve_maps[prefix] = entries
            label = next((label for label, identifier in entries.items() if identifier == selected), next(iter(entries)))
            getattr(self, prefix + "_session_reserve").set(label)
            box = self._session_reserve_boxes.get(prefix)
            if box is not None:
                box.configure(values=tuple(entries), state="readonly" if actor.resource_pools else "disabled")
        self._session_reserve_actor = self.session_actor_key

    def _supernatural_pool(self, prefix):
        use_session = getattr(self, prefix + "_use_session").get()
        actor = self.combat_session.combatants[self.session_actor_key]
        identifier = self._selected_session_reserve(prefix) if use_session else None
        reserve = (max(0, actor.resource_pools[identifier]["current"]) if identifier in actor.resource_pools
                   else int(getattr(self, prefix + "_reserve").get()))
        return ResourcePool(
            fp=max(0, actor.current_fp) if use_session else int(getattr(self, prefix + "_fp").get()),
            energy_reserve=reserve,
            external_energy=int(self.magic_external.get()) if prefix == "magic" else 0,
        )

    def _supernatural_lines(self, result):
        lines = self._resistance_lines(result)
        for item in result.breakdown:
            if item["key"] == "rule_of_16":
                continue
            key = "supernatural_mod_" + item["key"]
            name = t(key)
            lines.append(f"{name if name != key else item['key']}: {item['value']:+g} · {item['source']} p.{item['page']}")
        if result.resource_delta:
            lines.append(t("supernatural_spent", fp=-result.resource_delta.get("fp", 0),
                           reserve=-result.resource_delta.get("energy_reserve", 0),
                           external=-result.resource_delta.get("external_energy", 0),
                           group=-result.resource_delta.get("ceremonial_assistants", 0)))
        if result.resistance and result.resistance.roll is not None:
            lines.append(t("supernatural_resistance_roll", roll=result.resistance.roll))
        for effect in result.effects:
            if effect.kind == "heal_hp":
                lines.append(t("magic_heal_effect", value=effect.value))
            if effect.metadata.get("action") in {"emotion_sense", "mental_surgery"}:
                lines.append(t("psi_effect_" + effect.metadata["action"]))
        for pending in result.pending_effects:
            kind = pending["kind"]
            if kind == "very_high_mana_fp_recovery":
                lines.append(t("supernatural_recover_fp", fp=pending["fp"]))
            elif kind == "gm_effect":
                lines.append(t("supernatural_gm_effect"))
            elif kind in {"spell_failure", "psi_failure"} and pending.get("critical"):
                lines.append(t("supernatural_gm_critical"))
        lines.append(t("common_references") + " " + "; ".join(f"{item.source} p.{item.page}" for item in result.references))
        return lines

    def _remember_supernatural(self, prefix, result, label):
        if result.valid and getattr(self, prefix + "_use_session").get():
            target = self.combat_session.combatants[self.session_target_key]
            healing = 0
            if not target.dead and target.injury_tolerance == "living":
                healing = min(max(0, target.max_hp - target.current_hp),
                              sum(int(effect.value) for effect in result.effects if effect.kind == "heal_hp"))
            reserve_id = self._selected_session_reserve(prefix)
            reserve_change = result.resource_delta.get("energy_reserve", 0) if reserve_id else 0
            self._supernatural_drafts[prefix] = (self.session_actor_key, self.session_target_key,
                                                self.combat_session.to_dict(), result.state_delta.fp_change,
                                                healing, label, reserve_id, reserve_change)

    def _apply_supernatural(self, prefix):
        draft = self._supernatural_drafts.get(prefix)
        box = self.magic_result_text if prefix == "magic" else self.powers_result_text
        if draft is None:
            messagebox.showinfo(t("session_title"), t("supernatural_resolve_for_session"))
            return
        actor_id, target_id, snapshot, fp, healing, label, reserve_id, reserve_change = draft
        if ((actor_id, target_id, snapshot) != (self.session_actor_key, self.session_target_key, self.combat_session.to_dict())
                or getattr(box, "stale", False) or not getattr(self, prefix + "_use_session").get()
                or reserve_id != self._selected_session_reserve(prefix)):
            messagebox.showwarning(t("session_title"), t("ui_session_stale"))
            return
        actor, target = (self.combat_session.combatants[key] for key in (actor_id, target_id))
        if not (fp or healing or reserve_change):
            messagebox.showinfo(t("session_title"), t("session_nothing_to_apply"))
            return
        preview = t("supernatural_apply_preview", actor=actor.name, fp=fp, target=target.name, hp=healing)
        resources = {}
        if reserve_id and reserve_change:
            resources[reserve_id] = reserve_change
            preview += "\n" + t("encounter_reserve_change", label=actor.resource_pools[reserve_id]["label"],
                                 amount=reserve_change)
        if not messagebox.askyesno(t("session_title"), preview):
            return
        try:
            self.combat_session.apply_action(actor_id, target_id, StateDelta(hp_change=healing),
                                             StateDelta(fp_change=fp, resource_changes=resources),
                                             label, advance_action=False)
        except (OSError, ValueError) as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))
            return
        self._session_changed()
        box.insert(tk.END, "\n\n" + t("session_applied"))

    def _run_magic(self, resolve, maintain=False):
        self._supernatural_drafts.pop("magic", None)
        try:
            spell = self._magic_map[self.magic_spell.get()]
            if self.magic_cost_override.get().strip():
                spell = replace(spell, base_cost=float(self.magic_cost_override.get()))
            if self.magic_time_override.get().strip():
                spell = replace(spell, casting_time_seconds=float(self.magic_time_override.get()))
            data = CastingInput(spell=spell, system=self.magic_system.get(), profile=self.magic_profile.get(),
                                skill=int(self.magic_skill.get()), distance_yards=self._optional_number(self.magic_distance, float, 0),
                                area_radius_yards=self._optional_number(self.magic_radius, float, 1),
                                resources=self._supernatural_pool("magic"), size_modifier=int(self.magic_size.get()),
                                resistance=self._resistance_input("magic", spell.requires_resistance and not maintain),
                                ceremony=getattr(self, '_magic_ceremony', None), is_mage=self.magic_is_mage.get(),
                                target_visible=self.magic_visible.get(), custom_modifier=int(self.magic_mod.get()),
                                mana_level=self.magic_mana.get(), maintenance_cycles=int(self.magic_cycles.get()),
                                same_day_castings=int(self.magic_healing_attempts.get()), physician_skill=int(self.magic_physician.get()),
                                magery=int(self.magic_magery.get()), magic_resistance=int(self.magic_target_mr.get()),
                                target_waives_resistance=self.magic_waives_resistance.get(),
                                maintenance_only=maintain)
            result = self.spell_calc.resolve(data) if resolve else self.spell_calc.calculate(data)
            if resolve:
                self._remember_supernatural("magic", result, "spell_maintenance" if maintain else "spell_cast")
            lines = [f"Valid: {result.valid}", f"Skill: {result.effective_skill}",
                f"Energy: {result.energy_cost}", f"Time: {result.casting_time_seconds}s",
                t("magic_source_parameters", energy=spell.original.get('energy', spell.base_cost),
                  time=spell.original.get('casting_time', spell.casting_time_seconds), source=spell.source, page=spell.page)]
            if maintain:
                lines.insert(0, t("magic_renew_note"))
            if result.roll:
                lines.append(f"Roll: {result.roll.get('roll', '—')} · {self._format_roll(result.roll)}")
            if result.maintenance_cost is not None:
                lines.append(t("magic_upkeep_result", cost=result.maintenance_cost, forecast=result.maintenance_forecast))
            if result.duration_seconds:
                lines.append(t("magic_duration_result", seconds=result.duration_seconds))
            if result.errors:
                lines.append(f"Errors: {self._format_errors(result.errors)}")
            self._show_result(self.magic_result_text, lines + self._supernatural_lines(result))
        except (ValueError, OverflowError, KeyError):
            self._show_result(self.magic_result_text, [t("supernatural_invalid_input")])

    def _run_ability(self):
        self._supernatural_drafts.pop("power", None)
        try:
            result = self.ability_calc.calculate(AbilityBuildInput(
                self._advantage_map[self.power_advantage.get()], levels=int(self.power_levels.get())))
            lines = [f"Base cost: {result.unmodified_cost}", f"Modifier: {result.net_modifier_percent:+d}%",
                     f"Final cost: {result.modified_cost}"] if result.valid else [
                         f"Valid: {result.valid}", f"Errors: {self._format_errors(result.errors)}"]
            self._show_result(self.powers_result_text, lines)
        except (ValueError, OverflowError, KeyError):
            self._show_result(self.powers_result_text, [t("supernatural_invalid_input")])

    def _run_psi(self, resolve=True):
        self._supernatural_drafts.pop("power", None)
        try:
            ability = self._psi_map[self.power_psi.get()]
            data = PsiUseInput(
                ability, skill=int(self.power_skill.get()), level=int(self.power_level.get()),
                distance_yards=self._optional_number(self.power_distance, float, 0), resources=self._supernatural_pool("power"),
                resistance=self._resistance_input("power", bool(ability.resist_attribute)), contact=self.power_contact.get(),
                talent=int(self.power_talent.get()), repeated_attempts=int(self.power_repeats.get()),
                repeat_cost_due=self.power_repeat_cost.get(), target_living_sapient=self.power_living_target.get(),
                target_willing=self.power_target_willing.get(), target_restrained=self.power_target_restrained.get(),
                changed_disadvantage_points=int(self.power_disadvantage_points.get()))
            result = self.psi_calc.resolve(data) if resolve else self.psi_calc.calculate(data)
            if resolve:
                self._remember_supernatural("power", result, "psi_use")
            lines = [f"Valid: {result.valid}", f"Skill: {result.effective_skill}", f"FP: {result.fp_cost}"]
            if result.character_point_cost is not None:
                lines.append(t("psi_point_cost", points=result.character_point_cost))
            if result.activation_time_seconds is not None:
                lines.append(f"Time: {result.activation_time_seconds}s")
            elif result.valid:
                lines.append(t("psi_unspecified_time"))
            if result.roll:
                lines.append(f"Roll: {result.roll['roll']} · {self._format_roll(result.roll)}")
            if result.errors:
                lines.append(f"Errors: {self._format_errors(result.errors)}")
            self._show_result(self.powers_result_text, lines + self._supernatural_lines(result))
        except (ValueError, OverflowError, KeyError):
            self._show_result(self.powers_result_text, [t("supernatural_invalid_input")])

    def _run_vehicle(self):
        try:
            record = self._vehicle_map[self.vehicle_selected.get()]
            state = self.vehicle_session.vehicles.get(record.identifier, VehicleState(record))
            result = self.vehicle_calc.calculate_movement(VehicleMovementInput(
                state, duration_seconds=int(self.vehicle_duration.get()), environment=self.vehicle_environment.get()))
            self._pending_vehicle_movement = (record.identifier, result, deepcopy(state),
                                             self.vehicle_session.snapshot(),
                                             (self.vehicle_selected.get(), self.vehicle_duration.get(), self.vehicle_environment.get()))
            units = UnitSystem(self.result_units.get())
            self._show_result(self.vehicles_result_text, [f"Valid: {result.valid}",
                f"Speed: {units.display(result.initial_speed, 'yards_per_second')} -> {units.display(result.final_speed, 'yards_per_second')}",
                f"Distance: {units.display(result.distance_yards, 'yards')}", f"Fuel: {result.fuel_used} h",
                f"Delta-V: {units.display(result.delta_v_used_mps, 'miles_per_second')}",
                f"Errors: {self._format_errors(result.errors)}"])
        except ValueError as exc: self._show_result(self.vehicles_result_text, [f"Error: {exc}"])

    def _apply_vehicle_movement(self):
        try:
            if self._pending_vehicle_movement is None:
                raise ValueError('stale_vehicle_movement')
            identifier, result, state, snapshot, inputs = self._pending_vehicle_movement
            if inputs != (self.vehicle_selected.get(), self.vehicle_duration.get(), self.vehicle_environment.get()):
                raise ValueError('stale_vehicle_movement')
            if not result.valid:
                raise ValueError('invalid_vehicle_movement')
            units = UnitSystem(self.result_units.get())
            preview = t('ui_vehicle_preview', speed=units.display(result.final_speed, 'yards_per_second'),
                        fuel=result.fuel_used, time=result.travel_time_seconds)
            if messagebox.askyesno(t('ui_vehicle_apply'), preview, parent=self.root):
                self.vehicle_session.apply_movement(identifier, result, state, snapshot)
                self._pending_vehicle_movement = None
                self._show_result(self.vehicles_result_text, [t('ui_vehicle_applied')])
        except (ValueError, OSError) as exc:
            self._show_result(self.vehicles_result_text, [self._format_errors([str(exc)])])

    def _undo_vehicle_movement(self):
        try:
            if self.vehicle_session.undo():
                self._pending_vehicle_movement = None
                self._show_result(self.vehicles_result_text, [t('ui_vehicle_undone')])
        except (ValueError, OSError) as exc:
            self._show_result(self.vehicles_result_text, [self._format_errors([str(exc)])])

    def _social_profiles(self):
        actor = CharacterSocialProfile("actor", "Actor", skills={self.social_skill.get(): int(self.social_skill_level.get())})
        target = CharacterSocialProfile("target", "Target", will=int(self.social_target_will.get()))
        return actor, target

    def _run_reaction(self):
        try:
            actor, _ = self._social_profiles()
            result = self.social_calc.resolve_reaction(ReactionInput(actor, situational_modifier=int(self.social_modifier.get())))
            self._show_result(self.social_result_text, [f"Roll: {result.roll}", f"Modifier: {result.modifiers:+d}",
                f"Total: {result.total}", f"Reaction: {result.band}"])
        except ValueError as exc: self._show_result(self.social_result_text, [f"Error: {exc}"])

    def _run_influence(self):
        try:
            actor, target = self._social_profiles()
            result = self.social_calc.resolve_influence(InfluenceInput(
                actor, target, self.social_skill.get(), modifier=int(self.social_modifier.get()), expanded=True))
            lines = [f"Valid: {result.valid}", f"Success: {result.success}",
                     f"Margin: {result.margin}", f"Reaction: {result.reaction_band}", f"Errors: {self._format_errors(result.errors)}"]
            for pending in result.pending_effects:
                lines.append(t("social_pending_" + pending["kind"]))
            self._show_result(self.social_result_text, lines)
        except ValueError as exc: self._show_result(self.social_result_text, [f"Error: {exc}"])

    def _run_mass_combat(self, resolve=True):
        self._pending_mass_round = None
        self._pending_mass_end = None
        self._last_mass_result = None
        try:
            if self.campaign_session.battle_ended:
                raise ValueError('battle_already_ended')
            attacker = ForceRecord("gui.mass.attacker", "Attacker", [ElementRecord("a", "Force", float(self.mass_attacker_ts.get()), ["Inf"])],
                                   commander_strategy=int(self.mass_attacker_strategy.get()))
            defender = ForceRecord("gui.mass.defender", "Defender", [ElementRecord("d", "Force", float(self.mass_defender_ts.get()), ["Inf"])],
                                   commander_strategy=int(self.mass_defender_strategy.get()))
            def stored_force(proposed):
                saved = self.campaign_session.forces.get(proposed.identifier)
                if (saved is not None and saved.commander_strategy == proposed.commander_strategy and
                        math.isclose(saved.troop_strength, proposed.troop_strength, rel_tol=1e-14)):
                    return deepcopy(saved)
                return proposed
            attacker, defender = stored_force(attacker), stored_force(defender)
            data = BattleInput(attacker, defender, attacker_casualties=float(self.mass_attacker_casualties.get()),
                               parley_response=self.mass_parley_response.get(),
                               **{side+'_response_strategy':var.get() for side,var in self.mass_initiative_response.items()},
                               round_number=self.campaign_session.battle_round_number,
                               **{key:var.get() for key,var in self.mass_context_flags.items()},
                               **{key:int(var.get()) if var.get().strip() else None for key,var in self.mass_rally_values.items()},
                               attacker_defense_bonus=int(self.mass_defense_bonus['attacker'].get()),
                               defender_defense_bonus=int(self.mass_defense_bonus['defender'].get()),
                               attacker_strategy=self.mass_attacker_choice.get(), defender_strategy=self.mass_defender_choice.get(),
                               defender_casualties=float(self.mass_defender_casualties.get()),
                               attacker_position=int(self.mass_attacker_position.get()), defender_position=int(self.mass_defender_position.get()),
                               attacker_classes=deepcopy(self._mass_classes.get('attacker', {})),
                               defender_classes=deepcopy(self._mass_classes.get('defender', {})), encounter_battle=self.mass_encounter.get(),
                               **{side + suffix: self.campaign_session.battle_strategy_state.get('gui.mass.'+side,{}).get(key,default)
                                  for side in ('attacker','defender')
                                  for suffix,key,default in (('_indirect_uses','uses',0),('_previous_strategy','previous',''))},
                               **{side+'_'+key:var.get() for side,flags in self.mass_raid_flags.items() for key,var in flags.items()})
            if not resolve:
                result = self.mass_combat_calc.calculate(data)
                self._last_mass_result = None
                if result.valid and result.event != 'combat':
                    self._show_result(self.mass_result_text, [t('mass_event_' + result.event)])
                    return
                self._show_result(self.mass_result_text, [t('mass_calculation_targets', attacker=result.attacker_target,
                    defender=result.defender_target), t('mass_casualties_rule'), self._format_errors(result.errors)] + self._mass_modifier_lines(result))
                return
            result = self.mass_combat_calc.resolve(data)
            self._last_mass_result = result
            if result.valid and result.outcome in ('parley', 'no_battle'):
                if result.outcome=='no_battle':
                    self._pending_mass_end=(deepcopy(data),deepcopy(self.campaign_session.to_dict()),self._mass_inputs())
                self._show_result(self.mass_result_text, [t('mass_event_' + result.outcome)] +
                                  ([t('mass_no_battle_hint')] if result.outcome=='no_battle' else []))
                return
            self._pending_mass_round = (deepcopy(data), deepcopy(result), deepcopy(self.campaign_session.to_dict()), self._mass_inputs())
            self._show_result(self.mass_result_text, [f"Valid: {result.valid}", f"TS: {result.attacker_ts} vs {result.defender_ts}",
                f"Margin: {result.margin}", f"Outcome: {result.outcome}",
                f"Casualties: {result.attacker_casualty_percent}% / {result.defender_casualty_percent}%",
                f"Errors: {self._format_errors(result.errors)}", t('mass_casualties_rule'),
                t('mass_logistic_round',attacker=result.state_delta.logistic_losses.get(data.attacker.identifier,0),
                  defender=result.state_delta.logistic_losses.get(data.defender.identifier,0))] + self._mass_modifier_lines(result)+self._mass_rally_lines(result))
        except ValueError as exc: self._show_result(self.mass_result_text, [f"Error: {exc}"])

    def _mass_inputs(self):
        return tuple(v.get() for v in (self.mass_attacker_ts, self.mass_defender_ts,
            self.mass_attacker_strategy, self.mass_defender_strategy,
            self.mass_attacker_choice, self.mass_defender_choice,
            self.mass_parley_response,
            self.mass_attacker_casualties, self.mass_defender_casualties, self.mass_attacker_position,
            self.mass_defender_position, self.mass_encounter)) + (json.dumps(self._mass_classes, sort_keys=True),) + tuple(
                var.get() for flags in self.mass_raid_flags.values() for var in flags.values())+tuple(v.get() for v in self.mass_defense_bonus.values())+tuple(v.get() for v in self.mass_context_flags.values())+tuple(v.get() for v in self.mass_rally_values.values())+tuple(v.get() for v in self.mass_initiative_response.values())

    def _mass_rally_lines(self,result):
        end=[t('mass_battle_end',outcome=t('mass_aftermath_'+result.battle_end['victor']))] if result.battle_end else []
        return end+[t('mass_rally_result',side=t('mass_aftermath_side_'+side),roll=check['roll'],
                  outcome=t('mass_rally_success' if check['success'] else 'mass_rally_failure'))
                for side,check in result.rally_results.items()]

    def _mass_modifier_lines(self, result):
        strategies=[t('mass_effective_strategies',attacker=t('mass_choice_'+item['attacker']),defender=t('mass_choice_'+item['defender']))
                    for item in result.breakdown if item['key']=='effective_strategies']
        return strategies+[t('mass_modifier_line', name=t('mass_' + item['key']) if not item['key'].startswith('class_') else item['key'].removeprefix('class_'), attacker=item['attacker'],
                  defender=item['defender'], page=item['page']) for item in result.breakdown
                if item['key'].startswith('class_') or item['key'].startswith('position') or item['key'] in ('strategy_superiority','strategy_repeat','strategy_desperate','desperate_misfortune','parley_refusal','defense_bonus','confused_retreat')]

    def _sync_mass_fields(self):
        for side in ('attacker', 'defender'):
            key = 'gui.mass.' + side
            force = self.campaign_session.forces.get(key)
            if force is not None:
                getattr(self, 'mass_' + side + '_ts').set(format(force.troop_strength, '.15g'))
                getattr(self, 'mass_' + side + '_strategy').set(str(force.commander_strategy))
            getattr(self, 'mass_' + side + '_casualties').set(str(self.campaign_session.battle_casualties.get(key, 0)))
            getattr(self, 'mass_' + side + '_position').set(str(self.campaign_session.battle_positions.get(key, 0)))
            for condition in ('confused','started_confused','mobile'):
                self.mass_context_flags[side+'_'+condition].set(self.campaign_session.battle_conditions.get(key,{}).get(condition,False))
        self._mass_classes = {side: deepcopy(self.campaign_session.battle_class_strengths.get('gui.mass.' + side, {}))
                              for side in ('attacker', 'defender')}
        self.mass_encounter.set(self.campaign_session.battle_encounter)
        self.mass_context_flags['siege'].set(self.campaign_session.battle_settings.get('siege',False))
        for side in ('attacker','defender'):
            self.mass_defense_bonus[side].set(str(self.campaign_session.battle_settings.get(side+'_db',0)))

    def _apply_mass_round(self):
        try:
            if self._pending_mass_end is not None:
                data,snapshot,inputs=self._pending_mass_end
                if inputs!=self._mass_inputs() or snapshot!=self.campaign_session.to_dict():
                    raise ValueError('stale_battle_result')
                if not messagebox.askyesno(t('mass_apply_round'),t('mass_confirm_no_battle'),parent=self.root):return
                self.campaign_session.end_without_combat(data,snapshot)
                self._pending_mass_end=None
                self._sync_mass_fields()
                self._show_result(self.mass_result_text,[t('mass_no_battle_recorded')])
                return
            if self._pending_mass_round is None:
                raise ValueError('stale_battle_result')
            data, result, snapshot, inputs = self._pending_mass_round
            if inputs != self._mass_inputs() or not result.valid or snapshot != self.campaign_session.to_dict():
                raise ValueError('stale_battle_result')
            preview = t('mass_round_preview', attacker=result.attacker_casualty_percent,
                        defender=result.defender_casualty_percent)
            preview += '\n' + t('mass_pb_next', attacker=result.state_delta.battle_positions.get(data.attacker.identifier, 0),
                                defender=result.state_delta.battle_positions.get(data.defender.identifier, 0))
            preview += '\n' + t('mass_logistic_round',attacker=result.state_delta.logistic_losses.get(data.attacker.identifier,0),
                                defender=result.state_delta.logistic_losses.get(data.defender.identifier,0))
            preview += '\n'+'\n'.join(self._mass_rally_lines(result))
            if not messagebox.askyesno(t('mass_apply_round'), preview, parent=self.root):
                return
            self.campaign_session.apply_battle_round(data, result, snapshot)
            self._pending_mass_round = None
            self._sync_mass_fields()
            self._show_result(self.mass_result_text, [t('mass_round_applied')])
        except (ValueError, OSError) as exc:
            self._show_result(self.mass_result_text, [self._format_errors([str(exc)])])

    def _finish_mass_battle(self):
        try:
            snapshot = deepcopy(self.campaign_session.to_dict())
            casualties = self.campaign_session.battle_casualties
            if set(casualties) != {'gui.mass.attacker', 'gui.mass.defender'}:
                raise ValueError('mass_no_active_battle')
            final = {}
            for side in ('attacker', 'defender'):
                key = 'gui.mass.' + side
                value = simpledialog.askfloat(t('mass_finish_battle'), t('mass_final_' + side),
                    initialvalue=casualties[key], minvalue=0, maxvalue=100, parent=self.root)
                if value is None: return
                final[key] = value
            preview = t('mass_final_confirm', attacker=final['gui.mass.attacker'], defender=final['gui.mass.defender'])
            if not messagebox.askyesno(t('mass_finish_battle'), preview, parent=self.root): return
            self.campaign_session.finalize_battle(final, snapshot)
            self._pending_mass_round = None
            self._sync_mass_fields()
            self._show_result(self.mass_result_text, [t('mass_final_applied')])
        except (ValueError, OSError) as exc:
            self._show_result(self.mass_result_text, [self._format_errors([str(exc)])])

    def _undo_mass_campaign(self):
        try:
            if messagebox.askyesno(t('ui_campaign_undo'), t('ui_campaign_undo_confirm'), parent=self.root):
                self.campaign_session.undo()
                self._pending_mass_round = None
                self._sync_mass_fields()
                self._show_result(self.mass_result_text, [t('mass_campaign_restored')])
        except (ValueError, OSError) as exc:
            self._show_result(self.mass_result_text, [self._format_errors([str(exc)])])

    # ═════════════════════════════════════════════════════════════════
    # MÉTODOS DE CONVERSÃO DE UNIDADES
    # ═════════════════════════════════════════════════════════════════
    def _meters_to_yards(self, meters: float) -> int:
        """
        Converte metros para jardas (arredonda para inteiro).
        
        GURPS usa jardas internamente, mas a interface usa metros.
        Arredondamento: GURPS arredonda para o inteiro mais próximo.
        """
        return round(meters * METERS_TO_YARDS)

    def _yards_to_meters(self, yards: int) -> float:
        """Converte jardas para metros (1 casa decimal)."""
        return round(yards * YARDS_TO_METERS, 1)

    def _format_meters(self, yards: int) -> str:
        """Formata jardas como metros para exibição."""
        meters = self._yards_to_meters(yards)
        return f"{meters}m"

    def _get_int_var(self, var: tk.IntVar, min_val: int = 0, max_val: int = 10000) -> int:
        """Obtém valor inteiro de IntVar com validação."""
        val = var.get()
        if val < min_val:
            return min_val
        if val > max_val:
            return max_val
        return val

    # ═════════════════════════════════════════════════════════════════
    # MÉTODOS DE CÁLCULO
    # ═════════════════════════════════════════════════════════════════

    # ─── Knockback ───────────────────────────────────────────────
    def _calculate_knockback(self):
        """Calcula knockback baseado nos inputs do usuário."""
        try:
            result = self.knockback_calc.calculate_knockback(
                damage_type=self.kb_damage_type.get(),
                basic_damage=self.kb_basic_damage.get(),
                target_st=self.kb_target_st.get(),
                target_hp=self.kb_target_hp.get(),
                target_dr=self.kb_target_dr.get(),
                perfect_balance=self.kb_perfect_balance.get()
            )

            self.kb_result_text.delete(1.0, tk.END)
            if not result["valid"]:
                self.kb_result_text.insert(tk.END, t("knockback_invalid"))
            elif result["yards_back"] == 0:
                self.kb_result_text.insert(tk.END, t("knockback_none"))
            else:
                self.kb_result_text.insert(tk.END, t(
                    "knockback_summary",
                    yards=result["yards_back"],
                    meters=self._format_meters(result["yards_back"]),
                ))

            if result["yards_back"] > 0:
                self.kb_result_text.insert(tk.END, f"\n\n{t('knockback_details')}")
                self.kb_result_text.insert(tk.END,
                    f"\n{t('knockback_damage_value', value=result['knockback_damage'])}")
                self.kb_result_text.insert(tk.END,
                    f"\n{t('knockback_meters_back', value=self._format_meters(result['yards_back']))}")
                self.kb_result_text.insert(tk.END,
                    f"\n{t('knockback_roll_modifier', value=result['roll_modifier'])}")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    def _roll_knockback(self):
        """Rola 3d6 para verificação de knockback."""
        roll, rolls = roll_3d6()
        self.kb_roll_result.set(roll)

    def _check_knockback_roll(self):
        """Verifica se o alvo resiste ao knockback."""
        try:
            kb_result = self.knockback_calc.calculate_knockback(
                damage_type=self.kb_damage_type.get(),
                basic_damage=self.kb_basic_damage.get(),
                target_st=self.kb_target_st.get(),
                target_hp=self.kb_target_hp.get(),
                target_dr=self.kb_target_dr.get(),
                perfect_balance=self.kb_perfect_balance.get()
            )

            if kb_result["yards_back"] == 0:
                self.kb_result_text.delete(1.0, tk.END)
                self.kb_result_text.insert(tk.END, t("knockback_none"))
                return

            roll_result = self.kb_roll_result.get()
            roll_check = self.knockback_calc.calculate_knockback_roll(
                yards_back=kb_result["yards_back"],
                effective_skill=self.kb_effective_skill.get(),
                roll_result=roll_result,
                perfect_balance=self.kb_perfect_balance.get()
            )

            self.kb_result_text.delete(1.0, tk.END)
            self.kb_result_text.insert(tk.END, t(
                "knockback_summary",
                yards=kb_result["yards_back"],
                meters=self._format_meters(kb_result["yards_back"]),
            ))
            self.kb_result_text.insert(tk.END,
                f"\n\n{t('knockback_verification')}")
            self.kb_result_text.insert(tk.END,
                f"\n{t('knockback_roll_result', value=roll_result)}")
            self.kb_result_text.insert(tk.END,
                f"\n{t('knockback_effective_skill', value=roll_check['effective_skill'])}")
            roll_message = t(
                "roll_success" if roll_check["success"] else "roll_failure",
                margin=roll_check["margin"],
            )
            self.kb_result_text.insert(tk.END,
                f"\n{t('combat_result_label', value=roll_message)}")

            if roll_check["fall_down"]:
                self.kb_result_text.insert(tk.END,
                    f"\n\n{t('knockback_fall_warning')}")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Slam/Investida ──────────────────────────────────────────
    def _calculate_slam(self):
        """Calcula dano de investida (slam)."""
        try:
            # Converter m/s para jardas/seg (cálculos usam jardas)
            att_vel_yd = self._meters_to_yards(self.slam_attacker_velocity.get())
            def_vel_yd = self._meters_to_yards(self.slam_defender_velocity.get())

            result = self.slam_calc.calculate_slam(
                attacker_hp=self.slam_attacker_hp.get(),
                attacker_velocity=att_vel_yd,
                defender_hp=self.slam_defender_hp.get(),
                defender_velocity=def_vel_yd,
                collision_type=self.slam_collision_type.get(),
                attacker_skill_bonus=self.slam_attacker_damage_bonus.get(),
            )

            self.slam_result_text.delete(1.0, tk.END)
            damage_lines = (
                t('slam_attacker_damage', expression=result['attacker_damage_dice'], value=result['attacker_damage_total']),
                t('slam_defender_damage', expression=result['defender_damage_dice'], value=result['defender_damage_total']),
            )
            self.slam_result_text.oficina_highlights = damage_lines
            # Converter resultado de volta para metros
            collision_vel_m = UnitSystem(self.result_units.get()).display(result["collision_velocity"], "yards_per_second")
            self.slam_result_text.insert(tk.END,
                f"{t('result_collision_velocity', value=collision_vel_m)}\n")
            self.slam_result_text.insert(tk.END, '\n'.join(damage_lines) + '\n')
            self.slam_result_text.insert(
                tk.END, f"\n{t('slam_' + result['outcome'])}\n"
            )

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Quedas ──────────────────────────────────────────────────
    def _calculate_falls(self):
        """Calcula dano por queda."""
        try:
            # Converter metros para jardas
            distance_yards = self._meters_to_yards(self.falls_distance.get())

            result = self.falls_calc.calculate_fall(
                distance_yards=distance_yards,
                target_hp=self.falls_hp.get(),
                surface_type=self.falls_surface.get(),
                acrobatics_success=self.falls_acrobatics.get(),
                swimming_success=self.falls_swimming.get(),
                armor_dr=self.falls_dr.get(),
            )

            self.falls_result_text.delete(1.0, tk.END)
            injury = t('result_total_injury', value=result['total_injury'])
            self.falls_result_text.oficina_highlights = (injury,)
            velocity_m = round(result["velocity"] * YARDS_TO_METERS, 1)
            self.falls_result_text.insert(tk.END,
                f"{t('result_distance', meters=self.falls_distance.get(), yards=distance_yards)}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_impact_velocity', mps=velocity_m, yps=result['velocity'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_basic_damage', expression=result['damage_dice'], value=result['damage_total'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_penetrating_damage', value=result['penetrating_damage'])}\n")
            self.falls_result_text.insert(tk.END,
                f"{t('result_blunt_trauma', value=result['blunt_trauma'])}\n")
            self.falls_result_text.insert(tk.END, injury + '\n')
            if result["surface_type"] == "water":
                self.falls_result_text.insert(tk.END,
                    f"{t('falls_swimming_modifier', value=result['swimming_modifier'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Colisões ────────────────────────────────────────────────
    def _calculate_collisions(self):
        """Calcula dano de colisão entre objetos."""
        try:
            # Converter m/s para jardas/seg
            vel1_yd = self._meters_to_yards(self.coll_obj1_velocity.get())
            vel2_yd = self._meters_to_yards(self.coll_obj2_velocity.get())

            result = self.collisions_calc.calculate_collision(
                object1_hp=self.coll_obj1_hp.get(),
                object1_velocity=vel1_yd,
                object2_hp=self.coll_obj2_hp.get(),
                object2_velocity=vel2_yd,
                collision_type=self.coll_type.get(),
                surface_type=self.coll_surface.get(),
                immovable_object=self.coll_immovable.get(),
                object2_dr=self.coll_obj2_dr.get(),
                obstacle_breakable=self.coll_breakable.get(),
            )

            self.coll_result_text.delete(1.0, tk.END)
            damage_lines = (
                t('collisions_object1_damage', expression=result['object1_damage_dice'], value=result['object1_damage_total']),
                t('collisions_object2_damage', expression=result['object2_damage_dice'], value=result['object2_damage_total']),
            )
            self.coll_result_text.oficina_highlights = damage_lines
            collision_vel_m = UnitSystem(self.result_units.get()).display(result["collision_velocity"], "yards_per_second")
            self.coll_result_text.insert(tk.END,
                f"{t('result_collision_velocity', value=collision_vel_m)}\n")
            self.coll_result_text.insert(tk.END, '\n'.join(damage_lines) + '\n')
            if result["damage_cap"] is not None:
                self.coll_result_text.insert(tk.END,
                    f"{t('collisions_damage_cap', value=result['damage_cap'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Explosões ───────────────────────────────────────────────
    def _calculate_explosions(self):
        """Calcula dano de explosão."""
        try:
            # Converter metros para jardas
            distance_yards = self._meters_to_yards(self.exp_distance.get())

            result = self.explosions_calc.calculate_explosion(
                basic_damage_dice=self.exp_basic_damage.get(),
                fragmentation_dice=self.exp_fragmentation.get(),
                distance_yards=distance_yards,
                target_dr=self.exp_dr.get(),
                direct_hit=self.exp_direct_hit.get(),
                target_sm=self.exp_target_sm.get(),
                posture_modifier=self.exp_posture_modifier.get(),
            )

            self.exp_result_text.delete(1.0, tk.END)
            injury = t('result_total_injury', value=result['injury'])
            self.exp_result_text.oficina_highlights = (injury,)
            blast_radius_m = round(result["blast_radius"] * YARDS_TO_METERS, 1)
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_blast_radius', meters=blast_radius_m, yards=result['blast_radius'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_blast_damage', expression=result['collateral_damage_dice'], value=result['collateral_damage_total'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_blast_injury', value=result['blast_injury'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_fragment_hits', value=result['fragment_hits'])}\n")
            self.exp_result_text.insert(tk.END,
                f"{t('explosions_fragment_injury', value=result['fragment_injury_total'])}\n")
            self.exp_result_text.insert(tk.END, injury + '\n')

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Queda de Objetos ────────────────────────────────────────
    def _calculate_falling_objects(self):
        """Calcula dano por objeto caindo."""
        try:
            # Converter metros para jardas
            distance_yards = self._meters_to_yards(self.fo_distance.get())

            result = self.falling_objects_calc.calculate_falling_object(
                distance_yards=distance_yards,
                object_hp=self.fo_object_hp.get(),
                target_hp=self.fo_target_hp.get(),
                target_sm=self.fo_target_sm.get(),
                object_sm=self.fo_object_sm.get(),
                target_aware=self.fo_target_aware.get(),
                dropping_skill=self.fo_dropping_skill.get(),
                target_dodge=self.fo_target_dodge.get(),
                aimed=self.fo_aimed.get(),
            )

            self.fo_result_text.delete(1.0, tk.END)
            velocity_m = round(result["velocity"] * YARDS_TO_METERS, 1)
            self.fo_result_text.insert(tk.END,
                f"{t('result_distance', meters=self.fo_distance.get(), yards=distance_yards)}\n")
            self.fo_result_text.insert(tk.END,
                f"{t('result_impact_velocity', mps=velocity_m, yps=result['velocity'])}\n")
            self.fo_result_text.insert(tk.END,
                f"{t('falling_objects_attack_roll', roll=result['attack_roll'], skill=result['effective_skill'])}\n")
            if result["target_can_dodge"]:
                self.fo_result_text.insert(tk.END,
                    f"{t('falling_objects_dodge_roll', roll=result['dodge_roll'], defense=result['target_dodge'])}\n")
            outcome_lines = (t('falling_objects_outcome_' + result['outcome']),
                             t('result_basic_damage', expression=result['damage_dice'], value=result['damage_total']))
            self.fo_result_text.oficina_highlights = outcome_lines
            self.fo_result_text.insert(tk.END, '\n'.join(outcome_lines) + '\n')
            if result["move_penalty"] > 0:
                self.fo_result_text.insert(tk.END,
                    f"{t('falling_objects_move_limit')}\n")
            if result["defense_penalty"] > 0:
                self.fo_result_text.insert(tk.END,
                    f"{t('falling_objects_defense_penalty', value=result['defense_penalty'])}\n")

        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Sessão compartilhada ────────────────────────────────────
    def _change_session_roles(self, labels, actor_changed):
        variable = self.session_actor if actor_changed else self.session_target
        identifier = labels.get(variable.get())
        if identifier is not None:
            self._select_encounter_role("actor" if actor_changed else "target", identifier)

    def _select_encounter_role(self, role, identifier):
        if identifier not in self.combat_session.combatants:
            return
        actor, target = self.session_actor_key, self.session_target_key
        if role == "actor":
            actor, target = identifier, actor if identifier == target else target
        elif role == "target":
            actor, target = target if identifier == actor else actor, identifier
        else:
            raise ValueError("invalid_encounter_role")
        self.session_actor_key, self.session_target_key = self.combat_session.selected_pair(actor, target)
        self._session_changed()

    def _swap_encounter_roles(self):
        self._select_encounter_role("actor", self.session_target_key)

    def _change_melee_defense(self, _event=None):
        self.melee_defense_key = self._melee_defense_labels[self.melee_defense.get()]
        self._load_target_defense()
        self._last_melee_result = None
        self._last_grapple_result = None

    def _load_target_defense(self):
        target = self.combat_session.combatants[self.session_target_key]
        defense = self.melee_defense_key
        value = None if defense in target.unknown_defenses else getattr(target, defense)
        self.melee_defense_score.set("" if value is None else str(value))

    def _session_defense(self, target, aware=True):
        explicit = self._optional_number(self.melee_defense_score, int)
        if explicit is None and aware and self.melee_defense_key in target.unknown_defenses:
            raise ValueError(t("encounter_defense_required", defense=t("melee_defense_" + self.melee_defense_key)))
        return explicit

    def _refresh_session_summary(self, sync_fields=True):
        actor = self.combat_session.combatants[self.session_actor_key]
        target = self.combat_session.combatants[self.session_target_key]
        actor_conditions = ", ".join(actor.conditions) or t("session_no_conditions")
        target_conditions = ", ".join(target.conditions) or t("session_no_conditions")
        self.session_summary.set(t(
            "session_summary", actor=actor.name, actor_hp=actor.current_hp, actor_max=actor.max_hp,
            actor_conditions=actor_conditions, target=target.name, target_hp=target.current_hp,
            target_max=target.max_hp, target_conditions=target_conditions,
            seconds=self.combat_session.elapsed_seconds,
        ))
        if sync_fields:
            if hasattr(self, "melee_attacker_st"):
                self.melee_attacker_st.set(str(actor.st))
                self.melee_target_hp.set(str(target.current_hp))
                self.melee_target_ht.set(str(target.ht))
                self._load_target_defense()
            if hasattr(self, "injury_target_hp"):
                self.injury_target_hp.set(str(target.current_hp))
                self.injury_target_ht.set(str(target.ht))
                self.injury_natural_dr.set(str(target.armor.natural_dr))
            self._refresh_session_reserves()
        if hasattr(self, "injury_armor_summary"):
            self._refresh_armor_summary()
        if hasattr(self, "refresh_home_session"):
            self.refresh_home_session()
        window = getattr(self, "_combat_prep_window", None)
        if window is not None and window.winfo_exists():
            window.refresh_from_session()
        self._battle_map_changed()

    def _advance_session_time(self, seconds):
        try:
            results = self.combat_session.advance_time(seconds)
            self._refresh_session_summary(sync_fields=True)
            if hasattr(self, "injury_result_text"):
                lines = [t("session_time_advanced", seconds=seconds)]
                for item in results:
                    lines.append(t(
                        "session_bleeding_result", combatant=self.combat_session.combatants[item["combatant"]].name,
                        location=t("injury_location_" + item["location"]), roll=item["roll"],
                        target=item["target"], loss=item["hp_loss"],
                    ))
                self.injury_result_text.delete(1.0, tk.END)
                self.injury_result_text.insert(tk.END, "\n".join(lines))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _undo_session(self):
        try:
            if self.combat_session.undo():
                self._session_changed()
            else:
                messagebox.showinfo(t("session_title"), t("session_nothing_to_undo"))
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))

    def _new_session(self):
        if not messagebox.askyesno(t("session_new"), t("session_new_confirm")):
            return
        try:
            self._replace_active_session(CombatSession.new(self.combat_session.autosave_path))
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))

    def _replace_active_session(self, candidate):
        candidate.save()
        self.combat_session = candidate
        self.session_actor_key, self.session_target_key = candidate.selected_pair()
        # Even a reopened snapshot with the same IDs is a new scenario context.
        self._session_reserve_actor = None
        self._map_ranged_transfer = None
        self._ranged_drafts = {}
        self._clear_ranged_draft()
        self._refresh_handoff_choices()
        self._session_changed()

    def _session_changed(self):
        self.session_actor_key, self.session_target_key = self.combat_session.selected_pair(
            self.session_actor_key, self.session_target_key)
        self._last_melee_result = None
        self._last_grapple_result = None
        self._last_injury_result = None
        self._pending_session_context = {}
        self._supernatural_drafts.clear()
        labels = self._session_labels()
        names = {value: key for key, value in labels.items()}
        for box in self._session_boxes:
            box["values"] = tuple(labels)
        self.session_actor.set(names[self.session_actor_key])
        self.session_target.set(names[self.session_target_key])
        self._refresh_session_summary()

    def _use_session_weapons(self):
        actor = self.combat_session.combatants[self.session_actor_key]
        target = self.combat_session.combatants[self.session_target_key]
        melee = self.melee_weapon_catalog.get(actor.melee_weapon_id)
        ranged = self.weapon_catalog.get(actor.ranged_weapon_id)
        if melee:
            self.melee_search.set("")
            self._populate_melee_weapons(self.melee_weapon_catalog.search())
            label = next(key for key, item in self._melee_weapon_labels.items() if item.identifier == melee.identifier)
            self.melee_weapon.set(label)
            self._load_selected_melee_weapon()
        if ranged:
            self.ranged_search.set("")
            self._populate_ranged_weapon_box(self.weapon_catalog.search())
            label = next(key for key, identifier in self._ranged_weapon_map.items() if identifier == ranged.identifier)
            self.ranged_weapon.set(label)
            self._load_selected_weapon()
        self.ranged_shooter_st.set(str(actor.st))
        missing = []
        if target.unknown_size_modifier:
            missing.append(t("encounter_ranged_sm_missing"))
        else:
            self.ranged_sm.set(str(target.size_modifier))
        if "dodge" in target.unknown_defenses:
            self.ranged_dodge.set("")
            missing.append(t("encounter_ranged_dodge_missing"))
        else:
            self.ranged_dodge.set(str(target.dodge))
        self.ranged_target_aware.set(target.aware)
        self.ranged_target_hp.set(str(target.max_hp))
        if missing:
            messagebox.showinfo(t("tab_ranged"), "\n".join(missing))

    def _optional_injury_rules(self):
        return OptionalInjuryRules(
            bleeding=self.injury_rule_bleeding.get(),
            severe_bleeding=self.injury_rule_severe_bleeding.get(),
            accumulated_wounds=self.injury_rule_accumulated.get(),
            partial_injury=self.injury_rule_partial.get(),
            lasting_injury=self.injury_rule_lasting.get(),
            armor_gaps=self.injury_rule_gaps.get(),
            harsh_layering=self.injury_rule_layering.get(),
            edge_protection=self.injury_rule_edge.get(),
            plate_degradation=self.injury_rule_degradation.get(),
        )

    # ─── Corpo a corpo / Melee ───────────────────────────────────
    def _populate_melee_weapons(self, records):
        labels = {
            "{} — {} p.{} [{}]".format(item.name, item.source, item.page, item.identifier): item
            for item in records
        }
        self._melee_weapon_labels = labels
        self.melee_weapon_box["values"] = list(labels)
        if labels:
            current = self.melee_weapon.get()
            if current not in labels:
                self.melee_weapon.set(next(iter(labels)))
            self._load_selected_melee_weapon()

    def _filter_melee_weapons(self):
        selected = set(self._selected_sources())
        self._populate_melee_weapons([
            item for item in self.melee_weapon_catalog.search(self.melee_search.get())
            if item.source in selected or item.source == "Custom"
        ])

    def _load_selected_melee_weapon(self, _event=None):
        record = getattr(self, "_melee_weapon_labels", {}).get(self.melee_weapon.get())
        if not record:
            return
        self._melee_base_weapon = record
        mode = record.damage_modes[0]
        self.melee_weapon_name.set(record.name)
        self.melee_damage.set(mode.damage)
        self.melee_damage_type.set(mode.damage_type)
        self.melee_armor_divisor.set(str(mode.armor_divisor).rstrip("0").rstrip("."))
        self.melee_reach.set(", ".join(mode.reach))
        self.melee_parry.set(mode.parry)
        self.melee_min_st.set(str(mode.minimum_st or ""))
        first_reach = next((item.replace("*", "") for item in mode.reach if item.replace("*", "").isdigit()), None)
        if first_reach:
            self.melee_distance.set(first_reach)
        elif "C" in mode.reach:
            self.melee_distance.set("0.5")

    def _change_melee_profile(self, _event=None):
        self.melee_profile_key = self._melee_profile_labels[self.melee_profile.get()]
        self._populate_melee_styles()
        self._populate_melee_techniques()

    def _populate_melee_styles(self):
        records = self.style_catalog.search(profile=self.melee_profile_key)
        labels = {t("common_none"): None}
        labels.update({"{} — p.{}".format(item.name, item.page): item for item in records})
        self._melee_style_labels = labels
        self.melee_style_box["values"] = list(labels)
        if self.melee_style.get() not in labels:
            self.melee_style.set(t("common_none"))

    def _populate_melee_techniques(self):
        if not hasattr(self, "melee_technique_box"):
            return
        records = self.technique_catalog.search(
            profile=self.melee_profile_key, include_silly=self.melee_allow_silly.get()
        )
        labels = {t("common_none"): None}
        labels.update({"{} — p.{}".format(item.name, item.page): item for item in records})
        self._melee_technique_labels = labels
        self.melee_technique_box["values"] = list(labels)
        if self.melee_technique.get() not in labels:
            self.melee_technique.set(t("common_none"))

    def _current_melee_weapon(self):
        base = getattr(self, "_melee_base_weapon", None)
        original_mode = base.damage_modes[0] if base and base.damage_modes else None
        mode = MeleeDamageMode(
            damage=self.melee_damage.get().strip(),
            damage_type=self.melee_damage_type.get().strip().lower(),
            reach=[item.strip() for item in self.melee_reach.get().split(",") if item.strip()] or ["C"],
            parry=self.melee_parry.get().strip() or "0",
            armor_divisor=self._optional_number(self.melee_armor_divisor, float, 1.0),
            minimum_st=self._optional_number(self.melee_min_st, int, 0),
            two_handed=original_mode.two_handed if original_mode else False,
            becomes_unready=original_mode.becomes_unready if original_mode else False,
            requires_ready_to_change_reach=original_mode.requires_ready_to_change_reach if original_mode else False,
            attack_label=original_mode.attack_label if original_mode else "",
            linked_effects=deepcopy(original_mode.linked_effects) if original_mode else [],
            raw=original_mode.raw if original_mode else self.melee_damage.get().strip(),
        )
        return MeleeWeaponRecord(
            identifier=base.identifier if base else "custom.current.melee",
            source=base.source if base else "Custom", page=base.page if base else "-",
            name=self.melee_weapon_name.get().strip() or t("melee_custom_weapon"),
            tech_level=base.tech_level if base else "-", category=base.category if base else "Custom",
            skills=list(base.skills) if base else [], damage_modes=[mode],
            cost=base.cost if base else "", weight=base.weight if base else 0,
            legality_class=base.legality_class if base else "", quality=base.quality if base else "normal",
            natural_weapon=base.natural_weapon if base else False,
            training_weapon=base.training_weapon if base else False,
            tags=list(base.tags) if base else ["custom"], aliases=list(base.aliases) if base else [],
            original=dict(base.original) if base else {},
        )

    def _current_melee_input(self):
        actor = deepcopy(self.combat_session.combatants[self.session_actor_key])
        target = deepcopy(self.combat_session.combatants[self.session_target_key])
        actor.st = self._optional_number(self.melee_attacker_st, int, actor.st)
        current_hp = self._optional_number(self.melee_target_hp, int, target.current_hp)
        target.current_hp = current_hp
        target.max_hp = max(target.max_hp, 1, current_hp)
        target.ht = self._optional_number(self.melee_target_ht, int, target.ht)
        target.armor.natural_dr = self._optional_number(self.melee_target_dr, int, target.armor.natural_dr)
        technique = getattr(self, "_melee_technique_labels", {}).get(self.melee_technique.get())
        style = getattr(self, "_melee_style_labels", {}).get(self.melee_style.get())
        feint_condition = next((
            item for item in target.conditions
            if item.startswith("feint:" + actor.identifier + ":")
        ), "")
        feint_penalty = int(feint_condition.rsplit(":", 1)[-1]) if feint_condition else 0
        attacker_posture = {
            "crouching": -2, "kneeling": -2, "sitting": -2, "crawling": -4,
            "prone": -4, "lying": -4,
        }.get(actor.posture, 0)
        target_posture = {
            "crouching": 0, "kneeling": -2, "sitting": -2, "crawling": -3,
            "prone": -3, "lying": -3,
        }.get(target.posture, 0)
        return MeleeAttackInput(
            weapon=self._current_melee_weapon(), attacker=actor, target=target,
            profile=self.melee_profile_key, source_set=self._selected_sources(),
            skill=self._optional_number(self.melee_skill, int, 0), maneuver=self.melee_maneuver_key,
            technique=technique, style=style, allow_silly=self.melee_allow_silly.get(),
            distance_yards=self._optional_number(self.melee_distance, float, 1.0),
            hit_location=self.melee_location_key,
            deceptive_attack_penalty=self._optional_number(self.melee_deceptive, int, 0),
            feint_defense_penalty=feint_penalty, feint_condition=feint_condition,
            telegraphic_attack=self.melee_telegraphic.get(),
            rapid_strike_attacks=self._optional_number(self.melee_rapid_strikes, int, 1),
            trained_by_master=self.melee_trained_by_master.get(), weapon_master=self.melee_weapon_master.get(),
            dual_weapon_attack=self.melee_dual_weapon.get(), offhand=self.melee_offhand.get(),
            ambidextrous=self.melee_ambidextrous.get(), custom_modifier=self._optional_number(self.melee_custom_modifier, int, 0),
            weapon_ready="weapon_unready" not in actor.conditions,
            attacker_posture_modifier=attacker_posture, target_posture_modifier=target_posture,
            new_posture=self.melee_new_posture_key,
            target_aware=self.melee_target_aware.get(), defense_type=self.melee_defense_key,
            defense_score=self._session_defense(target, self.melee_target_aware.get() and not target.unconscious
                                                and self.melee_maneuver_key not in {"evaluate", "feint", "ready", "change_posture", "do_nothing"}),
            retreat=self.melee_retreat_key,
            optional_injury_rules=self._optional_injury_rules(),
        )

    def _run_melee(self, operation):
        self._last_grapple_result = None
        try:
            data = self._current_melee_input()
            if operation == "calculate":
                result = self.melee_calc.calculate(data)
            else:
                result = self.melee_calc.resolve(
                    data, resolve_defense=operation == "resolve", resolve_damage=operation == "resolve"
                )
            self._last_melee_result = result if operation == "resolve" and result.valid else None
            remember_session(self, 'melee')
            lines = [t("melee_summary", weapon=data.weapon.name, profile=t("rules_profile_" + result.profile))]
            if result.errors:
                lines.append(t("common_problems") + " " + ", ".join(t("melee_error_" + item) for item in result.errors))
            lines.extend(("", t("melee_modifier_memory")))
            for item in result.modifiers:
                lines.append("{:+d}  {} — {} p.{}{}".format(
                    item["value"], t("melee_modifier_" + item["key"]), item["source"], item["page"],
                    " ({})".format(item["detail"]) if item["detail"] else "",
                ))
            skill_line = t("melee_effective_skill", value=result.effective_skill, probability=result.probability)
            self.melee_result_text.oficina_highlights = (skill_line,) if result.valid else ()
            lines.append(skill_line)
            if result.defense_score is not None:
                lines.append(t("melee_effective_defense", value=result.defense_score))
            for restriction in result.defense_restrictions:
                lines.append(t("melee_restriction_" + restriction))
            for attack in result.attacks:
                outcome = attack["attack"]
                lines.extend(("", t("melee_attack_result", index=attack["index"], roll=outcome["roll"], margin=outcome["margin"])))
                if attack["defense"]:
                    defense = attack["defense"]
                    lines.append(t("melee_defense_result", roll=defense["roll"], target=defense["target"], success=t("common_yes") if defense["success"] else t("common_no")))
                lines.append(t("melee_hit_result", value=t("common_yes") if attack["hit"] else t("common_no")))
                if attack["damage"]:
                    injury = attack["damage"]["injury"]
                    lines.append(t(
                        "melee_damage_result", expression=attack["damage"]["expression"],
                        basic=attack["damage"]["basic_damage"], dr=injury["effective_dr"],
                        penetrating=injury["penetrating_damage"], injury=injury["injury"],
                    ))
            for pending in result.pending_effects:
                if pending["kind"] == "feint" and "contest" in pending:
                    contest = pending["contest"]
                    lines.append(t(
                        "melee_feint_result", actor_roll=contest["actor"]["roll"],
                        target_roll=contest["target"]["roll"], penalty=pending["defense_penalty"],
                    ))
                elif pending["kind"] == "stun_recovery" and "roll" in pending:
                    recovery = pending["roll"]
                    lines.append(t(
                        "melee_stun_recovery", roll=recovery["roll"], target=recovery["target"],
                        success=t("common_yes") if recovery["success"] else t("common_no"),
                    ))
                else:
                    lines.append(t("melee_pending_effect", value=pending["kind"]))
            if result.notes:
                lines.append(t("common_notes") + " " + ", ".join(t("melee_note_" + item) for item in result.notes))
            lines.append("")
            lines.append(t("common_references") + " " + "; ".join(
                "{} p.{}".format(ref.source, ref.page) for ref in result.references
            ))
            self.melee_result_text.delete(1.0, tk.END)
            self.melee_result_text.insert(tk.END, "\n".join(lines))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _apply_melee_result(self):
        if self._last_melee_result is None:
            messagebox.showinfo(t("session_title"), t("session_nothing_to_apply"))
            return
        if not confirm_session(self, 'melee', self._last_melee_result.state_delta, self._last_melee_result.attacker_delta):
            return
        try:
            self.combat_session.apply_action(
                self.session_actor_key, self.session_target_key,
                self._last_melee_result.state_delta, self._last_melee_result.attacker_delta, "melee_attack",
            )
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))
            return
        self._last_melee_result = None
        self._refresh_session_summary(sync_fields=True)
        self.melee_result_text.insert(tk.END, "\n\n" + t("session_applied"))

    def _save_melee_preset(self):
        try:
            record = self._current_melee_weapon()
            slug = re.sub(r"[^a-z0-9]+", "-", record.name.casefold()).strip("-") or "weapon"
            record.identifier = "custom.melee-weapon." + slug
            record.source, record.page = "Custom", "-"
            self.melee_weapon_catalog.save_custom(record)
            self._populate_melee_weapons(self.melee_weapon_catalog.search(self.melee_search.get()))
            messagebox.showinfo(t("melee_preset_title"), t("melee_preset_saved"))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _import_melee_presets(self):
        filename = filedialog.askopenfilename(
            title=t("melee_import_title"), filetypes=[(t("common_json_files"), "*.json")],
        )
        if not filename:
            return
        try:
            count = self.melee_weapon_catalog.import_file(Path(filename))
            self._populate_melee_weapons(self.melee_weapon_catalog.search(self.melee_search.get()))
            messagebox.showinfo(t("melee_preset_title"), t("common_imported_count", count=count))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _export_melee_presets(self):
        filename = filedialog.asksaveasfilename(
            title=t("melee_export_title"), defaultextension=".json",
            filetypes=[(t("common_json_files"), "*.json")],
        )
        if not filename:
            return
        try:
            records = list(self.melee_weapon_catalog.custom)
            if not records:
                record = self._current_melee_weapon()
                slug = re.sub(r"[^a-z0-9]+", "-", record.name.casefold()).strip("-") or "weapon"
                record.identifier = "custom.melee-weapon." + slug
                record.source, record.page = "Custom", "-"
                records = [record]
            self.melee_weapon_catalog.export_file(Path(filename), records)
            messagebox.showinfo(t("melee_preset_title"), t("common_exported_count", count=len(records)))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _run_grapple(self):
        try:
            actor = deepcopy(self.combat_session.combatants[self.session_actor_key])
            target = deepcopy(self.combat_session.combatants[self.session_target_key])
            result = self.grappling_calc.resolve(GrappleActionInput(
                actor=actor, target=target, action=self.melee_grapple_action_key,
                profile=self.melee_profile_key,
                skill=self._optional_number(self.melee_skill, int, actor.dx),
                resistance=self._optional_number(self.melee_grapple_resistance, int),
                defense_score=self._session_defense(target, target.aware and
                                                    self.melee_grapple_action_key in {"grapple", "shove"}),
                defense_type=self.melee_defense_key,
                location=self.melee_location_key,
                two_handed=self.melee_grapple_two_handed.get(),
                technique=getattr(self, "_melee_technique_labels", {}).get(self.melee_technique.get()),
            ))
            self._last_grapple_result = result if result.valid else None
            self._last_melee_result = None
            remember_session(self, 'grapple')
            lines = [t(
                "grapple_summary", action=t("grapple_action_" + result.action),
                success=t("common_yes") if result.success else t("common_no"),
            )]
            if result.errors:
                lines.append(t("common_problems") + " " + ", ".join(
                    t("grapple_error_" + item) for item in result.errors
                ))
            if result.attack:
                lines.append(t(
                    "grapple_attack_result", roll=result.attack["roll"],
                    target=result.attack["target"], margin=result.attack["margin"],
                ))
            if result.defense:
                lines.append(t(
                    "grapple_defense_result", roll=result.defense["roll"],
                    target=result.defense["target"], success=t("common_yes") if result.defense["success"] else t("common_no"),
                ))
            if result.contest:
                lines.append(t(
                    "grapple_contest_result", actor_roll=result.contest["actor"]["roll"],
                    actor_margin=result.contest["actor_margin"], target_roll=result.contest["target"]["roll"],
                    target_margin=result.contest["target_margin"],
                ))
            if result.damage:
                lines.append(t("grapple_damage_result", value=result.damage.injury))
            for pending in result.pending_effects:
                lines.append(t("melee_pending_effect", value=pending["kind"]))
            lines.append(t("common_references") + " " + "; ".join(
                "{} p.{}".format(ref.source, ref.page) for ref in result.references
            ))
            self.melee_result_text.delete(1.0, tk.END)
            self.melee_result_text.insert(tk.END, "\n".join(lines))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _apply_grapple_result(self):
        if self._last_grapple_result is None:
            messagebox.showinfo(t("session_title"), t("session_nothing_to_apply"))
            return
        if not confirm_session(self, 'grapple', self._last_grapple_result.target_delta, self._last_grapple_result.actor_delta):
            return
        try:
            self.combat_session.apply_action(
                self.session_actor_key, self.session_target_key,
                self._last_grapple_result.target_delta, self._last_grapple_result.actor_delta,
                "grappling_" + self._last_grapple_result.action,
            )
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))
            return
        self._last_grapple_result = None
        self._refresh_session_summary(sync_fields=True)
        self.melee_result_text.insert(tk.END, "\n\n" + t("session_applied"))

    # ─── Trauma / Injury ─────────────────────────────────────────
    def _populate_armor(self, records):
        labels = {
            "{} — {} p.{} [DR {}]".format(item.name, item.source, item.page, item.dr): item
            for item in records
        }
        self._armor_labels = labels
        self.injury_armor_box["values"] = list(labels)
        if labels and self.injury_armor.get() not in labels:
            self.injury_armor.set(next(iter(labels)))

    def _filter_armor(self):
        selected = set(self._selected_sources())
        self._populate_armor([
            item for item in self.armor_catalog.search(self.injury_armor_search.get())
            if item.source in selected or item.source == "Custom"
        ])

    def _equip_selected_armor(self):
        armor = getattr(self, "_armor_labels", {}).get(self.injury_armor.get())
        if armor is None:
            return
        try:
            self.combat_session.equip_armor(self.session_target_key, armor)
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))
            return
        self._refresh_session_summary(sync_fields=True)

    def _clear_target_armor(self):
        try:
            self.combat_session.clear_armor(self.session_target_key)
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))
            return
        self._refresh_session_summary(sync_fields=True)

    def _import_armor_presets(self):
        filename = filedialog.askopenfilename(
            title=t("injury_armor_import_title"), filetypes=[(t("common_json_files"), "*.json")],
        )
        if not filename:
            return
        try:
            count = self.armor_catalog.import_file(Path(filename))
            self._populate_armor(self.armor_catalog.search(self.injury_armor_search.get()))
            messagebox.showinfo(t("injury_section_armor"), t("common_imported_count", count=count))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _export_selected_armor(self):
        armor = getattr(self, "_armor_labels", {}).get(self.injury_armor.get())
        if armor is None:
            return
        filename = filedialog.asksaveasfilename(
            title=t("injury_armor_export_title"), defaultextension=".json",
            filetypes=[(t("common_json_files"), "*.json")],
        )
        if not filename:
            return
        try:
            record = deepcopy(armor)
            slug = re.sub(r"[^a-z0-9]+", "-", record.name.casefold()).strip("-") or "armor"
            record.identifier = "custom.armor." + slug
            record.source, record.page = "Custom", "-"
            self.armor_catalog.export_file(Path(filename), [record])
            messagebox.showinfo(t("injury_section_armor"), t("common_exported_count", count=1))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _refresh_armor_summary(self):
        target = self.combat_session.combatants[self.session_target_key]
        if not target.armor.layers:
            self.injury_armor_summary.set(t("injury_no_armor"))
            return
        self.injury_armor_summary.set(t("injury_equipped_armor", value=", ".join(
            "{} (DR {})".format(layer.armor.name, layer.armor.dr) for layer in target.armor.layers
        )))

    def _current_injury_input(self):
        target = deepcopy(self.combat_session.combatants[self.session_target_key])
        if self._injury_ranged_draft is not None:
            draft = self._injury_ranged_draft
            return InjuryInput(packet=replace(draft.packet, direction=self.injury_direction_key,
                                              chinks=self.injury_chinks.get()), target=target,
                               profile=draft.profile, optional_rules=self._optional_injury_rules())
        current_hp = self._optional_number(self.injury_target_hp, int, target.current_hp)
        target.current_hp = current_hp
        target.max_hp = max(target.max_hp, 1, current_hp)
        target.ht = self._optional_number(self.injury_target_ht, int, target.ht)
        target.armor.natural_dr = self._optional_number(self.injury_natural_dr, int, target.armor.natural_dr)
        packet = DamagePacket(
            basic_damage=self._optional_number(self.injury_basic_damage, int, 0),
            damage_type=self.injury_damage_type.get().strip().lower(),
            armor_divisor=self._optional_number(self.injury_armor_divisor, float, 1.0),
            hit_location=self.injury_location_key, direction=self.injury_direction_key,
            source="Manual", page="-", large_area=self.injury_large_area.get(),
            chinks=self.injury_chinks.get(),
        )
        return InjuryInput(
            packet=packet, target=target, profile=self.injury_profile_key,
            optional_rules=self._optional_injury_rules(),
        )

    def _run_injury(self, operation):
        self._last_injury_result = None
        self._injury_draft_resolved = False
        try:
            data = self._current_injury_input()
            result = self.injury_calc.calculate(data) if operation == "calculate" else self.injury_calc.resolve(data)
            self._last_injury_result = result if result.valid else None
            self._injury_draft_resolved = operation == "resolve" and result.valid
            remember_session(self, 'injury')
            lines = [t("injury_summary", profile=t("rules_profile_" + result.profile), location=t("injury_location_" + data.packet.hit_location))]
            if result.errors:
                lines.append(t("common_problems") + " " + ", ".join(t("injury_error_" + item) for item in result.errors))
            final_line = t("injury_final_result", value=result.injury, before=result.target_hp_before,
                           after=result.target_hp_after)
            self.injury_result_text.oficina_highlights = (final_line,) if result.valid else ()
            lines.extend((
                t("injury_basic_result", value=data.packet.basic_damage),
                t("injury_dr_result", total=result.total_dr, effective=result.effective_dr, divisor=data.packet.armor_divisor),
                t("injury_penetrating_result", value=result.penetrating_damage),
                t("injury_wounding_result", value=result.wounding_modifier),
                final_line,
            ))
            if result.blunt_trauma:
                lines.append(t("injury_blunt_trauma_result", value=result.blunt_trauma))
            if result.major_wound:
                lines.append(t("injury_major_wound"))
            if result.crippling:
                lines.append(t("injury_crippling", location=t("injury_location_" + data.packet.hit_location)))
            if result.dismemberment:
                lines.append(t("injury_dismemberment", location=t("injury_location_" + data.packet.hit_location)))
            for layer in result.armor_layers:
                lines.append(t("injury_layer_result", name=layer["name"], dr=layer["dr"], protects=t("common_yes") if layer["protects"] else t("common_no")))
            for check in result.checks:
                if "roll" in check:
                    lines.append(t("injury_check_result", kind=check["kind"], roll=check["roll"], target=check["target"], success=t("common_yes") if check["success"] else t("common_no")))
                else:
                    lines.append(t(
                        "injury_check_pending", kind=check["kind"],
                        target=check.get("target", t("injury_manual_resolution")),
                    ))
            if result.notes:
                lines.append(t("common_notes") + " " + ", ".join(result.notes))
            lines.append(t("common_references") + " " + "; ".join(
                "{} p.{}".format(ref.source, ref.page) for ref in result.references
            ))
            self.injury_result_text.delete(1.0, tk.END)
            self.injury_result_text.insert(tk.END, "\n".join(lines))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _apply_injury_result(self):
        if self._last_injury_result is None:
            messagebox.showinfo(t("session_title"), t("session_nothing_to_apply"))
            return
        if self._injury_ranged_draft and not self._injury_draft_resolved:
            messagebox.showinfo(t("session_title"), t("handoff_resolve_first"))
            return
        if not confirm_session(self, 'injury', self._last_injury_result.state_delta):
            return
        draft = self._injury_ranged_draft
        try:
            self.combat_session.apply(
                self.session_actor_key, self.session_target_key, self._last_injury_result.state_delta,
                "ranged_injury" if draft else "manual_injury", advance_action=False,
            )
        except OSError as exc:
            messagebox.showerror(t("session_title"), t("local_data_save_error", error=exc))
            return
        if draft:
            if self._ranged_drafts.get(draft.number) is draft:
                del self._ranged_drafts[draft.number]
            self._refresh_handoff_choices()
            self._clear_ranged_draft()
        self._last_injury_result = None
        self._refresh_session_summary(sync_fields=True)
        self.injury_result_text.insert(tk.END, "\n\n" + t("session_applied"))

    # ─── Combate legado (API preservada) ─────────────────────────
    def _roll_combat_attack(self):
        """
        Rola ataque usando Attack Skill (não ST).
        
        Attack Skill é a habilidade para acertar (ex: Sword-15).
        ST é separado e usado apenas para dano.
        """
        try:
            result = self.combat_calc.calculate_attack_roll(
                effective_skill=self.combat_attack_skill.get()
            )
            self.combat_result_text.delete(1.0, tk.END)
            self.combat_result_text.insert(tk.END,
                f"{t('combat_attack_header')}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_skill_label', value=result['effective_skill'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_roll_label', value=result['roll_result'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_result_label', value=t('combat_outcome_' + result['outcome'], margin=result['margin']))}\n")
        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    def _roll_combat_defense(self):
        """Rola defesa usando Effective Defense."""
        try:
            result = self.combat_calc.calculate_defense_roll(
                effective_defense=self.combat_defense.get()
            )
            self.combat_result_text.delete(1.0, tk.END)
            self.combat_result_text.insert(tk.END,
                f"{t('combat_defense_header')}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_defense_label', value=result['effective_defense'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_roll_label', value=result['roll_result'])}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_result_label', value=t('combat_outcome_' + result['outcome'], margin=result['margin']))}\n")
        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    def _roll_combat_damage(self):
        """
        Rola dano usando ST (Força), NÃO Attack Skill.
        
        ST determina thrust/swing via Damage Table (p. 16).
        Attack Skill é apenas para acertar.
        """
        try:
            # Usa o campo ST separado para dano
            st = self.combat_st.get()
            entry = self.combat_calc.get_damage_table_entry(st)
            from utils.dice_roller import roll_dice
            thrust_result, _ = roll_dice(entry["thrust"])
            swing_result, _ = roll_dice(entry["swing"])

            self.combat_result_text.delete(1.0, tk.END)
            self.combat_result_text.insert(tk.END,
                f"{t('combat_damage_header', st=st)}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_thrust_damage', expression=entry['thrust'], value=thrust_result)}\n")
            self.combat_result_text.insert(tk.END,
                f"{t('combat_swing_damage', expression=entry['swing'], value=swing_result)}\n")
        except Exception as e:
            messagebox.showerror(t("common_error_title"), str(e))

    # ─── Tiro / Ranged Combat ───────────────────────────────────
    @staticmethod
    def _map_pair_geometry(model, actor_id, target_id):
        first = model.tokens.get(actor_id)
        second = model.tokens.get(target_id)
        if first is None or second is None:
            return None
        return (model.grid, model.cell_size, model.origin_x, model.origin_y, model.yards_per_cell,
                first.q, first.r, second.q, second.r)

    def _send_map_distance_to_ranged(self, actor_id, target_id, yards):
        model = self.combat_session.battle_map
        combatants = self.combat_session.combatants
        geometry = self._map_pair_geometry(model, actor_id, target_id)
        if (actor_id == target_id or actor_id not in combatants or target_id not in combatants
                or geometry is None or not math.isfinite(yards) or yards < 0):
            raise ValueError("map_need_pair")
        measured = model.distance_yards(*geometry[-4:])
        if not math.isclose(measured, yards, rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError("map_settings_stale")
        self.session_actor_key, self.session_target_key = actor_id, target_id
        self._session_changed()
        meters = measured * YARDS_TO_METERS
        self._map_ranged_transfer = (actor_id, target_id, geometry, measured, meters,
                                     combatants[actor_id].name, combatants[target_id].name)
        self.ranged_distance.set(repr(meters))
        self._refresh_ranged_map_hint()
        self.choose_tool(8)

    def _refresh_ranged_map_hint(self, *_):
        transfer = self._map_ranged_transfer
        if transfer is not None:
            actor_id, target_id, geometry, yards, meters, actor_name, target_name = transfer
            try:
                current = self._optional_number(self.ranged_distance, float)
            except ValueError:
                current = None
            if current is None or not math.isclose(current, meters, rel_tol=1e-14, abs_tol=1e-14):
                transfer = self._map_ranged_transfer = None
        text = ""
        if transfer is not None:
            text = t("ranged_map_distance", actor=actor_name, target=target_name,
                     distance=UnitSystem(self.result_units.get()).display(yards, "yards"))
            if ((actor_id, target_id) != (self.session_actor_key, self.session_target_key)
                    or geometry != self._map_pair_geometry(self.combat_session.battle_map, actor_id, target_id)):
                text += "\n" + t("ranged_map_distance_stale")
        self.ranged_map_hint.set(text)
        label = getattr(self, "ranged_map_hint_label", None)
        if label is not None and label.winfo_exists():
            if text and not label.winfo_manager():
                label.pack(fill=tk.X, pady=(0, 5))
            elif not text:
                label.pack_forget()

    @staticmethod
    def _optional_number(variable, converter=float, default=None):
        value = variable.get().strip()
        return default if value == "" else converter(value.replace(",", "."))

    def _current_ranged_weapon(self):
        base = getattr(self, "_ranged_base_weapon", None)
        mode = replace(base.damage_modes[0] if base else DamageMode("1d", "cr"),
            dice=self.ranged_damage.get().strip(),
            damage_type=self.ranged_damage_type.get().strip().lower(),
            armor_divisor=self._optional_number(self.ranged_armor_divisor, float, 1.0),
            minimum_range=self._optional_number(self.ranged_minimum_range, float, 0.0),
            half_damage_range=self._optional_number(self.ranged_half_damage, float),
            max_range=self._optional_number(self.ranged_max_range, float),
        )
        rof = self._optional_number(self.ranged_rof, float, 1.0)
        return WeaponRecord(
            identifier=base.identifier if base else "custom.current",
            source=base.source if base else "Custom",
            page=base.page if base else "-",
            name=self.ranged_weapon_name.get().strip() or t("ranged_custom_weapon"),
            tech_level=base.tech_level if base else "-",
            category=base.category if base else "Custom",
            skills=list(base.skills) if base else [],
            damage_modes=[mode],
            accuracy=self._optional_number(self.ranged_acc, int, 0),
            range_raw="{}/{}".format(self.ranged_half_damage.get(), self.ranged_max_range.get()),
            weight_raw=base.weight_raw if base else "",
            rate_of_fire_modes=[rof],
            projectiles_per_shot=self._optional_number(self.ranged_projectiles, int, 1),
            shots_raw=self.ranged_shots_stat.get().strip(),
            shots_capacity=base.shots_capacity if base else None,
            chamber_capacity=base.chamber_capacity if base else 0,
            reload_seconds=base.reload_seconds if base else None,
            reload_individual=base.reload_individual if base else False,
            strength=self._optional_number(self.ranged_required_st, int),
            strength_flags=base.strength_flags if base else "",
            bulk=self._optional_number(self.ranged_bulk, int),
            recoil=self._optional_number(self.ranged_rcl, int, 1),
            recoil_secondary=base.recoil_secondary if base else None,
            malfunction=self._optional_number(self.ranged_malf, int, 17),
            full_auto_only=base.full_auto_only if base else False,
            cost=base.cost if base else "",
            legality_class=base.legality_class if base else "",
            tags=list(base.tags) if base else ["custom"],
            aliases=list(base.aliases) if base else [],
            original=dict(base.original) if base else {},
        )

    def _current_ranged_input(self):
        transfer = self._map_ranged_transfer
        return RangedAttackInput(
            weapon=self._current_ranged_weapon(),
            profile=self.ranged_profile_key,
            skill=self._optional_number(self.ranged_skill, int, 0),
            distance_m=self._optional_number(self.ranged_distance, float, 0.0),
            map_distance_yards=transfer[3] if transfer is not None else None,
            target_speed_mps=self._optional_number(self.ranged_speed, float, 0.0),
            target_sm=self._optional_number(self.ranged_sm, int, 0),
            aim_seconds=self._optional_number(self.ranged_aim_seconds, int, 0),
            aim_lost=self.ranged_aim_lost.get(),
            braced=self.ranged_braced.get(),
            scope_bonus=self._optional_number(self.ranged_scope, int, 0),
            laser_bonus=self._optional_number(self.ranged_laser, int, 0),
            targeting_system_bonus=self._optional_number(self.ranged_targeting, int, 0),
            maneuver=self.ranged_maneuver_key,
            shots_fired=self._optional_number(self.ranged_shots_fired, int, 1),
            hit_location=self.ranged_location_key,
            posture_modifier=self._optional_number(self.ranged_posture, int, 0),
            cover_modifier=self._optional_number(self.ranged_cover, int, 0),
            visibility_modifier=self._optional_number(self.ranged_visibility, int, 0),
            cannot_see_target=self.ranged_cannot_see.get(),
            offhand=self.ranged_offhand.get(),
            shooter_strength=self._optional_number(self.ranged_shooter_st, int),
            custom_modifier=self._optional_number(self.ranged_custom_modifier, int, 0),
            target_aware=self.ranged_target_aware.get(),
            dodge=self._optional_number(self.ranged_dodge, int),
            target_dr=self._optional_number(self.ranged_dr, int, 0),
            target_hp=self._optional_number(self.ranged_target_hp, int, 10),
            rangefinder_bonus=self._optional_number(self.ranged_rangefinder, int, 0),
            precision_aiming_bonus=self._optional_number(self.ranged_precision_aiming, int, 0),
            follow_up_aim_bonus=self._optional_number(self.ranged_follow_up_aim, int, 0),
            fast_firing_modifier=self._optional_number(self.ranged_fast_firing, int, 0),
            cinematic_modifier=self._optional_number(self.ranged_cinematic_modifier, int, 0),
            ammunition=self.ranged_ammunition_key,
            minute_of_angle=self.ranged_minute_of_angle.get(),
        )

    def _run_ranged(self, operation):
        self._ranged_drafts = {}
        self._refresh_handoff_choices()
        try:
            attack_input = self._current_ranged_input()
            result = (self.ranged_calc.calculate(attack_input) if operation == "calculate"
                      else self.ranged_calc.resolve(
                          attack_input,
                          resolve_defense=operation == "resolve",
                          resolve_damage=operation == "resolve",
                      ))
            self._ranged_metrics = (result.effective_skill, result.probability) if result.valid else None
            self.ranged_layout.set_metrics(self._ranged_metrics)
            self.ranged_result_text.delete(1.0, tk.END)
            lines = [t("ranged_summary", weapon=attack_input.weapon.name,
                       profile=t("ranged_profile_" + result.profile))]
            lines.append(t("ranged_range_result", meters=attack_input.distance_m,
                           yards=result.distance_yards, valid=t("common_yes") if result.range_valid else t("common_no")))
            if result.beyond_half_damage:
                lines.append(t("ranged_half_damage_warning"))
            lines.append("")
            lines.append(t("ranged_modifier_memory"))
            for modifier in result.modifiers:
                lines.append("{:+d}  {} — {} p.{}{}".format(
                    modifier["value"], t("ranged_modifier_" + modifier["key"]),
                    modifier["source"], modifier["page"],
                    " ({})".format(modifier["detail"]) if modifier["detail"] else "",
                ))
            lines.append(t("ranged_effective_skill", value=result.effective_skill, probability=result.probability))
            if result.errors:
                lines.append(t("ranged_errors") + " " + ", ".join(
                    t("ranged_error_" + error) for error in result.errors
                ))
            if result.attack:
                outcome = ("critical_hit" if result.attack["critical_success"] else
                           "critical_miss" if result.attack["critical_failure"] else
                           "hit" if result.attack["success"] else "miss")
                lines.extend(("", t("ranged_attack_roll", roll=result.attack["roll"],
                                     outcome=t("combat_outcome_" + outcome, margin=result.attack["margin"]))))
                if result.malfunction:
                    lines.append(t("ranged_malfunction"))
                if operation == "attack":
                    lines.append(t("ranged_hits_before_defense", value=result.hits_before_defense))
                else:
                    lines.append(t("ranged_hits_before_defense", value=result.hits_before_defense))
                    if result.defense:
                        lines.append(t("ranged_defense_result", roll=result.defense["roll"],
                                       avoided=result.defense["hits_avoided"]))
                    lines.append(t("ranged_hits_after_defense", value=result.hits_after_defense))
                    for index, damage in enumerate(result.damages, 1):
                        lines.append(t("ranged_damage_result", index=index,
                                       basic=damage["basic_damage"], dr=damage["effective_dr"],
                                       penetrating=damage["penetrating_damage"],
                                       multiplier=damage["wounding_modifier"], injury=damage["injury"]))
            if operation == "resolve" and result.valid:
                for index in range(len(result.damages)):
                    try:
                        draft = RangedHitDraft.from_result(result, attack_input.weapon, index)
                    except ValueError:
                        lines.append(t("handoff_special_hit", number=index + 1))
                    else:
                        self._ranged_drafts[draft.number] = draft
                self._refresh_handoff_choices()
            self.ranged_result_text.insert(tk.END, "\n".join(lines))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _refresh_handoff_choices(self):
        values = tuple(str(number) for number in self._ranged_drafts)
        self._handoff_picker["values"] = values
        self._handoff_selected.set(values[0] if values else "")
        self._handoff_button.state(["!disabled" if values else "disabled"])

    def _open_ranged_draft(self):
        selected = self._handoff_selected.get()
        if not selected or getattr(self.ranged_result_text, "stale", False):
            messagebox.showwarning(t("tab_ranged"), t("handoff_stale"))
            return
        draft = self._ranged_drafts.get(int(selected))
        if draft is None:
            return
        if self._injury_ranged_draft is not None and not messagebox.askyesno(t("tab_injury"), t("handoff_replace")):
            return
        if self._injury_ranged_draft is None:
            self._injury_manual_form = (
                tuple((var, var.get()) for var in (self.injury_basic_damage, self.injury_damage_type,
                      self.injury_armor_divisor, self.injury_chinks, self.injury_large_area)),
                self.injury_location_key, self.injury_profile_key, self.injury_direction_key,
            )
        self._injury_ranged_draft = draft
        self._injury_draft_resolved = False
        self._last_injury_result = None
        self.injury_basic_damage.set(str(draft.packet.basic_damage))
        self.injury_damage_type.set(draft.packet.damage_type)
        self.injury_armor_divisor.set(str(draft.packet.armor_divisor))
        self.injury_location_key = draft.packet.hit_location
        self.injury_profile_key = draft.profile
        self.injury_location.set(next(label for label, key in self._injury_location_labels.items() if key == self.injury_location_key))
        self.injury_profile.set(next(label for label, key in self._injury_profile_labels.items() if key == draft.profile))
        self.injury_direction_key = draft.packet.direction
        self.injury_direction.set(next(label for label, key in self._injury_direction_labels.items() if key == draft.packet.direction))
        self.injury_chinks.set(False)
        self.injury_large_area.set(False)
        self._refresh_session_summary(sync_fields=True)
        self._refresh_ranged_draft()
        self.choose_tool(7)
        self._run_injury("calculate")

    def _clear_ranged_draft(self):
        self._injury_ranged_draft = None
        self._injury_draft_resolved = False
        self._last_injury_result = None
        if self._injury_manual_form:
            fields, self.injury_location_key, self.injury_profile_key, self.injury_direction_key = self._injury_manual_form
            self._injury_manual_form = None
            for var, value in fields:
                var.set(value)
            for variable, key, labels in ((self.injury_location, self.injury_location_key, self._injury_location_labels),
                                          (self.injury_profile, self.injury_profile_key, self._injury_profile_labels),
                                          (self.injury_direction, self.injury_direction_key, self._injury_direction_labels)):
                variable.set(next(label for label, identifier in labels.items() if identifier == key))
        self._refresh_ranged_draft()

    def _refresh_ranged_draft(self):
        draft = self._injury_ranged_draft
        for entry in self._injury_locked_entries:
            entry.configure(state="readonly" if draft else "normal")
        for box in self._injury_locked_boxes:
            box.configure(state="disabled" if draft else "readonly")
        self._injury_large_area_box.state(["disabled" if draft else "!disabled"])
        if not draft:
            self._injury_handoff_banner.pack_forget()
            return
        message = t("handoff_draft", number=draft.number, weapon=draft.weapon_name)
        if draft.half_damage_applied:
            message += " " + t("handoff_half_damage")
        self._injury_handoff_message.configure(text=message)
        self._injury_handoff_banner.pack(side=tk.TOP, fill=tk.X, before=self._injury_scroll_canvas)

    def _save_ranged_preset(self):
        try:
            weapon = self._current_ranged_weapon()
            weapon.identifier = "custom." + re.sub(r"[^a-z0-9]+", "-", weapon.name.casefold()).strip("-")
            weapon.source = "Custom"
            weapon.page = "-"
            self.weapon_catalog.save_custom(weapon)
            self._populate_ranged_weapon_box(self.weapon_catalog.search(self.ranged_search.get()))
            messagebox.showinfo(t("ranged_preset_title"), t("ranged_preset_saved"))
        except Exception as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    def _import_ranged_presets(self):
        path = filedialog.askopenfilename(title=t("ranged_import"), filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            count = self.weapon_catalog.import_file(path)
            self._populate_ranged_weapon_box(self.weapon_catalog.search(self.ranged_search.get()))
            messagebox.showinfo(t("ranged_preset_title"), t("ranged_imported", count=count))
        except ValueError:
            messagebox.showerror(t("common_error_title"), t("ranged_invalid_json"))

    def _export_ranged_presets(self):
        path = filedialog.asksaveasfilename(title=t("ranged_export"), defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self.weapon_catalog.export_file(path)
            messagebox.showinfo(t("ranged_preset_title"), t("ranged_exported"))
        except OSError as exc:
            messagebox.showerror(t("common_error_title"), str(exc))

    # ═════════════════════════════════════════════════════════════════
    # IDIOMA
    # ═════════════════════════════════════════════════════════════════
    def _change_language(self, language: str):
        """
        Muda idioma e reconstrói toda a interface.
        
        Todos os textos são traduzidos via sistema i18n.
        """
        self.i18n.set_language(language)
        self._rebuild_ui()
        self._update_title()

        self._save_preferences()

    def _update_title(self):
        """Atualiza título da janela."""
        self.root.title("{} v{} · Oficina".format(t("app_title"), __version__))

    def run(self):
        """Inicia o loop principal da aplicação."""
        self.root.mainloop()


def main():
    """Função principal - ponto de entrada da aplicação."""
    if sys.argv[1:] == ["--startup-check"]:
        from utils.startup_check import run
        run(GURPSCalculator)
        return
    app = GURPSCalculator()
    app.run()


if __name__ == "__main__":
    main()
