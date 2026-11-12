from html.parser import HTMLParser

import pyoxigraph as ox
import pytest

from managraph import docs

MG = "https://w3id.org/managraph/ontology#"


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    anchors = docs.build(out)
    return out, anchors


def test_files_for_the_w3id_redirects(site):
    out, _ = site
    for path in ("index.html", "404.html", "ontology/index.html", "ontology/managraph.ttl", ".nojekyll"):
        assert (out / path).exists(), path


def test_merged_turtle_equals_the_source_files(site):
    out, _ = site
    merged, sources = ox.Store(), ox.Store()
    merged.load(path=str(out / "ontology" / "managraph.ttl"), format=ox.RdfFormat.TURTLE)
    for path in docs.Ontology().files:
        sources.load(path=str(path), format=ox.RdfFormat.TURTLE)
    assert len(merged) == len(sources) > 0


def test_every_class_and_property_has_an_anchor(site):
    _, anchors = site
    onto = docs.Ontology()
    for kind in (docs.OWL + "Class", docs.OWL + "ObjectProperty", docs.OWL + "DatatypeProperty",
                 docs.OWL + "AnnotationProperty"):
        for term in onto.terms(kind):
            assert docs.anchor(term) in anchors, term.value


@pytest.mark.parametrize("anchor", ["Card", "hasSubtype", "type-creature-Elf", "type-artifact-Spacecraft",
                                    "keyword-changeling", "color-W", "format-commander", "vocab-frame-2015"])
def test_vocabulary_anchors(site, anchor):
    out, anchors = site
    assert anchor in anchors
    assert f'id="{anchor}"' in (out / "ontology" / "index.html").read_text(encoding="utf-8")


def test_ids_are_unique(site):
    out, _ = site
    ids = []

    class Collect(HTMLParser):
        def handle_starttag(self, tag, attrs):
            ids.extend(v for k, v in attrs if k == "id")

    Collect().feed((out / "ontology" / "index.html").read_text(encoding="utf-8"))
    assert len(ids) == len(set(ids))


def test_pages_carry_the_fan_content_notice(site):
    out, _ = site
    for path in ("index.html", "404.html", "ontology/index.html"):
        text = (out / path).read_text(encoding="utf-8")
        assert "unofficial Fan Content permitted under the" in text
        assert "not affiliated with or" in text


def test_pages_link_the_endpoint(site):
    out, _ = site
    home = (out / "index.html").read_text(encoding="utf-8")
    not_found = (out / "404.html").read_text(encoding="utf-8")
    assert f'href="{docs.ENDPOINT}"' in home
    assert docs.YASGUI + "#query=" in home
    assert f'var endpoint = "{docs.ENDPOINT}";' in not_found
    assert "ENDPOINT_URL" not in not_found and "YASGUI_URL" not in not_found


def test_yasgui_link_encodes_query_and_endpoint():
    link = docs.yasgui_link("SELECT * { ?s ?p ?o }")
    assert link.startswith(docs.YASGUI + "#query=SELECT%20%2A%20%7B")
    assert "&endpoint=https%3A%2F%2F" in link
