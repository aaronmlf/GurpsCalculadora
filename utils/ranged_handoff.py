"""Translate an already-rolled ordinary projectile into a Trauma draft."""

from dataclasses import dataclass

from calculators.injury import DamagePacket


@dataclass(frozen=True)
class RangedHitDraft:
    number: int
    weapon_name: str
    profile: str
    packet: DamagePacket
    half_damage_applied: bool
    encounter_pair: tuple[str, str] | None = None

    @classmethod
    def from_result(cls, result, weapon, index, *, encounter_pair=None):
        if not result.valid or not 0 <= index < len(result.damages):
            raise ValueError("handoff_no_hit")
        hit = result.damages[index]
        packet = hit.get("injury_result", {}).get("packet")
        if (not packet or packet.get("explosive") or packet.get("linked_effects")
                or packet.get("hit_location") == "weapon"
                or any(key in hit for key in ("close_shotgun_multiplier", "follow_up", "explosion",
                                               "fragmentation", "resistance", "effect_type", "effect_shape"))):
            raise ValueError("handoff_special_hit")
        return cls(index + 1, weapon.name, result.profile, DamagePacket.from_dict(packet),
                   result.beyond_half_damage, encounter_pair)
