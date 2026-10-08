"""Rebuild compact spell statistics from Poppler word coordinates, not split columns.

Input: pdftotext -bbox output for Magic's appendix (PDF pages 225-239).
Output: statistical overrides only; never descriptions or page images.
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def name_key(name):
    return re.sub(r'[^a-z0-9]', '', name.lower().replace('*', ''))


def seconds(raw):
    if raw in {"Instant", "Instant."}:
        return 0
    match = re.fullmatch(r'(\d+)\s*(sec\.?|min\.?|hr\.?|hrs\.?|hour|hours|day|days|week|weeks)', raw)
    if not match:
        return None
    unit = match[2].rstrip('.')
    return int(match[1]) * {'sec': 1, 'min': 60, 'hr': 3600, 'hrs': 3600,
                          'hour': 3600, 'hours': 3600, 'day': 86400, 'days': 86400,
                          'week': 604800, 'weeks': 604800}[unit]


def extract(path):
    ns = {'h': 'http://www.w3.org/1999/xhtml'}
    result = {}
    for page in ET.parse(path).findall('.//h:page', ns):
        words = page.findall('h:word', ns)
        headers = [w for w in words if w.text == 'Class']
        if not headers:
            continue
        header = headers[0]
        y_header = float(header.get('yMin'))
        offset = float(header.get('xMin')) - 179.318970
        rows = {}
        for word in words:
            y = float(word.get('yMin'))
            if y <= y_header + 5 or y > 735:
                continue
            rows.setdefault(round(y), []).append(word)
        for row in rows.values():
            def column(left, right):
                return ' '.join(w.text or '' for w in sorted(row, key=lambda w: float(w.get('xMin')))
                    if left <= (float(w.get('xMin')) + float(w.get('xMax'))) / 2 - offset < right)
            reference = column(65, 100)
            if not reference.isdigit():
                continue
            name = column(100, 178)
            if not name:
                continue
            energy, duration, time = column(338, 378), column(302, 338), column(378, 424)
            record = {'page': reference, 'name': name.rstrip('*'), 'original': {
                'energy': energy, 'duration': duration, 'casting_time': time,
                'class': column(178, 246), 'table_source': 'Magic pp. 223-237'}}
            cost = re.fullmatch(r'(\d+)(?:/(\d+|H|S))?', energy)
            record['base_cost'] = int(cost[1]) if cost else None
            record['maintenance_cost'] = None
            if cost and cost[2]:
                record['maintenance_cost'] = (int(cost[1]) / 2 if cost[2] == 'H' else
                                               int(cost[1]) if cost[2] == 'S' else int(cost[2]))
            record['casting_time_seconds'] = seconds(time)
            record['duration_seconds'] = seconds(duration)
            result[name_key(name)] = record
    # The centered variable-cost Missile row crosses the Energy boundary.
    # Preserve its notation explicitly; the application requires user parameters.
    if 'fireball' in result:
        result['fireball']['original'].update(energy='1 to Magery#', duration='Instant', casting_time='1 to 3 sec.')
        result['fireball']['duration_seconds'] = 0
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('bbox')
    parser.add_argument('output')
    args = parser.parse_args()
    rows = extract(args.bbox)
    Path(args.output).write_text(json.dumps({'schema': 'gurps.magic-table.v1', 'spells': rows},
                                          ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(rows)} statistical rows extracted')
