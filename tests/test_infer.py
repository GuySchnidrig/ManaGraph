import pyoxigraph as ox
import pytest

from managraph import infer, iri
from managraph.load import load

MG = "https://w3id.org/managraph/ontology#"
CHANGELING_CREATURE = "11111111-1111-1111-1111-111111111111"
CHANGELING_ENCHANTMENT = "22222222-2222-2222-2222-222222222222"
ARTIST = "33333333-3333-3333-3333-333333333333"


def _data() -> str:
    changeling = iri.keyword("Changeling")
    lines = []
    for oracle_id, card_type in ((CHANGELING_CREATURE, "Creature"), (CHANGELING_ENCHANTMENT, "Enchantment")):
        card, face = iri.card(oracle_id), iri.face(oracle_id, 0)
        lines += [
            f"<{card}> a <{MG}Card> ; <{MG}hasKeyword> <{changeling}> ; <{MG}hasFace> <{face}> ; <{MG}name> \"Card\" .",
            f"<{face}> a <{MG}Face> ; <{MG}faceOf> <{card}> ; <{MG}hasCardType> <{iri.type_('card', card_type)}> .",
        ]
    lines.append(f"<{iri.artist(ARTIST)}> a <{MG}Artist> .")
    return "\n".join(lines)


@pytest.fixture()
def store(tmp_path):
    (tmp_path / "rdf").mkdir()
    store = load(None, tmp_path / "rdf")  # ontology only, in memory
    store.load(_data().encode(), format=ox.RdfFormat.TURTLE)
    return store


def ask(store, pattern):
    return store.query(f"PREFIX mg: <{MG}> ASK {{ {pattern} }}")


def test_changeling_creature_gets_every_creature_type(store):
    infer.infer(store)
    face = iri.face(CHANGELING_CREATURE, 0)
    for name in ("Elf", "Time Lord", "Shapeshifter"):
        assert ask(store, f"<{face}> mg:hasSubtype <{iri.type_('creature', name)}>")
    count = store.query(f"PREFIX mg: <{MG}> SELECT (COUNT(*) AS ?n) WHERE {{ <{face}> mg:hasSubtype ?t }}")
    total = store.query(f"PREFIX mg: <{MG}> SELECT (COUNT(*) AS ?n) WHERE {{ ?t a mg:CreatureType }}")
    assert next(count)["n"].value == next(total)["n"].value


def test_changeling_needs_a_creature_or_kindred_face(store):
    infer.infer(store)
    assert not ask(store, f"<{iri.face(CHANGELING_ENCHANTMENT, 0)}> mg:hasSubtype ?t")


def test_subproperty_and_subclass(store):
    infer.infer(store)
    face = iri.face(CHANGELING_CREATURE, 0)
    assert ask(store, f"<{face}> mg:hasType <{iri.type_('card', 'Creature')}>")
    assert ask(store, f"<{face}> mg:hasType <{iri.type_('creature', 'Elf')}>")  # subtype from changeling, then hasType
    assert ask(store, f'<{iri.card(CHANGELING_CREATURE)}> <http://www.w3.org/2000/01/rdf-schema#label> "Card"')
    assert ask(store, f"<{iri.artist(ARTIST)}> a <http://xmlns.com/foaf/0.1/Person>")
    assert ask(store, f"<{iri.type_('land', 'Forest')}> a mg:Subtype, mg:Type")


def test_inverse(tmp_path):
    (tmp_path / "rdf").mkdir()
    store = load(None, tmp_path / "rdf")
    card, face = iri.card(CHANGELING_CREATURE), iri.face(CHANGELING_CREATURE, 0)
    store.add(ox.Quad(ox.NamedNode(face), ox.NamedNode(MG + "faceOf"), ox.NamedNode(card)))
    infer.infer(store)
    assert ask(store, f"<{card}> mg:hasFace <{face}>")


def test_second_run_derives_nothing(store):
    assert infer.infer(store)
    assert infer.infer(store) == []
