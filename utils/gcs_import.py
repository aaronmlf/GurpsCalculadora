"""Read computed character snapshots from GCS, without running sheet scripts.

Formats verified against GCS's public v5 Attribute/Entity serializers, the
Master Library character sheets, and its Fantasy Grounds PC export templates.
https://github.com/richardwilkes/gcs/blob/main/model/gurps/attribute.go
https://github.com/richardwilkes/gcs/blob/main/model/gurps/entity.go
https://github.com/richardwilkes/gcs_master_library/tree/main/Library/Output%20Templates
https://gurpscharactersheet.com/output_templates.html
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import xml.etree.ElementTree as ET


SUPPORTED_SUFFIXES = ('.gcs', '.xml')
LIBRARY_SUFFIXES = frozenset({'.gct', '.adq', '.adm', '.skl', '.spl', '.eqp', '.eqm', '.not'})
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_BATCH_FILES = 40
MAX_ATTRIBUTES = 256
MAX_ENERGY_TRACKS = 32
MAX_STAT = 1_000_000_000
_XML_NUMBER = re.compile(r'[+-]?[0-9]{1,12}(?:\.[0-9]{1,8})?\Z')


class GCSImportError(ValueError):
    def __init__(self, code: str, detail: str = ''):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ImportedEnergyTrack:
    identifier: str
    name: str
    maximum: int
    current: int


@dataclass(frozen=True)
class ImportedLocationDR:
    path: tuple[str, ...]
    name: str
    base: int
    adjustments: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ImportedCharacter:
    source_id: str
    name: str
    st: int
    dx: int
    iq: int
    ht: int
    max_hp: int
    current_hp: int
    max_fp: int
    current_fp: int
    basic_speed: float
    source_format: str
    source_version: str
    source_name: str = ''
    will: int | None = None
    per: int | None = None
    basic_move: int | None = None
    size_modifier: int | None = None
    base_size_modifier: int | None = None
    dodge: int | None = None
    parry: int | None = None
    block: int | None = None
    dodge_by_encumbrance: tuple[int, ...] = ()
    energy_tracks: tuple[ImportedEnergyTrack, ...] = ()
    location_dr: tuple[ImportedLocationDR, ...] = ()


@dataclass(frozen=True)
class GCSImportResult:
    path: Path
    character: ImportedCharacter | None = None
    error: str | None = None
    detail: str = ''


def _label(value, field, *, maximum=128):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(
            unicodedata.category(c) in {'Cc', 'Cs'} for c in value):
        raise GCSImportError('gcs_invalid_stat', field)
    return value.strip()


def _numeric(value, field, *, minimum=-MAX_STAT, integral=True):
    if (type(value) not in (int, Decimal) or isinstance(value, Decimal) and not value.is_finite()
            or not minimum <= value <= MAX_STAT):
        raise GCSImportError('gcs_invalid_stat', field)
    if integral:
        integer = int(value)
        if integer != value:
            raise GCSImportError('gcs_invalid_stat', field)
        return integer
    return float(value)


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise GCSImportError('gcs_invalid_document')
        value[key] = item
    return value


def _invalid_constant(_value):
    raise GCSImportError('gcs_invalid_document')


def _locations(body, parents=()):
    """Keep localized DR and typed bonuses distinct from global armor."""
    if not isinstance(body, dict) or len(parents) >= 8:
        return
    locations = body.get('locations', [])
    if not isinstance(locations, list):
        return
    for item in locations:
        if not isinstance(item, dict):
            continue
        calc = item.get('calc')
        dr = calc.get('dr') if isinstance(calc, dict) else None
        try:
            key = _label(item.get('id'), 'hit_location')
            name = _label(item.get('choice_name') or item.get('table_name') or key, 'hit_location')
            path = (*parents, key)
            if isinstance(dr, dict) and dr and len(dr) <= 32:
                base = _numeric(dr.get('all', 0), 'dr')
                bonuses = tuple((_label(k, 'dr'), _numeric(v, 'dr')) for k, v in dr.items() if k != 'all')
                yield ImportedLocationDR(path, name, base, bonuses)
        except GCSImportError:
            # Location data is an optional reference; never replace it with
            # a whole-body default or block the core sheet over custom armor.
            continue
        yield from _locations(item.get('sub_table'), path)


def _native(raw: bytes, source_name: str) -> ImportedCharacter:
    try:
        doc = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_strict_object,
                         parse_constant=_invalid_constant, parse_float=Decimal)
    except GCSImportError:
        raise
    except (ValueError, UnicodeError, RecursionError, InvalidOperation) as exc:
        raise GCSImportError('gcs_invalid_document') from exc
    if not isinstance(doc, dict):
        raise GCSImportError('gcs_invalid_document')
    if isinstance(doc.get('rows'), list) and 'profile' not in doc:
        raise GCSImportError('gcs_library_only')
    version = doc.get('version')
    if type(version) is not int or version != 5:
        raise GCSImportError('gcs_unsupported_version', str(version) if type(version) is int and abs(version) < 10000 else '')
    if not isinstance(doc.get('profile'), dict) or not isinstance(doc.get('attributes'), list):
        raise GCSImportError('gcs_invalid_document')
    if len(doc['attributes']) > MAX_ATTRIBUTES:
        raise GCSImportError('gcs_invalid_stat', 'attributes')
    profile = doc['profile']
    name = _label(profile.get('name'), 'name')
    source_id = _label(doc.get('id'), 'id', maximum=256)
    attributes = {}
    for record in doc['attributes']:
        if not isinstance(record, dict):
            raise GCSImportError('gcs_invalid_document')
        identifier = _label(record.get('attr_id'), 'attr_id')
        if identifier in attributes:
            raise GCSImportError('gcs_invalid_document')
        attributes[identifier] = record

    def calculated(identifier, *, required=True, field='value', minimum=0, integral=True):
        calc = attributes.get(identifier, {}).get('calc')
        if not isinstance(calc, dict) or field not in calc:
            if required:
                code = 'gcs_missing_current' if field == 'current' else 'gcs_missing_calculated'
                raise GCSImportError(code, identifier)
            return None
        return _numeric(calc[field], identifier, minimum=minimum, integral=integral)

    settings = doc.get('settings') if isinstance(doc.get('settings'), dict) else {}
    definitions = settings.get('attributes')
    labels = {}
    if isinstance(definitions, list):
        for item in definitions:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                continue
            labels[item['id']] = item.get('full_name') or item.get('name')
    pools = []
    for identifier, record in attributes.items():
        calc = record.get('calc')
        # GCS writes calc.current for pools (including custom pools), never
        # for plain attributes. Keep only computed pools with both values.
        if identifier in {'hp', 'fp'} or not isinstance(calc, dict) or 'current' not in calc:
            continue
        maximum = calculated(identifier)
        current = calculated(identifier, field='current', minimum=-MAX_STAT)
        label = _label(labels.get(identifier) or identifier, identifier)
        pools.append(ImportedEnergyTrack(identifier, label, maximum, current))
    if len(pools) > MAX_ENERGY_TRACKS:
        raise GCSImportError('gcs_invalid_stat', 'energy_tracks')

    dodge_by_encumbrance = ()
    stats = doc.get('calc')
    dodge_table = stats.get('dodge') if isinstance(stats, dict) else None
    if isinstance(dodge_table, list) and len(dodge_table) == 5:
        try:
            dodge_by_encumbrance = tuple(_numeric(value, 'dodge', minimum=0) for value in dodge_table)
        except GCSImportError:
            pass
    # The native sheet does not save the current encumbrance index with the
    # table. We can select a current number only if all five values agree.
    dodge = dodge_by_encumbrance[0] if len(set(dodge_by_encumbrance)) == 1 else None
    base_sm = _numeric(profile['SM'], 'SM') if 'SM' in profile else None

    return ImportedCharacter(
        source_id=source_id, name=name, source_format='gcs_native', source_version='5', source_name=source_name,
        st=calculated('st'), dx=calculated('dx'), iq=calculated('iq'), ht=calculated('ht'),
        max_hp=calculated('hp', minimum=1), current_hp=calculated('hp', field='current', minimum=-MAX_STAT),
        max_fp=calculated('fp'), current_fp=calculated('fp', field='current', minimum=-MAX_STAT),
        basic_speed=calculated('basic_speed', integral=False), basic_move=calculated('basic_move', required=False),
        will=calculated('will', required=False), per=calculated('per', required=False), base_size_modifier=base_sm,
        dodge=dodge, dodge_by_encumbrance=dodge_by_encumbrance, energy_tracks=tuple(pools),
        location_dr=tuple(islice(_locations(settings.get('body_type')), 256)),
    )


def _xml_child(parent, key):
    if parent is None:
        return None
    found = parent.findall(key)
    if len(found) > 1:
        raise GCSImportError('gcs_invalid_document')
    return found[0] if found else None


def _xml_text(parent, key):
    node = _xml_child(parent, key)
    if node is None:
        return None
    if len(node):
        raise GCSImportError('gcs_invalid_stat', key)
    return (node.text or '').strip()


def _xml_number(parent, key, *, required=True, current=False, minimum=0, integral=True):
    value = _xml_text(parent, key)
    if not value or value == '-':
        if required:
            raise GCSImportError('gcs_missing_current' if current else 'gcs_missing_calculated', key)
        return None
    if not _XML_NUMBER.fullmatch(value):
        raise GCSImportError('gcs_invalid_stat', key)
    return _numeric(Decimal(value), key, minimum=minimum, integral=integral)


def _fantasy_grounds(raw: bytes, source_name: str) -> ImportedCharacter:
    # The verified templates write ISO-8859-1 (and ET also accepts UTF-8).
    # Reject declarations/entities and alternate NUL encodings before parse.
    if (b'\0' in raw or raw.count(b'<') > 100_000 or
            re.search(rb'<!\s*(?:doctype|entity)\b', raw, flags=re.IGNORECASE)):
        raise GCSImportError('gcs_invalid_document')
    try:
        root = ET.fromstring(raw)
    except (ET.ParseError, LookupError, ValueError, RecursionError) as exc:
        raise GCSImportError('gcs_invalid_document') from exc
    if root.tag != 'root':
        raise GCSImportError('gcs_unsupported_format', '.xml')
    if root.get('version') == '2.8' and _xml_child(root, 'npc') is not None:
        # Both official NPC templates publish maximum HP/FP only.
        raise GCSImportError('gcs_missing_current', 'HP / FP')
    character = _xml_child(root, 'character')
    if root.get('release') != '4|CoreRPG:3' or root.get('version') != '3.2' or character is None:
        raise GCSImportError('gcs_unsupported_format', '.xml')
    attributes = _xml_child(character, 'attributes')
    combat = _xml_child(character, 'combat')
    traits = _xml_child(character, 'traits')
    name = _label(_xml_text(character, 'name'), 'name')
    # The official XML has no persistent sheet ID. Fingerprinting exact
    # bytes deduplicates only identical exports, not separately saved sheets.
    source_id = 'gcs-fg:' + sha256(raw).hexdigest()
    dr = _xml_text(combat, 'dr')
    location_dr = ()
    # GENERAL_DR is torso only. Composite values such as "7/2" are left for
    # manual adjudication rather than being interpreted as a uniform layer.
    if dr and _XML_NUMBER.fullmatch(dr):
        location_dr = (ImportedLocationDR(('torso',), 'torso', _numeric(Decimal(dr), 'dr')),)
    return ImportedCharacter(
        source_id=source_id, name=name, source_format='gcs_fantasy_grounds_pc', source_version='3.2',
        source_name=source_name,
        st=_xml_number(attributes, 'strength'), dx=_xml_number(attributes, 'dexterity'),
        iq=_xml_number(attributes, 'intelligence'), ht=_xml_number(attributes, 'health'),
        max_hp=_xml_number(attributes, 'hitpoints', minimum=1),
        current_hp=_xml_number(attributes, 'hps', current=True, minimum=-MAX_STAT),
        max_fp=_xml_number(attributes, 'fatiguepoints'),
        current_fp=_xml_number(attributes, 'fps', current=True, minimum=-MAX_STAT),
        basic_speed=_xml_number(attributes, 'basicspeed', integral=False),
        basic_move=_xml_number(attributes, 'basicmove', required=False),
        will=_xml_number(attributes, 'will', required=False), per=_xml_number(attributes, 'perception', required=False),
        size_modifier=_xml_number(traits, 'sizemodifier', required=False, minimum=-MAX_STAT),
        dodge=_xml_number(combat, 'dodge', required=False), parry=_xml_number(combat, 'parry', required=False),
        block=_xml_number(combat, 'block', required=False), location_dr=location_dr,
    )


def load_gcs_file(path: str | Path) -> ImportedCharacter:
    """Read a local, regular character file, with no side effects."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix in LIBRARY_SUFFIXES:
        raise GCSImportError('gcs_library_only', suffix)
    if suffix not in SUPPORTED_SUFFIXES:
        raise GCSImportError('gcs_unsupported_format', suffix[:16])
    try:
        initial = path.lstat()
        if not stat.S_ISREG(initial.st_mode):
            raise GCSImportError('gcs_unreadable')
        if initial.st_size > MAX_FILE_BYTES:
            raise GCSImportError('gcs_file_too_large')
        # O_NONBLOCK avoids waiting on a FIFO substituted after the stat.
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(path, flags), 'rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise GCSImportError('gcs_unreadable')
            raw = handle.read(MAX_FILE_BYTES + 1)
    except GCSImportError:
        raise
    except (OSError, ValueError) as exc:
        raise GCSImportError('gcs_unreadable') from exc
    if len(raw) > MAX_FILE_BYTES:
        raise GCSImportError('gcs_file_too_large')
    return _native(raw, path.name) if suffix == '.gcs' else _fantasy_grounds(raw, path.name)


def read_gcs_files(paths) -> tuple[GCSImportResult, ...]:
    """Return per-file previews/errors, including partial successes."""
    results = []
    for index, path in enumerate(islice(paths, MAX_BATCH_FILES + 1)):
        path = Path(path)
        if index == MAX_BATCH_FILES:
            results.append(GCSImportResult(path, error='gcs_batch_limit', detail=str(MAX_BATCH_FILES)))
            break
        try:
            results.append(GCSImportResult(path, character=load_gcs_file(path)))
        except GCSImportError as exc:
            results.append(GCSImportResult(path, error=exc.code, detail=exc.detail))
    return tuple(results)
