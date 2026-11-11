import pytest

from managraph.scope import is_game_card


@pytest.mark.parametrize("layout", ["normal", "modal_dfc", "split", "adventure", "meld", "reversible_card"])
def test_game_layouts_kept(layout):
    assert is_game_card({"layout": layout})


@pytest.mark.parametrize(
    "layout",
    ["art_series", "token", "double_faced_token", "emblem", "planar", "scheme", "vanguard", "front_card"],
)
def test_non_game_layouts_dropped(layout):
    assert not is_game_card({"layout": layout})
