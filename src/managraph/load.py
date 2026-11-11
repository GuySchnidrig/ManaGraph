"""Load the ontology and the converted data into a local Oxigraph store.

The store is rebuilt from scratch on every run, in ``store/`` (gitignored).
Later steps (inference, SHACL validation) query it.

Usage::

    uv run python -m managraph.load
"""

from __future__ import annotations

import argparse
import gzip
import shutil
from pathlib import Path

import pyoxigraph as ox

from managraph import convert, download

DEFAULT_STORE = download.PROJECT_ROOT / "store"


INFERRED = "inferred.nt.gz"


def rdf_files(rdf_dir: Path = convert.DEFAULT_OUT, ontology_dir: Path = convert.ONTOLOGY_DIR,
              inferred: bool = True) -> list[Path]:
    """Every file that makes up the graph: the ontology, then the data.

    With ``inferred=False``, leave out the output of the inference step, so a
    rerun infers from the asserted triples only.
    """
    data = [p for p in sorted(rdf_dir.glob("*.nt.gz")) if inferred or p.name != INFERRED]
    return sorted(ontology_dir.glob("*.ttl")) + data


def load(store_path: Path | None = DEFAULT_STORE, rdf_dir: Path = convert.DEFAULT_OUT,
         ontology_dir: Path = convert.ONTOLOGY_DIR) -> ox.Store:
    """Build a fresh store from the asserted triples (no ``inferred.nt.gz``).

    ``store_path=None`` keeps it in memory.
    """
    if store_path is None:
        store = ox.Store()
    else:
        if store_path.exists():
            shutil.rmtree(store_path)
        store = ox.Store(str(store_path))

    for path in rdf_files(rdf_dir, ontology_dir, inferred=False):
        if path.suffix == ".ttl":
            store.bulk_load(path=str(path), format=ox.RdfFormat.TURTLE)
        else:
            with gzip.open(path, "rb") as data:
                store.bulk_load(data, format=ox.RdfFormat.N_TRIPLES)
    print(f"load: {len(store):,} triples into {store_path or 'memory'}")
    return store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the ontology and RDF data into Oxigraph.")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE, help="store directory (rebuilt)")
    parser.add_argument("--rdf-dir", type=Path, default=convert.DEFAULT_OUT, help="converted N-Triples")
    args = parser.parse_args(argv)
    load(args.store, args.rdf_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
