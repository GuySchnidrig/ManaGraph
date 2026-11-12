"""Build the static site for GitHub Pages: ontology documentation and files.

The w3id rules in ``w3id/managraph/.htaccess`` expect, under
https://guyschnidrig.github.io/ManaGraph/:

- ``ontology/managraph.ttl``  every ``ontology/*.ttl`` merged into one Turtle file
- ``ontology/``               HTML documentation. Each class and property is
                              anchored by its local name, so ``…/ontology#Card``
                              lands on Card.
- ``404.html``                GitHub Pages serves it for every other path, i.e.
                              every other ManaGraph IRI. Vocabulary IRIs
                              (``type/creature/Elf``) jump to their entry in the
                              documentation. Card, printing, set and other data
                              IRIs get a short page about the identifier.
- ``index.html``              landing page

No card data is published; see the README on licensing.

Usage::

    uv run python -m managraph.docs            # writes site/
"""

from __future__ import annotations

import argparse
import html
import shutil
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import pyoxigraph as ox

from managraph import __version__, convert, download, iri

DEFAULT_OUT = download.PROJECT_ROOT / "site"
REPO = "https://github.com/GuySchnidrig/ManaGraph"
# The public SPARQL endpoint (a proof of concept on a home server, see deploy/).
ENDPOINT = "https://homelab.taila88e34.ts.net/"
YASGUI = "https://yasgui.triply.cc/"


def yasgui_link(query: str) -> str:
    """A YASGUI editor link that opens ``query`` against the ManaGraph endpoint."""
    return f"{YASGUI}#query={quote(query)}&endpoint={quote(ENDPOINT, safe='')}&requestMethod=POST"

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
DCTERMS = "http://purl.org/dc/terms/"
FOAF = "http://xmlns.com/foaf/0.1/"
MG = iri.ONTOLOGY
ONTOLOGY_IRI = MG.rstrip("#")

PREFIXES = {
    "mg": MG, "rdf": RDF, "rdfs": RDFS, "owl": OWL, "xsd": XSD, "skos": SKOS,
    "dcterms": DCTERMS, "foaf": FOAF,
    "cardtype": f"{iri.BASE}type/card/", "supertype": f"{iri.BASE}type/super/",
    "creature": f"{iri.BASE}type/creature/", "keyword": f"{iri.BASE}keyword/",
    "color": f"{iri.BASE}color/", "format": f"{iri.BASE}format/", "layout": f"{iri.BASE}layout/",
    "settype": f"{iri.BASE}set-type/", "rarity": f"{iri.BASE}rarity/", "vocab": f"{iri.BASE}vocab/",
}

# Which classes' individuals are listed, in this order, and how.
VOCABULARIES = [
    ("Colors and mana", ["ManaType"], "table"),
    ("Card types", ["CardType"], "table"),
    ("Supertypes", ["Supertype"], "table"),
    ("Subtypes", ["ArtifactType", "EnchantmentType", "LandType", "PlaneswalkerType", "SpellType",
                  "CreatureType", "PlanarType", "DungeonType", "BattleType"], "inline"),
    ("Keywords", ["KeywordAbility", "KeywordAction", "AbilityWord"], "table"),
    ("Formats", ["Format"], "table"),
    ("Layouts", ["Layout"], "table"),
    ("Set types", ["SetType"], "table"),
    ("Rarities", ["Rarity"], "table"),
]


# --- reading the ontology ---------------------------------------------------


FILE_ORDER = ["core.ttl", "mana.ttl", "vocab.ttl", "types.ttl", "keywords.ttl"]


class Ontology:
    def __init__(self, ontology_dir: Path = convert.ONTOLOGY_DIR):
        rank = {name: i for i, name in enumerate(FILE_ORDER)}
        self.files = sorted(ontology_dir.glob("*.ttl"), key=lambda p: (rank.get(p.name, len(rank)), p.name))
        self.store = ox.Store()
        for path in self.files:
            self.store.load(path=str(path), format=ox.RdfFormat.TURTLE)

    def objects(self, subject, predicate: str) -> list:
        return [q.object for q in self.store.quads_for_pattern(subject, ox.NamedNode(predicate), None)]

    def subjects(self, predicate: str, obj) -> list:
        return [q.subject for q in self.store.quads_for_pattern(None, ox.NamedNode(predicate), obj)]

    def one(self, subject, predicate: str) -> str | None:
        values = self.objects(subject, predicate)
        return values[0].value if values else None

    def terms(self, kind: str) -> list[ox.NamedNode]:
        found = [s for s in self.subjects(RDF + "type", ox.NamedNode(kind))
                 if isinstance(s, ox.NamedNode) and s.value.startswith(MG)]
        return sorted(found, key=lambda n: n.value.removeprefix(MG).casefold())

    def individuals(self, class_name: str) -> list[ox.NamedNode]:
        found = [s for s in self.subjects(RDF + "type", ox.NamedNode(MG + class_name)) if isinstance(s, ox.NamedNode)]
        return sorted(set(found), key=lambda n: (self.label(n) or n.value).casefold())

    def label(self, node) -> str | None:
        return self.one(node, RDFS + "label")

    def turtle(self) -> bytes:
        """All ontology files as one Turtle document, comments and order kept.

        Concatenated Turtle files are valid Turtle: prefixes may be declared
        again, and the files only use anonymous blank nodes (``[]``).
        """
        parts = [f"# ManaGraph ontology: {', '.join(p.name for p in self.files)}, merged.\n"
                 f"# Source: {REPO}/tree/main/ontology\n"]
        for path in self.files:
            parts.append(f"\n# {'=' * 74}\n# {path.name}\n# {'=' * 74}\n\n" + path.read_text(encoding="utf-8"))
        return "".join(parts).encode("utf-8")


def anchor(node: ox.NamedNode) -> str:
    """HTML id for a term: ``Card`` for mg:Card, ``type-creature-Elf`` for a type."""
    if node.value.startswith(MG):
        return node.value.removeprefix(MG)
    return node.value.removeprefix(iri.BASE).replace("/", "-")


def curie(value: str) -> str:
    for prefix, ns in PREFIXES.items():
        if value.startswith(ns) and value != ns:
            return f"{prefix}:{value.removeprefix(ns)}"
    return value


# --- HTML helpers -----------------------------------------------------------

e = html.escape

CSS = """
:root { --bg:#fdfdfc; --fg:#1d1d1f; --muted:#5f6368; --line:#e3e3e0; --accent:#7a3b8f; --code:#f3f2ef; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16161a; --fg:#e8e8ea; --muted:#a0a0a8; --line:#2c2c33; --accent:#c79be0; --code:#222228; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width: 60rem; margin: 0 auto; padding: 2rem 1rem 4rem; }
a { color: var(--accent); }
h1 { font-size: 2rem; margin: 0 0 .25rem; }
h2 { margin-top: 3rem; padding-bottom: .3rem; border-bottom: 1px solid var(--line); }
h3 { margin: 2rem 0 .25rem; }
code, pre { font-family: ui-monospace,SFMono-Regular,Consolas,monospace; font-size: .9em; background: var(--code); border-radius: 4px; }
code { padding: .1em .3em; }
pre { padding: .8rem 1rem; overflow-x: auto; }
.muted, .iri { color: var(--muted); }
.iri { font-size: .85rem; word-break: break-all; }
.term { padding: .2rem 0 1rem; border-bottom: 1px solid var(--line); }
.term:target, li:target, tr:target, span:target { background: color-mix(in srgb, var(--accent) 15%, transparent); }
dl { display: grid; grid-template-columns: max-content 1fr; gap: .2rem 1rem; margin: .5rem 0 0; }
dt { color: var(--muted); }
dd { margin: 0; }
table { border-collapse: collapse; width: 100%; font-size: .95rem; }
th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid var(--line); vertical-align: top; }
.inline span { display: inline-block; margin: 0 .6rem .2rem 0; }
nav ul { columns: 2; padding-left: 1.2rem; }
footer { margin-top: 4rem; font-size: .85rem; color: var(--muted); }
"""

FOOTER = f"""<footer>
<p>ManaGraph is unofficial Fan Content permitted under the
<a href="https://company.wizards.com/en/legal/fancontentpolicy">Fan Content Policy</a>.
Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast.
©Wizards of the Coast LLC.</p>
<p>Card data comes from <a href="https://scryfall.com">Scryfall</a>; ManaGraph is not affiliated with or
endorsed by Scryfall. Code and ontology: <a href="{REPO}/blob/main/LICENSE">MIT License</a>,
<a href="{REPO}">source on GitHub</a>.</p>
</footer>"""


def page(title: str, body: str, description: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<style>{CSS}</style>
</head>
<body>
<main>
{body}
{FOOTER}
</main>
</body>
</html>
"""


class Renderer:
    def __init__(self, onto: Ontology):
        self.onto = onto
        self.anchors: set[str] = set()

    def ref(self, node) -> str:
        """A link to a term: in this page if documented here, else to its IRI."""
        if isinstance(node, ox.Literal):
            return f"<code>{e(node.value)}</code>"
        if isinstance(node, ox.BlankNode):
            return self.restriction(node)
        value = node.value
        if value.startswith(MG) or value.startswith(iri.BASE):
            return f'<a href="#{e(anchor(node))}"><code>{e(curie(value))}</code></a>'
        return f'<a href="{e(value)}"><code>{e(curie(value))}</code></a>'

    def restriction(self, node: ox.BlankNode) -> str:
        on = self.onto.objects(node, OWL + "onProperty")
        if on:
            for p, text in ((OWL + "minCardinality", "at least {}"), (OWL + "maxCardinality", "at most {}"),
                            (OWL + "cardinality", "exactly {}")):
                n = self.onto.one(node, p)
                if n:
                    return f"{text.format(e(n))} {self.ref(on[0])}"
            value = self.onto.objects(node, OWL + "hasValue")
            if value:
                return f"{self.ref(on[0])} value {self.ref(value[0])}"
        return '<span class="muted">(class expression)</span>'

    def refs(self, nodes) -> str:
        return ", ".join(self.ref(n) for n in nodes)

    def term(self, node: ox.NamedNode, kind: str) -> str:
        onto = self.onto
        local = anchor(node)
        self.anchors.add(local)
        rows = [("IRI", f'<span class="iri">{e(node.value)}</span>'), ("Kind", e(kind))]
        types = {t.value for t in onto.objects(node, RDF + "type")}
        if OWL + "FunctionalProperty" in types:
            rows.append(("Characteristics", "functional (at most one value)"))
        for label, predicate in (("Subclass of", RDFS + "subClassOf"), ("Subproperty of", RDFS + "subPropertyOf"),
                                 ("Domain", RDFS + "domain"), ("Range", RDFS + "range"),
                                 ("Inverse of", OWL + "inverseOf"),
                                 ("Goes with card types", MG + "subtypeOfCardType")):
            values = onto.objects(node, predicate)
            if values:
                rows.append((label, self.refs(values)))
        for label, predicate in (("Subclasses", RDFS + "subClassOf"), ("Subproperties", RDFS + "subPropertyOf")):
            values = [s for s in onto.subjects(predicate, node) if isinstance(s, ox.NamedNode)]
            if values:
                rows.append((label, self.refs(sorted(values, key=lambda n: n.value))))
        if kind == "Class":
            used = [p for p in onto.subjects(RDFS + "domain", node)]
            if used:
                rows.append(("Properties", self.refs(sorted(used, key=lambda n: n.value))))
            count = len(onto.individuals(local))
            if count:
                rows.append(("Individuals", f'{count} listed under <a href="#vocabularies">Vocabularies</a>'))
        section = onto.one(node, MG + "ruleSection")
        if section:
            rows.append(("Comprehensive Rules", e(section)))
        comment = onto.one(node, RDFS + "comment")
        dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
        return (f'<div class="term" id="{e(local)}"><h3>{e(onto.label(node) or local)} '
                f'<span class="muted">mg:{e(local)}</span></h3>'
                + (f"<p>{e(comment)}</p>" if comment else "") + f"<dl>{dl}</dl></div>")

    def vocabulary(self, title: str, classes: list[str], style: str) -> str:
        onto = self.onto
        parts = [f"<h3>{e(title)}</h3>"]
        for class_name in classes:
            members = onto.individuals(class_name)
            if class_name == "ManaType":  # colors are mana types too; list once
                members = sorted(set(members) | set(onto.individuals("Color")), key=lambda n: n.value)
            if not members:
                continue
            if len(classes) > 1:
                parts.append(f'<p><a href="#{class_name}"><strong>{e(onto.label(ox.NamedNode(MG + class_name)))}'
                             f"</strong></a> <span class=\"muted\">({len(members)})</span></p>")
            if style == "inline":
                spans = []
                for m in members:
                    self.anchors.add(anchor(m))
                    spans.append(f'<span id="{e(anchor(m))}" title="{e(m.value)}">{e(onto.label(m) or m.value)}</span>')
                parts.append(f'<p class="inline">{"".join(spans)}</p>')
            else:
                rows = []
                for m in members:
                    self.anchors.add(anchor(m))
                    extra = onto.one(m, MG + "ruleSection") or onto.one(m, SKOS + "notation") or ""
                    alt = ", ".join(a.value for a in onto.objects(m, SKOS + "altLabel"))
                    note = onto.one(m, RDFS + "comment") or (f"also: {alt}" if alt else "")
                    rows.append(f'<tr id="{e(anchor(m))}"><td>{e(onto.label(m) or "")}</td>'
                                f'<td class="iri">{e(curie(m.value))}</td><td>{e(extra)}</td><td>{e(note)}</td></tr>')
                head = "<tr><th>Label</th><th>IRI</th><th>Rule / symbol</th><th>Note</th></tr>"
                parts.append(f"<table>{head}{''.join(rows)}</table>")
        return "\n".join(parts)

    def concept_schemes(self) -> str:
        onto = self.onto
        schemes = sorted((s for s in onto.subjects(RDF + "type", ox.NamedNode(SKOS + "ConceptScheme"))
                          if isinstance(s, ox.NamedNode)), key=lambda n: n.value)
        by_scheme = defaultdict(list)
        for concept in onto.subjects(RDF + "type", ox.NamedNode(SKOS + "Concept")):
            for scheme in onto.objects(concept, SKOS + "inScheme"):
                by_scheme[scheme.value].append(concept)
        rows = []
        for scheme in schemes:
            self.anchors.add(anchor(scheme))
            concepts = sorted(by_scheme[scheme.value], key=lambda n: n.value)
            spans = []
            for c in concepts:
                self.anchors.add(anchor(c))
                spans.append(f'<span id="{e(anchor(c))}">{e(onto.one(c, SKOS + "prefLabel") or c.value)}</span>')
            listed = "".join(spans) or '<span class="muted">open scheme: concepts are minted from the data</span>'
            rows.append(f'<tr id="{e(anchor(scheme))}"><td>{e(onto.label(scheme) or "")}</td>'
                        f'<td class="iri">{e(curie(scheme.value))}</td><td class="inline">{listed}</td></tr>')
        return ("<h3>Printing attributes (SKOS concept schemes)</h3><table>"
                "<tr><th>Scheme</th><th>IRI</th><th>Concepts</th></tr>" + "".join(rows) + "</table>")


# --- pages ------------------------------------------------------------------


def ontology_page(onto: Ontology) -> tuple[str, set[str]]:
    r = Renderer(onto)
    root = ox.NamedNode(ONTOLOGY_IRI)
    title = onto.one(root, DCTERMS + "title") or "ManaGraph ontology"
    description = onto.one(root, DCTERMS + "description") or ""
    version = onto.one(root, OWL + "versionInfo") or __version__
    creators = [onto.one(c, FOAF + "name") or c.value for c in onto.objects(root, DCTERMS + "creator")]

    sections = [("Classes", OWL + "Class", "Class"), ("Object properties", OWL + "ObjectProperty", "Object property"),
                ("Datatype properties", OWL + "DatatypeProperty", "Datatype property"),
                ("Annotation properties", OWL + "AnnotationProperty", "Annotation property")]
    body = [f"""<h1>{e(title)}</h1>
<p>{e(description)}</p>
<dl>
<dt>IRI</dt><dd><code>{e(ONTOLOGY_IRI)}</code>, terms <code>{e(MG)}</code></dd>
<dt>Version</dt><dd>{e(version)}</dd>
<dt>Prefix</dt><dd><code>mg:</code></dd>
<dt>Creator</dt><dd>{e(", ".join(creators))}</dd>
<dt>Download</dt><dd><a href="managraph.ttl">managraph.ttl</a> (Turtle, all files merged)</dd>
<dt>Source</dt><dd><a href="{REPO}/tree/main/ontology">ontology/ on GitHub</a></dd>
</dl>
<nav><h2>Contents</h2><ul>"""]
    body += [f'<li><a href="#{name.lower().replace(" ", "-")}">{name}</a></li>' for name, _, _ in sections]
    body.append('<li><a href="#vocabularies">Vocabularies</a></li></ul></nav>')

    for name, kind_iri, kind in sections:
        terms = onto.terms(kind_iri)
        body.append(f'<h2 id="{name.lower().replace(" ", "-")}">{name} <span class="muted">({len(terms)})</span></h2>')
        body += [r.term(t, kind) for t in terms]

    body.append('<h2 id="vocabularies">Vocabularies</h2>'
                '<p>Individuals with IRIs of their own under <code>https://w3id.org/managraph/</code>. '
                "Types and keywords are generated from the Comprehensive Rules. Keywords that only "
                "Scryfall lists, Un-card types and values of the open SKOS schemes are minted from the data and "
                "aren't listed here.</p>")
    body += [r.vocabulary(*v) for v in VOCABULARIES]
    body.append(r.concept_schemes())
    return page(title, "\n".join(body), description), r.anchors


NOT_FOUND = """<h1>ManaGraph identifier</h1>
<p id="what">This address is not a page on this site.</p>
<div id="data" hidden>
  <p>It is an identifier in the ManaGraph knowledge graph. Look it up on the
  <a href="ENDPOINT_URL">ManaGraph SPARQL endpoint</a>:</p>
  <pre id="query"></pre>
  <p><a id="yasgui">Run it in YASGUI</a> · <a id="turtle">Result as Turtle</a></p>
  <p id="scryfall"></p>
</div>
<p><a href="BASE">ManaGraph home</a> · <a href="BASEontology/">Ontology documentation</a></p>
<script>
(function () {
  var base = "BASE";
  var path = location.pathname.slice(location.pathname.indexOf("/ManaGraph/") + "/ManaGraph/".length);
  var vocab = /^(type|keyword|color|format|layout|set-type|rarity|vocab)\\//;
  if (vocab.test(path)) {
    location.replace(base + "ontology/#" + path.replace(/\\/$/, "").replace(/\\//g, "-"));
    return;
  }
  var kind = path.split("/")[0];
  if (["card", "printing", "set", "artist", "illustration"].indexOf(kind) < 0) return;
  var id = "https://w3id.org/managraph/" + path;
  document.getElementById("what").textContent = "<" + id + ">";
  var query = "DESCRIBE <" + id + ">";
  var endpoint = "ENDPOINT_URL";
  document.getElementById("query").textContent = query;
  document.getElementById("turtle").href = endpoint + "?query=" + encodeURIComponent(query);
  document.getElementById("yasgui").href = "YASGUI_URL#query=" + encodeURIComponent(query) +
    "&endpoint=" + encodeURIComponent(endpoint) + "&requestMethod=POST";
  var m = path.match(/^card\\/([0-9a-f-]{36})/);
  var p = path.match(/^printing\\/([0-9a-f-]{36})/);
  var s = document.getElementById("scryfall");
  if (m) s.innerHTML = 'On Scryfall: <a href="https://scryfall.com/search?q=oracleid%3A' + m[1] + '&unique=prints">all printings of this card</a>';
  if (p) s.innerHTML = 'On Scryfall: <a href="https://api.scryfall.com/cards/' + p[1] + '?format=image&version=normal">card image</a>';
  document.getElementById("data").hidden = false;
})();
</script>"""

PAGES_BASE = "https://guyschnidrig.github.io/ManaGraph/"


def home_page(onto: Ontology) -> str:
    root = ox.NamedNode(ONTOLOGY_IRI)
    version = onto.one(root, OWL + "versionInfo") or __version__
    example = (download.PROJECT_ROOT / "queries" / "changeling-elves.rq")
    query = example.read_text(encoding="utf-8") if example.exists() else ""
    return page("ManaGraph", f"""<h1>ManaGraph</h1>
<p>A linked data knowledge graph of Magic: The Gathering cards, built from Scryfall data and queryable
with SPARQL: arbitrary joins, aggregations and property paths across cards, faces, printings, sets,
rulings and identifiers, on an ontology of Magic's type system.</p>
<ul>
<li><a href="ontology/">Ontology documentation</a> (version {e(version)}) ·
    <a href="ontology/managraph.ttl">Turtle</a></li>
<li><a href="{REPO}">Source, pipeline and example queries on GitHub</a></li>
</ul>
<h2>Query it</h2>
<p>SPARQL endpoint: <a href="{ENDPOINT}"><code>{ENDPOINT}</code></a>. It is a proof of concept on a
home server, rebuilt weekly from Scryfall data, without uptime guarantees. Open it in a SPARQL editor such
as <a href="{YASGUI}">YASGUI</a>, or build the graph and serve it yourself; see the README.</p>
<h2>Example</h2>
<pre>{e(query)}</pre>
<p><a href="{e(yasgui_link(query))}">Run this query in YASGUI</a></p>""", "ManaGraph: a SPARQL knowledge graph of Magic: The Gathering cards")


def build(out_dir: Path = DEFAULT_OUT, ontology_dir: Path = convert.ONTOLOGY_DIR) -> set[str]:
    """Write the site to ``out_dir`` (replaced). Returns the anchors of the ontology page."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "ontology").mkdir(parents=True)
    onto = Ontology(ontology_dir)

    (out_dir / "ontology" / "managraph.ttl").write_bytes(onto.turtle())
    ontology_html, anchors = ontology_page(onto)
    (out_dir / "ontology" / "index.html").write_text(ontology_html, encoding="utf-8")
    (out_dir / "index.html").write_text(home_page(onto), encoding="utf-8")
    not_found = (NOT_FOUND.replace("ENDPOINT_URL", ENDPOINT).replace("YASGUI_URL", YASGUI)
                 .replace("REPO", REPO).replace("BASE", PAGES_BASE))
    (out_dir / "404.html").write_text(page("ManaGraph identifier", not_found), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    print(f"docs: site written to {out_dir} ({len(anchors)} anchors)")
    return anchors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the GitHub Pages site.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (replaced)")
    args = parser.parse_args(argv)
    build(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
