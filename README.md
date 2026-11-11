# ManaGraph

A linked data knowledge graph of Magic: The Gathering cards, built from Scryfall data and queryable with SPARQL.

The JSON files and APIs from Scryfall are great for looking up cards. ManaGraph adds what they can't do: arbitrary joins, aggregations and property-path queries across cards, printings, rulings and external identifiers, on top of an ontology of Magic's type system.

> **Status:** early development. So far only the download step exists.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Usage

Run the pipeline:

```sh
uv run managraph                                 # oracle_cards + rulings
uv run managraph --types oracle_cards --force    # pick types, force re-download
```

Download individual Scryfall bulk files:

```sh
uv run python -m managraph.download --list       # available types and sizes
uv run python -m managraph.download rulings
```

Bulk files are saved as gzipped JSON Lines in `data/raw/scryfall/` and skipped when unchanged. They are not committed to the repository.

## Project layout

```
ontology/        OWL/RDFS ontology (Turtle): core, card types, mana
shapes/          SHACL shapes for data validation
rules/           inference/CONSTRUCT rules
src/managraph/   Python package: download, pipeline
data/            local downloads and generated RDF (gitignored)
```

## Data & licensing

- **Code and ontology:** the code, ontology, shapes and rules in this repository are licensed under the [MIT License](LICENSE).
- **Card data:** this repository contains no card data. The pipeline downloads it from [Scryfall](https://scryfall.com), and its use is subject to [Scryfall's API terms](https://scryfall.com/docs/api). The MIT License does not apply to it. ManaGraph is not affiliated with or endorsed by Scryfall.
- **Wizards of the Coast:** ManaGraph is unofficial Fan Content permitted under the [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy). Not approved/endorsed by Wizards. Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
