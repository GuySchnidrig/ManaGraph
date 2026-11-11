"""Validate the graph against the SHACL shapes in ``shapes/``, with rudof.

Validates the ontology plus every file in ``data/rdf/`` (inferred triples
included) and writes a standard SHACL validation report to
``data/reports/shacl.ttl``. Prints a summary per shape and severity.

rudof keeps the whole graph in memory: about 9 GB peak for the full data.
It can't read gzip, so the data is decompressed to a temporary folder first.

By default problems are only reported. With ``strict``, any result of
severity sh:Violation fails the run; sh:Warning never does.

Usage::

    uv run python -m managraph.validate            # report only
    uv run python -m managraph.validate --strict   # exit 1 on violations
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pyrudof

from managraph import convert, download, load

SHAPES_DIR = download.PROJECT_ROOT / "shapes"
REPORT_DIR = download.PROJECT_ROOT / "data" / "reports"
SHAPES_NS = "https://w3id.org/managraph/shapes#"


@dataclass(frozen=True)
class Result:
    severity: str  # "Violation", "Warning" or "Info"
    shape: str
    component: str
    focus: str
    path: str | None
    value: str | None
    message: str


@dataclass
class Report:
    conforms: bool
    results: list[Result]
    path: Path | None = None

    def count(self, severity: str) -> int:
        return sum(r.severity == severity for r in self.results)


def _shape_name(source: str, focus: str) -> str:
    """Readable name of the shape behind a result.

    Property shapes are blank nodes, so rudof reports a node ID; fall back
    to the focus node's kind (card, face, printing, ...).
    """
    if source.startswith(SHAPES_NS):
        return source.removeprefix(SHAPES_NS)
    if "/face/" in focus:
        return "Face"
    return focus.removeprefix("https://w3id.org/managraph/").split("/")[0].capitalize()


def validate(
    files: list[Path] | None = None,
    shapes_dir: Path = SHAPES_DIR,
    report_dir: Path | None = REPORT_DIR,
) -> Report:
    """Validate ``files`` (default: the full graph) against every shapes file in ``shapes_dir``."""
    files = load.rdf_files() if files is None else files
    rudof = pyrudof.Rudof(pyrudof.RudofConfig())

    with tempfile.TemporaryDirectory(prefix="managraph-validate-") as tmp:
        for path in files:
            if path.suffix == ".gz":
                plain = Path(tmp) / path.stem
                with gzip.open(path, "rb") as src, plain.open("wb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
                rudof.read_data(str(plain), format=pyrudof.RDFFormat.NTriples, merge=True)
                plain.unlink()
            else:
                rudof.read_data(str(path), format=pyrudof.RDFFormat.Turtle, merge=True)

    # rudof replaces the shapes on each read, so pass all files as one
    # document. Concatenated Turtle files are still valid Turtle.
    shapes = "\n".join(p.read_text(encoding="utf-8") for p in sorted(shapes_dir.glob("*.ttl")))
    rudof.read_shacl(shapes, format=pyrudof.ShaclFormat.Turtle)

    raw = rudof.validate_shacl(mode=pyrudof.ShaclValidationMode.Native)
    results = [
        Result(
            severity=str(entry.severity),
            shape=_shape_name(str(entry.source_shape), str(entry.focus_node)),
            component=str(entry.constraint_component).rsplit("#", 1)[-1].removesuffix("ConstraintComponent"),
            focus=str(entry.focus_node),
            path=entry.path,
            value=entry.value,
            message=str(entry.message).strip('"'),
        )
        for entry in raw.violations
    ]
    report = Report(conforms=raw.conforms, results=results)

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        report.path = report_dir / "shacl.ttl"
        turtle = rudof.serialize_shacl_validation_results(format=pyrudof.ResultShaclValidationFormat.Turtle)
        report.path.write_text(turtle, encoding="utf-8")
    return report


def summarize(report: Report, examples: int = 3) -> str:
    lines = [
        f"validate: {'conforms' if report.conforms else 'does not conform'}: "
        f"{report.count('Violation')} violation(s), {report.count('Warning')} warning(s)"
    ]
    groups = Counter((r.severity, r.shape, r.component, r.path) for r in report.results)
    for (severity, shape, component, path), n in sorted(groups.items(), key=lambda g: (g[0][0], -g[1])):
        where = f" {path.rsplit('#', 1)[-1]}" if path else ""
        lines.append(f"  {severity:9s} {n:6d}  {shape}{where} [{component}]")
        matching = [r for r in report.results if (r.severity, r.shape, r.component, r.path) == (severity, shape, component, path)]
        for r in matching[:examples]:
            lines.append(f"      {r.focus}: {r.message}")
    if report.path:
        lines.append(f"validate: report written to {report.path}")
    return "\n".join(lines)


def run(strict: bool = False) -> Report:
    """Validate the full graph and print a summary; raise if ``strict`` and there are violations."""
    report = validate()
    print(summarize(report))
    if strict and report.count("Violation"):
        raise SystemExit(f"validate: {report.count('Violation')} SHACL violation(s)")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the graph against the SHACL shapes.")
    parser.add_argument("--strict", action="store_true", help="exit with an error on sh:Violation results")
    args = parser.parse_args(argv)
    try:
        run(args.strict)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
