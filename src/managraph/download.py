"""Download Scryfall bulk data files.

Reads the Scryfall bulk-data index and fetches the requested files into a local
directory. Files are stored as served: gzipped JSON Lines (``<type>.jsonl.gz``),
one Scryfall object per line. A manifest next to the files records each file's ``updated_at`` so
unchanged files are skipped on later runs.

Usage::

    uv run python -m managraph.download                      # oracle_cards
    uv run python -m managraph.download oracle_cards rulings
    uv run python -m managraph.download --list               # show available types
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from managraph import __version__

BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
# Anchored to the repo root (src/managraph/download.py -> ../../), not the working
# directory, so running from a subfolder doesn't create a second data folder.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEST = PROJECT_ROOT / "data" / "raw" / "scryfall"
DEFAULT_TYPES = ("oracle_cards",)
MANIFEST_NAME = "manifest.json"

# Scryfall asks API clients to send a descriptive User-Agent and an Accept header.
HEADERS = {
    "User-Agent": f"managraph/{__version__}",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True)
class BulkFile:
    """One entry of the Scryfall bulk-data index."""

    type: str
    name: str
    updated_at: str
    compressed_size: int
    download_uri: str

    @property
    def filename(self) -> str:
        return f"{self.type}.jsonl.gz"


def _open(url: str, decode: bool = True) -> BinaryIO:
    """Open ``url``; with ``decode``, undo a gzip Content-Encoding from the server."""
    request = urllib.request.Request(url, headers=HEADERS)
    response = urllib.request.urlopen(request, timeout=60)
    if decode and response.headers.get("Content-Encoding") == "gzip":
        return gzip.GzipFile(fileobj=response)
    return response


def fetch_index() -> dict[str, BulkFile]:
    """Return the bulk-data index, keyed by type (e.g. ``oracle_cards``)."""
    with _open(BULK_DATA_URL) as response:
        payload = json.load(response)
    return {
        entry["type"]: BulkFile(
            type=entry["type"],
            name=entry["name"],
            updated_at=entry["updated_at"],
            compressed_size=entry["compressed_size"],
            download_uri=entry["jsonl_download_uri"],
        )
        for entry in payload["data"]
    }


def _read_manifest(dest: Path) -> dict[str, str]:
    path = dest / MANIFEST_NAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(dest: Path, manifest: dict[str, str]) -> None:
    path = dest / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def download(
    types: list[str] | tuple[str, ...] = DEFAULT_TYPES,
    dest: Path = DEFAULT_DEST,
    force: bool = False,
) -> list[Path]:
    """Download the given bulk types into ``dest`` and return their paths.

    Files whose ``updated_at`` matches the manifest are skipped unless ``force``.
    """
    index = fetch_index()
    unknown = [t for t in types if t not in index]
    if unknown:
        raise ValueError(f"Unknown bulk type(s): {', '.join(unknown)}. Available: {', '.join(sorted(index))}")

    dest.mkdir(parents=True, exist_ok=True)
    manifest = _read_manifest(dest)
    paths = []

    for bulk_type in types:
        entry = index[bulk_type]
        target = dest / entry.filename
        paths.append(target)

        if not force and target.exists() and manifest.get(bulk_type) == entry.updated_at:
            print(f"{bulk_type}: up to date ({entry.updated_at})")
            continue

        print(f"{bulk_type}: downloading {entry.compressed_size / 1e6:.0f} MB ...", flush=True)
        partial = target.with_name(target.name + ".part")
        with _open(entry.download_uri, decode=False) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out, length=1 << 20)
        partial.replace(target)

        manifest[bulk_type] = entry.updated_at
        _write_manifest(dest, manifest)
        print(f"{bulk_type}: saved to {target}")

    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Scryfall bulk data files.")
    parser.add_argument("types", nargs="*", default=list(DEFAULT_TYPES), help="bulk types to fetch (default: oracle_cards)")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"output directory (default: {DEFAULT_DEST})")
    parser.add_argument("--force", action="store_true", help="download even if the file is up to date")
    parser.add_argument("--list", action="store_true", help="list available bulk types and exit")
    args = parser.parse_args(argv)

    if args.list:
        for entry in fetch_index().values():
            print(f"{entry.type:<20} {entry.compressed_size / 1e6:>8.0f} MB  updated {entry.updated_at}")
        return 0

    try:
        download(args.types, args.dest, args.force)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
