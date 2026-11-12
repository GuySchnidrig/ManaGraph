import pyoxigraph as ox
import pytest

from managraph import iri, query

MG = iri.ONTOLOGY
ORACLE_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture()
def store():
    card = iri.card(ORACLE_ID)
    store = ox.Store()
    store.load(
        f'<{card}> a <{MG}Card> ; <{MG}name> "Lim-Dûl\'s Hex" ; '
        f"<{MG}hasType> <{iri.type_('creature', 'Elf')}> .".encode(),
        format=ox.RdfFormat.TURTLE,
    )
    return store


def test_with_prefixes_adds_missing():
    q = query.with_prefixes("SELECT * WHERE { ?s a mg:Card }")
    assert f"PREFIX mg: <{MG}>" in q
    assert f"PREFIX card: <{iri.BASE}card/>" in q
    assert q.endswith("SELECT * WHERE { ?s a mg:Card }")


def test_with_prefixes_keeps_declared():
    q = query.with_prefixes("prefix MG: <urn:x#>\nPREFIX mg: <urn:other#>\nASK {}")
    assert f"<{MG}>" not in q


def test_term_shortens_known_namespaces():
    assert query.term(ox.NamedNode(iri.card(ORACLE_ID))) == f"card:{ORACLE_ID}"
    assert query.term(ox.NamedNode(f"{MG}Card")) == "mg:Card"
    assert query.term(ox.NamedNode("http://example.org/x")) == "<http://example.org/x>"
    assert query.term(ox.NamedNode(f"{iri.BASE}card/")) == f"<{iri.BASE}card/>"  # namespace itself


def test_term_literals_blanks_and_unbound():
    assert query.term(ox.Literal("3", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer"))) == "3"
    assert query.term(ox.BlankNode("b0")) == "_:b0"
    assert query.term(None) == ""


def test_table_aligns_and_truncates():
    out = query.table(["a", "bb"], [["x" * 10, "y"]], max_width=6).splitlines()
    assert out == ["a       bb", "------  --", "xxx...  y"]
    assert query.table(["a"], []).splitlines() == ["a", "-"]


def test_run_select(store, capsys):
    query.run(store, "SELECT ?c ?n WHERE { ?c mg:name ?n }")
    out = capsys.readouterr().out
    assert f"card:{ORACLE_ID}" in out
    assert "Lim-Dûl's Hex" in out
    assert "1 result(s) in" in out


def test_run_select_limit(store, capsys):
    query.run(store, "SELECT ?p WHERE { ?c ?p ?o }", limit=1)
    assert "3 result(s), showing 1 in" in capsys.readouterr().out


def test_run_ask(store, capsys):
    query.run(store, f"ASK {{ ?c mg:hasType <{iri.type_('creature', 'Elf')}> }}")
    assert capsys.readouterr().out.strip() == "True"
    query.run(store, f"ASK {{ ?c mg:hasType <{iri.type_('creature', 'Goblin')}> }}")
    assert capsys.readouterr().out.strip() == "False"


def test_run_construct(store, capsys):
    query.run(store, "CONSTRUCT { ?c mg:name ?n } WHERE { ?c mg:name ?n }")
    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == ["subject", "predicate", "object"]
    assert f"card:{ORACLE_ID}  mg:name" in out


def test_repl_runs_queries_and_survives_errors(store, capsys, monkeypatch):
    lines = iter(["SELECT ?n", "WHERE { ?c mg:name ?n }", "", "SELECT bad", "", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(lines))
    query.repl(store, limit=50)
    out = capsys.readouterr().out
    assert "Lim-Dûl's Hex" in out
    assert "error:" in out


def test_main_runs_rq_file(tmp_path, store, capsys, monkeypatch):
    monkeypatch.setattr(ox.Store, "read_only", staticmethod(lambda _path: store))
    rq = tmp_path / "names.rq"
    rq.write_text("SELECT ?n WHERE { ?c mg:name ?n }", encoding="utf-8")
    assert query.main([str(rq), "--store", str(tmp_path)]) == 0
    assert "Lim-Dûl's Hex" in capsys.readouterr().out


def test_main_without_store(tmp_path):
    with pytest.raises(SystemExit):
        query.main(["ASK {}", "--store", str(tmp_path / "missing")])
