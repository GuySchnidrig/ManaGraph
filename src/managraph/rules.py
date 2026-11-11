"""Generate the type and keyword vocabularies from the Comprehensive Rules.

The Comprehensive Rules (CR) are the authority on Magic's types and keywords:

- 205.2a card types, 205.4a supertypes, 205.3g-q subtypes per card type
- 701.x keyword actions, 702.x keyword abilities, 207.2c ability words

This module downloads the current CR text from Wizards of the Coast, parses
those rules and writes ``ontology/types.ttl`` and ``ontology/keywords.ttl``.
Both files are generated: rerun this after each CR update instead of editing
them by hand. The classes and properties they use are defined in ``core.ttl``.

Usage::

    uv run python -m managraph.rules            # download if changed, regenerate
    uv run python -m managraph.rules --force    # re-download first
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from managraph import iri
from managraph.download import PROJECT_ROOT, _open

RULES_PAGE = "https://magic.wizards.com/en/rules"
DEFAULT_DEST = PROJECT_ROOT / "data" / "raw" / "rules"
ONTOLOGY_DIR = PROJECT_ROOT / "ontology"
RULES_FILE = "MagicCompRules.txt"
MANIFEST_NAME = "manifest.json"

_RULES_LINK = re.compile(r"https://media\.wizards\.com/[^\"'<>]+?\.txt")

# Subtype lists in rule 205.3, and the card types each list belongs to.
SUBTYPE_RULES = {
    "205.3g": "artifact",
    "205.3h": "enchantment",
    "205.3i": "land",
    "205.3j": "planeswalker",
    "205.3k": "spell",
    "205.3m": "creature",
    "205.3n": "planar",
    "205.3p": "dungeon",
    "205.3q": "battle",
}


# --- download ---------------------------------------------------------------


def find_rules_url(html: str) -> str:
    """Return the CR text file's URL from the rules page HTML."""
    match = _RULES_LINK.search(html)
    if not match:
        raise ValueError(f"no Comprehensive Rules .txt link found on {RULES_PAGE}")
    return quote(match.group(0), safe=":/")


def download(dest: Path = DEFAULT_DEST, force: bool = False) -> Path:
    """Download the current CR text into ``dest``, unless the same file is already there."""
    with _open(RULES_PAGE) as response:
        url = find_rules_url(response.read().decode("utf-8", errors="replace"))

    dest.mkdir(parents=True, exist_ok=True)
    target = dest / RULES_FILE
    manifest_path = dest / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    if not force and target.exists() and manifest.get("url") == url:
        print(f"rules: up to date ({url})")
        return target

    print(f"rules: downloading {url}", flush=True)
    with _open(url) as response:
        target.write_bytes(response.read())
    manifest_path.write_text(json.dumps({"url": url}, indent=2) + "\n", encoding="utf-8")
    return target


def read(path: Path) -> str:
    """Read a CR text file. Wizards has published it as UTF-8 and as Windows-1252."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return text.replace("\r\n", "\n").replace("\r", "\n")


# --- parsing ----------------------------------------------------------------


@dataclass
class Rules:
    """The parts of the CR the vocabularies are built from."""

    effective: str  # ISO date
    card_types: dict[str, str]  # name -> rule section, e.g. "Artifact" -> "301"
    supertypes: list[str]
    subtypes: dict[str, list[str]]  # category -> names
    basic_land_types: list[str]
    keyword_abilities: dict[str, str] = field(default_factory=dict)  # name -> section
    keyword_actions: dict[str, str] = field(default_factory=dict)
    ability_words: list[str] = field(default_factory=list)


def _body(text: str) -> str:
    """The numbered rules: skip the table of contents, stop at the glossary."""
    start = text.find("\n1. Game Concepts", text.find("\nCredits"))
    end = text.find("\nGlossary\n", start)
    if start < 0 or end < 0:
        raise ValueError("unexpected CR layout: rules body not found")
    return text[start:end]


def _rule(body: str, number: str) -> str:
    match = re.search(rf"^{re.escape(number)} (.+)$", body, re.MULTILINE)
    if not match:
        raise ValueError(f"rule {number} not found")
    return match.group(1)


def _split_list(items: str) -> list[str]:
    """Split "A, B, and C" (or a single item) into names."""
    parts = [p.strip() for p in items.split(",")]
    parts[-1] = re.sub(r"^and ", "", parts[-1])
    if len(parts) == 1 and " and " in parts[0]:
        parts = parts[0].split(" and ")
    return [p for p in (p.strip() for p in parts) if p]


def _listed(sentence: str, pattern: str, number: str) -> list[str]:
    match = re.search(pattern, sentence)
    if not match:
        raise ValueError(f"rule {number}: list not found")
    return _split_list(match.group(1))


def _singular(heading: str) -> str:
    """Section 3 headings are plural: "Sorceries", "Phenomena", "Kindreds"."""
    if heading.endswith("ies"):
        return heading[:-3] + "y"
    if heading.endswith("ena"):
        return heading[:-1] + "on"
    return heading.removesuffix("s")


def _effective(text: str) -> str:
    match = re.search(r"effective as of (\w+ \d{1,2}, \d{4})", text)
    if not match:
        raise ValueError("CR effective date not found")
    return datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()


def parse(text: str) -> Rules:
    """Parse types, supertypes, subtypes and keywords out of the CR text."""
    body = _body(text)

    card_type_names = _listed(_rule(body, "205.2a"), r"The card types are ([^.]+)\.", "205.2a")
    headings = {
        _singular(name): number
        for number, name in re.findall(r"^(3\d\d)\. (.+)$", body, re.MULTILINE)
    }
    missing = [name for name in card_type_names if name.capitalize() not in headings]
    if missing:
        raise ValueError(f"no section 3 rule for card type(s): {missing}")
    card_types = {name.capitalize(): headings[name.capitalize()] for name in card_type_names}

    supertypes = [
        name.capitalize()
        for name in _listed(_rule(body, "205.4a"), r"The supertypes are ([^.]+)\.", "205.4a")
    ]

    subtypes = {}
    for number, category in SUBTYPE_RULES.items():
        sentence = re.sub(r"\s*\(see rule [^)]*\)", "", _rule(body, number))
        if category == "creature":
            two_words = re.findall(r"two words long: ([^.]+)\.", sentence)
            names = _listed(sentence, r"one word long: ([^.]+)\.", number)
            names = [*(n for item in two_words for n in _split_list(item)), *names]
        else:
            names = _listed(sentence, r"(?:The \w+ types are|That \w+ type is) ([^.]+)\.", number)
        subtypes[category] = sorted(set(names), key=str.casefold)

    basic = _listed(_rule(body, "205.3i"), r"Of that list, ([^.]+?) are the basic land types", "205.3i")

    actions = dict(
        (name, number)
        for number, name in re.findall(r"^(701\.\d+)\. (.+)$", body, re.MULTILINE)
        if number != "701.1"  # 701.1 is the section's introduction
    )
    abilities = dict(
        (name, number)
        for number, name in re.findall(r"^(702\.\d+)\. (.+)$", body, re.MULTILINE)
        if number != "702.1"
    )
    ability_words = _listed(_rule(body, "207.2c"), r"The ability words are ([^.]+)\.", "207.2c")

    return Rules(
        effective=_effective(text),
        card_types=card_types,
        supertypes=supertypes,
        subtypes=subtypes,
        basic_land_types=basic,
        keyword_abilities=abilities,
        keyword_actions=actions,
        ability_words=ability_words,
    )


# --- Turtle output ----------------------------------------------------------

PREFIXES = {
    "mg": iri.ONTOLOGY,
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}
# Subtype category -> its class in core.ttl.
SUBTYPE_CLASSES = {
    "artifact": "ArtifactType",
    "battle": "BattleType",
    "creature": "CreatureType",
    "dungeon": "DungeonType",
    "enchantment": "EnchantmentType",
    "land": "LandType",
    "planar": "PlanarType",
    "planeswalker": "PlaneswalkerType",
    "spell": "SpellType",
}


def _literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _header(rules: Rules, source: str, what: str, prefixes: dict[str, str]) -> list[str]:
    lines = [
        f"# {what}",
        "#",
        "# GENERATED by `uv run python -m managraph.rules` from the Magic: The Gathering",
        f"# Comprehensive Rules effective {rules.effective}. Do not edit by hand.",
        f"# Source: {source}",
        "",
    ]
    prefixes = {**PREFIXES, **prefixes}
    width = max(map(len, prefixes)) + 2
    lines += [f"@prefix {p + ':':{width}s}<{ns}> ." for p, ns in prefixes.items()]
    return lines + [""]


def _individual(subject: str, classes: list[str], label: str, section: str | None = None,
                extra: list[str] = ()) -> list[str]:
    lines = [f"{subject} a owl:NamedIndividual, {', '.join(classes)} ;"]
    props = [f"rdfs:label {_literal(label)}@en", *extra]
    if section:
        props.append(f"mg:ruleSection {_literal(section)}")
    lines += [f"    {p} ;" for p in props[:-1]] + [f"    {props[-1]} ."]
    return lines + [""]


def _type_prefix(category: str) -> str:
    return {"card": "cardtype", "super": "supertype"}.get(category, category)


def types_ttl(rules: Rules, source: str = RULES_PAGE) -> str:
    """Turtle for every card type, supertype and subtype, plus the Changeling axiom."""
    categories = ["card", "super", *sorted(SUBTYPE_CLASSES)]
    prefixes = {_type_prefix(c): f"{iri.BASE}type/{c}/" for c in categories}
    prefixes["keyword"] = f"{iri.BASE}keyword/"
    lines = _header(rules, source, "ManaGraph types: card types, supertypes and subtypes (CR 205).", prefixes)

    def ref(category: str, name: str) -> str:
        return f"{_type_prefix(category)}:{iri.slug(name)}"

    lines += ["# --- Card types (205.2a) ---", ""]
    for name, section in rules.card_types.items():
        extra = ['skos:altLabel "Tribal"@en'] if name == "Kindred" else []  # 308.3
        lines += _individual(ref("card", name), ["mg:CardType"], name, section, extra)

    lines += ["# --- Supertypes (205.4a) ---", ""]
    for name in rules.supertypes:
        lines += _individual(ref("super", name), ["mg:Supertype"], name, "205.4a")

    for number, category in SUBTYPE_RULES.items():
        lines += [f"# --- {SUBTYPE_CLASSES[category]} ({number}) ---", ""]
        seen = set()
        for name in rules.subtypes[category]:
            local = iri.slug(name)
            if local in seen:
                raise ValueError(f"two {category} types share the IRI {local}")
            seen.add(local)
            classes = [f"mg:{SUBTYPE_CLASSES[category]}"]
            if category == "land" and name in rules.basic_land_types:
                classes.append("mg:BasicLandType")
            lines += _individual(ref(category, name), classes, name.replace("’", "'"))

    if "Changeling" not in rules.keyword_abilities:
        raise ValueError("Changeling not found among keyword abilities")
    section = rules.keyword_abilities["Changeling"]
    restrictions = [
        f"    [ a owl:Restriction ; owl:onProperty mg:hasSubtype ; owl:hasValue {ref('creature', n)} ]"
        for n in rules.subtypes["creature"]
    ]
    lines += [
        f"# --- Changeling ({section}a) ---",
        "#",
        "# \"Changeling\" means \"This object is every creature type.\" A face of a card",
        "# with changeling that is a creature or kindred has every creature type. The",
        "# card-type condition follows 205.3d: an object can't have a subtype that",
        "# doesn't correspond to one of its card types.",
        "",
        "[ a owl:Class ;",
        "  owl:intersectionOf (",
        "    [ a owl:Restriction ; owl:onProperty mg:faceOf ;",
        "      owl:someValuesFrom [ a owl:Restriction ; owl:onProperty mg:hasKeyword ;",
        "                           owl:hasValue keyword:changeling ] ]",
        "    [ a owl:Restriction ; owl:onProperty mg:hasCardType ;",
        f"      owl:someValuesFrom [ a owl:Class ; owl:oneOf ( {ref('card', 'Creature')} {ref('card', 'Kindred')} ) ] ]",
        "  ) ]",
        "  rdfs:subClassOf",
        " ,\n".join(restrictions) + " .",
        "",
    ]
    return "\n".join(lines)


def keywords_ttl(rules: Rules, source: str = RULES_PAGE) -> str:
    """Turtle for every keyword action (701), keyword ability (702) and ability word (207.2c)."""
    lines = _header(rules, source, "ManaGraph keywords: keyword actions, keyword abilities and ability words.",
                    {"keyword": f"{iri.BASE}keyword/"})

    entries: dict[str, dict] = {}  # IRI local name -> classes, label, sections

    def add(name: str, cls: str, section: str) -> None:
        local = iri.slug(name).lower()
        entry = entries.setdefault(local, {"label": name, "classes": [], "sections": []})
        entry["classes"].append(cls)
        entry["sections"].append(section)

    for name, section in rules.keyword_actions.items():
        add(name, "mg:KeywordAction", section)
    for name, section in rules.keyword_abilities.items():
        add(name, "mg:KeywordAbility", section)
    for name in rules.ability_words:
        add(name[0].upper() + name[1:], "mg:AbilityWord", "207.2c")

    for local, entry in sorted(entries.items()):
        sections = ", ".join(_literal(s) for s in entry["sections"])
        lines += _individual(f"keyword:{local}", entry["classes"], entry["label"],
                             extra=[f"mg:ruleSection {sections}"])
    return "\n".join(lines)


def generate(rules_path: Path, out_dir: Path = ONTOLOGY_DIR, source: str = RULES_PAGE) -> Rules:
    """Parse the CR at ``rules_path`` and write types.ttl and keywords.ttl to ``out_dir``."""
    rules = parse(read(rules_path))
    (out_dir / "types.ttl").write_text(types_ttl(rules, source), encoding="utf-8")
    (out_dir / "keywords.ttl").write_text(keywords_ttl(rules, source), encoding="utf-8")
    return rules


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate types.ttl and keywords.ttl from the Comprehensive Rules.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="where the CR text is saved")
    parser.add_argument("--out", type=Path, default=ONTOLOGY_DIR, help="ontology directory to write to")
    parser.add_argument("--force", action="store_true", help="re-download even if the CR is unchanged")
    args = parser.parse_args(argv)

    path = download(args.dest, args.force)
    manifest = json.loads((args.dest / MANIFEST_NAME).read_text(encoding="utf-8"))
    rules = generate(path, args.out, manifest["url"])
    n_sub = sum(len(v) for v in rules.subtypes.values())
    print(
        f"rules: CR {rules.effective}: {len(rules.card_types)} card types, {len(rules.supertypes)} supertypes, "
        f"{n_sub} subtypes, {len(rules.keyword_abilities)} keyword abilities, "
        f"{len(rules.keyword_actions)} keyword actions, {len(rules.ability_words)} ability words"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
