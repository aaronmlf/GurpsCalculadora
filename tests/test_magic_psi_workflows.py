"""Source-based checks for playable catalog entries and explicit resources."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from calculators.campaign import (CharacterSocialProfile, InfluenceInput, ReactionInput,
                                  SocialEngineeringEngine, canonical_influence_skill)
from calculators.magic import CastingInput, ResistanceCheck, ResourcePool, SpellcastingEngine
from calculators.powers import AbilityBuildInput, AbilityEngine, PsionicEngine, PsiUseInput
from utils.rules_catalog import ExtendedRulesCatalog, catalog_status


class CatalogWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = ExtendedRulesCatalog()

    def record(self, kind, identifier):
        return next(item for item in self.catalog.records(kind) if item.identifier == identifier)

    def test_status_distinguishes_working_parameters_from_reference(self):
        self.assertEqual(catalog_status(self.record('spells', 'spell.light')), 'calculable')
        self.assertEqual(catalog_status(self.record('spells', 'spell.fireball')), 'requires_parameters')
        self.assertEqual(catalog_status(self.record('magic_systems', 'magic.rpm')), 'reference_only')
        available = self.catalog.search('psi_abilities', status='calculable')
        self.assertEqual([item.identifier for item in available], ['psi.emotion-sense', 'psi.mental-surgery'])
        self.assertTrue(self.catalog.search('psi_abilities', status='reference_only'))

    def test_resisted_magic_reads_published_attribute_and_tie(self):
        spell = self.record('spells', 'spell.daze')
        engine = SpellcastingEngine()
        self.assertEqual(spell.resistance_notation, 'R-HT')
        data = CastingInput(spell, skill=15)
        missing = engine.resolve(data, cast_roll=10)
        self.assertIn('spell_requires_resistance', missing.errors)
        self.assertIsNone(missing.roll)
        check = ResistanceCheck(target=12)
        result = engine.resolve(replace(data, resistance=check), cast_roll=11, resistance_roll=8)
        self.assertTrue(result.valid)
        self.assertEqual(result.resistance.attribute, 'ht')
        self.assertTrue(result.resistance.resisted)
        self.assertIsNone(check.resisted)

    def test_magic_resistance_modifies_both_sides_even_if_target_waives_contest(self):
        spell = self.record('spells', 'spell.daze')
        engine = SpellcastingEngine()
        data = CastingInput(spell, skill=15, magic_resistance=3, resistance=ResistanceCheck(target=12))
        result = engine.calculate(data)
        self.assertEqual((result.effective_skill, result.resistance.target), (12, 15))
        area = engine.calculate(replace(data, spell=replace(spell, spell_class='area')))
        self.assertEqual((area.effective_skill, area.resistance.target), (15, 18))
        waived = engine.resolve(replace(data, resistance=None, target_waives_resistance=True), cast_roll=10)
        self.assertTrue(waived.valid)
        self.assertEqual(waived.effective_skill, 12)
        self.assertIsNone(waived.resistance)

    def test_information_spell_always_pays_full_cost(self):
        spell = replace(self.record('spells', 'spell.detect-magic'), spell_class='information')
        engine = SpellcastingEngine()
        data = CastingInput(spell)
        for roll in (3, 9, 13, 18):
            with self.subTest(roll=roll):
                self.assertEqual(engine.resolve(data, cast_roll=roll).resource_delta['fp'], -2)

    def test_light_forecast_does_not_charge_future_renewals(self):
        spell = self.record('spells', 'spell.light')
        data = CastingInput(spell, maintenance_cycles=3, resources=ResourcePool(fp=1))
        engine = SpellcastingEngine()
        preview = engine.calculate(data)
        self.assertTrue(preview.valid)
        self.assertEqual((preview.energy_cost, preview.maintenance_cost, preview.maintenance_forecast), (1, 1, 3))
        self.assertEqual(preview.resource_delta, {})
        self.assertEqual(preview.duration_seconds, 60)
        result = engine.resolve(data, cast_roll=9)
        self.assertEqual(result.resource_delta['fp'], -1)
        with patch('calculators.magic.roll_3d6', side_effect=AssertionError('maintenance rolled')):
            renewal = engine.maintain(data)
        self.assertTrue(renewal.valid)
        self.assertIsNone(renewal.roll)
        self.assertEqual((renewal.casting_time_seconds, renewal.resource_delta['fp']), (0, -1))
        self.assertFalse(renewal.effects)

    def test_minor_healing_keeps_effect_size_separate_from_discount(self):
        spell = self.record('spells', 'spell.minor-healing')
        engine = SpellcastingEngine()
        data = CastingInput(replace(spell, base_cost=3), skill=20,
                            resources=ResourcePool(fp=0, energy_reserve=1))
        result = engine.resolve(data, cast_roll=9)
        self.assertTrue(result.valid)
        self.assertEqual(result.energy_cost, 1)
        self.assertEqual(result.resource_delta['energy_reserve'], -1)
        self.assertEqual(result.state_delta.fp_change, 0)
        self.assertEqual((result.effects[0].kind, result.effects[0].value), ('heal_hp', 3))
        self.assertEqual(spell.prerequisites, ['Lend Vitality'])
        self.assertIn('invalid_healing_energy', engine.calculate(replace(
            data, spell=replace(spell, base_cost=4))).errors)
        enhanced = engine.calculate(replace(data, spell=replace(spell, base_cost=4), magery=4,
                                            resources=ResourcePool(fp=2)))
        self.assertTrue(enhanced.valid)
        self.assertEqual(enhanced.effects[0].value, 4)

    def test_minor_healing_repetition_and_first_cast_physician(self):
        spell = replace(self.record('spells', 'spell.minor-healing'), base_cost=3)
        engine = SpellcastingEngine()
        data = CastingInput(spell, skill=12, physician_skill=15)
        first = engine.resolve(data, cast_roll=18)
        self.assertFalse(first.roll['critical_failure'])
        self.assertEqual(first.resource_delta['fp'], -1)
        repeat = engine.resolve(replace(data, same_day_castings=1), cast_roll=18)
        self.assertEqual(repeat.effective_skill, 9)
        self.assertTrue(repeat.roll['critical_failure'])
        self.assertEqual(repeat.resource_delta['fp'], -3)
        self.assertFalse(repeat.effects)

    def test_spell_mana_and_visibility_are_explicit(self):
        spell = self.record('spells', 'spell.light')
        engine = SpellcastingEngine()
        data = CastingInput(spell, skill=12, distance_yards=3, target_visible=False)
        self.assertEqual(engine.calculate(data).effective_skill, 4)
        self.assertIn('mage_required_in_mana', engine.calculate(replace(data, is_mage=False)).errors)
        self.assertTrue(engine.calculate(replace(data, is_mage=False, mana_level='high')).valid)
        very_high = engine.resolve(replace(data, mana_level='very_high'), cast_roll=9)
        self.assertTrue(very_high.roll['critical_failure'])
        self.assertIn({'kind': 'very_high_mana_fp_recovery', 'fp': 1}, very_high.pending_effects)

    def test_regular_range_produces_integer_target_and_rejects_nonfinite_distance(self):
        engine = SpellcastingEngine()
        spell = self.record('spells', 'spell.light')
        data = CastingInput(spell, skill=12, distance_yards=3.25)
        self.assertEqual(engine.calculate(data).effective_skill, 8)
        self.assertEqual(engine.calculate(replace(data, distance_yards=3.0000000000000004)).effective_skill, 9)
        for invalid in (float('nan'), float('inf'), -1):
            result = engine.resolve(replace(data, distance_yards=invalid), cast_roll=3)
            self.assertIn('invalid_casting_input', result.errors)
            self.assertIsNone(result.roll)

    def test_emotion_sense_levels_match_range_and_character_cost(self):
        ability = self.record('psi_abilities', 'psi.emotion-sense')
        engine = PsionicEngine()
        base = PsiUseInput(ability, skill=14, resistance=ResistanceCheck(target=12))
        cases = ((1, 'skin', 0, 14, 3), (2, 'none', 20, 8, 9),
                 (3, 'none', 1760, 12, 18), (4, 'none', 1760, 14, 20),
                 (2, 'skin', 0, 16, 9))
        for level, contact, distance, skill, points in cases:
            with self.subTest(level=level, contact=contact):
                result = engine.calculate(replace(base, level=level, contact=contact, distance_yards=distance))
                self.assertTrue(result.valid, result.errors)
                self.assertEqual((result.effective_skill, result.character_point_cost), (skill, points))
                self.assertIsNone(result.activation_time_seconds)  # No fixed activation time is listed.
                self.assertEqual(result.fp_cost, 0)

    def test_emotion_sense_requires_valid_contact_target_and_will(self):
        ability = self.record('psi_abilities', 'psi.emotion-sense')
        engine = PsionicEngine()
        data = PsiUseInput(ability, contact='touch', target_living_sapient=False)
        result = engine.resolve(data, roll=3)
        self.assertIsNone(result.roll)
        self.assertIn('psi_skin_contact_required', result.errors)
        self.assertIn('psi_emotion_sense_target', result.errors)
        self.assertIn('psi_requires_resistance', result.errors)

    def test_psi_repeated_attempt_cost_on_failure_and_critical_resistance(self):
        ability = self.record('psi_abilities', 'psi.emotion-sense')
        engine = PsionicEngine()
        data = PsiUseInput(ability, skill=14, contact='skin', repeated_attempts=3,
                           resistance=ResistanceCheck(target=20), resources=ResourcePool(fp=0, energy_reserve=1))
        failed = engine.resolve(data, roll=18)
        self.assertEqual((failed.effective_skill, failed.fp_cost), (11, 1))
        self.assertEqual(failed.resource_delta, {'energy_reserve': -1, 'fp': 0})
        self.assertFalse(failed.effects)
        critical = engine.resolve(data, roll=3, resistance_roll=3)
        self.assertTrue(critical.roll['critical_success'])
        self.assertEqual(critical.resource_delta, {'energy_reserve': 0, 'fp': 0})
        self.assertTrue(critical.resistance.resisted)
        self.assertFalse(critical.effects)

    def test_mental_surgery_uses_published_times_and_five_point_penalty(self):
        ability = self.record('psi_abilities', 'psi.mental-surgery')
        engine = PsionicEngine()
        data = PsiUseInput(ability, skill=15, contact='skin', target_willing=True, changed_disadvantage_points=12)
        for level, seconds, points in ((1, 3600, 10), (2, 600, 25), (3, 60, 33), (4, 10, 48), (5, 1, 65)):
            with self.subTest(level=level):
                result = engine.calculate(replace(data, level=level))
                self.assertTrue(result.valid, result.errors)
                self.assertEqual((result.activation_time_seconds, result.character_point_cost), (seconds, points))
                self.assertEqual((result.effective_skill, result.fp_cost), (13, 0))
        with patch('calculators.powers.roll_3d6', side_effect=AssertionError('willing target resisted')):
            result = engine.resolve(replace(data, resistance=ResistanceCheck(target=20)), roll=9)
        self.assertIsNone(result.resistance)
        self.assertEqual(result.effects[0].metadata, {'action': 'mental_surgery', 'permanent': True,
                                                      'changed_disadvantage_points': 12})

    def test_mental_surgery_restrained_subject_resists_and_uncontrolled_cannot_roll(self):
        ability = self.record('psi_abilities', 'psi.mental-surgery')
        engine = PsionicEngine()
        data = PsiUseInput(ability, skill=14, contact='skin', resistance=ResistanceCheck(target=13))
        blocked = engine.resolve(data, roll=9, resistance_roll=8)
        self.assertIn('psi_mental_surgery_control', blocked.errors)
        self.assertIsNone(blocked.roll)
        result = engine.resolve(replace(data, target_restrained=True), roll=9, resistance_roll=8)
        self.assertTrue(result.valid, result.errors)
        self.assertTrue(result.resistance.resisted)
        self.assertFalse(result.effects)

    def test_invalid_ability_level_has_no_valid_looking_cost(self):
        advantage = self.catalog.records('advantages')[0]
        result = AbilityEngine().calculate(AbilityBuildInput(advantage, levels=0))
        self.assertFalse(result.valid)
        self.assertIn('invalid_ability_cost', result.errors)
        self.assertEqual(result.modified_cost, 0)


class SocialSkillTests(unittest.TestCase):
    def test_language_and_casing_preserve_special_influence_rules(self):
        engine = SocialEngineeringEngine()
        actor = CharacterSocialProfile('a', 'A', skills={'Sex Appeal': 15, 'Diplomacy': 15})
        target = CharacterSocialProfile('b', 'B', will=10)
        for name in ('Sex Appeal', 'sex appeal', 'Sedução', 'sex_appeal', 'Sedução (Sex Appeal)'):
            result = engine.resolve_influence(InfluenceInput(actor, target, name), actor_roll=10, target_roll=9)
            self.assertTrue(result.valid)
            self.assertEqual(result.reaction_band, 'very_good')
        result = engine.resolve_influence(InfluenceInput(actor, target, 'Diplomacia'), actor_roll=10, target_roll=9)
        self.assertTrue(result.valid)
        self.assertTrue(any(p['kind'] == 'take_better_reaction_roll' for p in result.pending_effects))
        self.assertEqual(canonical_influence_skill('LÁBIA'), 'fast_talk')

    def test_reaction_breakdown_sums_all_applied_modifiers(self):
        actor = CharacterSocialProfile('a', 'A', cultural_familiarity=False, charisma=1)
        result = SocialEngineeringEngine().resolve_reaction(ReactionInput(
            actor, disposition_modifier=2, situational_modifier=-1, group_modifier=3), roll=10)
        self.assertEqual(sum(item['value'] for item in result.breakdown), result.modifiers)
        self.assertEqual(result.total, 12)
