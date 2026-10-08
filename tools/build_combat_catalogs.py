#!/usr/bin/env python3
"""Build stats-only melee, armor, technique, and style runtime catalogs.

The source PDFs are local maintenance inputs and are never copied into the
application.  Generated records contain table statistics and compact index
fields only; descriptive prose and artwork are deliberately excluded.
"""

from collections import defaultdict
import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
MELEE_SCHEMA = "gurps-calculadora.melee-catalog.v1"
ARMOR_SCHEMA = "gurps-calculadora.armor-catalog.v1"
TECHNIQUE_SCHEMA = "gurps-calculadora.technique-catalog.v1"
STYLE_SCHEMA = "gurps-calculadora.style-catalog.v1"

BASIC = ROOT / "GURPS 4th Edition/Basic Set/GURPS 4th - Basic Set - Combined.pdf"
MARTIAL_ARTS = ROOT / "GURPS 4th Edition/Martial Arts/GURPS 4th - Martial Arts.pdf"
TECHNIQUES = ROOT / "GURPS 4th Edition/Martial Arts/GURPS 4th - Martial Arts - Techniques Cheat Sheet.pdf"
LOW_TECH = ROOT / "GURPS 4th Edition/Low-Tech/GURPS 4th - Low-Tech.pdf"
HIGH_TECH = ROOT / "GURPS 4th Edition/High-Tech/GURPS 4th - High-Tech.pdf"
ULTRA_TECH = ROOT / "GURPS 4th Edition/Ultra-Tech/GURPS 4th - Ultra-Tech v3.2.pdf"

MELEE_SOURCES = (
    ("Basic Set", BASIC, range(273, 277), -2),
    ("Martial Arts", MARTIAL_ARTS, range(227, 235), -1),
    ("Low-Tech", LOW_TECH, range(66, 73), -2),
    ("High-Tech", HIGH_TECH, range(198, 203), -2),
    ("Ultra-Tech", ULTRA_TECH, range(164, 169), -2),
)

ARMOR_SOURCES = (
    ("Basic Set", BASIC, range(285, 288), -2),
    ("Low-Tech", LOW_TECH, range(112, 115), -2),
    ("High-Tech", HIGH_TECH, range(68, 75), -2),
    ("Ultra-Tech", ULTRA_TECH, range(173, 186), -2),
)


def slug(text):
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plain.casefold()).strip("-")


def page_rows(pdf, page):
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
            top = round(float(parts[7]), 1)
        except ValueError:
            continue
        grouped[top].append((left, parts[11]))
    return [sorted(words) for _top, words in sorted(grouped.items())]


def cells_for(words, columns):
    cells = {name: [] for _left, name in columns}
    for left, word in words:
        selected = columns[0][1]
        for start, name in columns:
            if left >= start - 7:
                selected = name
        cells[selected].append(word)
    return {name: " ".join(values).strip() for name, values in cells.items()}


def split_items(raw):
    return [item.strip(" .") for item in re.split(r";", raw) if item.strip(" .")]


def parse_melee_damage(raw, reach, parry, strength):
    normalized = raw.replace("–", "-").replace("−", "-").replace("¥", "×")
    expression = re.search(r"(?:thr|sw|\d+d)(?:[+-]\d+)?", normalized, re.I)
    dtype = re.search(r"(?<!\w)(burn|cor|cr|cut|fat|imp|pi\+\+|pi\+|pi-|pi|tox|aff)(?!\w)", normalized, re.I)
    divisor = re.search(r"\((0?\.\d+|\d+(?:\.\d+)?)\)\s*(?:burn|cor|cr|cut|fat|imp|pi|tox)", normalized, re.I)
    flags = re.sub(r"\d", "", strength)
    return {
        "damage": expression.group(0).lower() if expression else "thr",
        "damage_type": dtype.group(1).lower() if dtype else "cr",
        "reach": [part.strip().replace("–", "-") for part in reach.split(",") if part.strip()] or ["C"],
        "parry": parry or "0",
        "armor_divisor": float(divisor.group(1)) if divisor else 1.0,
        "minimum_st": int(re.search(r"\d+", strength).group()) if re.search(r"\d+", strength) else 0,
        "two_handed": "†" in flags or "‡" in flags,
        "becomes_unready": "‡" in flags,
        "requires_ready_to_change_reach": "*" in reach,
        "attack_label": "",
        "linked_effects": [],
        "raw": raw.strip(),
    }


def melee_records():
    records = []
    seen = defaultdict(int)
    for source, pdf, pages, adjust in MELEE_SOURCES:
        current_skill = ""
        columns = None
        last = None
        before = len(records)
        for physical_page in pages:
            for words in page_rows(pdf, physical_page):
                line = " ".join(word for _left, word in words)
                if re.search(r"\((?:DX|HT|IQ)-\d", line) and len(line) < 150:
                    candidate = line.split("(", 1)[0].strip()
                    if candidate and "Weapon" not in candidate and candidate.upper() == candidate:
                        current_skill = candidate
                        continue
                texts = [word for _left, word in words]
                if all(name in texts for name in ("TL", "Weapon", "Damage", "Reach", "Parry")):
                    names = {"TL", "Weapon", "Damage", "Reach", "Parry", "Cost", "Weight", "ST", "Notes"}
                    columns = sorted((left, word) for left, word in words if word in names)
                    continue
                if not columns or not current_skill:
                    continue
                cells = cells_for(words, columns)
                tl = cells.get("TL", "")
                name = cells.get("Weapon", "")
                damage = cells.get("Damage", "")
                if re.fullmatch(r"\d+(?:-\d+)?\^?", tl) and name and damage:
                    printed_page = physical_page + adjust
                    stem = f"{slug(source)}.{printed_page}.{slug(current_skill)}.{slug(name)}"
                    seen[stem] += 1
                    identifier = stem if seen[stem] == 1 else f"{stem}.{seen[stem]}"
                    mode = parse_melee_damage(
                        damage, cells.get("Reach", ""), cells.get("Parry", ""), cells.get("ST", "")
                    )
                    last = {
                        "identifier": identifier,
                        "source": source,
                        "page": str(printed_page),
                        "name": name,
                        "tech_level": tl,
                        "category": current_skill,
                        "skills": [current_skill],
                        "damage_modes": [mode],
                        "cost": cells.get("Cost", ""),
                        "weight": float(re.search(r"\d+(?:\.\d+)?", cells.get("Weight", "0")).group()) if re.search(r"\d+(?:\.\d+)?", cells.get("Weight", "")) else 0.0,
                        "legality_class": "",
                        "quality": "normal",
                        "natural_weapon": current_skill in {"BRAWLING", "KARATE", "JUDO", "WRESTLING", "SUMO WRESTLING"},
                        "training_weapon": "training" in line.casefold(),
                        "tags": [slug(source), "catalog-table"],
                        "aliases": [],
                        "original": {key.casefold(): value for key, value in cells.items() if value},
                    }
                    records.append(last)
                elif last and damage and (name.casefold().startswith("or") or not tl):
                    mode = parse_melee_damage(
                        damage, cells.get("Reach", ""), cells.get("Parry", ""), cells.get("ST", "")
                    )
                    if mode["raw"] and mode["raw"] != last["damage_modes"][-1]["raw"]:
                        last["damage_modes"].append(mode)
        print(f"melee {source}: {len(records) - before}", file=sys.stderr)

    # Basic natural attacks are rules entries rather than table rows.
    natural = [
        ("punch", "Punch", "thr-1", "cr", ["C"], ["DX", "Brawling", "Boxing", "Karate"]),
        ("kick", "Kick", "thr", "cr", ["C", "1"], ["DX", "Brawling", "Karate"]),
        ("bite", "Bite", "thr-1", "cr", ["C"], ["DX", "Brawling"]),
        ("grapple", "Grapple", "thr", "cr", ["C"], ["DX", "Judo", "Wrestling", "Sumo Wrestling"]),
    ]
    for key, name, damage, dtype, reach, skills in natural:
        records.append({
            "identifier": f"basic-set.271.natural.{key}", "source": "Basic Set", "page": "271, 370",
            "name": name, "tech_level": "0", "category": "NATURAL WEAPON", "skills": skills,
            "damage_modes": [{
                "damage": damage, "damage_type": dtype, "reach": reach, "parry": "0",
                "armor_divisor": 1.0, "minimum_st": 0, "two_handed": False,
                "becomes_unready": False, "requires_ready_to_change_reach": False,
                "attack_label": name, "linked_effects": [], "raw": f"{damage} {dtype}",
            }],
            "cost": "", "weight": 0.0, "legality_class": "", "quality": "normal",
            "natural_weapon": True, "training_weapon": False,
            "tags": ["basic-set", "natural"], "aliases": [], "original": {},
        })
    records.sort(key=lambda item: (item["name"].casefold(), item["source"], item["identifier"]))
    return records


def normalize_locations(raw):
    text = raw.casefold().replace("/", ",")
    mapping = {
        "body": ["torso", "groin", "arm", "leg"],
        "limbs": ["arm", "leg"], "arms": ["arm"], "legs": ["leg"],
        "hands": ["hand"], "feet": ["foot"], "head": ["skull", "face", "eye"],
        "all": ["all"], "full suit": ["all"], "torso": ["torso"], "groin": ["groin"],
        "skull": ["skull"], "face": ["face"], "eyes": ["eye"], "neck": ["neck"],
    }
    found = []
    for token, locations in mapping.items():
        if token in text:
            for location in locations:
                if location not in found:
                    found.append(location)
    return found or ["torso"]


def parse_dr(raw, source, tl):
    values = [int(value) for value in re.findall(r"\d+", raw)]
    high = values[0] if values else 0
    low = values[1] if len(values) > 1 else high
    flexible = "*" in raw
    by_type = {}
    if len(values) > 1:
        if source in {"High-Tech", "Ultra-Tech"} or (tl.isdigit() and int(tl) >= 6):
            by_type = {"*": low, "cut": high, "pi-": high, "pi": high, "pi+": high, "pi++": high}
        else:
            by_type = {"*": high, "cr": low}
    return high, by_type, flexible


def armor_records():
    records = []
    seen = defaultdict(int)
    for source, pdf, pages, adjust in ARMOR_SOURCES:
        columns = None
        previous_tl = ""
        before = len(records)
        for physical_page in pages:
            for words in page_rows(pdf, physical_page):
                texts = [word for _left, word in words]
                low_tech_torso = source == "Low-Tech" and all(name in texts for name in ("TL", "Torso", "Armor", "DR", "Cost", "Weight"))
                item_header = "Armor" if "Armor" in texts else "Type" if "Type" in texts else None
                regular_header = item_header and all(name in texts for name in ("TL", "Location", "DR", "Cost", "Weight"))
                if regular_header or low_tech_torso:
                    names = {"TL", item_header, "Location", "DR", "Cost", "Weight", "LC", "Notes", "Power", "Don"}
                    columns = sorted((left, word) for left, word in words if word in names)
                    if low_tech_torso:
                        torso_left = next(left for left, word in words if word == "Torso")
                        columns = [(left, name) for left, name in columns if name != "Armor"]
                        columns.append((torso_left, "Armor"))
                        columns.sort()
                    continue
                if not columns:
                    continue
                cells = cells_for(words, columns)
                item_key = "Armor" if "Armor" in cells else "Type"
                raw_tl = cells.get("TL", "")
                name = cells.get(item_key, "")
                location = cells.get("Location", "") or ("torso" if source == "Low-Tech" else "")
                raw_dr = cells.get("DR", "")
                if re.fullmatch(r"\d+(?:-\d+)?", raw_tl):
                    previous_tl = raw_tl
                elif name.startswith("+"):
                    raw_tl = previous_tl
                else:
                    continue
                if not name or not location or not re.search(r"\d", raw_dr):
                    continue
                printed_page = physical_page + adjust
                stem = f"{slug(source)}.{printed_page}.{slug(name)}"
                seen[stem] += 1
                identifier = stem if seen[stem] == 1 else f"{stem}.{seen[stem]}"
                dr, dr_by_type, flexible = parse_dr(raw_dr, source, raw_tl)
                direction = "front" if "F" in raw_dr else "all"
                coverage = 5 if any(word in name.casefold() for word in ("breastplate", "cuirass", "plate insert", "trauma plate")) else 6
                weight_match = re.search(r"\d+(?:\.\d+)?", cells.get("Weight", ""))
                tags = [slug(source), "catalog-table"]
                if name.startswith("+"):
                    tags.append("addon")
                if flexible:
                    tags.append("flexible")
                records.append({
                    "identifier": identifier, "source": source, "page": str(printed_page),
                    "name": name.lstrip("+ "), "tech_level": raw_tl,
                    "locations": normalize_locations(location), "dr": dr,
                    "dr_by_type": dr_by_type, "direction": direction, "coverage": coverage,
                    "flexible": flexible, "rigid": not flexible,
                    "ablative": "ablative" in name.casefold(),
                    "semi_ablative": "semi-ablative" in name.casefold(),
                    "weight": float(weight_match.group()) if weight_match else 0.0,
                    "cost": cells.get("Cost", ""), "don_time": "", "dx_penalty": 0,
                    "move_penalty": 0, "legality_class": cells.get("LC", ""),
                    "tags": tags,
                    "original": {key.casefold(): value for key, value in cells.items() if value},
                })
        print(f"armor {source}: {len(records) - before}", file=sys.stderr)

    # Martial Arts training protection is presented as compact stats in prose.
    training = [
        ("Sparring Breastplate (Foam)", ["torso", "vitals"], 1, {"cr": 1, "*": 0}, "front", 40, 2.5),
        ("Sparring Breastplate (Leather)", ["torso", "vitals"], 2, {"cr": 2, "*": 1}, "front", 60, 4),
        ("Cup", ["groin"], 2, {"cr": 2, "*": 1}, "front", 20, 0),
        ("Sparring Foot Guards", ["foot"], 2, {"cr": 2, "*": 1}, "all", 30, 0.5),
        ("Sparring Helmet (Foam)", ["skull", "face"], 1, {"cr": 1, "*": 0}, "all", 40, 1),
        ("Sparring Helmet (Padded)", ["skull", "face"], 2, {"cr": 2, "*": 1}, "all", 60, 3),
        ("Kendo Do", ["torso", "vitals"], 3, {}, "front", 100, 4),
        ("Kendo Kote", ["hand", "arm"], 2, {"cr": 2, "*": 1}, "all", 65, 1),
        ("Kendo Men", ["face", "neck", "skull"], 3, {"skull": 1, "*": 3}, "front", 150, 5),
        ("Fencing Mask", ["skull", "eye", "face"], 2, {}, "all", 50, 3),
        ("Shin Pads", ["leg", "foot"], 2, {"cr": 2, "*": 1}, "front", 40, 2),
    ]
    for name, locations, dr, by_type, direction, cost, weight in training:
        records.append({
            "identifier": f"martial-arts.234.{slug(name)}", "source": "Martial Arts", "page": "234",
            "name": name, "tech_level": "6", "locations": locations, "dr": dr,
            "dr_by_type": by_type, "direction": direction, "coverage": 6,
            "flexible": True, "rigid": False, "ablative": False, "semi_ablative": False,
            "weight": weight, "cost": f"${cost}", "don_time": "", "dx_penalty": 0,
            "move_penalty": 0, "legality_class": "", "tags": ["martial-arts", "training"],
            "original": {},
        })
    records.sort(key=lambda item: (item["name"].casefold(), item["source"], item["identifier"]))
    return records


def technique_records():
    records = []
    seen = defaultdict(int)
    columns = [(54, "name"), (145, "difficulty"), (180, "prerequisite"), (300, "default"),
               (392, "maximum"), (458, "damage"), (530, "page")]
    last = None
    for page in range(3, 7):
        for words in page_rows(TECHNIQUES, page):
            line = " ".join(word for _left, word in words)
            if "About GURPS" in line:
                last = None
                break
            if "Techniques Table" in line or ("Technique" in line and "Difficulty" in line and "Prerequisite" in line):
                last = None
                continue
            cells = cells_for(words, columns)
            printed_page = cells["page"]
            if re.fullmatch(r"\d+", printed_page):
                raw_name = cells["name"].strip()
                if not raw_name or raw_name in {"Technique", "Techniques Table"}:
                    continue
                cinematic = "*" in raw_name
                silly = "†" in raw_name
                name = raw_name.replace("*", "").replace("†", "").strip()
                stem = f"martial-arts.{printed_page}.{slug(name)}"
                seen[stem] += 1
                identifier = stem if seen[stem] == 1 else f"{stem}.{seen[stem]}"
                last = {
                    "identifier": identifier, "source": "Martial Arts", "page": printed_page,
                    "name": name, "difficulty": cells["difficulty"],
                    "prerequisites": [cells["prerequisite"]] if cells["prerequisite"] else [],
                    "defaults": [cells["default"]] if cells["default"] else [],
                    "maximum": cells["maximum"], "profile": "cinematic" if cinematic or silly else "realistic",
                    "silly": silly, "automatable": False, "attack_modifier": 0,
                    "defense_modifier": 0, "damage_modifier": 0, "damage_per_die": 0,
                    "effects": {"summary": cells["damage"]}, "style_ids": [], "tags": [],
                    "original": {"name": raw_name, "damage": cells["damage"]},
                }
                default_penalty = re.search(r"(?:PS|Karate|Brawling|Judo|Wrestling|Parry|Block|DX|HT|ST)-(\d+)", cells["default"], re.I)
                if default_penalty:
                    last["attack_modifier"] = -int(default_penalty.group(1))
                bonus = re.search(r"Per attack\s*\+(\d+)", cells["damage"], re.I)
                if bonus:
                    last["damage_modifier"] = int(bonus.group(1))
                    last["automatable"] = True
                if re.search(r"Per attack|Kick|Punch", cells["damage"], re.I):
                    last["automatable"] = True
                records.append(last)
            elif last:
                for key in ("name", "prerequisite", "default", "maximum", "damage"):
                    if cells[key]:
                        if key == "name":
                            last["name"] = (last["name"] + " " + cells[key]).strip()
                        elif key == "prerequisite":
                            last["prerequisites"][0] = (last["prerequisites"][0] + " " + cells[key]).strip()
                        elif key == "default":
                            last["defaults"][0] = (last["defaults"][0] + " " + cells[key]).strip()
                        elif key == "maximum":
                            last["maximum"] = (last["maximum"] + " " + cells[key]).strip()
                        else:
                            last["effects"]["summary"] = (last["effects"].get("summary", "") + " " + cells[key]).strip()
                            last["original"]["damage"] = last["effects"]["summary"]
    # Correct identifiers if a wrapped name completed after the first row.
    fixed = defaultdict(int)
    for record in records:
        if "*" in record["name"]:
            record["profile"] = "cinematic"
        if "†" in record["name"]:
            record["profile"] = "cinematic"
            record["silly"] = True
        record["name"] = record["name"].replace("*", "").replace("†", "").strip()
        stem = f"martial-arts.{record['page']}.{slug(record['name'])}"
        fixed[stem] += 1
        record["identifier"] = stem if fixed[stem] == 1 else f"{stem}.{fixed[stem]}"
        record["tags"] = [record["profile"], "silly" if record["silly"] else "technique"]
    records.sort(key=lambda item: (item["name"].casefold(), item["page"], item["identifier"]))
    return records


def _capture_component(text, label, labels):
    alternatives = "|".join(re.escape(item) for item in labels if item != label)
    match = re.search(re.escape(label) + r"\s*(.*?)(?=(?:" + alternatives + r")\s*|$)", text, re.I)
    return split_items(match.group(1)) if match else []


def style_records():
    lines = []
    current_page = None
    for physical_page in range(150, 212):
        current_page = physical_page - 1
        output = subprocess.check_output(
            ["pdftotext", "-f", str(physical_page), "-l", str(physical_page), "-raw", str(MARTIAL_ARTS), "-"],
            text=True, errors="replace",
        )
        lines.append((f"<<<PAGE:{current_page}>>>", current_page))
        lines.extend((line.strip(), current_page) for line in output.splitlines() if line.strip())
    headers = []
    for index, (line, page) in enumerate(lines):
        cost_match = re.fullmatch(r"(\d+) points?", line)
        if not cost_match or index == 0:
            continue
        name = lines[index - 1][0].strip()
        if (2 <= len(name) <= 70 and ":" not in name and not name.endswith((".", ",", ";"))
                and not name.startswith("<<<") and len(name.split()) <= 9):
            headers.append((index - 1, name, int(cost_match.group(1)), page))
    records = []
    seen = defaultdict(int)
    labels = ["Skills:", "Techniques:", "Cinematic Skills:", "Cinematic Techniques:", "Perks:", "Optional Traits"]
    for position, (start, name, cost, page) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        segment_lines = [line for line, _page in lines[start + 2:end] if not line.startswith("<<<PAGE:")]
        segment = " ".join(segment_lines)
        main = segment.split("Optional Traits", 1)[0]
        required = _capture_component(main, "Skills:", labels)
        techniques = _capture_component(main, "Techniques:", labels)
        cinematic_skills = _capture_component(main, "Cinematic Skills:", labels)
        cinematic_techniques = _capture_component(main, "Cinematic Techniques:", labels)
        perks = _capture_component(main, "Perks:", labels)
        if not required and not techniques and not cinematic_skills:
            continue
        stem = f"martial-arts.{page}.{slug(name)}"
        seen[stem] += 1
        identifier = stem if seen[stem] == 1 else f"{stem}.{seen[stem]}"
        records.append({
            "identifier": identifier, "source": "Martial Arts", "page": str(page),
            "name": name.title() if name.upper() == name else name,
            "required_skills": required, "techniques": techniques,
            "cinematic_skills": cinematic_skills, "cinematic_techniques": cinematic_techniques,
            "perks": perks, "optional_traits": [], "minimum_cost": cost,
            "profile": "cinematic" if page >= 207 else "realistic", "origin": "", "period": "",
            "original": {"cost": f"{cost} points"},
        })
    records.sort(key=lambda item: (item["name"].casefold(), item["page"], item["identifier"]))
    return records


def write_catalog(path, schema, key, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": schema, key: records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{path.name}: {len(records)}", file=sys.stderr)


def main():
    for source in (BASIC, MARTIAL_ARTS, TECHNIQUES, LOW_TECH, HIGH_TECH, ULTRA_TECH):
        if not source.exists():
            raise SystemExit(f"Missing source PDF: {source}")
    melee = melee_records()
    armor = armor_records()
    techniques = technique_records()
    styles = style_records()
    style_by_technique = defaultdict(list)
    for style in styles:
        for raw in style["techniques"] + style["cinematic_techniques"]:
            base = re.sub(r"\s*\([^)]*\)\s*", "", raw).strip().casefold()
            style_by_technique[base].append(style["identifier"])
    for technique in techniques:
        technique["style_ids"] = sorted(set(style_by_technique.get(technique["name"].casefold(), [])))
    write_catalog(ROOT / "data/melee_weapons.json", MELEE_SCHEMA, "weapons", melee)
    write_catalog(ROOT / "data/armor.json", ARMOR_SCHEMA, "armor", armor)
    write_catalog(ROOT / "data/techniques.json", TECHNIQUE_SCHEMA, "techniques", techniques)
    write_catalog(ROOT / "data/styles.json", STYLE_SCHEMA, "styles", styles)


if __name__ == "__main__":
    main()
