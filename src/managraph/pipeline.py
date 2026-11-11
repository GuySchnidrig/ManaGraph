"""Run the full ManaGraph build workflow.

Steps, in order:

1. download  - fetch Scryfall bulk data (``managraph.download``)
2. convert   - write N-Triples to data/rdf/ (``managraph.convert``)
3. load      - build an Oxigraph store in store/ (``managraph.load``)
4. infer     - write inferred triples to data/rdf/inferred.nt.gz (``managraph.infer``)
5. validate  - check the graph against shapes/ with SHACL (``managraph.validate``);
               reports problems, doesn't fail the build

Usage::

    uv run managraph                         # default bulk types
    uv run managraph --types oracle_cards rulings --force
"""

from __future__ import annotations

import argparse
from pathlib import Path

from managraph import convert, download, infer, load, validate

# oracle_cards holds one representative printing per card; default_cards has
# every printing (English or the only language), needed for printing-level
# fields like rarity, artist, frame and finishes.
DEFAULT_TYPES = ("oracle_cards", "default_cards", "rulings")


def run(
    types: list[str] | tuple[str, ...] = DEFAULT_TYPES,
    raw_dir: Path = download.DEFAULT_DEST,
    force: bool = False,
) -> None:
    """Run every pipeline step in order."""
    print("== download ==")
    download.download(types, raw_dir, force)
    print("== convert ==")
    convert.convert(raw_dir)
    print("== load ==")
    store = load.load()
    print("== infer ==")
    infer.run(store)
    del store  # free the Oxigraph store before rudof loads the graph
    print("== validate ==")
    validate.run()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="managraph", description="Build the ManaGraph knowledge graph.")
    parser.add_argument("--types", nargs="+", default=list(DEFAULT_TYPES), help="Scryfall bulk types to fetch")
    parser.add_argument("--raw-dir", type=Path, default=download.DEFAULT_DEST, help="where raw downloads go")
    parser.add_argument("--force", action="store_true", help="re-download even if files are up to date")
    args = parser.parse_args(argv)

    run(args.types, args.raw_dir, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
