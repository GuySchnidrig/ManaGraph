"""Materialize inferred triples, so a store without reasoning (QLever) can serve them.

A small, fixed set of OWL/RDFS rules, each driven by the axioms in the
ontology rather than by hard-coded terms:

- subproperty:  ?s sub ?o, sub rdfs:subPropertyOf+ sup        => ?s sup ?o
                e.g. mg:hasCardType => mg:hasType, mg:name => rdfs:label
- subclass:     ?x a C, C rdfs:subClassOf+ D (named classes)  => ?x a D
                e.g. mg:BasicLandType => mg:LandType, mg:Artist => foaf:Person
- inverse:      ?s p ?o, p owl:inverseOf q                    => ?o q ?s
- existential conjunction => hasValue, the shape of the Changeling axiom in
  types.ttl:
      (p1 some (p2 value v)) and (p3 some {a, b, ...})  subClassOf  (p value w)
      ?x p1 ?y . ?y p2 v . ?x p3 a                      => ?x p w

Rules run in rounds until a round adds nothing. Only new triples are kept;
they are added to the store and written to ``data/rdf/inferred.nt.gz``.

Not implemented: rdfs:domain/range typing (the converter types every node
explicitly) and consistency checks such as disjointness and functional
properties, which belong to SHACL validation.

Usage::

    uv run python -m managraph.infer     # needs a store from managraph.load
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

import pyoxigraph as ox

from managraph import convert, load

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
A = ox.NamedNode(RDF + "type")
PREFIXES = f"PREFIX rdf: <{RDF}> PREFIX rdfs: <{RDFS}> PREFIX owl: <{OWL}> "
MAX_ROUNDS = 10

Rule = Callable[[ox.Store], Iterator[ox.Triple]]


def _rows(store: ox.Store, query: str) -> list:
    return list(store.query(PREFIXES + query))


def subproperty(store: ox.Store) -> Iterator[ox.Triple]:
    for row in _rows(store, """
            SELECT DISTINCT ?sub ?sup WHERE {
                ?sub rdfs:subPropertyOf+ ?sup FILTER(isIRI(?sub) && isIRI(?sup) && ?sub != ?sup)
            }"""):
        for quad in store.quads_for_pattern(None, row["sub"], None):
            yield ox.Triple(quad.subject, row["sup"], quad.object)


def subclass(store: ox.Store) -> Iterator[ox.Triple]:
    for row in _rows(store, """
            SELECT DISTINCT ?sub ?sup WHERE {
                ?sub rdfs:subClassOf+ ?sup FILTER(isIRI(?sub) && isIRI(?sup) && ?sub != ?sup)
            }"""):
        for quad in store.quads_for_pattern(None, A, row["sub"]):
            yield ox.Triple(quad.subject, A, row["sup"])


def inverse(store: ox.Store) -> Iterator[ox.Triple]:
    pairs = set()
    for row in _rows(store, "SELECT ?p ?q WHERE { ?p owl:inverseOf ?q FILTER(isIRI(?p) && isIRI(?q)) }"):
        pairs |= {(row["p"], row["q"]), (row["q"], row["p"])}
    for p, q in pairs:
        for quad in store.quads_for_pattern(None, p, None):
            if not isinstance(quad.object, ox.Literal):
                yield ox.Triple(quad.object, q, quad.subject)


def existential_has_value(store: ox.Store) -> Iterator[ox.Triple]:
    """(p1 some (p2 value v)) and (p3 some oneOf(...)) subClassOf (p value w)."""
    # The axiom's subject is a blank node, which can't be named in a later
    # query, so collect everything about it in this one.
    axioms: dict[tuple, tuple[set, set]] = {}
    for row in _rows(store, """
            SELECT ?gci ?p1 ?p2 ?v ?p3 ?a ?p ?w WHERE {
                ?gci owl:intersectionOf ?list ; rdfs:subClassOf ?head .
                ?list rdf:first ?r1 ; rdf:rest ?rest . ?rest rdf:first ?r2 ; rdf:rest rdf:nil .
                ?r1 owl:onProperty ?p1 ; owl:someValuesFrom ?f1 .
                ?f1 owl:onProperty ?p2 ; owl:hasValue ?v .
                ?r2 owl:onProperty ?p3 ; owl:someValuesFrom ?f2 .
                ?f2 owl:oneOf/rdf:rest*/rdf:first ?a .
                ?head owl:onProperty ?p ; owl:hasValue ?w .
            }"""):
        allowed, heads = axioms.setdefault((row["gci"], row["p1"], row["p2"], row["v"], row["p3"]), (set(), set()))
        allowed.add(row["a"])
        heads.add((row["p"], row["w"]))

    for (_, p1, p2, v, p3), (allowed_nodes, heads) in axioms.items():
        allowed = ", ".join(sorted(str(a) for a in allowed_nodes))
        matches = _rows(store, f"""
            SELECT DISTINCT ?x WHERE {{
                ?x {p1} ?y . ?y {p2} {v} .
                ?x {p3} ?a FILTER(?a IN ({allowed}))
            }}""")
        for row in matches:
            for p, w in heads:
                yield ox.Triple(row["x"], p, w)


RULES: dict[str, Rule] = {
    "existential": existential_has_value,
    "inverse": inverse,
    "subproperty": subproperty,
    "subclass": subclass,
}


def infer(store: ox.Store) -> list[ox.Triple]:
    """Apply ``RULES`` until nothing new is derived; add and return the new triples."""
    inferred: list[ox.Triple] = []
    per_rule: Counter[str] = Counter()
    for round_number in range(1, MAX_ROUNDS + 1):
        new: dict[ox.Triple, None] = {}
        for name, rule in RULES.items():
            for triple in rule(store):
                if triple not in new and ox.Quad(triple.subject, triple.predicate, triple.object) not in store:
                    new[triple] = None
                    per_rule[name] += 1
        if not new:
            break
        store.extend(ox.Quad(t.subject, t.predicate, t.object) for t in new)
        inferred += new
    else:
        raise RuntimeError(f"inference did not converge in {MAX_ROUNDS} rounds")
    print(f"infer: {len(inferred):,} triples in {round_number - 1} round(s): {dict(per_rule)}")
    return inferred


def run(store: ox.Store, out_dir: Path = convert.DEFAULT_OUT) -> int:
    """Infer over ``store`` and write the result to ``out_dir/inferred.nt.gz``."""
    return convert.write(out_dir / load.INFERRED, infer(store))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize inferred triples.")
    parser.add_argument("--store", type=Path, default=load.DEFAULT_STORE, help="store built by managraph.load")
    parser.add_argument("--out", type=Path, default=convert.DEFAULT_OUT, help="where inferred.nt.gz goes")
    args = parser.parse_args(argv)
    run(ox.Store(str(args.store)), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
