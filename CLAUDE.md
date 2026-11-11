# CLAUDE.md

## What this is

ManaGraph is a linked data knowledge graph of Magic: The Gathering cards. It offers SPARQL as an alternative way to query the card data, alongside the JSON files and REST/GraphQL APIs from Scryfall and MTGJSON. SPARQL adds arbitrary joins, aggregations and property-path traversal, and dereferenceable links to external IDs. The ontology, OWL reasoning and SHACL validation serve that goal: the graph should be correct, well-modeled and pleasant to query.

## Setup

- Python ≥ 3.12, managed with **uv**. Use `uv add <pkg>` to add dependencies, `uv sync` to install them and `uv run ...` to run code. Do not use pip or conda. Commit `uv.lock`.
- Triple stores:
  - **Building:** **Oxigraph** through `pyoxigraph`, used inside the pipeline for loading, inference and validation.
  - **Serving:** **QLever** is the public SPARQL endpoint. It builds a read-only index from the generated N-Triples/Turtle files, rebuilt on each data update. It has no OWL reasoning, so the pipeline writes inferred triples into the data before indexing.
  - Write only standard SPARQL 1.1, with no store-specific extensions, so either store can run every query.
- Package code lives in `src/managraph/` (src layout, `uv_build` backend).
- `uv run managraph` runs the full build, through `run()` in [src/managraph/pipeline.py](src/managraph/pipeline.py). Add each new step (convert, load, validate) to `run()` in order. Split the argument parsing into a `cli.py` once there are several subcommands.
- `data/` (raw downloads, generated RDF), local Oxigraph stores (`store/`, `*.oxigraph/`) and QLever indexes (`qlever/`) are gitignored.

## Naming

- **ManaGraph**: repo name, display name and prose.
- **managraph** (lowercase): everything technical, including the Python package, CLI command, Docker image and namespace IRI `https://w3id.org/managraph/`.

## Data

- Source: **Scryfall bulk data**, never the per-card API.
  - `uv run python -m managraph.download [types...]` ([src/managraph/download.py](src/managraph/download.py)) reads the index at `https://api.scryfall.com/bulk-data`. It saves each file as served, gzipped JSON Lines, to `data/raw/scryfall/<type>.jsonl.gz`.
  - A `manifest.json` in that folder records `updated_at` per type, so unchanged files are skipped.
  - Index entries carry `jsonl_download_uri` and `compressed_size`. There is no plain-JSON `download_uri`.
  - Types: `oracle_cards` (one per oracle ID, the default), `default_cards` (printings), `all_cards`, `rulings`, `unique_artwork`, `art_tags`, `oracle_tags`.
  - Read the files by streaming them line by line with `gzip.open(..., "rt", encoding="utf-8")`.
- Keep downloaded raw data out of git.
- The source data updates often, so the build should be an automated pipeline that can be rerun, not a one-off dump.

## Modeling plan

- **IRIs**: oracle cards (the "work") get IRIs from the oracle ID. Printings get IRIs from the printing ID. Faces of split, MDFC and adventure cards are separate nodes linked to their card.
- **Type hierarchy in OWL**: supertypes, card types and subtypes, e.g. Equipment ⊑ Artifact, Aura ⊑ Enchantment, Forest ⊑ Land.
  - Edge cases: Dryad Arbor (both Land and Creature), Kindred/Tribal.
  - **Changeling = has every creature type** is the first reasoning showcase.
- **External IDs**: Scryfall, Multiverse, MTGO, TCGplayer, Cardmarket and Card Kingdom become IRIs linked with `skos:exactMatch`. Wikidata federation for artists and sets comes later.
- **SHACL shapes**: use them to hunt for data bugs, e.g. color identity vs. mana cost, face back-links, legalities.
- **Keywords and ability words**: entities linked to their Comprehensive Rules section numbers.
- **Rules text** stays a literal. Do not try to parse abilities semantically.
- **Prices** stay out of the graph.

v1 scope: atomic cards, sets, printings, identifiers and legalities. Decks and sealed products come later.

Cheapest path: a JSON-LD `@context` over the bulk JSON, plus a small Python step for IRI minting and face splitting.

## Conventions

- Python, PEP 8.
- Use **Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`, `ci:`, `deps:`, `refactor:`. Release Please builds the version bumps and CHANGELOG from them.
  - Before 1.0, `feat` bumps the minor version, `fix` bumps the patch, and `feat!` (breaking) bumps the minor.
  - Never hand-edit the version. It lives in `pyproject.toml`, `src/managraph/__init__.py` (the `x-release-please-version` line), `uv.lock` and `.release-please-manifest.json`, and Release Please updates all four.
- Dependabot opens weekly grouped PRs for uv and GitHub Actions dependencies.
- CI (`.github/workflows/pipeline.yml`) runs `uv sync --locked` and `uv run managraph` on every PR and push to `main`.
  - Keep `uv.lock` in sync with `pyproject.toml`, or the install step fails.
  - Scryfall downloads are cached between runs.
  - When a pipeline step is added, CI covers it automatically.
- Before publishing a dataset or endpoint, check the data source's license and the Wizards of the Coast Fan Content Policy. Card names and text are WotC IP.
