"""Embedded and user-defined ranged weapon catalogs."""

import json
import os
from pathlib import Path
import platform
import re
from typing import Any, Dict, Iterable, List, Optional

from calculators.ranged_combat import WeaponRecord


CATALOG_SCHEMA = "gurps-calculadora.weapon-catalog.v1"


def application_data_dir() -> Path:
    """Return a per-user writable folder without touching the installation."""
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
        self._load_builtin()
        if load_user:
            self._load_user()

    @staticmethod
    def _read_document(path: Path) -> Dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
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
            records.append(record)
        identifiers = [record.identifier for record in records]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate_weapon_identifier")
        return records

    def _load_builtin(self) -> None:
        self.builtin = self._records(self._read_document(self.catalog_path))

    def _load_user(self) -> None:
        if self.user_path.exists():
            self.custom = self._records(self._read_document(self.user_path))

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
            weapon.identifier = "custom." + (safe or "weapon")
        existing = {record.identifier: record for record in self.custom}
        existing[weapon.identifier] = weapon
        self.custom = sorted(existing.values(), key=lambda item: item.identifier)
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_path.write_text(
            json.dumps(self._document(self.custom), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def import_file(self, path: Path) -> int:
        imported = self._records(self._read_document(Path(path)))
        existing = {record.identifier: record for record in self.custom}
        for weapon in imported:
            if not weapon.identifier.startswith("custom."):
                weapon.identifier = "custom.imported." + weapon.identifier
            existing[weapon.identifier] = weapon
        self.custom = sorted(existing.values(), key=lambda item: item.identifier)
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_path.write_text(
            json.dumps(self._document(self.custom), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return len(imported)

    def export_file(self, path: Path, records: Optional[Iterable[WeaponRecord]] = None) -> None:
        selected = list(records) if records is not None else list(self.custom)
        Path(path).write_text(
            json.dumps(self._document(selected), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
