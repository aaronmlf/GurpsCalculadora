"""Versioned catalogs for magic, powers, psi, vehicles, and mass combat."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from calculators.magic import MagicSystemRecord, SpellRecord
from calculators.powers import AdvantageRecord, ModifierRecord, PowerRecord, PsiAbilityRecord, PsiTechniqueRecord
from calculators.campaign import ElementRecord


RULES_CATALOG_SCHEMA = "gurps-calculadora.extended-rules-catalog.v1"


_FACTORIES = {
    "magic_systems": MagicSystemRecord,
    "spells": SpellRecord.from_dict,
    "advantages": AdvantageRecord,
    "modifiers": ModifierRecord,
    "powers": PowerRecord,
    "psi_abilities": PsiAbilityRecord.from_dict,
    "psi_techniques": PsiTechniqueRecord,
    "mass_elements": ElementRecord,
}


class ExtendedRulesCatalog:
    def __init__(self, path: Optional[Path] = None):
        root = Path(__file__).resolve().parents[1]
        self.path = Path(path) if path else root / "data" / "extended_rules.json"
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_catalog_json") from exc
        if not isinstance(document, dict) or document.get("schema") != RULES_CATALOG_SCHEMA:
            raise ValueError("invalid_catalog_schema")
        override_path = self.path.with_name('magic_table_stats.json')
        overrides = json.loads(override_path.read_text(encoding='utf-8'))['spells'] if override_path.exists() else {}
        self._collections: Dict[str, List[Any]] = {}
        identifiers: set[str] = set()
        for key, factory in _FACTORIES.items():
            values = document.get(key)
            if not isinstance(values, list):
                raise ValueError("invalid_catalog_records")
            records = []
            for raw in values:
                if not isinstance(raw, dict):
                    raise ValueError(f"invalid_catalog_record:{key}")
                raw = dict(raw)
                if key == 'spells':
                    name = re.sub(r'[^a-z0-9]', '', raw.get('name', '').lower())
                    correction = overrides.get(name)
                    if correction and str(correction['page']) == str(raw.get('page')) and raw.get('source') == 'Magic':
                        raw.update({k: correction[k] for k in ('base_cost', 'maintenance_cost', 'casting_time_seconds', 'duration_seconds', 'original')})
                        raw['spell_class'] = correction['original']['class']
                try:
                    record = factory(raw) if callable(factory) and not isinstance(factory, type) else factory(**raw)
                except (TypeError, ValueError, AttributeError) as exc:
                    raise ValueError(f"invalid_catalog_record:{key}:{raw.get('identifier', '?')}:{exc}") from exc
                if not getattr(record, "identifier", "") or not getattr(record, "name", ""):
                    raise ValueError("incomplete_catalog_record")
                if record.identifier in identifiers:
                    raise ValueError("duplicate_catalog_identifier")
                identifiers.add(record.identifier)
                records.append(record)
            self._collections[key] = records

    def records(self, kind: str) -> List[Any]:
        if kind not in self._collections:
            raise ValueError("unknown_catalog_kind")
        return list(self._collections[kind])

    def search(self, kind: str, query: str = "", source: Optional[str] = None,
               profile: Optional[str] = None, tag: Optional[str] = None) -> List[Any]:
        needle = query.casefold().strip()
        result = []
        for record in self.records(kind):
            if needle and needle not in record.name.casefold():
                continue
            if source is not None and source.casefold() not in getattr(record, "source", "").casefold():
                continue
            record_profile = getattr(record, "profile", "basic")
            if profile == "basic" and record_profile != "basic":
                continue
            if profile == "realistic" and record_profile == "cinematic":
                continue
            if tag is not None and tag not in getattr(record, "tags", []):
                continue
            result.append(record)
        return sorted(result, key=lambda item: (item.name.casefold(), item.identifier))
