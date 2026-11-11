from pathlib import Path

import pyoxigraph as ox
import pytest

ONTOLOGY_DIR = Path(__file__).parent.parent / "ontology"
MG = "https://w3id.org/managraph/ontology#"


@pytest.mark.parametrize("path", sorted(ONTOLOGY_DIR.glob("*.ttl")), ids=lambda p: p.name)
def test_turtle_parses(path):
    list(ox.parse(path=str(path), format=ox.RdfFormat.TURTLE))


def test_every_term_is_labelled():
    store = ox.Store()
    for path in ONTOLOGY_DIR.glob("*.ttl"):
        store.load(path=str(path), format=ox.RdfFormat.TURTLE)
    unlabelled = store.query(f"""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT ?term WHERE {{
            VALUES ?kind {{ owl:Class owl:ObjectProperty owl:DatatypeProperty }}
            ?term a ?kind .
            FILTER(STRSTARTS(STR(?term), "{MG}"))
            FILTER NOT EXISTS {{ ?term rdfs:label ?label }}
        }}""")
    assert [row["term"].value for row in unlabelled] == []
