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


def _store():
    store = ox.Store()
    for path in ONTOLOGY_DIR.glob("*.ttl"):
        store.load(path=str(path), format=ox.RdfFormat.TURTLE)
    return store


def test_every_individual_and_annotation_is_labelled():
    unlabelled = _store().query("""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT ?term WHERE {
            VALUES ?kind { owl:NamedIndividual owl:AnnotationProperty skos:ConceptScheme }
            ?term a ?kind .
            FILTER NOT EXISTS { ?term rdfs:label ?label }
        }""")
    assert [row["term"].value for row in unlabelled] == []


def test_every_used_ontology_term_is_declared():
    """Catch typos: each mg: term used as a predicate or object is defined somewhere."""
    undeclared = _store().query(f"""
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT DISTINCT ?term WHERE {{
            {{ ?s ?term ?o }} UNION {{ ?s ?p ?term }}
            FILTER(isIRI(?term) && STRSTARTS(STR(?term), "{MG}"))
            FILTER NOT EXISTS {{ ?term rdf:type ?kind }}
        }}""")
    assert [row["term"].value for row in undeclared] == []
