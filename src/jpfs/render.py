"""Outputs (design S7): canonical facts with provenance, a rendered table, and the full record.

Facts are the product; the rendered table is derived from the same typed rows, never the reverse.
"""

import hashlib
from collections import defaultdict
from dataclasses import asdict
from datetime import date
from importlib.metadata import version

from jpfs.checks import Interval, interval
from jpfs.model import Amount, Cell, Period, Role, Row
from jpfs.pipeline import Result
from jpfs.text import normalize

EXTRACTOR = f"jpfs.layout@{version('jpfs')}"


def to_facts(result: Result) -> list[dict]:
    """One fact per printed cell; a blank cell is not a fact, a '－' is."""
    if result.table is None:
        return []
    vouchers = _vouchers(result)
    return [
        _fact(result, row, result.table.periods[p], cell, vouchers[r, p])
        for r, row in enumerate(result.table.rows)
        for p, cell in enumerate(row.cells)
        if cell is not None
    ]


def _vouchers(result: Result) -> defaultdict[tuple[int, int], list[str]]:
    """Names of the passing constraints that cover each (row, period) cell."""
    vouchers: defaultdict[tuple[int, int], list[str]] = defaultdict(list)
    for check in result.verification.checks if result.verification else ():
        if check.passed:
            for row in (check.constraint.total, *check.constraint.terms):
                vouchers[row, check.period].append(check.constraint.name)
    return vouchers


def _fact(result: Result, row: Row, period: Period, cell: Cell, constraints: list[str]) -> dict:
    """A fact in the schema of the design's Appendix A, less the fields of stages not built yet:
    taxonomy concept, second-path agreement and XBRL match."""
    header = result.table.header
    rounding = result.verification.rounding
    amount, scale = cell.amount, header.scale
    return {
        "fact_id": _fact_id(result, row, period),
        "statement": {
            "type": header.kind,
            "title": header.title,
            "scope": _scope(header.consolidated),
            "correction": header.correction,
        },
        "row": {
            "label_raw": row.label,
            "label_norm": normalize(row.label),
            "path": list(row.path),
            "level": row.level,
            "role": row.role,
        },
        "period": {
            "label": period.label,
            "type": "duration" if period.start else "instant",
            "start": _iso(period.start),
            "end": _iso(period.end),
        },
        "value": {
            "printed": cell.text,
            "reported": amount.value,
            "unit": "JPY" if scale else None,
            "scale": scale,
            "jpy": amount.value * scale if scale else None,
            "interval_jpy": _bounds(interval(amount, rounding).scaled(scale)) if scale else None,
            "sign": None if amount.nil else "-" if amount.negative else "+",
            "state": "nil" if amount.nil else "amount",
            "rounding": rounding,
        },
        "flags": {"corrected": cell.corrected, "footnote_refs": list(row.notes)},
        "provenance": {
            "doc_sha256": result.source.sha256,
            "page": result.source.page,
            "bbox": [round(v, 1) for v in cell.bbox],
            "extractor": EXTRACTOR,
        },
        "verification": {"state": result.state, "constraints_passed": constraints},
    }


def _scope(consolidated: bool | None) -> str | None:
    if consolidated is None:
        return None
    return "consolidated" if consolidated else "non_consolidated"


def _fact_id(result: Result, row: Row, period: Period) -> str:
    source, header = result.source, result.table.header
    statement = f"{header.title}:{header.correction}"
    period_key = f"{period.label}:{_iso(period.start)}:{_iso(period.end)}"
    key = "|".join([source.sha256, str(source.page), statement, "/".join(row.path), period_key])
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _bounds(bounds: Interval) -> dict:
    return {
        "lo": _number(bounds.lo),
        "hi": _number(bounds.hi),
        "lo_closed": bounds.lo_closed,
        "hi_closed": bounds.hi_closed,
    }


def _number(x: float) -> int | float:
    return int(x) if float(x).is_integer() else x


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def to_markdown(result: Result) -> str:
    table, verification = result.table, result.verification
    if table is None or verification is None:
        return f"Page {result.source.page}: {result.state} ({'; '.join(result.reasons)})\n"
    passed = sum(c.passed for c in verification.checks)
    lines = [
        f"## {table.header.title or 'Untitled statement'} ({result.state})",
        "",
        f"Page {result.source.page} · unit {table.header.unit or '?'} · "
        f"rounding {verification.rounding} ({verification.rounding_basis}) · "
        f"{passed}/{len(verification.checks)} checks pass",
        "",
        "| 科目 | " + " | ".join(_period_heading(p) for p in table.periods) + " |",
        "|---|" + "---:|" * len(table.periods),
    ]
    for row in table.rows:
        label = "　" * row.level + row.label
        if row.role is Role.TOTAL:
            label = f"**{label}**"
        lines.append(f"| {label} | " + " | ".join(_cell_text(c) for c in row.cells) + " |")
    if any(cell and cell.corrected for row in table.rows for cell in row.cells):
        lines += ["", "✎ corrected figure (訂正箇所)"]
    if result.reasons:
        lines += ["", *(f"- {reason}" for reason in result.reasons)]
    return "\n".join(lines) + "\n"


def _period_heading(period: Period) -> str:
    dates = " – ".join(_iso(d) for d in (period.start, period.end) if d)
    return f"{period.label}<br>{dates}" if dates else period.label


def _cell_text(cell: Cell | None) -> str:
    if cell is None:
        return ""
    return _format(cell.amount) + (" ✎" if cell.corrected else "")


def _format(amount: Amount) -> str:
    if amount.nil:
        return "－"
    return ("△" if amount.negative else "") + f"{amount.magnitude:,}"


def to_record(result: Result) -> dict:
    """Everything the pipeline knows about one table, for review and debugging."""
    return {"state": result.state, "reasons": list(result.reasons), **asdict(result)}
