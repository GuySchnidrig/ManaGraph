import gzip
import json

import pyoxigraph as ox
import pytest

from managraph import convert, iri

ORACLE_ID = "b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6"
SCRYFALL_ID = "0000579f-7b35-4ed3-b44c-db2a538066fe"
ARTIST_ID = "9e6a55ae-be4d-4c23-a2a5-135737ffd879"
ILLUSTRATION_ID = "7106ab4f-bd3e-4d2a-ba9c-7f223b5a0b7f"
MG = "https://w3id.org/managraph/ontology#"


@pytest.fixture(scope="module")
def vocab():
    return convert.Vocabulary()


# --- type lines -------------------------------------------------------------


@pytest.mark.parametrize(
    "type_line, expected",
    [
        ("Legendary Creature — Elf Druid",
         [("super", "Legendary"), ("card", "Creature"), ("creature", "Elf"), ("creature", "Druid")]),
        ("Land Creature — Forest Dryad",
         [("card", "Land"), ("card", "Creature"), ("land", "Forest"), ("creature", "Dryad")]),
        ("Artifact — Spacecraft", [("card", "Artifact"), ("artifact", "Spacecraft")]),
        ("Legendary Creature — Time Lord Human",
         [("super", "Legendary"), ("card", "Creature"), ("creature", "Time Lord"), ("creature", "Human")]),
        ("Land — Urza's Mine", [("card", "Land"), ("land", "Urza's"), ("land", "Mine")]),
        ("Tribal Instant — Angel", [("card", "Kindred"), ("card", "Instant"), ("creature", "Angel")]),
        ("Host Creature — Dog", [("card", "Creature"), ("creature", "Dog"), ("un", "Host")]),
        ("Instant", [("card", "Instant")]),
        ("", []),
    ],
)
def test_parse_type_line(vocab, type_line, expected):
    assert sorted(convert.parse_type_line(type_line, vocab)) == sorted(expected)


def test_long_unknown_phrase_is_one_un_type(vocab):
    parsed = convert.parse_type_line("Creature — Lady of Proper Etiquette", vocab)
    assert ("un", "Lady of Proper Etiquette") in parsed


# --- colors -----------------------------------------------------------------


@pytest.mark.parametrize(
    "cost, expected",
    [("{2}{W}{U}", ["W", "U"]), ("{W/U}{G/P}", ["W", "U", "G"]), ("{3}", []), ("", []), ("{C}", [])],
)
def test_mana_cost_colors(cost, expected):
    assert convert.mana_cost_colors(cost) == expected


def test_split_face_colors_come_from_their_own_cost():
    card = {"layout": "split", "colors": ["U", "R"]}
    assert convert.face_colors(card, {"mana_cost": "{1}{R}"}) == ["R"]


def test_flip_faces_share_the_card_colors():
    card = {"layout": "flip", "colors": ["U"]}
    assert convert.face_colors(card, {"mana_cost": ""}) == ["U"]


# --- end to end -------------------------------------------------------------

ORACLE_CARD = {
    "object": "card", "id": SCRYFALL_ID, "oracle_id": ORACLE_ID, "name": "Fire // Ice",
    "layout": "split", "cmc": 4.0, "colors": ["U", "R"], "color_identity": ["U", "R"],
    "keywords": ["Changeling", "Treasure"], "reserved": False, "game_changer": False,
    "legalities": {"modern": "legal", "vintage": "restricted", "standard": "not_legal", "legacy": "banned"},
    "card_faces": [
        {"object": "card_face", "name": "Fire", "mana_cost": "{1}{R}", "type_line": "Instant",
         "oracle_text": "Fire deals 2 damage divided as you choose among one or two targets."},
        {"object": "card_face", "name": "Ice", "mana_cost": "{1}{U}", "type_line": "Instant",
         "oracle_text": "Tap target permanent.\nDraw a card."},
    ],
}
PRINTING = {
    **ORACLE_CARD, "set": "mh2", "set_name": "Modern Horizons 2", "set_type": "draft_innovation",
    "collector_number": "290", "released_at": "2021-06-18", "rarity": "uncommon",
    "games": ["paper", "mtgo"], "finishes": ["nonfoil", "foil"], "frame": "2015", "border_color": "black",
    "frame_effects": ["showcase"], "watermark": "d&d", "multiverse_ids": [522269, 522270],
    "tcgplayer_id": 240000, "artist": "Magali Villeneuve", "artist_ids": [ARTIST_ID],
    "illustration_id": ILLUSTRATION_ID,
}
TOKEN = {**ORACLE_CARD, "oracle_id": "00037840-6089-42ec-8c5c-281f9f474504", "layout": "token"}
RULING = {"object": "ruling", "oracle_id": ORACLE_ID, "source": "wotc", "published_at": "2021-03-19",
          "comment": "Fire and Ice are separate halves."}


def _jsonl(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as out:
        out.writelines(json.dumps(row) + "\n" for row in rows)


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    raw = tmp_path_factory.mktemp("raw")
    out = tmp_path_factory.mktemp("rdf")
    _jsonl(raw / "oracle_cards.jsonl.gz", [ORACLE_CARD, TOKEN])
    _jsonl(raw / "default_cards.jsonl.gz", [PRINTING, {**TOKEN, "id": TOKEN["oracle_id"]}])
    _jsonl(raw / "rulings.jsonl.gz", [RULING, {**RULING, "oracle_id": TOKEN["oracle_id"]}])
    convert.convert(raw, out)
    store = ox.Store()
    for path in out.glob("*.nt.gz"):
        store.load(gzip.open(path, "rb").read(), format=ox.RdfFormat.N_TRIPLES)
    return store


def ask(store, pattern):
    return store.query(f"PREFIX mg: <{MG}> ASK {{ {pattern} }}")


def test_card_and_faces(graph):
    card, fire = iri.card(ORACLE_ID), iri.face(ORACLE_ID, 0)
    assert ask(graph, f'<{card}> a mg:Card ; mg:name "Fire // Ice" ; mg:hasFace <{fire}>')
    assert ask(graph, f'<{fire}> mg:faceOf <{card}> ; mg:name "Fire" ; mg:color <{iri.color("R")}>')
    assert not ask(graph, f'<{fire}> mg:color <{iri.color("U")}>')
    assert ask(graph, f'<{fire}> mg:hasCardType <{iri.type_("card", "Instant")}>')


def test_legalities(graph):
    card = iri.card(ORACLE_ID)
    assert ask(graph, f'<{card}> mg:legalIn <{iri.format_("modern")}> ; mg:restrictedIn <{iri.format_("vintage")}> '
                      f'; mg:bannedIn <{iri.format_("legacy")}>')
    assert not ask(graph, f'<{card}> ?p <{iri.format_("standard")}>')


def test_keywords_cr_and_minted(graph):
    card = iri.card(ORACLE_ID)
    assert ask(graph, f'<{card}> mg:hasKeyword <{iri.keyword("Changeling")}>')
    # Treasure is not a CR keyword, so the converter declares it
    assert ask(graph, f'<{iri.keyword("Treasure")}> a mg:Keyword')
    assert not ask(graph, f'<{iri.keyword("Changeling")}> a mg:Keyword')  # declared in keywords.ttl instead


def test_printing(graph):
    p = iri.printing(SCRYFALL_ID)
    assert ask(graph, f'<{p}> a mg:Printing ; mg:printingOf <{iri.card(ORACLE_ID)}> ; mg:inSet <{iri.set_("mh2")}> '
                      f'; mg:rarity <{iri.rarity("uncommon")}> ; mg:frame <{iri.concept("frame", "2015")}>')
    assert ask(graph, f'<{iri.set_("mh2")}> mg:setType <{iri.set_type("draft_innovation")}>')
    assert ask(graph, f'<{p}> <http://www.w3.org/2004/02/skos/core#exactMatch> <{iri.multiverse(522270)}>')
    assert ask(graph, f'<{p}> mg:hasIllustration/mg:illustratedBy/mg:name "Magali Villeneuve"')
    # open scheme concepts are minted, percent-encoded
    assert ask(graph, f'<{iri.concept("watermark", "d&d")}> a <http://www.w3.org/2004/02/skos/core#Concept>')


def test_ruling(graph):
    r = iri.ruling(ORACLE_ID, RULING["published_at"], RULING["comment"])
    assert ask(graph, f'<{r}> mg:rulingOn <{iri.card(ORACLE_ID)}> ; mg:rulingSource "wotc"')


def test_non_game_layouts_dropped_with_their_printings_and_rulings(graph):
    token = TOKEN["oracle_id"]
    assert not ask(graph, f"<{iri.card(token)}> ?p ?o")
    assert not ask(graph, f"<{iri.printing(token)}> ?p ?o")
    assert not ask(graph, f"?r mg:rulingOn <{iri.card(token)}>")
