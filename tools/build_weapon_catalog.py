#!/usr/bin/env python3
"""Build the redistributable stats-only weapon catalog from owned PDFs.

This maintenance tool is not used by the packaged application.  It extracts
only table cells (names, game statistics, and page references), never prose or
artwork.  The generated JSON is the runtime resource.
"""

import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gurps-calculadora.weapon-catalog.v1"
SOURCES = (
    ("Basic Set", ROOT / "GURPS 4th Edition/Basic Set/GURPS 4th - Basic Set - Combined.pdf", range(270, 285), -2),
    ("High-Tech", ROOT / "GURPS 4th Edition/High-Tech/GURPS 4th - High-Tech - Weapon Tables.pdf", range(3, 18), 0),
    ("Low-Tech", ROOT / "GURPS 4th Edition/Low-Tech/GURPS 4th - Low-Tech.pdf", range(75, 91), -2),
    ("Ultra-Tech", ROOT / "GURPS 4th Edition/Ultra-Tech/GURPS 4th - Ultra-Tech v3.2.pdf", range(112, 159), -2),
)
ALLOWED_SKILLS = (
    "GUNS", "GUNNER", "ARTILLERY", "BEAM WEAPONS", "BOW", "CROSSBOW",
    "THROWN", "SLING", "LIQUID PROJECTOR", "INNATE ATTACK", "BLOWPIPE",
    "SPEAR THROWER", "SPORT", "DROPPING",
)
EXCLUDED = ("MELEE", "SHIELD", "CLOAK", "NET (", "WHIP")


def page_rows(pdf: Path, page: int):
    """Return visually aligned word rows from Poppler's TSV coordinates."""
    output = subprocess.check_output(
        ["pdftotext", "-f", str(page), "-l", str(page), "-tsv", str(pdf), "-"],
        text=True, errors="replace",
    )
    grouped = defaultdict(list)
    for line in output.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or parts[0] != "5":
            continue
        try:
            left = float(parts[6])
            top = float(parts[7])
        except ValueError:
            continue
        grouped[round(top, 1)].append((left, parts[11]))
    return [sorted(words) for _top, words in sorted(grouped.items())]


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plain.casefold()).strip("-")


def number(text: str, default=None):
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return default
    value = float(match.group())
    return int(value) if value.is_integer() else value


def parse_damage(raw: str):
    normalized = raw.replace("¥", "×").replace("x", "×").replace("–", "-").strip()
    resistance = normalized if "aff" in normalized.casefold() or normalized.startswith(("HT", "Will")) else None
    dice_match = re.search(r"(?:\d+d|thr|sw)(?:[+-]\d+)?(?:[×*]\d+(?:\.\d+)?)?", normalized, re.I)
    dice = dice_match.group() if dice_match else "1d"
    divisor = 1.0
    if dice_match:
        tail = normalized[dice_match.end():]
        divisor_match = re.match(r"\s*\((\d+(?:\.\d+)?)\)", tail)
        if divisor_match:
            divisor = float(divisor_match.group(1))
    type_match = re.search(r"(?<!\w)(pi\+\+|pi\+|pi-|pi|burn|cor|cr|cut|fat|imp|tox|aff)(?!\w)", normalized, re.I)
    damage_type = type_match.group(1).lower() if type_match else ("aff" if resistance else "cr")
    return {
        "dice": dice,
        "damage_type": damage_type,
        "armor_divisor": divisor,
        "minimum_range": 0.0,
        "half_damage_range": None,
        "max_range": None,
        "follow_up": None,
        "explosive": bool(re.search(r"\bex\b", normalized, re.I)),
        "fragmentation": None,
        "resistance": resistance,
        "effect_shape": "projectile",
        "area_radius_yards": None,
        "cone_width_yards": None,
        "raw": raw.strip(),
    }


def parse_range(raw: str, mode: dict):
    values = [float(item.replace(",", "")) for item in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if not values or "ST" in raw.upper() or "×" in raw or "x" in raw.lower():
        return
    if len(values) >= 2:
        mode["half_damage_range"], mode["max_range"] = values[0], values[1]
    else:
        mode["max_range"] = values[0]


def parse_rof(raw: str):
    normalized = raw.replace("¥", "×").replace("x", "×")
    pellet_match = re.search(r"×\s*(\d+)", normalized)
    pellets = int(pellet_match.group(1)) if pellet_match else 1
    before = normalized.split("×", 1)[0]
    modes = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", before)] or [1.0]
    return modes, pellets, "!" in raw


def parse_shots(raw: str):
    normalized = raw.replace(",", "")
    capacity_match = re.match(r"(\d+)(?:\+(\d+))?", normalized)
    reload_match = re.search(r"\((\d+)(i)?\)", normalized, re.I)
    return (
        int(capacity_match.group(1)) if capacity_match else None,
        int(capacity_match.group(2) or 0) if capacity_match else 0,
        int(reload_match.group(1)) if reload_match else None,
        bool(reload_match and reload_match.group(2)),
    )


def skill_allowed(skill: str) -> bool:
    upper = skill.upper()
    return any(value in upper for value in ALLOWED_SKILLS) and not any(value in upper for value in EXCLUDED)


def parse_source(source: str, pdf: Path, pages, page_adjust: int):
    records = []
    seen = {}
    current_skill = ""
    columns = None
    for physical_page in pages:
        for words in page_rows(pdf, physical_page):
            line = " ".join(word for _left, word in words)
            header = re.match(r"^\s*([^a-z].*?)\s+\((?:DX|HT|IQ)-\d", line)
            if header and "Weapon" not in line:
                candidate = header.group(1).strip()
                if len(candidate) < 90:
                    current_skill = candidate
                    continue
            texts = [word for _left, word in words]
            if all(name in texts for name in ("TL", "Weapon", "Damage", "Acc")):
                valid_names = {"TL", "Weapon", "Damage", "Acc", "Range", "Weight", "RoF", "Shots", "ST", "Bulk", "Rcl", "Cost", "LC", "Notes"}
                positions = [(left, word) for left, word in words if word in valid_names]
                positions.sort()
                columns = positions if len(positions) >= 7 else None
                continue
            if not columns or not skill_allowed(current_skill):
                continue
            first_column = columns[0][0]
            row_words = [(left, word) for left, word in words if left >= first_column - 5]
            row_match = re.fullmatch(r"\d+(?:-\d+)?\^?", row_words[0][1]) if row_words else None
            if not row_match:
                if records and any(marker in line.casefold() for marker in ("follow-up", "linked")):
                    cells = {name: [] for _left, name in columns}
                    for left, word in row_words:
                        selected = columns[0][1]
                        for start, field in columns:
                            if left >= start - 10:
                                selected = field
                        cells[selected].append(word)
                    follow_up = parse_damage(" ".join(cells.get("Damage", [])))
                    if follow_up["raw"]:
                        records[-1]["damage_modes"][0]["follow_up"] = follow_up
                continue
            cell_words = {name: [] for _left, name in columns}
            for left, word in row_words:
                selected = columns[0][1]
                for start, field in columns:
                    if left >= start - 10:
                        selected = field
                cell_words[selected].append(word)
            cells = {name: " ".join(values).strip() for name, values in cell_words.items()}
            tech_level = row_words[0][1]
            damage_index = next((index for index, (_left, word) in enumerate(row_words[1:], 1)
                                 if re.match(r"^(?:\d+d|thr|sw|HT|Will|spec\.)", word, re.I)), None)
            if damage_index is not None:
                name = " ".join(word for _left, word in row_words[1:damage_index]).strip()
                if row_words[damage_index][1] not in cells.get("Damage", "").split():
                    cells["Damage"] = (row_words[damage_index][1] + " " + cells.get("Damage", "")).strip()
            else:
                name = cells.get("Weapon", "")
            damage = cells.get("Damage", "")
            if len(name) < 2 or not damage:
                continue
            mode = parse_damage(damage)
            parse_range(cells.get("Range", ""), mode)
            acc_values = [int(value) for value in re.findall(r"\d+", cells.get("Acc", ""))]
            rof_modes, pellets, full_auto = parse_rof(cells.get("RoF", ""))
            shots_capacity, chamber_capacity, reload_seconds, reload_individual = parse_shots(cells.get("Shots", ""))
            rcl_values = [int(value) for value in re.findall(r"\d+", cells.get("Rcl", ""))]
            strength_match = re.search(r"\d+", cells.get("ST", ""))
            bulk = number(cells.get("Bulk", ""))
            printed_page = physical_page + page_adjust
            stem = "{}.{}.{}.{}".format(slug(source), printed_page, slug(current_skill), slug(name))
            seen[stem] = seen.get(stem, 0) + 1
            identifier = stem if seen[stem] == 1 else "{}.{}".format(stem, seen[stem])
            tags = [slug(source), "catalog-table"]
            if pellets > 1:
                tags.append("shotgun")
            if mode["resistance"]:
                tags.append("affliction")
            if mode["explosive"]:
                tags.append("explosive")
            if mode["dice"].lower().startswith(("thr", "sw")):
                tags.append("muscle-powered")
            record = {
                "identifier": identifier,
                "source": source,
                "page": str(printed_page),
                "name": name,
                "tech_level": tech_level,
                "category": current_skill,
                "skills": [current_skill],
                "damage_modes": [mode],
                "accuracy": acc_values[0] if acc_values else 0,
                "accuracy_secondary": acc_values[1] if len(acc_values) > 1 else 0,
                "range_raw": cells.get("Range", ""),
                "weight_raw": cells.get("Weight", ""),
                "rate_of_fire_modes": rof_modes,
                "projectiles_per_shot": pellets,
                "shots_raw": cells.get("Shots", ""),
                "shots_capacity": shots_capacity,
                "chamber_capacity": chamber_capacity,
                "reload_seconds": reload_seconds,
                "reload_individual": reload_individual,
                "strength": int(strength_match.group()) if strength_match else None,
                "strength_flags": re.sub(r"\d", "", cells.get("ST", "")),
                "bulk": int(bulk) if bulk is not None else None,
                "recoil": rcl_values[0] if rcl_values else 1,
                "recoil_secondary": rcl_values[1] if len(rcl_values) > 1 else None,
                "malfunction": (
                    12 if tech_level.startswith("3") and ("GUNS" in current_skill or "GUNNER" in current_skill)
                    else 14 if tech_level.startswith("4") and ("GUNS" in current_skill or "GUNNER" in current_skill)
                    else 16 if tech_level.startswith("5") and ("GUNS" in current_skill or "GUNNER" in current_skill)
                    else 17
                ),
                "full_auto_only": full_auto,
                "cost": cells.get("Cost", ""),
                "legality_class": cells.get("LC", ""),
                "tags": tags,
                "aliases": [],
                "original": {key.casefold(): value for key, value in cells.items() if value},
            }
            records.append(record)
    return records


def main():
    records = []
    for source, pdf, pages, adjustment in SOURCES:
        if not pdf.exists():
            raise SystemExit("Missing source PDF: {}".format(pdf))
        extracted = parse_source(source, pdf, pages, adjustment)
        print("{}: {}".format(source, len(extracted)), file=sys.stderr)
        records.extend(extracted)
    records.sort(key=lambda item: (item["source"], int(re.match(r"\d+", item["page"]).group()), item["name"]))
    output = ROOT / "data" / "weapons.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema": SCHEMA, "weapons": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("total: {}".format(len(records)), file=sys.stderr)


if __name__ == "__main__":
    main()
