"""Decide which Scryfall card objects belong in the graph.

ManaGraph models cards you play Magic with. Scryfall also lists objects that
aren't game cards, or that only exist in casual variants, and those are left
out:

- ``art_series``: art cards from collector boosters
- ``token``, ``double_faced_token``: tokens, and minigame inserts printed like them
- ``emblem``: emblems created by planeswalkers
- ``planar``, ``scheme``, ``vanguard``: Planechase, Archenemy and Vanguard cards
- ``front_card``: non-game inserts with the type line "Card"
"""

from __future__ import annotations

NON_GAME_LAYOUTS = frozenset({
    "art_series",
    "token",
    "double_faced_token",
    "emblem",
    "planar",
    "scheme",
    "vanguard",
    "front_card",
})


def is_game_card(card: dict) -> bool:
    """True if a Scryfall card object belongs in the graph."""
    return card.get("layout") not in NON_GAME_LAYOUTS
