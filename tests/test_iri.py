import pytest

from managraph import iri

ORACLE_ID = "b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6"
SCRYFALL_ID = "0000579f-7b35-4ed3-b44c-db2a538066fe"


def test_card():
    assert iri.card(ORACLE_ID) == f"https://w3id.org/managraph/card/{ORACLE_ID}"


def test_card_normalizes_uuid_case():
    assert iri.card(ORACLE_ID.upper()) == iri.card(ORACLE_ID)


def test_face():
    assert iri.face(ORACLE_ID, 1) == f"https://w3id.org/managraph/card/{ORACLE_ID}/face/1"


@pytest.mark.parametrize("index", [-1, 1.0, "0", True])
def test_face_rejects_bad_index(index):
    with pytest.raises(ValueError):
        iri.face(ORACLE_ID, index)


def test_printing():
    assert iri.printing(SCRYFALL_ID) == f"https://w3id.org/managraph/printing/{SCRYFALL_ID}"


@pytest.mark.parametrize("bad", ["", "not-a-uuid", None, "../etc/passwd"])
def test_uuid_ids_reject_garbage(bad):
    with pytest.raises(ValueError):
        iri.card(bad)
    with pytest.raises(ValueError):
        iri.printing(bad)


def test_set_lowercases():
    assert iri.set_("LEA") == "https://w3id.org/managraph/set/lea"
    assert iri.set_("p30a") == "https://w3id.org/managraph/set/p30a"


@pytest.mark.parametrize("bad", ["", "le a", "lea/x", None])
def test_set_rejects_bad_code(bad):
    with pytest.raises(ValueError):
        iri.set_(bad)


def test_ontology():
    assert iri.ontology("Card") == "https://w3id.org/managraph/ontology#Card"


def test_external_ids():
    assert iri.scryfall(SCRYFALL_ID) == f"https://api.scryfall.com/cards/{SCRYFALL_ID}"
    assert iri.scryfall_oracle(ORACLE_ID) == (
        f"https://scryfall.com/search?q=oracleid%3A{ORACLE_ID}&unique=prints"
    )
    assert iri.multiverse(600) == "https://gatherer.wizards.com/Pages/Card/Details.aspx?multiverseid=600"
    assert iri.multiverse("600") == iri.multiverse(600)
    assert iri.tcgplayer(1234) == "https://www.tcgplayer.com/product/1234"
    assert iri.cardmarket(5678) == "https://www.cardmarket.com/en/Magic/Products?idProduct=5678"


@pytest.mark.parametrize("bad", [0, -3, "abc", None, True])
def test_external_numeric_ids_reject_garbage(bad):
    with pytest.raises(ValueError):
        iri.tcgplayer(bad)


def test_all_oracle_cards_mint():
    """Every card in the local oracle dump gets a valid card IRI (skipped without data)."""
    import gzip
    import json
    from pathlib import Path

    path = Path("data/raw/scryfall/oracle_cards.jsonl.gz")
    if not path.exists():
        pytest.skip("no local Scryfall download")
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            card_iri = iri.card(data["oracle_id"])
            assert card_iri not in seen
            seen.add(card_iri)
            iri.printing(data["id"])
            iri.set_(data["set"])


# --- vocabularies -----------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [("Elf", "Elf"), ("Time Lord", "Time_Lord"), ("Urza’s", "Urzas"), ("Urza's", "Urzas"),
     ("For Mirrodin!", "For_Mirrodin"), ("Power-Plant", "Power-Plant")],
)
def test_slug(name, expected):
    assert iri.slug(name) == expected


@pytest.mark.parametrize("name", ["", "  ", "!", None])
def test_slug_rejects_empty(name):
    with pytest.raises(ValueError):
        iri.slug(name)


def test_type_keeps_categories_apart():
    assert iri.type_("artifact", "Spacecraft") == "https://w3id.org/managraph/type/artifact/Spacecraft"
    assert iri.type_("planar", "Spacecraft") != iri.type_("artifact", "Spacecraft")


def test_type_rejects_unknown_category():
    with pytest.raises(ValueError):
        iri.type_("tribal", "Elf")


def test_keyword_is_lowercase():
    assert iri.keyword("First strike") == "https://w3id.org/managraph/keyword/first_strike"
    assert iri.keyword("First Strike") == iri.keyword("first strike")


def test_color():
    assert iri.color("w") == "https://w3id.org/managraph/color/W"
    with pytest.raises(ValueError):
        iri.color("X")


@pytest.mark.parametrize("fn, key", [(iri.format_, "commander"), (iri.layout, "modal_dfc"), (iri.set_type, "token"), (iri.rarity, "mythic")])
def test_keyed_vocabularies(fn, key):
    assert fn(key).endswith("/" + key)
    with pytest.raises(ValueError):
        fn("Not A Key")


def test_concept():
    assert iri.concept("frame", "2015") == "https://w3id.org/managraph/vocab/frame/2015"
    assert iri.concept("watermark", "d&d") == "https://w3id.org/managraph/vocab/watermark/d%26d"
    with pytest.raises(ValueError):
        iri.concept("price", "usd")


def test_artist_and_illustration():
    assert iri.artist(SCRYFALL_ID) == f"https://w3id.org/managraph/artist/{SCRYFALL_ID}"
    assert iri.illustration(SCRYFALL_ID) == f"https://w3id.org/managraph/illustration/{SCRYFALL_ID}"


def test_ruling_is_stable_and_text_sensitive():
    a = iri.ruling(ORACLE_ID, "2021-03-19", "Some text.")
    assert a == iri.ruling(ORACLE_ID, "2021-03-19", "Some text.")
    assert a != iri.ruling(ORACLE_ID, "2021-03-19", "Other text.")
    assert a.startswith(iri.card(ORACLE_ID) + "/ruling/")


def test_un_type():
    assert iri.type_("un", "Donkey") == "https://w3id.org/managraph/type/un/Donkey"
