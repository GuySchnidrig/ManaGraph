import gzip
import json
from pathlib import Path

import pytest

from managraph import convert, validate
from test_convert import ORACLE_CARD, PRINTING, RULING

ONTOLOGY = sorted((Path(__file__).parent.parent / "ontology").glob("*.ttl"))
MG = "https://w3id.org/managraph/"


def _jsonl(path, rows):
    with gzip.open(path, "wt", encoding="utf-8") as out:
        out.writelines(json.dumps(row) + "\n" for row in rows)


def _validate(tmp_path, turtle: str) -> validate.Report:
    data = tmp_path / "data.ttl"
    data.write_text("@prefix mg: <https://w3id.org/managraph/ontology#> .\n"
                    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + turtle, encoding="utf-8")
    return validate.validate([*ONTOLOGY, data], report_dir=None)


def _messages(report, severity="Violation"):
    return [r.message for r in report.results if r.severity == severity]


def test_converter_output_has_no_violations(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "rdf"
    raw.mkdir()
    _jsonl(raw / "oracle_cards.jsonl.gz", [ORACLE_CARD])
    _jsonl(raw / "default_cards.jsonl.gz", [PRINTING])
    _jsonl(raw / "rulings.jsonl.gz", [RULING])
    convert.convert(raw, out)
    report = validate.validate([*ONTOLOGY, *sorted(out.glob("*.nt.gz"))], report_dir=tmp_path)
    assert report.count("Violation") == 0, validate.summarize(report)
    assert report.path.read_text(encoding="utf-8").strip()


def test_mana_cost_color_must_be_in_identity(tmp_path):
    report = _validate(tmp_path, f"""
        <x:card> a mg:Card ; mg:hasFace <x:face> ; mg:colorIdentity <{MG}color/G> .
        <x:face> a mg:Face ; mg:faceOf <x:card> ; mg:manaCost "{{1}}{{G/U}}" .
    """)
    assert any("color/U from a face's mana cost" in m for m in _messages(report))
    assert not any("color/G from" in m for m in _messages(report))


def test_ability_set_color_outside_identity_is_only_a_warning(tmp_path):
    report = _validate(tmp_path, f"""
        <x:card> a mg:Card ; mg:hasFace <x:face> ; mg:colorIdentity <{MG}color/G> .
        <x:face> a mg:Face ; mg:faceOf <x:card> ; mg:manaCost "{{2}}{{G}}" ; mg:color <{MG}color/G>, <{MG}color/U> .
    """)
    assert not any("identity" in m for m in _messages(report))
    assert any("face color" in m and "color/U" in m for m in _messages(report, "Warning"))


def test_two_legality_statuses(tmp_path):
    report = _validate(tmp_path, f"<x:card> a mg:Card ; mg:legalIn <{MG}format/modern> ; mg:bannedIn <{MG}format/modern> .")
    assert any("two legality statuses" in m for m in _messages(report))


def test_face_back_link_and_index(tmp_path):
    report = _validate(tmp_path, """
        <x:card> a mg:Card ; mg:hasFace <x:a>, <x:b> .
        <x:a> a mg:Face ; mg:faceOf <x:card> ; mg:faceIndex "0"^^xsd:nonNegativeInteger .
        <x:b> a mg:Face ; mg:faceIndex "0"^^xsd:nonNegativeInteger .
    """)
    messages = _messages(report)
    assert any("x:b doesn't link back" in m for m in messages)
    assert any("share the face index 0" in m for m in messages)


def test_subtype_must_fit_a_card_type_warning(tmp_path):
    report = _validate(tmp_path, f"""
        <x:face> a mg:Face ; mg:hasCardType <{MG}type/card/Instant> ; mg:hasSubtype <{MG}type/creature/Elf> .
    """)
    assert any("205.3d" in m for m in _messages(report, "Warning"))
    assert not any("205.3d" in m for m in _messages(report))


def test_printing_needs_one_set(tmp_path):
    report = _validate(tmp_path, "<x:p> a mg:Printing ; mg:inSet <x:s1>, <x:s2> .")
    assert any(r.path and r.path.endswith("inSet") and r.component == "MaxCount" for r in report.results)


@pytest.mark.parametrize("source, ok", [('"wotc"', True), ('"scryfall"', True), ('"reddit"', False)])
def test_ruling_source(tmp_path, source, ok):
    report = _validate(tmp_path, f"<x:r> a mg:Ruling ; mg:rulingSource {source} .")
    assert ok == (not any(r.component == "In" for r in report.results))
