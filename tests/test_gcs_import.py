"""Synthetic fixtures shaped like the verified GCS v5 and FG PC serializers."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from utils.gcs_import import GCSImportError, load_gcs_file, read_gcs_files


def native_fixture():
    values = {'st': 18, 'dx': 13, 'iq': 11, 'ht': 12, 'basic_speed': 6.25,
              'basic_move': 6, 'will': 12, 'per': 14}
    return {
        'version': 5,
        'id': 'fixture-sheet-1',
        'profile': {'name': 'João de Sá', 'SM': -1},
        # Deliberately different adjustment and calculated value: trait/equipment
        # bonuses can change these values and are never reconstructed by import.
        'attributes': [{'attr_id': key, 'adj': 0, 'calc': {'value': value, 'points': 0}}
                       for key, value in values.items()] + [
            {'attr_id': 'hp', 'adj': 0, 'damage': 25, 'calc': {'value': 20, 'current': -5, 'points': 0}},
            {'attr_id': 'fp', 'adj': 0, 'damage': 8, 'calc': {'value': 14, 'current': 6, 'points': 0}},
            {'attr_id': 'er_psi', 'adj': 0, 'damage': 4, 'calc': {'value': 9, 'current': 5, 'points': 0}},
        ],
        'settings': {
            'attributes': [{'id': 'er_psi', 'type': 'pool', 'name': 'ER', 'full_name': 'Reserva Psi'}],
            'body_type': {'locations': [{'id': 'torso', 'choice_name': 'Tronco',
                                        'calc': {'dr': {'all': 6, 'cutting': 2}}},
                                       {'id': 'face', 'choice_name': 'Rosto', 'calc': {'dr': {'all': 1}}}]},
        },
        'calc': {'dodge': [11, 10, 9, 8, 7], 'move': [6, 4, 3, 2, 1], 'parry_bonus': 2, 'block_bonus': 1},
        'traits': [{'name': 'Synthetic script', 'script': 'This is ignored by the reader.'}],
    }


def xml_fixture():
    # Master Library's Fantasy Grounds PC template uses these tag names and
    # ISO-8859-1 declaration; this fixture is not a distributed GCS sheet.
    return '''<?xml version="1.0" encoding="iso-8859-1"?>
<root release="4|CoreRPG:3" version="3.2"><character>
<name type="string">João de Sá</name><attributes>
<strength type="number">18</strength><dexterity type="number">13</dexterity>
<intelligence type="number">11</intelligence><health type="number">12</health>
<hitpoints type="number">20</hitpoints><hps type="number">-5</hps>
<fatiguepoints type="number">14</fatiguepoints><fps type="number">6</fps>
<basicspeed type="string">6.25</basicspeed><basicmove type="string">6</basicmove>
<will type="number">12</will><perception type="number">14</perception></attributes>
<combat><dodge type="number">9</dodge><parry type="number">11</parry>
<block type="number">-</block><dr type="string">6</dr></combat>
<traits><sizemodifier type="string">+1</sizemodifier></traits>
</character></root>'''.encode('iso-8859-1')


class GCSImportTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))

    def file(self, name, value):
        path = self.directory / name
        path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode('utf-8'))
        return path

    def assert_error(self, path, code, detail=None):
        with self.assertRaises(GCSImportError) as caught:
            load_gcs_file(path)
        self.assertEqual(caught.exception.code, code)
        if detail is not None:
            self.assertEqual(caught.exception.detail, detail)

    def test_native_uses_calculated_attributes_and_never_edits_source(self):
        path = self.file('Teste.GCS', native_fixture())
        original = path.read_bytes()
        record = load_gcs_file(path)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual((record.source_format, record.source_version, record.source_name), ('gcs_native', '5', 'Teste.GCS'))
        self.assertEqual((record.source_id, record.name), ('fixture-sheet-1', 'João de Sá'))
        self.assertEqual((record.st, record.dx, record.iq, record.ht), (18, 13, 11, 12))
        self.assertEqual((record.max_hp, record.current_hp, record.max_fp, record.current_fp), (20, -5, 14, 6))
        self.assertEqual((record.basic_speed, record.basic_move, record.will, record.per), (6.25, 6, 12, 14))
        self.assertEqual((record.base_size_modifier, record.size_modifier), (-1, None))
        self.assertEqual((record.dodge, record.parry, record.block), (None, None, None))
        self.assertEqual(record.dodge_by_encumbrance, (11, 10, 9, 8, 7))
        track, = record.energy_tracks
        self.assertEqual((track.identifier, track.name, track.maximum, track.current), ('er_psi', 'Reserva Psi', 9, 5))
        torso, face = record.location_dr
        self.assertEqual((torso.path, torso.name, torso.base, torso.adjustments), (('torso',), 'Tronco', 6, (('cutting', 2),)))
        self.assertEqual((face.path, face.base), (('face',), 1))

    def test_missing_calculated_stat_does_not_fall_back_to_adjustment(self):
        data = native_fixture()
        del data['attributes'][0]['calc']
        self.assert_error(self.file('uncomputed.gcs', data), 'gcs_missing_calculated', 'st')

    def test_missing_current_hp_is_not_replaced_by_maximum_or_raw_damage(self):
        data = native_fixture()
        hp = next(attr for attr in data['attributes'] if attr['attr_id'] == 'hp')
        del hp['calc']['current']
        self.assert_error(self.file('no-pool.gcs', data), 'gcs_missing_current', 'hp')

    def test_native_unknown_or_ambiguous_stats_are_not_invented(self):
        data = native_fixture()
        data['attributes'] = [row for row in data['attributes'] if row['attr_id'] not in ('will', 'basic_move')]
        data['calc']['dodge'] = [1] * 5  # Encumbrance does not change this specific result.
        record = load_gcs_file(self.file('optional.gcs', data))
        self.assertIsNone(record.will)
        self.assertIsNone(record.basic_move)
        self.assertEqual(record.dodge, 1)

    def test_native_rejects_unverified_versions_and_duplicate_keys(self):
        data = native_fixture()
        data['version'] = 4
        self.assert_error(self.file('old.gcs', data), 'gcs_unsupported_version', '4')
        self.assert_error(self.file('duplicate.gcs', b'{"version":5,"version":5}'), 'gcs_invalid_document')
        self.assert_error(self.file('deep.gcs', b'[' * 1100 + b'0' + b']' * 1100), 'gcs_invalid_document')

    def test_numeric_validation_rejects_nonfinite_bool_and_fractional_hp(self):
        data = native_fixture()
        for raw, code in ((True, 'gcs_invalid_stat'), (1.5, 'gcs_invalid_stat'), (float('nan'), 'gcs_invalid_document')):
            with self.subTest(raw=raw):
                data['attributes'][0]['calc']['value'] = raw
                self.assert_error(self.file('invalid.gcs', data), code)

    def test_foreign_documents_and_library_parts_are_distinguished(self):
        self.assert_error(self.file('notes.json', {}), 'gcs_unsupported_format')
        self.assert_error(self.file('traits.adq', {'version': 5, 'rows': []}), 'gcs_library_only', '.adq')
        self.assert_error(self.file('template.gct', {'version': 5}), 'gcs_library_only', '.gct')
        self.assert_error(self.file('renamed.gcs', {'version': 5, 'rows': []}), 'gcs_library_only')
        self.assert_error(self.file('other.xml', b'<book/>'), 'gcs_unsupported_format', '.xml')

    def test_official_pc_export_uses_current_defenses_and_only_torso_dr(self):
        raw = xml_fixture()
        record = load_gcs_file(self.file('sheet.xml', raw))
        duplicate = load_gcs_file(self.file('copy.xml', raw))
        self.assertEqual((record.source_format, record.source_version), ('gcs_fantasy_grounds_pc', '3.2'))
        self.assertEqual((record.source_id, record.name), (duplicate.source_id, 'João de Sá'))
        self.assertEqual((record.max_hp, record.current_hp, record.max_fp, record.current_fp), (20, -5, 14, 6))
        self.assertEqual((record.dodge, record.parry, record.block, record.size_modifier), (9, 11, None, 1))
        torso, = record.location_dr
        self.assertEqual((torso.path, torso.base), (('torso',), 6))

    def test_official_pc_export_accepts_weapon_flags_on_best_parry(self):
        for suffix in (b'F', b'U', b'FU'):
            with self.subTest(suffix=suffix):
                raw = xml_fixture().replace(b'>11</parry>', b'>11' + suffix + b'</parry>')
                self.assertEqual(load_gcs_file(self.file('parry.xml', raw)).parry, 11)
        raw = xml_fixture().replace(b'>11</parry>', b'>11UNKNOWN</parry>')
        self.assert_error(self.file('bad-parry.xml', raw), 'gcs_invalid_stat', 'parry')
        raw = xml_fixture().replace(b'>9</dodge>', b'>9F</dodge>')
        self.assert_error(self.file('bad-dodge.xml', raw), 'gcs_invalid_stat', 'dodge')

    def test_official_pc_export_preserves_names_in_utf8_and_latin1(self):
        latin1 = xml_fixture()
        utf8 = latin1.decode('iso-8859-1').encode('utf-8')
        for raw in (latin1, utf8, utf8.replace(b'iso-8859-1', b'UTF-8')):
            with self.subTest(raw_name=raw.split(b'</name>')[0][-14:]):
                path = self.file('accent.xml', raw)
                self.assertEqual(load_gcs_file(path).name, 'João de Sá')
                self.assertEqual(path.read_bytes(), raw)

    def test_npc_xml_requires_full_sheet_and_xml_blocks_entities(self):
        self.assert_error(self.file('npc.xml', b'<root version="2.8"><npc/></root>'), 'gcs_missing_current')
        xml = '<!DOCTYPE root [<!ENTITY expand SYSTEM "file:///etc/passwd">]><root>&expand;</root>'
        for encoding in ('utf-8', 'utf-16'):
            self.assert_error(self.file('entity.xml', xml.encode(encoding)), 'gcs_invalid_document')

    def test_batch_collects_partial_success_and_bounds_input(self):
        first = self.file('first.gcs', native_fixture())
        bad = self.file('bad.gcs', b'[')
        third = self.file('third.xml', xml_fixture())
        with patch('utils.gcs_import.MAX_BATCH_FILES', 3):
            a, b, c, omitted = read_gcs_files(iter((first, bad, third, first, bad)))
        self.assertEqual((a.path, a.character.name, a.error), (first, 'João de Sá', None))
        self.assertEqual((b.path, b.character, b.error), (bad, None, 'gcs_invalid_document'))
        self.assertEqual((c.path, c.character.dodge), (third, 9))
        self.assertEqual((omitted.character, omitted.error, omitted.detail), (None, 'gcs_batch_limit', '3'))

    def test_rejects_unreadable_or_oversized_paths(self):
        self.assert_error(self.directory / 'missing.gcs', 'gcs_unreadable')
        folder = self.directory / 'folder.gcs'
        folder.mkdir()
        self.assert_error(folder, 'gcs_unreadable')
        with patch('utils.gcs_import.MAX_FILE_BYTES', 8):
            self.assert_error(self.file('huge.gcs', b'x' * 9), 'gcs_file_too_large')
