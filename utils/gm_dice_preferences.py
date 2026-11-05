"""Small, local expression lists; store totals, never individual dice."""

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import tempfile
from typing import Tuple

from utils.gm_dice import DiceRollError, parse_dice


FAVORITES_LIMIT = 12
RECENT_LIMIT = 12
_FILE_LIMIT = 16_384


def _clean_expressions(values, limit):
    if not isinstance(values, list):
        return ()
    result = []
    for value in values:
        try:
            expression = parse_dice(value).expression
        except DiceRollError:
            continue
        if expression not in result:
            result.append(expression)
            if len(result) == limit:
                break
    return tuple(result)


@dataclass(frozen=True)
class DiceExpressions:
    favorites: Tuple[str, ...] = ()
    recent: Tuple[str, ...] = ()
    recent_totals: Tuple[Tuple[str, int], ...] = ()

    @classmethod
    def load(cls, path):
        try:
            with Path(path).open('rb') as handle:
                payload = handle.read(_FILE_LIMIT + 1)
            if len(payload) > _FILE_LIMIT:
                return cls()
            document = json.loads(payload)
        except (OSError, ValueError, RecursionError):
            return cls()
        if not isinstance(document, dict) or document.get('schema') != 1:
            return cls()
        recent = _clean_expressions(document.get('recent'), RECENT_LIMIT)
        saved_totals = document.get('recent_totals')
        totals = ()
        if isinstance(saved_totals, dict):
            totals = tuple((expression, saved_totals[expression]) for expression in recent
                           if cls._valid_total(expression, saved_totals.get(expression)))
        return cls(_clean_expressions(document.get('favorites'), FAVORITES_LIMIT), recent, totals)

    @staticmethod
    def _valid_total(expression, total):
        parsed = parse_dice(expression)
        return (type(total) is int and parsed.count + parsed.modifier <= total <=
                parsed.count * parsed.sides + parsed.modifier)

    def remember(self, expression, total=None):
        expression = parse_dice(expression).expression
        recent = (expression, *(entry for entry in self.recent if entry != expression))[:RECENT_LIMIT]
        totals = dict(self.recent_totals)
        if self._valid_total(expression, total):
            totals[expression] = total
        return replace(self, recent=recent, recent_totals=tuple((entry, totals[entry])
                                                               for entry in recent if entry in totals))

    def toggle_favorite(self, expression):
        expression = parse_dice(expression).expression
        if expression in self.favorites:
            favorites = tuple(entry for entry in self.favorites if entry != expression)
        else:
            if len(self.favorites) >= FAVORITES_LIMIT:
                raise DiceRollError('favorite_limit')
            favorites = (expression, *self.favorites)
        return replace(self, favorites=favorites)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({'schema': 1, 'favorites': self.favorites, 'recent': self.recent,
                           'recent_totals': dict(self.recent_totals)}, handle)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
