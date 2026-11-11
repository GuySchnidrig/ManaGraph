"""Convert Scryfall bulk data to RDF.

Reads the downloaded bulk files and writes gzipped N-Triples to ``data/rdf/``:

- ``cards.nt.gz``      cards and their faces (from ``oracle_cards``)
- ``printings.nt.gz``  printings, sets, illustrations and artists (``default_cards``)
- ``rulings.nt.gz``    rulings (``rulings``)
- ``minted.nt.gz``     vocabulary terms the data uses but the ontology doesn't
                       declare: Scryfall-only keywords, Un types, and concepts
                       in the open SKOS schemes (frame effects, promo types,
                       watermarks)

Non-game layouts are skipped (``managraph.scope``). Both directions of the
structural links are written (hasFace/faceOf, hasPrinting/printingOf,
hasRuling/rulingOn), so the graph is usable before any reasoning step.

Usage::

    uv run python -m managraph.convert
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pyoxigraph as ox

from managraph import download, iri
from managraph.scope import is_game_card

DEFAULT_OUT = download.PROJECT_ROOT / "data" / "rdf"
ONTOLOGY_DIR = download.PROJECT_ROOT / "ontology"

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"

A = ox.NamedNode(RDF + "type")
LABEL = ox.NamedNode(RDFS + "label")
SEE_ALSO = ox.NamedNode(RDFS + "seeAlso")
EXACT_MATCH = ox.NamedNode(SKOS + "exactMatch")
PREF_LABEL = ox.NamedNode(SKOS + "prefLabel")
IN_SCHEME = ox.NamedNode(SKOS + "inScheme")
CONCEPT = ox.NamedNode(SKOS + "Concept")
XSD_DATE = ox.NamedNode(XSD + "date")
XSD_DECIMAL = ox.NamedNode(XSD + "decimal")
XSD_INTEGER = ox.NamedNode(XSD + "integer")
XSD_NON_NEGATIVE = ox.NamedNode(XSD + "nonNegativeInteger")
XSD_BOOLEAN = ox.NamedNode(XSD + "boolean")

_MG: dict[str, ox.NamedNode] = {}


def mg(term: str) -> ox.NamedNode:
    """Ontology term ``mg:{term}``."""
    node = _MG.get(term)
    if node is None:
        node = _MG[term] = ox.NamedNode(iri.ontology(term))
    return node


def node(value: str) -> ox.NamedNode:
    return ox.NamedNode(value)


def text(value: str) -> ox.Literal:
    return ox.Literal(value)


def date(value: str) -> ox.Literal:
    return ox.Literal(value, datatype=XSD_DATE)


def integer(value: int) -> ox.Literal:
    return ox.Literal(str(int(value)), datatype=XSD_INTEGER)


def decimal(value: float) -> ox.Literal:
    return ox.Literal(repr(float(value)), datatype=XSD_DECIMAL)


def boolean(value: bool) -> ox.Literal:
    return ox.Literal("true" if value else "false", datatype=XSD_BOOLEAN)


def T(s: ox.NamedNode, p: ox.NamedNode, o: ox.NamedNode | ox.Literal) -> ox.Triple:  # noqa: N802
    return ox.Triple(s, p, o)


# --- vocabulary -------------------------------------------------------------

# Card type -> subtype categories that go with it (CR 205.3c-d, 205.3g-q).
SUBTYPE_CATEGORIES = {
    "Artifact": ("artifact",),
    "Enchantment": ("enchantment",),
    "Land": ("land",),
    "Planeswalker": ("planeswalker",),
    "Instant": ("spell",),
    "Sorcery": ("spell",),
    "Creature": ("creature",),
    "Kindred": ("creature",),
    "Plane": ("planar",),
    "Dungeon": ("dungeon",),
    "Battle": ("battle",),
}
ALL_SUBTYPE_CATEGORIES = tuple(sorted({c for cats in SUBTYPE_CATEGORIES.values() for c in cats}))
LONGEST_SUBTYPE = 4  # words, e.g. "Bolas's Meditation Realm"


def _norm(name: str) -> str:
    return name.replace("’", "'").casefold()


class Vocabulary:
    """The terms the ontology declares, plus whatever the data needs minted.

    ``types[category][normalized label]`` gives a type's canonical label.
    ``ensure`` returns a term's node and, if the ontology doesn't declare it,
    records triples declaring it in ``minted``.
    """

    def __init__(self, ontology_dir: Path = ONTOLOGY_DIR):
        store = ox.Store()
        for path in sorted(ontology_dir.glob("*.ttl")):
            store.load(path=str(path), format=ox.RdfFormat.TURTLE)
        self.declared = {
            quad.subject.value for quad in store.quads_for_pattern(None, A, None)
            if isinstance(quad.subject, ox.NamedNode)
        }
        self.types: dict[str, dict[str, str]] = {}
        prefix = iri.BASE + "type/"
        # Alternative labels resolve too: "Tribal" is the old name of Kindred (CR 308.3).
        for row in store.query(f"""
            SELECT ?t ?name ?label WHERE {{
                ?t a ?cls ; <{RDFS}label> ?label ; <{RDFS}label>|<{SKOS}altLabel> ?name .
                ?cls <{RDFS}subClassOf>* <{iri.ontology('Type')}> .
            }}"""):
            category = row["t"].value.removeprefix(prefix).split("/", 1)[0]
            self.types.setdefault(category, {})[_norm(row["name"].value)] = row["label"].value
        self.minted: list[ox.Triple] = []
        self.minted_counts: Counter[str] = Counter()

    def ensure(self, value: str, cls: ox.NamedNode, label: str,
               label_property: ox.NamedNode = LABEL, extra: Iterable[tuple] = ()) -> ox.NamedNode:
        subject = node(value)
        if value not in self.declared:
            self.declared.add(value)
            self.minted += [T(subject, A, cls), T(subject, label_property, text(label))]
            self.minted += [T(subject, p, o) for p, o in extra]
            self.minted_counts[cls.value.rsplit("#", 1)[-1].rsplit("/", 1)[-1]] += 1
        return subject

    def concept(self, scheme: str, value: str) -> ox.NamedNode:
        return self.ensure(iri.concept(scheme, value), CONCEPT, value, PREF_LABEL,
                           [(IN_SCHEME, node(iri.concept_scheme(scheme)))])

    def find_type(self, name: str, categories: Iterable[str]) -> tuple[str, str] | None:
        key = _norm(name)
        for category in categories:
            label = self.types.get(category, {}).get(key)
            if label:
                return category, label
        return None


# --- type lines -------------------------------------------------------------


def parse_type_line(type_line: str, vocab: Vocabulary) -> list[tuple[str, str]]:
    """Split one face's type line into ``(category, name)`` pairs.

    Words before the dash are supertypes and card types; words after it are
    subtypes, matched against the categories of the face's card types first
    (so "Spacecraft" on an artifact is the artifact type), longest name first
    ("Time Lord"). Words the CR doesn't know become Un types (category "un"):
    one per word, or, if a part of the line has four or more unknown words,
    one Un type for the whole phrase.
    """
    left, _, right = type_line.partition("—")
    result: list[tuple[str, str]] = []

    unknown: list[str] = []
    card_types: list[str] = []
    for word in left.split():
        found = vocab.find_type(word, ("card", "super"))
        if found:
            result.append(found)
            if found[0] == "card":
                card_types.append(found[1])
        else:
            unknown.append(word)
    result += _un_types(unknown)

    preferred = tuple(dict.fromkeys(c for t in card_types for c in SUBTYPE_CATEGORIES.get(t, ())))
    words = right.split()
    unknown = []
    i = 0
    while i < len(words):
        for size in range(min(LONGEST_SUBTYPE, len(words) - i), 0, -1):
            name = " ".join(words[i:i + size])
            found = vocab.find_type(name, preferred) or vocab.find_type(name, ALL_SUBTYPE_CATEGORIES)
            if found:
                result.append(found)
                i += size
                break
        else:
            unknown.append(words[i])
            i += 1
    result += _un_types(unknown)
    return result


def _un_types(words: list[str]) -> list[tuple[str, str]]:
    if len(words) >= 4:
        words = [" ".join(words)]
    names = []
    for word in words:
        name = word.strip(",.")
        try:
            iri.slug(name)
        except ValueError:
            continue
        names.append(("un", name))
    return names


# --- colors -----------------------------------------------------------------

_SYMBOL = re.compile(r"\{([^}]*)\}")


def mana_cost_colors(mana_cost: str) -> list[str]:
    """Colors of the mana symbols in a cost (CR 202.2): ``"{2}{W/U}"`` -> ``["W", "U"]``."""
    found = []
    for symbol in _SYMBOL.findall(mana_cost or ""):
        for part in symbol.split("/"):
            if part in ("W", "U", "B", "R", "G") and part not in found:
                found.append(part)
    return found


def face_colors(card: dict, face: dict) -> list[str]:
    """A face's colors. Split and adventure faces often lack ``colors``, so
    derive them from the face's mana cost and color indicator. Both halves of a
    flip card share the card's colors (only the top half has a mana cost)."""
    if "colors" in face:
        return face["colors"]
    if card.get("layout") == "flip":
        return card.get("colors", [])
    return list(dict.fromkeys(mana_cost_colors(face.get("mana_cost", "")) + face.get("color_indicator", [])))


# --- cards ------------------------------------------------------------------

LEGALITY = {"legal": "legalIn", "restricted": "restrictedIn", "banned": "bannedIn"}


def faces_of(card: dict) -> list[dict]:
    """The card's faces: ``card_faces`` if present, else the card itself."""
    return card.get("card_faces") or [card]


def card_triples(card: dict, vocab: Vocabulary) -> Iterator[ox.Triple]:
    """Triples for one ``oracle_cards`` object: the card and its faces."""
    oracle_id = card["oracle_id"]
    c = node(iri.card(oracle_id))
    yield T(c, A, mg("Card"))
    yield T(c, mg("oracleId"), text(oracle_id))
    yield T(c, mg("name"), text(card["name"]))
    yield T(c, SEE_ALSO, node(iri.scryfall_oracle(oracle_id)))
    if card.get("cmc") is not None:
        yield T(c, mg("manaValue"), decimal(card["cmc"]))
    yield T(c, mg("layout"), vocab.ensure(iri.layout(card["layout"]), mg("Layout"), card["layout"]))
    yield T(c, mg("reserved"), boolean(card.get("reserved", False)))
    yield T(c, mg("gameChanger"), boolean(card.get("game_changer", False)))

    for code in card.get("color_identity", []):
        yield T(c, mg("colorIdentity"), node(iri.color(code)))
    for code in card.get("produced_mana", []):
        try:
            yield T(c, mg("producesMana"), node(iri.color(code)))
        except ValueError:
            pass

    for name in card.get("keywords", []):
        try:
            keyword = vocab.ensure(iri.keyword(name), mg("Keyword"), name)
        except ValueError:
            continue
        yield T(c, mg("hasKeyword"), keyword)

    for key, status in card.get("legalities", {}).items():
        if status in LEGALITY:
            fmt = vocab.ensure(iri.format_(key), mg("Format"), key)
            yield T(c, mg(LEGALITY[status]), fmt)

    for index, face in enumerate(faces_of(card)):
        yield from face_triples(card, face, index, c, vocab)


def face_triples(card: dict, face: dict, index: int, c: ox.NamedNode,
                 vocab: Vocabulary) -> Iterator[ox.Triple]:
    f = node(iri.face(card["oracle_id"], index))
    yield T(f, A, mg("Face"))
    yield T(c, mg("hasFace"), f)
    yield T(f, mg("faceOf"), c)
    yield T(f, mg("faceIndex"), ox.Literal(str(index), datatype=XSD_NON_NEGATIVE))
    yield T(f, mg("name"), text(face["name"]))

    for key, prop in (("mana_cost", "manaCost"), ("type_line", "typeLine"), ("oracle_text", "oracleText"),
                      ("power", "power"), ("toughness", "toughness"), ("loyalty", "loyalty"),
                      ("defense", "defense")):
        if face.get(key):
            yield T(f, mg(prop), text(face[key]))

    for code in face_colors(card, face):
        yield T(f, mg("color"), node(iri.color(code)))
    for code in face.get("color_indicator", []):
        yield T(f, mg("colorIndicator"), node(iri.color(code)))

    prop = {"card": "hasCardType", "super": "hasSupertype"}
    for category, name in parse_type_line(face.get("type_line", ""), vocab):
        if category == "un":
            t = vocab.ensure(iri.type_("un", name), mg("UnType"), name)
        else:
            t = node(iri.type_(category, name))
        yield T(f, mg(prop.get(category, "hasType" if category == "un" else "hasSubtype")), t)


# --- printings --------------------------------------------------------------


def printing_oracle_id(card: dict) -> str | None:
    """Oracle ID of a printing. Reversible cards carry it on their faces only."""
    if card.get("oracle_id"):
        return card["oracle_id"]
    ids = {face.get("oracle_id") for face in card.get("card_faces", [])} - {None}
    return ids.pop() if len(ids) == 1 else None


def _artists(card: dict) -> dict[str, str | None]:
    """Artist ID -> name, where the name can be matched to the ID."""
    ids = card.get("artist_ids", [])
    names = (card.get("artist") or "").split(" & ")
    if len(names) != len(ids):
        names = [None] * len(ids)
    return dict(zip(ids, names))


def _illustrations(card: dict) -> list[tuple[str, list[str]]]:
    """``(illustration_id, artist_ids)`` per face, or for the whole printing."""
    found = []
    for face in card.get("card_faces", []):
        if face.get("illustration_id"):
            found.append((face["illustration_id"], [face["artist_id"]] if face.get("artist_id") else []))
    if not found and card.get("illustration_id"):
        found.append((card["illustration_id"], card.get("artist_ids", [])))
    return found


def _links(make: Callable[[int | str], str], value) -> Iterator[ox.NamedNode]:
    try:
        yield node(make(value))
    except ValueError:
        return


class PrintingConverter:
    """Converts ``default_cards`` objects, writing each set, illustration and artist once."""

    def __init__(self, vocab: Vocabulary):
        self.vocab = vocab
        self.sets: set[str] = set()
        self.illustrations: set[str] = set()
        self.artists: set[str] = set()

    def triples(self, card: dict, oracle_id: str) -> Iterator[ox.Triple]:
        vocab = self.vocab
        p = node(iri.printing(card["id"]))
        c = node(iri.card(oracle_id))
        yield T(p, A, mg("Printing"))
        yield T(p, mg("scryfallId"), text(card["id"]))
        yield T(p, EXACT_MATCH, node(iri.scryfall(card["id"])))
        yield T(p, mg("printingOf"), c)
        yield T(c, mg("hasPrinting"), p)
        yield T(p, mg("collectorNumber"), text(card["collector_number"]))
        if card.get("released_at"):
            yield T(p, mg("releasedAt"), date(card["released_at"]))
        if card.get("rarity"):
            yield T(p, mg("rarity"), vocab.ensure(iri.rarity(card["rarity"]), mg("Rarity"), card["rarity"]))

        yield from self._set(card, p)
        yield from self._art(card, p)
        yield from self._attributes(card, p)
        yield from self._identifiers(card, p)

    def _set(self, card: dict, p: ox.NamedNode) -> Iterator[ox.Triple]:
        s = node(iri.set_(card["set"]))
        yield T(p, mg("inSet"), s)
        if card["set"] in self.sets:
            return
        self.sets.add(card["set"])
        yield T(s, A, mg("Set"))
        yield T(s, mg("setCode"), text(card["set"]))
        yield T(s, mg("name"), text(card["set_name"]))
        if card.get("set_type"):
            yield T(s, mg("setType"),
                    self.vocab.ensure(iri.set_type(card["set_type"]), mg("SetType"), card["set_type"]))

    def _art(self, card: dict, p: ox.NamedNode) -> Iterator[ox.Triple]:
        names = _artists(card)
        for illustration_id, artist_ids in _illustrations(card):
            i = node(iri.illustration(illustration_id))
            yield T(p, mg("hasIllustration"), i)
            if illustration_id in self.illustrations:
                continue
            self.illustrations.add(illustration_id)
            yield T(i, A, mg("Illustration"))
            yield T(i, mg("illustrationId"), text(illustration_id))
            for artist_id in artist_ids:
                a = node(iri.artist(artist_id))
                yield T(i, mg("illustratedBy"), a)
                if artist_id not in self.artists:
                    self.artists.add(artist_id)
                    yield T(a, A, mg("Artist"))
                    yield T(a, mg("artistId"), text(artist_id))
                    if names.get(artist_id):
                        yield T(a, mg("name"), text(names[artist_id]))

    def _attributes(self, card: dict, p: ox.NamedNode) -> Iterator[ox.Triple]:
        vocab = self.vocab
        many = (("games", "game", "game"), ("finishes", "finish", "finish"),
                ("frame_effects", "frame_effect", "frameEffect"), ("promo_types", "promo_type", "promoType"))
        one = (("frame", "frame", "frame"), ("border_color", "border_color", "borderColor"),
               ("security_stamp", "security_stamp", "securityStamp"))
        for key, scheme, prop in many:
            for value in card.get(key, []):
                yield T(p, mg(prop), vocab.concept(scheme, value))
        for key, scheme, prop in one:
            if card.get(key):
                yield T(p, mg(prop), vocab.concept(scheme, card[key]))
        watermarks = {card.get("watermark")} | {f.get("watermark") for f in card.get("card_faces", [])}
        for value in sorted(watermarks - {None, ""}):
            yield T(p, mg("watermark"), vocab.concept("watermark", value))

    def _identifiers(self, card: dict, p: ox.NamedNode) -> Iterator[ox.Triple]:
        for multiverse_id in card.get("multiverse_ids", []):
            yield T(p, mg("multiverseId"), integer(multiverse_id))
            for link in _links(iri.multiverse, multiverse_id):
                yield T(p, EXACT_MATCH, link)
        for key, prop in (("mtgo_id", "mtgoId"), ("mtgo_foil_id", "mtgoFoilId"), ("arena_id", "arenaId"),
                          ("tcgplayer_id", "tcgplayerId"), ("tcgplayer_etched_id", "tcgplayerEtchedId"),
                          ("cardmarket_id", "cardmarketId")):
            if card.get(key) is not None:
                yield T(p, mg(prop), integer(card[key]))
        if card.get("tcgplayer_id") is not None:
            yield from (T(p, EXACT_MATCH, link) for link in _links(iri.tcgplayer, card["tcgplayer_id"]))
        if card.get("cardmarket_id") is not None:
            yield from (T(p, EXACT_MATCH, link) for link in _links(iri.cardmarket, card["cardmarket_id"]))


# --- rulings ----------------------------------------------------------------


def ruling_triples(ruling: dict) -> Iterator[ox.Triple]:
    oracle_id, published, comment = ruling["oracle_id"], ruling["published_at"], ruling["comment"]
    r = node(iri.ruling(oracle_id, published, comment))
    c = node(iri.card(oracle_id))
    yield T(r, A, mg("Ruling"))
    yield T(c, mg("hasRuling"), r)
    yield T(r, mg("rulingOn"), c)
    yield T(r, mg("publishedAt"), date(published))
    yield T(r, mg("rulingSource"), text(ruling["source"]))
    yield T(r, mg("rulingText"), text(comment))


# --- driver -----------------------------------------------------------------


def read_jsonl(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                yield json.loads(line)


def write(path: Path, triples: Iterable[ox.Triple]) -> int:
    """Write triples as gzipped N-Triples; return how many were written."""
    count = 0

    def counted():
        nonlocal count
        for triple in triples:
            count += 1
            yield triple

    partial = path.with_name(path.name + ".part")
    with gzip.open(partial, "wb", compresslevel=6) as out:
        ox.serialize(counted(), out, ox.RdfFormat.N_TRIPLES)
    partial.replace(path)
    return count


def convert(raw_dir: Path = download.DEFAULT_DEST, out_dir: Path = DEFAULT_OUT,
            ontology_dir: Path = ONTOLOGY_DIR) -> dict[str, int]:
    """Convert the bulk files in ``raw_dir`` to N-Triples in ``out_dir``.

    Returns the number of triples written per output file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    vocab = Vocabulary(ontology_dir)
    cards: set[str] = set()
    skipped: Counter[str] = Counter()

    def card_stream():
        for card in read_jsonl(raw_dir / "oracle_cards.jsonl.gz"):
            if not is_game_card(card) or not card.get("oracle_id"):
                skipped["card"] += 1
                continue
            cards.add(card["oracle_id"])
            yield from card_triples(card, vocab)

    def printing_stream():
        printings = PrintingConverter(vocab)
        for card in read_jsonl(raw_dir / "default_cards.jsonl.gz"):
            oracle_id = printing_oracle_id(card)
            if not is_game_card(card) or oracle_id not in cards:
                skipped["printing"] += 1
                continue
            yield from printings.triples(card, oracle_id)

    def ruling_stream():
        for ruling in read_jsonl(raw_dir / "rulings.jsonl.gz"):
            if ruling["oracle_id"] not in cards:
                skipped["ruling"] += 1
                continue
            yield from ruling_triples(ruling)

    counts = {
        "cards.nt.gz": write(out_dir / "cards.nt.gz", card_stream()),
        "printings.nt.gz": write(out_dir / "printings.nt.gz", printing_stream()),
        "rulings.nt.gz": write(out_dir / "rulings.nt.gz", ruling_stream()),
    }
    counts["minted.nt.gz"] = write(out_dir / "minted.nt.gz", vocab.minted)

    for name, count in counts.items():
        print(f"convert: {name}: {count:,} triples")
    print(f"convert: {len(cards):,} cards; skipped {dict(skipped)}")
    print(f"convert: minted {dict(vocab.minted_counts)}")
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Scryfall bulk data to N-Triples.")
    parser.add_argument("--raw-dir", type=Path, default=download.DEFAULT_DEST, help="downloaded bulk files")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    args = parser.parse_args(argv)
    convert(args.raw_dir, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
