"""Pacote de calculadoras GURPS 4e."""

from .knockback import KnockbackCalculator
from .slam import SlamCalculator
from .falls import FallsCalculator
from .collisions import CollisionsCalculator
from .explosions import ExplosionsCalculator
from .falling_objects import FallingObjectsCalculator
from .combat import CombatCalculator
from .ranged_combat import (
    DamageMode,
    RangedAttackInput,
    RangedAttackResult,
    RangedCombatCalculator,
    WeaponRecord,
)
from .injury import (
    ArmorLayer,
    ArmorLoadout,
    ArmorRecord,
    CombatantState,
    DamagePacket,
    InjuryEngine,
    InjuryInput,
    InjuryResult,
    OptionalInjuryRules,
    StateDelta,
    WoundRecord,
)
from .combat_session import CombatSession, SessionEvent
from .melee_combat import (
    GrappleActionInput,
    GrappleActionResult,
    GrapplingEngine,
    MeleeAttackInput,
    MeleeAttackResult,
    MeleeCombatCalculator,
    MeleeDamageMode,
    MeleeWeaponRecord,
    StyleRecord,
    TechniqueRecord,
)
from .strength import (
    DamageBonusInput, DamageBonusResult, EffortOption, StrengthCalculationInput,
    StrengthCalculationResult, StrengthEngine, StrengthProfile,
)
from .magic import (
    CastingInput, CastingResult, EffectPacket, MagicSystemRecord, ResourcePool,
    ResistanceCheck, SpellRecord, SpellcastingEngine,
)
from .powers import (
    AbilityBuildInput, AbilityBuildResult, AbilityEngine, AdvantageRecord,
    ModifierRecord, PowerRecord, PsiAbilityRecord, PsiTechniqueRecord,
    PsiUseInput, PsiUseResult, PsionicEngine,
)
from .vehicles import (
    SpacecraftRecord, VehicleAttackInput, VehicleCatalog, VehicleCollisionInput,
    VehicleEngine, VehicleMovementInput, VehicleMovementResult, VehicleRecord,
    VehicleSession, VehicleState,
)
from .campaign import (
    BattleInput, BattleResult, CampaignSession, CampaignStateDelta,
    CharacterSocialProfile, ElementRecord, ForceRecord, InfluenceInput,
    InfluenceResult, MassCombatEngine, OrganizationRecord, ReactionInput,
    ReactionResult, RelationshipRecord, SocialEngineeringEngine,
)

__all__ = [
    "KnockbackCalculator",
    "SlamCalculator",
    "FallsCalculator",
    "CollisionsCalculator",
    "ExplosionsCalculator",
    "FallingObjectsCalculator",
    "CombatCalculator",
    "DamageMode",
    "WeaponRecord",
    "RangedAttackInput",
    "RangedAttackResult",
    "RangedCombatCalculator",
    "DamagePacket",
    "ArmorRecord",
    "ArmorLayer",
    "ArmorLoadout",
    "WoundRecord",
    "CombatantState",
    "StateDelta",
    "OptionalInjuryRules",
    "InjuryInput",
    "InjuryResult",
    "InjuryEngine",
    "CombatSession",
    "SessionEvent",
    "MeleeDamageMode",
    "MeleeWeaponRecord",
    "TechniqueRecord",
    "StyleRecord",
    "MeleeAttackInput",
    "MeleeAttackResult",
    "MeleeCombatCalculator",
    "GrappleActionInput",
    "GrappleActionResult",
    "GrapplingEngine",
    "StrengthProfile", "EffortOption", "StrengthCalculationInput",
    "StrengthCalculationResult", "DamageBonusInput", "DamageBonusResult", "StrengthEngine",
    "ResourcePool", "ResistanceCheck", "EffectPacket", "MagicSystemRecord", "SpellRecord",
    "CastingInput", "CastingResult", "SpellcastingEngine",
    "AdvantageRecord", "ModifierRecord", "PowerRecord", "AbilityBuildInput",
    "AbilityBuildResult", "AbilityEngine", "PsiAbilityRecord", "PsiTechniqueRecord",
    "PsiUseInput", "PsiUseResult", "PsionicEngine",
    "VehicleRecord", "SpacecraftRecord", "VehicleState", "VehicleMovementInput",
    "VehicleMovementResult", "VehicleCollisionInput", "VehicleAttackInput", "VehicleSession",
    "VehicleEngine", "VehicleCatalog", "CharacterSocialProfile", "ReactionInput",
    "ReactionResult", "InfluenceInput", "InfluenceResult", "RelationshipRecord",
    "OrganizationRecord", "ElementRecord", "ForceRecord", "BattleInput", "BattleResult",
    "CampaignStateDelta", "CampaignSession", "SocialEngineeringEngine", "MassCombatEngine",
]
