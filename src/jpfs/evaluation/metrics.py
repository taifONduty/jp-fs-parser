"""Fact-level accuracy: a table is correct when its facts are, not when its grid looks right.

A fact is (row path, period, typed amount). The path, not the label, is the row's identity:
the sample page alone has four rows labelled その他 and four labelled 減価償却累計額.
"""

from collections.abc import Hashable

from jpfs.model import Table


def score(predicted: Table, gold: Table) -> dict:
    header_correct = _header(predicted) == _header(gold)
    rows = _prf({row.path for row in predicted.rows}, {row.path for row in gold.rows})
    facts = _prf(_facts(predicted), _facts(gold))
    return {
        "header_correct": header_correct,
        "rows": rows,
        "facts": facts,
        "page_exact": header_correct and rows["f1"] == facts["f1"] == 1.0,
    }


def _header(table: Table) -> tuple:
    h = table.header
    periods = tuple((p.label, p.start, p.end) for p in table.periods)
    return h.title, h.consolidated, h.correction, h.unit, periods


def _facts(table: Table) -> set[tuple]:
    return {
        (row.path, table.periods[p].end or table.periods[p].label, cell.amount)
        for row in table.rows
        for p, cell in enumerate(row.cells)
        if cell is not None
    }


def _prf(predicted: set[Hashable], gold: set[Hashable]) -> dict:
    matched = len(predicted & gold)
    precision = matched / len(predicted) if predicted else 0.0
    recall = matched / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matched": matched,
        "predicted": len(predicted),
        "gold": len(gold),
    }
