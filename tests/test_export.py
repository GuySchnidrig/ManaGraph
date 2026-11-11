import gzip
from pathlib import Path

import pyoxigraph as ox
import pytest

from managraph import convert, export

ROOT = Path(__file__).parent.parent
MG = "https://w3id.org/managraph/ontology#"


def test_export_concatenates_ontology_and_data(tmp_path):
    rdf = tmp_path / "rdf"
    rdf.mkdir()
    card = ox.NamedNode("https://w3id.org/managraph/card/b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6")
    convert.write(rdf / "cards.nt.gz", [ox.Triple(card, ox.NamedNode(MG + "name"), ox.Literal("Fire // Ice"))])
    convert.write(rdf / "inferred.nt.gz", [ox.Triple(card, ox.NamedNode(MG + "reserved"), ox.Literal("false"))])

    path = export.export(tmp_path / "qlever", rdf)

    with gzip.open(path, "rb") as data:  # one gzip stream across all members
        store = ox.Store()
        store.load(data, format=ox.RdfFormat.N_TRIPLES)
    ask = lambda q: store.query(f"PREFIX mg: <{MG}> ASK {{ {q} }}")
    assert ask(f'{card} mg:name "Fire // Ice"')
    assert ask(f"{card} mg:reserved ?x")  # inferred triples are included
    assert ask("mg:Card a <http://www.w3.org/2002/07/owl#Class>")  # the ontology too
    assert ask("<https://w3id.org/managraph/type/creature/Elf> a mg:CreatureType")


@pytest.mark.parametrize("path", sorted((ROOT / "queries").glob("*.rq")), ids=lambda p: p.name)
def test_example_queries_are_valid_sparql(path):
    # Runs on an empty store: checks syntax, not results.
    list(ox.Store().query(path.read_text(encoding="utf-8")))
