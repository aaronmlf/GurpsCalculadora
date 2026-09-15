import unittest

from calculators.injury import CombatantState
from calculators.melee_combat import (
    GrappleActionInput,
    GrapplingEngine,
    MeleeAttackInput,
    MeleeCombatCalculator,
    StyleRecord,
    TechniqueRecord,
)
from utils.combat_catalog import MeleeWeaponCatalog


class MeleeCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = MeleeWeaponCatalog(load_user=False)
        cls.punch = next(item for item in catalog.weapons if item.identifier.endswith("natural.punch"))
        cls.sword = next(item for item in catalog.weapons if item.name == "Broadsword" and item.source == "Basic Set")

    def setUp(self):
        self.engine = MeleeCombatCalculator()
        self.attacker = CombatantState(identifier="a", name="A", st=12, dx=12)
        self.target = CombatantState(identifier="b", name="B", dodge=9, parry=9, block=9)

    def data(self, **changes):
        values = dict(
            weapon=self.sword, attacker=self.attacker, target=self.target,
            skill=16, distance_yards=1, defense_score=9,
        )
        values.update(changes)
        return MeleeAttackInput(**values)

    def test_deceptive_attack_trades_two_skill_for_one_defense(self):
        result = self.engine.calculate(self.data(deceptive_attack_penalty=4))
        self.assertEqual(result.effective_skill, 12)
        self.assertEqual(result.defense_score, 7)
        self.assertTrue(result.valid)
        too_far = self.engine.calculate(self.data(skill=13, deceptive_attack_penalty=4))
        self.assertIn("deceptive_attack_requires_final_skill_10", too_far.errors)

    def test_telegraphic_attack_is_profile_gated_and_conflicts_with_deceptive(self):
        basic = self.engine.calculate(self.data(telegraphic_attack=True))
        self.assertIn("telegraphic_attack_outside_profile", basic.errors)
        realistic = self.engine.calculate(self.data(profile="realistic", telegraphic_attack=True))
        self.assertEqual(realistic.effective_skill, 20)
        self.assertEqual(realistic.defense_score, 11)
        conflict = self.engine.calculate(self.data(
            profile="realistic", telegraphic_attack=True, deceptive_attack_penalty=2
        ))
        self.assertIn("telegraphic_and_deceptive_conflict", conflict.errors)

    def test_rapid_strike_penalties_and_profiles(self):
        basic = self.engine.calculate(self.data(rapid_strike_attacks=2))
        self.assertEqual(basic.attack_count, 2)
        self.assertEqual(basic.effective_skill, 10)
        self.assertIn("too_many_basic_rapid_strikes", self.engine.calculate(
            self.data(rapid_strike_attacks=3)
        ).errors)
        master = self.engine.calculate(self.data(
            profile="realistic", rapid_strike_attacks=3, trained_by_master=True
        ))
        self.assertEqual(master.effective_skill, 10)

    def test_dual_weapon_attack_creates_two_attacks_without_rapid_strike_penalty(self):
        result = self.engine.calculate(self.data(dual_weapon_attack=True))
        self.assertEqual(result.attack_count, 2)
        self.assertEqual(result.effective_skill, 12)
        self.assertNotIn("rapid_strike", {item["key"] for item in result.modifiers})

    def test_maneuver_profile_isolation_and_move_and_attack_cap(self):
        committed = self.engine.calculate(self.data(maneuver="committed_determined"))
        self.assertIn("martial_arts_maneuver_outside_profile", committed.errors)
        realistic = self.engine.calculate(self.data(profile="realistic", maneuver="committed_determined"))
        self.assertEqual(realistic.effective_skill, 18)
        self.assertIn("attacker_cannot_retreat", realistic.defense_restrictions)
        move = self.engine.calculate(self.data(skill=30, maneuver="move_and_attack"))
        self.assertEqual(move.effective_skill, 9)

    def test_previous_maneuver_conditions_control_active_defenses(self):
        self.target.conditions.append("all_out_attack_no_defense")
        no_defense = self.engine.calculate(self.data())
        self.assertIsNone(no_defense.defense_score)
        self.target.conditions[:] = ["committed_attack_defense_restrictions"]
        committed = self.engine.calculate(self.data(retreat="retreat"))
        self.assertEqual(committed.defense_score, 7)
        self.target.conditions[:] = ["defensive_attack_parry_bonus"]
        parry = self.engine.calculate(self.data(defense_type="parry"))
        self.assertEqual(parry.defense_score, 10)

    def test_reach_ready_strength_and_offhand_validation(self):
        out = self.engine.calculate(self.data(distance_yards=3))
        self.assertIn("target_out_of_reach", out.errors)
        unready = self.engine.calculate(self.data(weapon_ready=False))
        self.assertIn("weapon_not_ready", unready.errors)
        weak = self.engine.calculate(self.data(
            attacker=CombatantState(identifier="a", name="A", st=5), offhand=True
        ))
        keys = {item["key"] for item in weak.modifiers}
        self.assertIn("insufficient_strength", keys)
        self.assertIn("offhand", keys)

    def test_resolve_attack_defense_damage_and_state_delta(self):
        result = self.engine.resolve(
            self.data(attack_rolls=[10], defense_rolls=[12], damage_rolls=[6], knockdown_rolls=[10])
        )
        self.assertTrue(result.attacks[0]["hit"])
        self.assertEqual(result.attacks[0]["damage"]["basic_damage"], 6)
        self.assertLess(result.state_delta.hp_change, 0)
        defended = self.engine.resolve(self.data(attack_rolls=[10], defense_rolls=[8]))
        self.assertFalse(defended.attacks[0]["hit"])
        self.assertEqual(defended.state_delta.hp_change, 0)

    def test_critical_hit_allows_no_defense(self):
        result = self.engine.resolve(self.data(attack_rolls=[4], defense_rolls=[3], damage_rolls=[2]))
        self.assertIsNone(result.attacks[0]["defense"])
        self.assertTrue(result.attacks[0]["hit"])

    def test_style_is_advisory_not_a_hard_restriction(self):
        technique = TechniqueRecord(
            "t", "Martial Arts", "70", "Counterattack", "H", ["Sword"], ["PS-5"], "PS"
        )
        style = StyleRecord("s", "Martial Arts", "150", "Style", ["Sword"], ["Feint"])
        result = self.engine.calculate(self.data(profile="realistic", technique=technique, style=style))
        self.assertTrue(result.valid)
        self.assertIn("technique_not_listed_in_selected_style", result.notes)

    def test_cinematic_and_silly_techniques_are_gated(self):
        cinematic = TechniqueRecord(
            "c", "Martial Arts", "84", "Hand Catch", "H", [], [], "PS", profile="cinematic"
        )
        self.assertIn("cinematic_technique_outside_profile", self.engine.calculate(
            self.data(profile="realistic", technique=cinematic)
        ).errors)
        silly = TechniqueRecord(
            "s", "Martial Arts", "88", "Wet Willy", "H", [], [], "PS", profile="cinematic", silly=True
        )
        self.assertIn("silly_technique_disabled", self.engine.calculate(
            self.data(profile="cinematic", technique=silly)
        ).errors)
        self.assertTrue(self.engine.calculate(
            self.data(profile="cinematic", technique=silly, allow_silly=True)
        ).valid)

    def test_non_attack_maneuver_produces_pending_effect_without_roll(self):
        result = self.engine.resolve(self.data(maneuver="evaluate", evaluate_turns=1))
        self.assertEqual(result.attacks, [])
        self.assertEqual(result.pending_effects[0]["kind"], "evaluate")

    def test_feint_resolves_quick_contest_without_dealing_damage(self):
        data = self.data(maneuver="feint", feint_target_skill=12, feint_roll=8, feint_target_roll=11)
        result = self.engine.resolve(data)
        self.assertTrue(result.valid)
        self.assertEqual(result.attacks, [])
        feint = next(item for item in result.pending_effects if item["kind"] == "feint")
        self.assertEqual(feint["defense_penalty"], 7)
        self.assertTrue(feint["contest"]["actor_wins"])
        self.assertIn("feint:a:7", result.state_delta.add_conditions)

        follow_up = self.engine.resolve(self.data(
            feint_defense_penalty=7, feint_condition="feint:a:7",
            rapid_strike_attacks=2, attack_rolls=[10, 10], defense_rolls=[10, 10],
        ))
        self.assertEqual(follow_up.attacks[0]["defense"]["target"], 2)
        self.assertEqual(follow_up.attacks[1]["defense"]["target"], 9)
        self.assertIn("feint:a:7", follow_up.state_delta.remove_conditions)

    def test_do_nothing_can_recover_from_stun_without_mutating_input(self):
        attacker = CombatantState(identifier="a", name="A", st=12, dx=12)
        attacker.stunned = True
        attacker.conditions.append("stunned")
        data = self.data(attacker=attacker, maneuver="do_nothing", stun_recovery_roll=8)
        result = self.engine.resolve(data)
        self.assertFalse(attacker.unconscious)
        self.assertTrue(attacker.stunned)
        self.assertFalse(result.attacker_delta.set_stunned)
        self.assertIn("stunned", result.attacker_delta.remove_conditions)

    def test_change_posture_returns_an_explicit_actor_delta(self):
        result = self.engine.resolve(self.data(maneuver="change_posture", new_posture="prone"))
        self.assertEqual(result.attacker_delta.posture, "prone")
        self.assertIn("prone", result.attacker_delta.add_conditions)


class GrapplingTests(unittest.TestCase):
    def setUp(self):
        self.engine = GrapplingEngine()
        self.actor = CombatantState(identifier="a", name="A", st=12, dx=12)
        self.target = CombatantState(identifier="b", name="B", st=10, dx=10, dodge=8)

    def test_grapple_adds_relationship_and_condition(self):
        result = self.engine.resolve(GrappleActionInput(
            self.actor, self.target, action="grapple", skill=14,
            attack_roll=10, defense_roll=12, location="arm",
        ))
        self.assertTrue(result.success)
        self.assertEqual(result.target_delta.grapple_updates["a"]["location"], "arm")
        self.assertIn("grappled", result.target_delta.add_conditions)

    def test_takedown_pin_lock_and_break_free_require_valid_state(self):
        self.target.grapples["a"] = {"attacker": "a", "location": "arm", "state": "grappled"}
        takedown = self.engine.resolve(GrappleActionInput(
            self.actor, self.target, action="takedown", skill=14,
            actor_contest_roll=8, target_contest_roll=14,
        ))
        self.assertEqual(takedown.target_delta.posture, "prone")
        lock = self.engine.resolve(GrappleActionInput(
            self.actor, self.target, action="arm_lock", profile="realistic", skill=14,
            actor_contest_roll=8, target_contest_roll=14,
        ))
        self.assertEqual(lock.target_delta.grapple_updates["a"]["state"], "arm_lock")
        pin_invalid = self.engine.resolve(GrappleActionInput(
            self.actor, self.target, action="pin", skill=14,
            actor_contest_roll=8, target_contest_roll=14,
        ))
        self.assertIn("pin_requires_grounded_target", pin_invalid.errors)
        self.actor.grapples["b"] = {"attacker": "b", "location": "torso", "state": "grappled"}
        escaped = self.engine.resolve(GrappleActionInput(
            self.actor, self.target, action="break_free", skill=14,
            actor_contest_roll=8, target_contest_roll=14,
        ))
        self.assertIsNone(escaped.actor_delta.grapple_updates["b"])

    def test_martial_arts_actions_do_not_leak_to_basic(self):
        self.target.grapples["a"] = {"attacker": "a", "location": "arm", "state": "grappled"}
        result = self.engine.resolve(GrappleActionInput(
            self.actor, self.target, action="arm_lock", profile="basic"
        ))
        self.assertIn("martial_arts_grapple_action_outside_profile", result.errors)


if __name__ == "__main__":
    unittest.main()
