import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from jpfs import Result, parse_pdf
from jpfs.cli import main
from jpfs.evaluation.gold import load_gold
from jpfs.evaluation.metrics import score
from jpfs.layout import PageContent, Word
from jpfs.model import Amount, PageState, Rounding, RoundingBasis, Table
from jpfs.pipeline import page_failure
from jpfs.verdict import verify

DATA = Path(__file__).parents[1] / "data"
PDF = DATA / "balance_sheet_p4.pdf"
GOLD = DATA / "balance_sheet_p4.gold.tsv"


@pytest.fixture(scope="module")
def sample() -> Result:
    (result,) = parse_pdf(PDF)
    return result


@pytest.fixture(scope="module")
def gold() -> Table:
    return load_gold(GOLD)


def test_sample_page_is_exact_and_verified(sample: Result, gold: Table) -> None:
    assert score(sample.table, gold)["page_exact"]
    assert sample.state is PageState.VERIFIED
    assert sample.verification.rounding is Rounding.TRUNCATE
    assert sample.verification.rounding_basis is RoundingBasis.INFERRED


def test_correction_underlines_are_found(sample: Result) -> None:
    corrected = {
        (row.label, sample.table.periods[p].label)
        for row in sample.table.rows
        for p, cell in enumerate(row.cells)
        if cell is not None and cell.corrected
    }
    assert corrected == {("投資有価証券", "当連結会計年度"), ("関係会社株式", "当連結会計年度")}


def test_a_misread_digit_sends_the_page_to_review(sample: Result) -> None:
    cash = sample.table.rows[2]
    misread = replace(cash.cells[1], amount=Amount(608_291))  # printed 608,281
    rows = list(sample.table.rows)
    rows[2] = replace(cash, cells=(cash.cells[0], misread))
    verification = verify(
        replace(sample.table, rows=tuple(rows)), Rounding.TRUNCATE, RoundingBasis.INFERRED
    )
    assert verification.state is PageState.NEEDS_REVIEW
    assert any("sum:流動資産合計" in reason for reason in verification.reasons)


def test_a_table_without_its_statement_title_is_not_accepted(sample: Result) -> None:
    header = replace(sample.table.header, title=None, kind=None, consolidated=None)
    verification = verify(
        replace(sample.table, header=header), Rounding.TRUNCATE, RoundingBasis.INFERRED
    )
    assert verification.state is PageState.NEEDS_REVIEW
    assert any("no statement title" in reason for reason in verification.reasons)


def test_a_decimal_without_its_own_unit_is_reviewed(sample: Result) -> None:
    cash = sample.table.rows[2]
    decimal = replace(cash.cells[1], amount=Amount(Decimal("12.34")), text="12.34")
    rows = list(sample.table.rows)
    rows[2] = replace(cash, cells=(cash.cells[0], decimal))
    verification = verify(
        replace(sample.table, rows=tuple(rows)), Rounding.TRUNCATE, RoundingBasis.INFERRED
    )
    assert verification.state is PageState.NEEDS_REVIEW
    assert any("its own unit is not printed" in reason for reason in verification.reasons)


def test_a_table_without_any_value_fails(sample: Result) -> None:
    rows = tuple(replace(row, cells=()) for row in sample.table.rows)
    empty = replace(sample.table, periods=(), rows=rows)
    assert verify(empty, Rounding.TRUNCATE, RoundingBasis.INFERRED).state is PageState.FAILED


def test_statement_pages_without_a_table_fail_explicitly() -> None:
    def page(word: str, text: str = "") -> PageContent:
        return PageContent((Word(word, 60, 40, 60 + 9 * len(word), 49),), (), 600.0, text)

    assert "連結貸借対照表" in page_failure(page("（１）連結貸借対照表"), [], [])
    assert page_failure(PageContent((), (), 600.0, ""), [], []) is not None
    assert page_failure(page("経営成績", "(cid:3)"), [], ["unmapped glyphs (cid)"]) is not None
    assert page_failure(page("経営成績"), [], []) is None  # prose, not a statement


def test_evaluate_reports_accuracy_verifier_strength_and_baseline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["evaluate", str(PDF), str(GOLD)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["accuracy"]["page_exact"]
    assert report["verification"]["exact_equality_would_fail"] == "13/20"
    strength = report["mutation_detection"]["truncate"]
    assert strength["tens digit or above"]["rate"] == strength["lost △"]["rate"] == 1.0
    assert strength["units digit"]["rate"] < 1.0  # hides inside the rounding interval
    assert strength["adjacent rows swapped"]["rate"] < 1.0  # sums are order-blind
    assert report["baselines"]["pdfplumber, ruling lines"]["rows_reproduced"] == "43/43"


def test_cli_writes_facts_table_and_record(tmp_path: Path) -> None:
    assert main(["parse", str(PDF), "-o", str(tmp_path)]) == 0
    out = tmp_path / PDF.stem
    facts = [json.loads(line) for line in (out / "p1-1.facts.jsonl").read_text().splitlines()]
    assert len(facts) == 74
    assert {fact["verification"]["state"] for fact in facts} == {"verified"}
    assert "| **　資産合計** | 7,534,110 | 5,135,249 |" in (out / "p1-1.md").read_text()
    assert json.loads((out / "p1-1.json").read_text())["state"] == "verified"
