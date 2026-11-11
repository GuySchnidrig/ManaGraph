"""Write the full graph as one gzipped N-Triples file for QLever.

QLever builds its index inside a Docker container that only sees the folder
of the Qleverfile, so everything it indexes must be in ``qlever/``. This step
writes ``qlever/managraph.nt.gz``: the ontology (converted from Turtle) plus
every file in ``data/rdf/``, inferred triples included.

The data files are copied byte for byte: a sequence of gzip members is itself
a valid gzip file, so ``zcat`` reads them as one stream.

Usage::

    uv run python -m managraph.export
    cd qlever && qlever index && qlever start
"""

from __future__ import annotations

import argparse
import gzip
import io
import shutil
from pathlib import Path

import pyoxigraph as ox

from managraph import convert, download, load

QLEVER_DIR = download.PROJECT_ROOT / "qlever"
GRAPH_FILE = "managraph.nt.gz"


def export(out_dir: Path = QLEVER_DIR, rdf_dir: Path = convert.DEFAULT_OUT,
           ontology_dir: Path = convert.ONTOLOGY_DIR) -> Path:
    """Write ``out_dir/managraph.nt.gz`` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / GRAPH_FILE
    partial = target.with_name(target.name + ".part")

    with partial.open("wb") as out:
        for path in load.rdf_files(rdf_dir, ontology_dir, inferred=True):
            if path.suffix == ".ttl":
                # Each file is parsed on its own, so blank node IDs stay unique across files.
                buffer = io.BytesIO()
                ox.serialize(ox.parse(path=str(path), format=ox.RdfFormat.TURTLE), buffer,
                             ox.RdfFormat.N_TRIPLES)
                out.write(gzip.compress(buffer.getvalue()))
            else:
                with path.open("rb") as src:
                    shutil.copyfileobj(src, out, 1 << 20)
    partial.replace(target)
    print(f"export: {target} ({target.stat().st_size / 1e6:.0f} MB)")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the full graph for QLever.")
    parser.add_argument("--out", type=Path, default=QLEVER_DIR, help="QLever folder (holds the Qleverfile)")
    args = parser.parse_args(argv)
    export(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
