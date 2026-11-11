"""Mint IRIs for ManaGraph resources and link targets for external IDs.

All ManaGraph resources live under ``https://w3id.org/managraph/``:

- card (the oracle "work"): ``card/{oracle_id}``
- card face:                ``card/{oracle_id}/face/{index}``
- printing:                 ``printing/{scryfall_id}``
- set:                      ``set/{set_code}``

Cards and printings are keyed by Scryfall's UUIDs, which stay the same when
names or text change. Faces have no ID of their own, so they are numbered by
their position in ``card_faces`` (0 = front). Set codes are lowercased, as
Scryfall serves them.

These IRIs are a public contract: saved queries and external links depend on
them. Don't change a pattern without a migration plan.

External IDs map to the providers' own URLs, linked with ``skos:exactMatch``.
MTGO and Card Kingdom IDs have no public per-ID URL, so they stay literals.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import quote

BASE = "https://w3id.org/managraph/"
ONTOLOGY = BASE + "ontology#"

_SET_CODE = re.compile(r"^[a-z0-9]+$")


def _uuid(value: str, what: str) -> str:
    """Return ``value`` as a lowercase canonical UUID string, or raise ValueError."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"invalid {what}: {value!r}") from None
    return str(parsed)


def card(oracle_id: str) -> str:
    """IRI of an oracle card, the work shared by all its printings."""
    return f"{BASE}card/{_uuid(oracle_id, 'oracle_id')}"


def face(oracle_id: str, index: int) -> str:
    """IRI of one face of a multi-face card (split, MDFC, adventure, ...)."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError(f"invalid face index: {index!r}")
    return f"{card(oracle_id)}/face/{index}"


def printing(scryfall_id: str) -> str:
    """IRI of a printing, keyed by its Scryfall card ID."""
    return f"{BASE}printing/{_uuid(scryfall_id, 'Scryfall ID')}"


def set_(code: str) -> str:
    """IRI of a set, keyed by its lowercased set code (e.g. ``"lea"``)."""
    normalized = code.lower() if isinstance(code, str) else code
    if not isinstance(normalized, str) or not _SET_CODE.match(normalized):
        raise ValueError(f"invalid set code: {code!r}")
    return f"{BASE}set/{normalized}"


def ontology(term: str) -> str:
    """IRI of a class or property in the ManaGraph ontology."""
    return ONTOLOGY + term


# --- external IDs -----------------------------------------------------------


def _positive_int(value: int | str, what: str) -> int:
    try:
        number = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"invalid {what}: {value!r}") from None
    if number <= 0 or isinstance(value, bool):
        raise ValueError(f"invalid {what}: {value!r}")
    return number


def scryfall(scryfall_id: str) -> str:
    """Scryfall API URL of a printing."""
    return f"https://api.scryfall.com/cards/{_uuid(scryfall_id, 'Scryfall ID')}"


def scryfall_oracle(oracle_id: str) -> str:
    """Scryfall search URL listing every printing of an oracle card."""
    query = quote(f"oracleid:{_uuid(oracle_id, 'oracle_id')}")
    return f"https://scryfall.com/search?q={query}&unique=prints"


def multiverse(multiverse_id: int | str) -> str:
    """Gatherer URL of a printing's multiverse ID."""
    number = _positive_int(multiverse_id, "multiverse ID")
    return f"https://gatherer.wizards.com/Pages/Card/Details.aspx?multiverseid={number}"


def tcgplayer(product_id: int | str) -> str:
    """TCGplayer product page."""
    return f"https://www.tcgplayer.com/product/{_positive_int(product_id, 'TCGplayer ID')}"


def cardmarket(product_id: int | str) -> str:
    """Cardmarket product page."""
    number = _positive_int(product_id, "Cardmarket ID")
    return f"https://www.cardmarket.com/en/Magic/Products?idProduct={number}"
