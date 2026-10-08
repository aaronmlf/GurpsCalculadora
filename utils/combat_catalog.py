"""Embedded and user-defined catalogs for melee, armor, techniques, and styles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Dict, Generic, Iterable, List, Mapping, Optional, TypeVar

from calculators.injury import ArmorRecord
from calculators.melee_combat import MeleeWeaponRecord, StyleRecord, TechniqueRecord
from utils.weapon_catalog import application_data_dir


MELEE_CATALOG_SCHEMA = "gurps-calculadora.melee-catalog.v1"
ARMOR_CATALOG_SCHEMA = "gurps-calculadora.armor-catalog.v1"
TECHNIQUE_CATALOG_SCHEMA = "gurps-calculadora.technique-catalog.v1"
STYLE_CATALOG_SCHEMA = "gurps-calculadora.style-catalog.v1"

T = TypeVar("T")


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _custom_identifier(name: str, kind: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or kind
    return f"custom.{kind}.{safe}"


class _Catalog(Generic[T]):
    def __init__(self, schema: str, key: str, factory: Callable[[Mapping[str, Any]], T],
                 builtin_path: Path, user_path: Path, load_user: bool = True):
        self.schema = schema
        self.key = key
        self.factory = factory
        self.builtin_path = builtin_path
        self.user_path = user_path
        self.builtin = self._records(self._read_document(builtin_path))
        self.custom: List[T] = []
        if load_user and user_path.exists():
            self.custom = self._records(self._read_document(user_path))

    def _read_document(self, path: Path) -> Dict[str, Any]:
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_catalog_json") from exc
        if not isinstance(document, dict) or document.get("schema") != self.schema:
            raise ValueError("invalid_catalog_schema")
        if not isinstance(document.get(self.key), list):
            raise ValueError("invalid_catalog_records")
        return document

    def _records(self, document: Mapping[str, Any]) -> List[T]:
        records = []
        identifiers = []
        for value in document[self.key]:
            if not isinstance(value, Mapping):
                raise ValueError("invalid_catalog_record")
            record = self.factory(value)
            identifier = getattr(record, "identifier", "")
            name = getattr(record, "name", "")
            if not identifier or not name:
                raise ValueError("incomplete_catalog_record")
            identifiers.append(identifier)
            records.append(record)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate_catalog_identifier")
        return records

    @property
    def records(self) -> List[T]:
        return self.builtin + self.custom

    def get(self, identifier: str) -> Optional[T]:
        for record in reversed(self.records):
            if getattr(record, "identifier") == identifier:
                return record
        return None

    def _document(self, records: Iterable[T]) -> Dict[str, Any]:
        return {self.schema_key: self.schema, self.key: [record.to_dict() for record in records]}

    @property
    def schema_key(self) -> str:
        return "schema"

    def save_custom(self, record: T, kind: str) -> None:
        if not getattr(record, "identifier").startswith("custom."):
            setattr(record, "identifier", _custom_identifier(getattr(record, "name"), kind))
        existing = {getattr(item, "identifier"): item for item in self.custom}
        existing[getattr(record, "identifier")] = record
        self.custom = sorted(existing.values(), key=lambda item: getattr(item, "identifier"))
        _atomic_json(self.user_path, self._document(self.custom))

    def import_file(self, path: Path) -> int:
        imported = self._records(self._read_document(Path(path)))
        existing = {getattr(item, "identifier"): item for item in self.custom}
        for item in imported:
            identifier = getattr(item, "identifier")
            if not identifier.startswith("custom."):
                identifier = "custom.imported." + identifier
                setattr(item, "identifier", identifier)
            existing[identifier] = item
        self.custom = sorted(existing.values(), key=lambda item: getattr(item, "identifier"))
        _atomic_json(self.user_path, self._document(self.custom))
        return len(imported)

    def export_file(self, path: Path, records: Optional[Iterable[T]] = None) -> None:
        _atomic_json(Path(path), self._document(list(records) if records is not None else self.custom))


def _source_priority(source: str) -> int:
    return 9 if source == "Basic Set" else 0


class MeleeWeaponCatalog(_Catalog[MeleeWeaponRecord]):
    def __init__(self, catalog_path: Optional[Path] = None, user_path: Optional[Path] = None,
                 load_user: bool = True):
        root = Path(__file__).resolve().parents[1]
        super().__init__(
            MELEE_CATALOG_SCHEMA, "weapons", MeleeWeaponRecord.from_dict,
            Path(catalog_path) if catalog_path else root / "data" / "melee_weapons.json",
            Path(user_path) if user_path else application_data_dir() / "melee_weapons.json",
            load_user,
        )

    @property
    def weapons(self) -> List[MeleeWeaponRecord]:
        return self.records

    def search(self, query: str = "", tech_level: Optional[str] = None,
               source: Optional[str] = None, category: Optional[str] = None,
               skill: Optional[str] = None) -> List[MeleeWeaponRecord]:
        needle = query.casefold().strip()
        results = []
        for record in self.records:
            if needle and needle not in " ".join([record.name] + record.aliases).casefold():
                continue
            if tech_level is not None and record.tech_level.casefold() != str(tech_level).casefold():
                continue
            if source is not None and source.casefold() not in record.source.casefold():
                continue
            if category is not None and category.casefold() not in record.category.casefold():
                continue
            if skill is not None and not any(skill.casefold() in value.casefold() for value in record.skills):
                continue
            results.append(record)
        return sorted(results, key=lambda item: (item.name.casefold(), _source_priority(item.source), item.identifier))

    def save_custom(self, record: MeleeWeaponRecord) -> None:
        if not record.damage_modes:
            raise ValueError("incomplete_catalog_record")
        super().save_custom(record, "melee-weapon")


class ArmorCatalog(_Catalog[ArmorRecord]):
    def __init__(self, catalog_path: Optional[Path] = None, user_path: Optional[Path] = None,
                 load_user: bool = True):
        root = Path(__file__).resolve().parents[1]
        super().__init__(
            ARMOR_CATALOG_SCHEMA, "armor", ArmorRecord.from_dict,
            Path(catalog_path) if catalog_path else root / "data" / "armor.json",
            Path(user_path) if user_path else application_data_dir() / "armor.json",
            load_user,
        )

    @property
    def armor(self) -> List[ArmorRecord]:
        return self.records

    def search(self, query: str = "", tech_level: Optional[str] = None,
               source: Optional[str] = None, location: Optional[str] = None,
               armor_type: Optional[str] = None) -> List[ArmorRecord]:
        needle = query.casefold().strip()
        results = []
        for record in self.records:
            if needle and needle not in record.name.casefold():
                continue
            if tech_level is not None and record.tech_level.casefold() != str(tech_level).casefold():
                continue
            if source is not None and source.casefold() not in record.source.casefold():
                continue
            if location is not None and "all" not in record.locations and location not in record.locations:
                continue
            if armor_type == "flexible" and not record.flexible:
                continue
            if armor_type == "rigid" and not record.rigid:
                continue
            if armor_type == "ablative" and not (record.ablative or record.semi_ablative):
                continue
            results.append(record)
        return sorted(results, key=lambda item: (item.name.casefold(), _source_priority(item.source), item.identifier))

    def save_custom(self, record: ArmorRecord) -> None:
        super().save_custom(record, "armor")


class TechniqueCatalog(_Catalog[TechniqueRecord]):
    def __init__(self, catalog_path: Optional[Path] = None, user_path: Optional[Path] = None,
                 load_user: bool = True):
        root = Path(__file__).resolve().parents[1]
        super().__init__(
            TECHNIQUE_CATALOG_SCHEMA, "techniques", TechniqueRecord.from_dict,
            Path(catalog_path) if catalog_path else root / "data" / "techniques.json",
            Path(user_path) if user_path else application_data_dir() / "techniques.json",
            load_user,
        )

    @property
    def techniques(self) -> List[TechniqueRecord]:
        return self.records

    def search(self, query: str = "", prerequisite: Optional[str] = None,
               profile: Optional[str] = None, style: Optional[str] = None,
               include_silly: bool = False) -> List[TechniqueRecord]:
        needle = query.casefold().strip()
        results = []
        for record in self.records:
            if needle and needle not in record.name.casefold():
                continue
            if prerequisite is not None and not any(
                prerequisite.casefold() in item.casefold() for item in record.prerequisites
            ):
                continue
            if profile == "realistic" and record.profile == "cinematic":
                continue
            if profile == "basic" and record.source != "Basic Set":
                continue
            if record.silly and not include_silly:
                continue
            if style is not None and style not in record.style_ids:
                continue
            results.append(record)
        return sorted(results, key=lambda item: (item.name.casefold(), item.page, item.identifier))

    def save_custom(self, record: TechniqueRecord) -> None:
        super().save_custom(record, "technique")


class StyleCatalog(_Catalog[StyleRecord]):
    def __init__(self, catalog_path: Optional[Path] = None, user_path: Optional[Path] = None,
                 load_user: bool = True):
        root = Path(__file__).resolve().parents[1]
        super().__init__(
            STYLE_CATALOG_SCHEMA, "styles", StyleRecord.from_dict,
            Path(catalog_path) if catalog_path else root / "data" / "styles.json",
            Path(user_path) if user_path else application_data_dir() / "styles.json",
            load_user,
        )

    @property
    def styles(self) -> List[StyleRecord]:
        return self.records

    def search(self, query: str = "", source: Optional[str] = None,
               skill: Optional[str] = None, technique: Optional[str] = None,
               profile: Optional[str] = None) -> List[StyleRecord]:
        needle = query.casefold().strip()
        results = []
        for record in self.records:
            if needle and needle not in record.name.casefold():
                continue
            if source is not None and source.casefold() not in record.source.casefold():
                continue
            if skill is not None and not any(skill.casefold() in item.casefold() for item in record.required_skills):
                continue
            if technique is not None and not any(
                technique.casefold() in item.casefold()
                for item in record.techniques + record.cinematic_techniques
            ):
                continue
            if profile == "realistic" and record.profile == "cinematic":
                continue
            if profile == "basic" and record.source != "Basic Set":
                continue
            results.append(record)
        return sorted(results, key=lambda item: (item.name.casefold(), item.page, item.identifier))

    def save_custom(self, record: StyleRecord) -> None:
        super().save_custom(record, "style")
