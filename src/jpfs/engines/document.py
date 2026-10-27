"""Document flow for the Docling engines. Their tables enter the jpfs intermediate representation
and go through the same cross-page assembly, rounding inference and verification as geometry's."""

import hashlib
from collections.abc import Collection
from functools import cache
from pathlib import Path
from typing import Protocol

import pdfplumber

from jpfs.assembly import carry_over
from jpfs.engines.grid import Grid, to_table
from jpfs.model import Table
from jpfs.pipeline import Result, Source, document_rounding
from jpfs.verdict import verify


class Engine(Protocol):
    def grids(self, pdf: str, page: int) -> list[Grid]: ...


def parse_pdf(
    path: str | Path, pages: Collection[int] | None = None, *, engine: Engine
) -> list[Result]:
    """Every statement table the engine finds on the selected 1-based pages (default: all)."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pdfplumber.open(path) as pdf:
        page_texts = ["".join(char["text"] for char in page.chars) for page in pdf.pages]
    numbers = sorted(pages) if pages else range(1, len(page_texts) + 1)
    if invalid := [n for n in numbers if not 1 <= n <= len(page_texts)]:
        raise ValueError(f"pages {invalid} outside 1..{len(page_texts)}")

    @cache
    def tables_on(number: int) -> tuple[Table, ...]:
        grids = engine.grids(str(path), number)
        tables = (to_table(grid, page_texts[number - 1]) for grid in grids)
        return tuple(table for table in tables if table is not None)

    found = [
        (Source(str(path), digest, number), table)
        for number in numbers
        for table in carry_over(tables_on(number), number, tables_on)
    ]
    rounding, basis = document_rounding("".join(page_texts), [table for _, table in found])
    return [Result(source, table, verify(table, rounding, basis)) for source, table in found]
