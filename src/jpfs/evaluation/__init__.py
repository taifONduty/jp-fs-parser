"""Evaluation harness: accuracy against gold, verifier strength, and an off-the-shelf baseline."""

from pathlib import Path

from jpfs.evaluation.baseline import baseline
from jpfs.evaluation.gold import load_gold
from jpfs.evaluation.metrics import score
from jpfs.evaluation.mutation import detection_rates
from jpfs.model import Rounding
from jpfs.pipeline import parse_pdf


def evaluate_page(pdf: Path, gold_path: Path, page: int) -> dict:
    gold = load_gold(gold_path)
    result = next((r for r in parse_pdf(pdf, [page]) if r.table is not None), None)
    if result is None or result.verification is None:
        raise ValueError(f"{pdf}: no statement table on page {page}")
    checks = result.verification.checks
    cells = sum(cell is not None for row in result.table.rows for cell in row.cells)
    return {
        "accuracy": score(result.table, gold),
        "verification": {
            "state": result.state,
            "rounding": f"{result.verification.rounding} ({result.verification.rounding_basis})",
            "checks_passed": f"{sum(c.passed for c in checks)}/{len(checks)}",
            "exact_equality_would_fail": f"{sum(c.residual != 0 for c in checks)}/{len(checks)}",
            "cell_coverage": round(1 - len(result.verification.uncovered) / cells, 3),
            "corrected_cells": [
                f"{row.label} / {result.table.periods[p].label}"
                for row in result.table.rows
                for p, cell in enumerate(row.cells)
                if cell is not None and cell.corrected
            ],
            "reasons": list(result.reasons),
        },
        "mutation_detection": {mode: detection_rates(gold, mode) for mode in Rounding},
        "baselines": baseline(pdf, page, gold),
    }
