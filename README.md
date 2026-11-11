# ManaGraph

[![pipeline](https://github.com/GuySchnidrig/ManaGraph/actions/workflows/pipeline.yml/badge.svg?branch=main)](https://github.com/GuySchnidrig/ManaGraph/actions/workflows/pipeline.yml)
[![release](https://img.shields.io/github/v/release/GuySchnidrig/ManaGraph)](https://github.com/GuySchnidrig/ManaGraph/releases)
[![Python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2FGuySchnidrig%2FManaGraph%2Fmain%2Fpyproject.toml)](pyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fe5196?logo=conventionalcommits&logoColor=white)](https://www.conventionalcommits.org)
[![License: MIT](https://img.shields.io/github/license/GuySchnidrig/ManaGraph)](LICENSE)

A linked data knowledge graph of Magic: The Gathering cards, built from Scryfall data and queryable with SPARQL.

The JSON files and APIs from Scryfall are great for looking up cards. ManaGraph adds what they can't do: arbitrary joins, aggregations and property-path queries across cards, printings, rulings and external identifiers, on top of an ontology of Magic's type system.

> **Status:** early development. The full build runs end to end (about 35,000 cards, 4.5 million triples), but there is no public endpoint yet.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Serving with QLever also needs Docker.

```sh
uv sync
```

## Build the graph

```sh
uv run managraph
```

This runs the whole pipeline in about 3 minutes and needs about 9 GB of memory at its peak, during validation:

| Step | What it does | Output |
|---|---|---|
| download | Fetches the Scryfall bulk files `oracle_cards`, `default_cards` and `rulings`, skipping unchanged ones | `data/raw/scryfall/` |
| convert | Turns cards, faces, printings, sets, art and rulings into RDF, leaving out non-game cards (tokens, art cards, planes, ...) | `data/rdf/*.nt.gz` |
| load | Loads the ontology and the data into a local Oxigraph store | `store/` |
| infer | Adds the triples a reasoner would derive (subclasses, subproperties, Changeling), since QLever doesn't reason | `data/rdf/inferred.nt.gz` |
| validate | Checks the graph against the SHACL shapes with [rudof](https://rudof-project.github.io/); fails on violations, reports warnings | `data/reports/shacl.ttl` |
| export | Writes the full graph as one file for QLever | `qlever/managraph.nt.gz` |

Each step can also run on its own, e.g. `uv run python -m managraph.validate`. Nothing under `data/`, `store/` or `qlever/` is committed except the Qleverfile.

The type and keyword vocabularies are generated from the [Comprehensive Rules](https://magic.wizards.com/en/rules). After a rules update, regenerate them:

```sh
uv run python -m managraph.rules
```

## Query it

Serve the graph with [QLever](https://github.com/ad-freiburg/qlever). The `qlever` command line tool needs Python 3.12 or later and runs QLever in Docker, so it works on Linux and macOS. On Windows, run it inside WSL2 with Docker, since it generates Linux shell commands.

```sh
cd qlever
uvx --python 3.12 qlever index     # build the index from managraph.nt.gz (first)
uvx --python 3.12 qlever start     # SPARQL endpoint on http://localhost:7019
uvx --python 3.12 qlever ui        # optional web UI on http://localhost:8176
```

[`queries/`](queries/) has example queries in plain SPARQL 1.1:

| Query | Shows |
|---|---|
| [`changeling-elves.rq`](queries/changeling-elves.rq) | Commander-legal Elves, Changelings included through inference |
| [`land-creatures.rq`](queries/land-creatures.rq) | Faces with two card types, like Dryad Arbor |
| [`creature-types.rq`](queries/creature-types.rq) | The most common creature types |
| [`most-reprinted.rq`](queries/most-reprinted.rq) | Cards with the most printings and sets |
| [`reserved-list-in-vintage.rq`](queries/reserved-list-in-vintage.rq) | Reserved List cards banned or restricted in Vintage |
| [`prolific-artists.rq`](queries/prolific-artists.rq) | Artists with the most illustrations |
| [`commander-bans-by-color.rq`](queries/commander-bans-by-color.rq) | Commander bans by number of colors in the identity |
| [`rulings-per-keyword.rq`](queries/rulings-per-keyword.rq) | Keyword abilities with the most rulings, linked to their rule number |

Example: every Commander-legal Elf, Changelings included:

```sparql
PREFIX mg:       <https://w3id.org/managraph/ontology#>
PREFIX creature: <https://w3id.org/managraph/type/creature/>
PREFIX format:   <https://w3id.org/managraph/format/>

SELECT ?name WHERE {
  ?card mg:legalIn format:commander ;
        mg:hasFace/mg:hasSubtype creature:Elf ;
        mg:name ?name .
}
```

## Project layout

```
ontology/        OWL ontology (Turtle): core classes and properties, mana, vocabularies;
                 types.ttl and keywords.ttl are generated from the Comprehensive Rules
shapes/          SHACL shapes for data validation
queries/         example SPARQL queries
qlever/          Qleverfile (index files are gitignored)
src/managraph/   Python package: download, rules, convert, load, infer, validate, export
data/            downloads, generated RDF and reports (gitignored)
```

## Ontology

The ontology lives in [`ontology/`](ontology/) as Turtle. Its documentation, with every class, property and vocabulary term, is published at [guyschnidrig.github.io/ManaGraph/ontology/](https://guyschnidrig.github.io/ManaGraph/ontology/), along with all files merged into one [`managraph.ttl`](https://guyschnidrig.github.io/ManaGraph/ontology/managraph.ttl). The `pages` workflow rebuilds it on every change to `main`; build it locally with `uv run python -m managraph.docs`.

To browse the core classes and properties as a diagram, open [`core.ttl` in WebVOWL](https://service.tib.eu/webvowl/#iri=https://raw.githubusercontent.com/GuySchnidrig/ManaGraph/refs/heads/main/ontology/core.ttl).

## Data & licensing

- **Code and ontology:** the code, ontology, shapes and rules in this repository are licensed under the [MIT License](LICENSE).
- **Card data:** this repository contains no card data. The pipeline downloads it from [Scryfall](https://scryfall.com), and its use is subject to [Scryfall's API terms](https://scryfall.com/docs/api). The MIT License does not apply to it. ManaGraph is not affiliated with or endorsed by Scryfall.
- **Wizards of the Coast:** ManaGraph is unofficial Fan Content permitted under the [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
