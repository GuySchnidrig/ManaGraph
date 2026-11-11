"""Mint IRIs for ManaGraph resources and link targets for external IDs.

All ManaGraph resources live under ``https://w3id.org/managraph/``:

- card (the oracle "work"): ``card/{oracle_id}``
- card face:                ``card/{oracle_id}/face/{index}``
- printing:                 ``printing/{scryfall_id}``
- set:                      ``set/{set_code}``
- ruling:                   ``card/{oracle_id}/ruling/{hash}``
- artist, illustration:     ``artist/{uuid}``, ``illustration/{uuid}``
- vocabularies (types, keywords, colors, formats, layouts, rarities, SKOS
  concepts for printing attributes): see the section further down.

Cards and printings are keyed by Scryfall's UUIDs, which stay the same when
names or text change. Faces have no ID of their own, so they are numbered by
their position in ``card_faces`` (0 = front). Single-faced cards have one
face, 0. Set codes are lowercased, as
Scryfall serves them.

These IRIs are a public contract: saved queries and external links depend on
them. Don't change a pattern without a migration plan.

External IDs map to the providers' own URLs, linked with ``skos:exactMatch``.
MTGO and Card Kingdom IDs have no public per-ID URL, so they stay literals.
Cards link to a Scryfall search page (``scryfall_oracle``) with
``rdfs:seeAlso``, since a search page is related to the card, not the same
concept.
"""

from __future__ import annotations

import hashlib
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
    """Scryfall search URL listing every printing of an oracle card.

    Link it with ``rdfs:seeAlso``, not ``skos:exactMatch``.
    """
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


# --- controlled vocabularies ------------------------------------------------
#
# Types, keywords, colors, formats, layouts, rarities and printing attributes
# are fixed vocabularies. Each gets its own path, so equal names in different
# vocabularies never clash (Spacecraft is both an artifact and a planar type).
#
# - type:         type/{category}/{Name}   e.g. type/creature/Elf
# - keyword:      keyword/{name}           e.g. keyword/first_strike
# - color:        color/{W|U|B|R|G|C}
# - format:       format/{key}             e.g. format/commander
# - layout:       layout/{key}             e.g. layout/modal_dfc
# - set type:     set-type/{key}           e.g. set-type/expansion
# - rarity:       rarity/{key}             e.g. rarity/mythic
# - SKOS concept: vocab/{scheme}/{value}   e.g. vocab/frame/2015

TYPE_CATEGORIES = frozenset({
    "card", "super",  # card types (205.2a) and supertypes (205.4a)
    "artifact", "battle", "creature", "dungeon", "enchantment",  # subtypes (205.3g-q)
    "land", "planar", "planeswalker", "spell",
    "un",  # type-line words not in the CR, mostly from Un-sets (mg:UnType)
})
COLORS = frozenset("WUBRGC")  # C is colorless mana, not a color (105.1, 106.1b)
CONCEPT_SCHEMES = frozenset({
    "game", "finish", "frame", "frame_effect", "border_color",
    "promo_type", "security_stamp", "watermark",
})

_KEY = re.compile(r"^[a-z0-9_]+$")
_SLUG = re.compile(r"^\w[\w-]*$")


def slug(name: str) -> str:
    """Local name for a type or keyword: punctuation dropped, spaces as ``_``.

    ``"Urza’s"`` -> ``"Urzas"``, ``"Time Lord"`` -> ``"Time_Lord"``,
    ``"For Mirrodin!"`` -> ``"For_Mirrodin"``. Case and hyphens are kept.
    """
    if not isinstance(name, str):
        raise ValueError(f"invalid name: {name!r}")
    local = re.sub(r"\s+", "_", re.sub(r"[^\w\s-]", "", name).strip())
    if not _SLUG.match(local):
        raise ValueError(f"invalid name: {name!r}")
    return local


def _key(value: str, what: str) -> str:
    if not isinstance(value, str) or not _KEY.match(value):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def type_(category: str, name: str) -> str:
    """IRI of a card type, supertype or subtype, e.g. ``type_("creature", "Elf")``."""
    if category not in TYPE_CATEGORIES:
        raise ValueError(f"invalid type category: {category!r}")
    return f"{BASE}type/{category}/{slug(name)}"


def keyword(name: str) -> str:
    """IRI of a keyword ability, keyword action or ability word (lowercased)."""
    return f"{BASE}keyword/{slug(name).lower()}"


def color(code: str) -> str:
    """IRI of a color or colorless mana, by its symbol (``W U B R G C``)."""
    if not isinstance(code, str) or code.upper() not in COLORS:
        raise ValueError(f"invalid color: {code!r}")
    return f"{BASE}color/{code.upper()}"


def format_(key: str) -> str:
    """IRI of a play format, by its Scryfall legalities key (e.g. ``"commander"``)."""
    return f"{BASE}format/{_key(key, 'format')}"


def layout(key: str) -> str:
    """IRI of a card layout, by its Scryfall key (e.g. ``"modal_dfc"``)."""
    return f"{BASE}layout/{_key(key, 'layout')}"


def set_type(key: str) -> str:
    """IRI of a set type, by its Scryfall key (e.g. ``"expansion"``, ``"token"``)."""
    return f"{BASE}set-type/{_key(key, 'set type')}"


def rarity(key: str) -> str:
    """IRI of a rarity, by its Scryfall key (e.g. ``"mythic"``)."""
    return f"{BASE}rarity/{_key(key, 'rarity')}"


def concept_scheme(scheme: str) -> str:
    """IRI of a SKOS concept scheme for a printing attribute."""
    if scheme not in CONCEPT_SCHEMES:
        raise ValueError(f"invalid concept scheme: {scheme!r}")
    return f"{BASE}vocab/{scheme}"


def concept(scheme: str, value: str) -> str:
    """IRI of a SKOS concept: one Scryfall value of a printing attribute.

    The value is lowercased and percent-encoded, so ``"d&d"`` -> ``d%26d``.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid {scheme} value: {value!r}")
    return f"{concept_scheme(scheme)}/{quote(value.lower(), safe='')}"


# --- other entities ---------------------------------------------------------


def artist(artist_id: str) -> str:
    """IRI of an artist, keyed by Scryfall's artist ID."""
    return f"{BASE}artist/{_uuid(artist_id, 'artist ID')}"


def illustration(illustration_id: str) -> str:
    """IRI of an illustration (artwork shared across printings), by Scryfall's illustration ID."""
    return f"{BASE}illustration/{_uuid(illustration_id, 'illustration ID')}"


def ruling(oracle_id: str, published_at: str, text: str) -> str:
    """IRI of a ruling on a card.

    Rulings have no ID of their own, so they are keyed by a hash of their date
    and text: stable across downloads, and a reworded ruling gets a new IRI.
    """
    digest = hashlib.sha1(f"{published_at}\n{text}".encode("utf-8")).hexdigest()[:16]
    return f"{card(oracle_id)}/ruling/{digest}"
