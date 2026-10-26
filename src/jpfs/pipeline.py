"""Document pipeline: ingest (S0), triage (S1), geometry extraction (S3a) and verification (S6)."""

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from jpfs.checks import derive_constraints, evaluate, infer_rounding
from jpfs.layout import extract_tables, read_page
from jpfs.model import PageState, Rounding, Table
from jpfs.text import audit_text_layer, declared_rounding
from jpfs.verdict import Verification, verify


@dataclass(frozen=True, slots=True)
class Source:
    path: str
    sha256: str
    page: int  # 1-based


@dataclass(frozen=True, slots=True)
class Result:
    """One statement table, or one page that could not be read."""

    source: Source
    table: Table | None = None
    verification: Verification | None = None
    failure: str | None = None

    @property
    def state(self) -> PageState:
        return self.verification.state if self.verification else PageState.FAILED

    @property
    def reasons(self) -> tuple[str, ...]:
        if self.verification:
            return self.verification.reasons
        return (self.failure,) if self.failure else ()


def parse_pdf(path: str | Path, pages: Collection[int] | None = None) -> list[Result]:
    """Every statement table on the selected 1-based pages (default: all), verified."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pdfplumber.open(path) as pdf:
        numbers = sorted(pages) if pages else range(1, len(pdf.pages) + 1)
        if invalid := [n for n in numbers if not 1 <= n <= len(pdf.pages)]:
            raise ValueError(f"pages {invalid} outside 1..{len(pdf.pages)}")
        contents = {n: read_page(pdf.pages[n - 1]) for n in numbers}
        document_text = "".join(char["text"] for page in pdf.pages for char in page.chars)

    failures: list[Result] = []
    found: list[tuple[Source, Table, list[str], list[str]]] = []
    for number, content in contents.items():
        page_source = Source(str(path), digest, number)
        if not content.words:
            failures.append(Result(page_source, failure="no text layer: needs the vision path"))
            continue
        untrusted, warnings = audit_text_layer(content.text)
        found += [(page_source, t, untrusted, warnings) for t in extract_tables(content)]

    rounding, basis = _document_rounding(document_text, [table for _, table, _, _ in found])
    verified = [
        Result(page_source, table, verify(table, rounding, basis, untrusted, warnings))
        for page_source, table, untrusted, warnings in found
    ]
    return sorted([*failures, *verified], key=lambda result: result.source.page)


def _document_rounding(text: str, tables: Sequence[Table]) -> tuple[Rounding, str]:
    """The filing's own note (千円未満切捨て) wins; otherwise a sign test over all its tables."""
    if (declared := declared_rounding(text)) is not None:
        return declared, "declared"
    checks = [
        check
        for table in tables
        for check in evaluate(table, derive_constraints(table.rows), Rounding.TRUNCATE)
    ]
    inferred = infer_rounding(checks)
    return inferred, "inferred" if inferred is Rounding.TRUNCATE else "undetermined"
