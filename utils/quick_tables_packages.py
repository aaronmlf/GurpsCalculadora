"""Opt-in reference packs. The catalogue imports no rules at startup."""
from dataclasses import replace
from functools import lru_cache


PACKAGE_IDS = ('tactical', 'martial_arts', 'action', 'magic', 'powers_psi',
               'social', 'mass_combat', 'space', 'wilderness', 'treasure', 'horror')


def normalize_packages(values):
    """Stable order; reject unknown IDs, non-string values and old malformed preferences."""
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    selected = {value for value in values if isinstance(value, str)}
    return tuple(key for key in PACKAGE_IDS if key in selected)


@lru_cache(maxsize=len(PACKAGE_IDS))
def _load_package(key):
    # Explicit local imports are also discoverable in the frozen executable.
    if key in ('tactical', 'martial_arts', 'action'):
        from utils.quick_tables_supp_combat import PACKS
    elif key in ('magic', 'powers_psi', 'space'):
        from utils.quick_tables_supp_supernatural import PACKS
    elif key in ('social', 'mass_combat', 'horror'):
        from utils.quick_tables_supp_campaign import PACKS
    elif key in ('wilderness', 'treasure'):
        from utils.quick_tables_supp_fantasy import PACKS
    else:
        return ()
    return tuple(replace(card, package=key) for card in PACKS[key])


def enabled_cards(packages=()):
    """Only requested packs can contribute cards or affect the search index."""
    return tuple(card for key in normalize_packages(packages) for card in _load_package(key))
