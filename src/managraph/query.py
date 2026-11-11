"""Run SPARQL against the local Oxigraph store, to try out queries without QLever.

The store built by ``uv run managraph`` already holds the ontology, the data
and the inferred triples, so results match what the QLever endpoint serves.
The common prefixes (mg:, creature:, format:, ...) are added automatically
when a query doesn't declare them.

Usage::

    uv run python -m managraph.query queries/most-reprinted.rq     # a query file
    uv run python -m managraph.query "SELECT * WHERE { ?s mg:name ?n } LIMIT 5"
    uv run python -m managraph.query                               # interactive

In interactive mode, type a query over one or more lines and end it with an
empty line. ``quit`` or Ctrl+C exits. Close it before rebuilding, since it
keeps the store open.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pyoxigraph as ox

from managraph import docs, iri, load

# docs.PREFIXES plus the instance namespaces, so card and printing IRIs print short.
PREFIXES = {
    **docs.PREFIXES,
    **{p: f"{iri.BASE}{p}/" for p in ("card", "printing", "set", "artist", "illustration")},
}


def with_prefixes(query: str) -> str:
    """Prepend the PREFIX declarations from ``PREFIXES`` that ``query`` lacks."""
    declared = {m.lower() for m in re.findall(r"PREFIX\s+([\w-]*):", query, re.IGNORECASE)}
    missing = [f"PREFIX {p}: <{ns}>" for p, ns in PREFIXES.items() if p not in declared]
    return "\n".join(missing + [query])


def term(value: ox.NamedNode | ox.BlankNode | ox.Literal | ox.Triple | None) -> str:
    """A short display form: IRIs shortened to a known prefix, literals as plain text."""
    if value is None:
        return ""
    if isinstance(value, ox.NamedNode):
        for prefix, ns in PREFIXES.items():
            if value.value.startswith(ns) and value.value != ns:
                return f"{prefix}:{value.value[len(ns):]}"
        return f"<{value.value}>"
    if isinstance(value, ox.BlankNode):
        return f"_:{value.value}"
    if isinstance(value, ox.Literal):
        return value.value
    return str(value)


def table(header: list[str], rows: list[list[str]], max_width: int = 60) -> str:
    """Rows as an aligned text table, cells cut at ``max_width`` characters."""
    rows = [[c if len(c) <= max_width else c[: max_width - 3] + "..." for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(header)]
    line = lambda cells: "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()
    return "\n".join([line(header), line(["-" * w for w in widths]), *map(line, rows)])


def run(store: ox.Store, query: str, limit: int = 50) -> None:
    """Run ``query`` and print its result: a table, a boolean or triples."""
    start = time.perf_counter()
    result = store.query(with_prefixes(query))
    if isinstance(result, ox.QueryBoolean):  # ASK
        print(bool(result))
        rows, total = [], None
    elif isinstance(result, ox.QuerySolutions):  # SELECT
        header = [v.value for v in result.variables]
        rows, total = [], 0
        for solution in result:
            total += 1
            if total <= limit:
                rows.append([term(solution[v]) for v in header])
        print(table(header, rows))
    else:  # CONSTRUCT / DESCRIBE
        rows, total = [], 0
        for triple in result:
            total += 1
            if total <= limit:
                rows.append([term(triple.subject), term(triple.predicate), term(triple.object)])
        print(table(["subject", "predicate", "object"], rows))
    elapsed = time.perf_counter() - start
    if total is not None:
        shown = f", showing {limit}" if total > limit else ""
        print(f"\n{total:,} result(s){shown} in {elapsed:.2f}s")


def repl(store: ox.Store, limit: int) -> None:
    """Read queries from the terminal, each ended by an empty line."""
    print("Type a SPARQL query, end it with an empty line. 'quit' exits.")
    while True:
        lines: list[str] = []
        try:
            while True:
                line = input("... " if lines else "sparql> ")
                if not lines and line.strip().lower() in {"quit", "exit"}:
                    return
                if not line.strip():
                    break
                lines.append(line)
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if lines:
            try:
                run(store, "\n".join(lines), limit)
            except (SyntaxError, OSError, ValueError) as error:
                print(f"error: {error}")
            print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Query the local Oxigraph store with SPARQL.")
    parser.add_argument("query", nargs="?", help="a .rq file or a query string; omit for interactive mode")
    parser.add_argument("--store", type=Path, default=load.DEFAULT_STORE, help="store built by managraph.load")
    parser.add_argument("--limit", type=int, default=50, help="rows to print (default 50)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # card names aren't all ASCII

    if not args.store.exists():
        parser.error(f"no store at {args.store}; run `uv run managraph` first")
    store = ox.Store.read_only(str(args.store))

    if args.query is None:
        repl(store, args.limit)
    else:
        path = Path(args.query)
        query = path.read_text(encoding="utf-8") if path.suffix == ".rq" and path.exists() else args.query
        run(store, query, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
