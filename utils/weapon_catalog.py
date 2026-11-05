"""Embedded and user-defined ranged weapon catalogs."""

import json
import math
import os
from pathlib import Path
import platform
import re
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional

from calculators.ranged_combat import WeaponRecord
from utils.local_json import quarantine_json, write_atomic_json


CATALOG_SCHEMA = "gurps-calculadora.weapon-catalog.v1"


def application_data_dir() -> Path:
    """Return a per-user writable folder without touching the installation."""
    override = os.environ.get("GURPS_CALCULADORA_DATA_DIR")
    if override and Path(override).is_absolute():
        return Path(override)
    system = platform.system().lower()
    if system == "windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / "GurpsCalculadora"
    if system == "darwin":
        return Path.home() / "Library" / "Application Support" / "GurpsCalculadora"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "GurpsCalculadora"


class WeaponCatalog:
    """Search built-in records and manage user presets as JSON."""

    def __init__(self, catalog_path: Optional[Path] = None,
                 user_path: Optional[Path] = None, load_user: bool = True):
        root = Path(__file__).resolve().parents[1]
        self.catalog_path = Path(catalog_path) if catalog_path else root / "data" / "weapons.json"
        self.user_path = Path(user_path) if user_path else application_data_dir() / "weapons.json"
        self.builtin: List[WeaponRecord] = []
        self.custom: List[WeaponRecord] = []
        self.load_warning: Optional[Path] = None
        self._writes_blocked = False
        self._load_builtin()
        if load_user:
            self._load_user()

    @staticmethod
    def _read_document(path: Path) -> Dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, RecursionError) as exc:
            raise ValueError("invalid_catalog_json") from exc
        if not isinstance(document, dict) or document.get("schema") != CATALOG_SCHEMA:
            raise ValueError("invalid_catalog_schema")
        records = document.get("weapons")
        if not isinstance(records, list):
            raise ValueError("invalid_catalog_records")
        return document

    @staticmethod
    def _records(document: Dict[str, Any]) -> List[WeaponRecord]:
        records = []
        for item in document["weapons"]:
            if not isinstance(item, dict):
                raise ValueError("invalid_weapon_record")
            record = WeaponRecord.from_dict(item)
            if not record.identifier or not record.name or not record.damage_modes:
                raise ValueError("incomplete_weapon_record")
            if (any(not isinstance(getattr(record, key), str)
                    for key in ("identifier", "name", "source", "page", "tech_level", "category"))
                    or any(not isinstance(values, list) or any(not isinstance(x, str) for x in values)
                           for values in (record.skills, record.aliases, record.tags))
                    or any(type(getattr(record, key)) is not int
                           for key in ("accuracy", "recoil", "malfunction", "projectiles_per_shot"))
                    or not isinstance(record.rate_of_fire_modes, list)
                    or any(type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0
                           for rate in record.rate_of_fire_modes)):
                raise ValueError("invalid_weapon_record")
            for mode in record.damage_modes:
                if (not isinstance(mode.dice, str) or not isinstance(mode.damage_type, str)
                        or not isinstance(mode.raw, str) or type(mode.armor_divisor) not in (int, float)
                        or not math.isfinite(mode.armor_divisor) or mode.armor_divisor <= 0):
                    raise ValueError("invalid_weapon_record")
            records.append(record)
        identifiers = [record.identifier for record in records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate_weapon_identifier")
        return records

    def _load_builtin(self) -> None:
        self.builtin = self._records(self._read_document(self.catalog_path))

    def _load_user(self) -> None:
        try:
            self.custom = self._records(self._read_document(self.user_path))
        except FileNotFoundError:
            return
        except OSError:
            self.load_warning = self.user_path
            self._writes_blocked = True
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            try:
                self.load_warning = quarantine_json(self.user_path)
            except OSError:
                self.load_warning = self.user_path
                self._writes_blocked = True

    @property
    def weapons(self) -> List[WeaponRecord]:
        return self.builtin + self.custom

    def get(self, identifier: str) -> Optional[WeaponRecord]:
        for record in reversed(self.weapons):
            if record.identifier == identifier:
                return record
        return None

    def search(self, query: str = "", tech_level: Optional[str] = None,
               source: Optional[str] = None, category: Optional[str] = None,
               skill: Optional[str] = None) -> List[WeaponRecord]:
        needle = query.casefold().strip()
        results = []
        for weapon in self.weapons:
            haystack = " ".join([weapon.name] + weapon.aliases).casefold()
            if needle and needle not in haystack:
                continue
            if tech_level is not None and weapon.tech_level.casefold() != str(tech_level).casefold():
                continue
            if source is not None and source.casefold() not in weapon.source.casefold():
                continue
            if category is not None and category.casefold() not in weapon.category.casefold():
                continue
            if skill is not None and not any(skill.casefold() in value.casefold() for value in weapon.skills):
                continue
            results.append(weapon)
        return sorted(results, key=lambda item: (item.name.casefold(), item.source, item.identifier))

    @staticmethod
    def _document(records: Iterable[WeaponRecord]) -> Dict[str, Any]:
        return {
            "schema": CATALOG_SCHEMA,
            "weapons": [record.to_dict() for record in records],
        }

    def save_custom(self, weapon: WeaponRecord) -> None:
        if not weapon.identifier.startswith("custom."):
            safe = re.sub(r"[^a-z0-9]+", "-", weapon.name.casefold()).strip("-")
            weapon = replace(weapon, identifier="custom." + (safe or "weapon"))
        existing = {record.identifier: record for record in self.custom}
        existing[weapon.identifier] = weapon
        self._commit(existing.values())

    def import_file(self, path: Path) -> int:
        imported = self._records(self._read_document(Path(path)))
        existing = {record.identifier: record for record in self.custom}
        for weapon in imported:
            if not weapon.identifier.startswith("custom."):
                weapon.identifier = "custom.imported." + weapon.identifier
            existing[weapon.identifier] = weapon
        self._commit(existing.values())
        return len(imported)

    def _commit(self, records: Iterable[WeaponRecord]) -> None:
        if self._writes_blocked:
            raise PermissionError(str(self.user_path))
        candidate = sorted(records, key=lambda item: item.identifier)
        write_atomic_json(self.user_path, self._document(candidate))
        self.custom = candidate

    def export_file(self, path: Path, records: Optional[Iterable[WeaponRecord]] = None) -> None:
        selected = list(records) if records is not None else list(self.custom)
        write_atomic_json(path, self._document(selected))
