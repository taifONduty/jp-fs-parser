"""Document pipeline: ingest (S0), triage (S1), geometry extraction (S3a), cross-page assembly (S4)
and verification (S6)."""

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pdfplumber

from jpfs.assembly import carry_over
from jpfs.checks import infer_rounding
from jpfs.layout import PageContent, extract_tables, read_page, statement_titles
from jpfs.model import PageState, Rounding, RoundingBasis, Table
from jpfs.text import audit_text_layer, declared_rounding
from jpfs.verdict import Verification, verify


@dataclass(frozen=True, slots=True)
class Source:
    path: str
    sha256: str
    page: int  # 1-based


@dataclass(frozen=True, slots=True)
class Result:
    """One statement table, or one statement page that could not be read."""

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
    failures: list[Result] = []
    found: list[tuple[Source, Table, list[str], list[str]]] = []
    with pdfplumber.open(path) as pdf:
        numbers = sorted(pages) if pages else range(1, len(pdf.pages) + 1)
        if invalid := [n for n in numbers if not 1 <= n <= len(pdf.pages)]:
            raise ValueError(f"pages {invalid} outside 1..{len(pdf.pages)}")
        document_text = "".join(char["text"] for page in pdf.pages for char in page.chars)

        @cache
        def content_of(number: int) -> PageContent:
            return read_page(pdf.pages[number - 1])

        @cache
        def tables_on(number: int) -> tuple[Table, ...]:
            return tuple(extract_tables(content_of(number)))

        for number in numbers:
            source = Source(str(path), digest, number)
            content = content_of(number)
            untrusted, warnings = audit_text_layer(content.text)
            tables = carry_over(tables_on(number), number, tables_on)
            if failure := page_failure(content, tables, untrusted):
                failures.append(Result(source, failure=failure))
            found += [(source, table, untrusted, warnings) for table in tables]

    rounding, basis = _document_rounding(document_text, [table for _, table, _, _ in found])
    verified = [
        Result(source, table, verify(table, rounding, basis, untrusted, warnings))
        for source, table, untrusted, warnings in found
    ]
    return sorted([*failures, *verified], key=lambda result: result.source.page)


def page_failure(
    content: PageContent, tables: Sequence[Table], untrusted: Sequence[str]
) -> str | None:
    """Why a page that should hold a statement yielded no table; None for other pages."""
    if tables:
        return None
    if not content.words:
        return "no text layer: needs the vision path"
    if titles := statement_titles(content):
        return f"{', '.join(titles)} on the page but no value columns found"
    if untrusted:
        return f"no table found and the text layer is untrusted: {'; '.join(untrusted)}"
    return None


def _document_rounding(text: str, tables: Sequence[Table]) -> tuple[Rounding, RoundingBasis]:
    """The filing's own note (千円未満切捨て) wins; otherwise a sign test over all its tables."""
    if (declared := declared_rounding(text)) is not None:
        return declared, RoundingBasis.DECLARED
    if infer_rounding(tables) is Rounding.TRUNCATE:
        return Rounding.TRUNCATE, RoundingBasis.INFERRED
    return Rounding.UNKNOWN, RoundingBasis.UNDETERMINED
