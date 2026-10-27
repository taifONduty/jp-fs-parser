import hashlib
import json
from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from jpfs.evaluation.compare import load, row, tables
from jpfs.evaluation.corpus import CORPUS, expected, prf, score_page, source_pdf, typed
from jpfs.model import Amount, Cell, Header, Period, Row, Table
from jpfs.pipeline import Result, Source


def test_gold_decoder_keeps_decimal_nil_and_signed_zero_distinct() -> None:
    assert typed("1,212.88") == ("amount", Decimal("1212.88"), False)
    assert len({typed("－"), typed("0"), typed("△0")}) == 3
    assert typed("(123)") == typed("△123")


def test_duplicate_predictions_count_against_precision() -> None:
    metric = prf(Counter({"cash": 3}), Counter({"cash": 2}))
    assert (metric["matched"], metric["precision"], metric["recall"]) == (2, 0.6667, 1.0)


def test_changed_source_is_rejected_without_overwriting_it(tmp_path: Path) -> None:
    pdf = tmp_path / "issuer.pdf"
    original = b"original filing"
    pdf.write_bytes(original)
    source = {"id": "issuer", "sha256": hashlib.sha256(original).hexdigest()}
    assert source_pdf(source, tmp_path, download=False) == pdf
    pdf.write_bytes(b"changed filing")
    with pytest.raises(ValueError, match="hash differs"):
        source_pdf(source, tmp_path, download=True)
    assert pdf.read_bytes() == b"changed filing"


def test_download_is_hash_checked_before_a_file_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("jpfs.evaluation.corpus.subprocess.check_output", lambda _: b"wrong PDF")
    source = {"id": "issuer", "url": "https://example.invalid/filing.pdf", "sha256": "different"}
    with pytest.raises(ValueError, match="downloaded PDF hash differs"):
        source_pdf(source, tmp_path, download=True)
    assert not (tmp_path / "issuer.pdf").exists()


def test_scoring_checks_units_duration_paths_and_column_dimensions(tmp_path: Path) -> None:
    (tmp_path / "gold.tsv").write_text("資産/現金\t百万円\t100\n")
    spec = {
        "gold": "gold.tsv",
        "title": "連結貸借対照表",
        "consolidated": True,
        "correction": None,
        "unit": "百万円",
        "columns": [{"label": "当期", "start": None, "end": "2025-03-31", "dimension": None}],
    }
    case = {
        "id": "test",
        "source": "test",
        "page": 1,
        "complexity": "simple",
        "features": [],
        "tables": [spec],
    }
    box = (0, 0, 0, 0)
    row = Row("現金", box, (Cell(Amount(100), "100", box),), path=("資産", "現金"))
    table = Table(
        Header("連結貸借対照表", None, True, None, "百万円"),
        (Period("当期", date(2025, 3, 31)),),
        (row,),
    )
    result = Result(Source("unused.pdf", "unused", 1), table)
    assert score_page(case, [result], tmp_path)["page_exact"]
    for altered in [
        replace(table, header=replace(table.header, unit="円")),
        replace(table, periods=(replace(table.periods[0], start=date(2024, 4, 1)),)),
        replace(table, rows=(replace(row, path=("現金",)),)),
    ]:
        assert score_page(case, [replace(result, table=altered)], tmp_path)["facts"]["matched"] == 0
    spec["columns"][0]["dimension"] = "資本金"
    assert score_page(case, [result], tmp_path)["facts"]["matched"] == 0


@pytest.mark.parametrize(
    ("directory", "expected_facts"),
    [
        (CORPUS, 592),
        (CORPUS.parent / "benchmark-expansion", 741),
        (CORPUS.parent / "benchmark-holdout", 618),
        (CORPUS.parent / "benchmark-holdout-2", 814),
    ],
)
def test_frozen_annotations_load_and_missing_pages_score_zero(
    directory: Path, expected_facts: int
) -> None:
    manifest = json.loads((directory / "manifest.json").read_text())
    total = 0
    for case in manifest["cases"]:
        for spec in case["tables"]:
            rows, facts = expected(spec, directory)
            assert rows and facts
            total += facts.total()
        missing = score_page(case, [], directory)
        assert missing["facts"]["recall"] == 0
        assert not missing["autoaccepted_page"] and not missing["page_exact"]
    assert total == expected_facts


def test_engine_comparison_pools_corpora_from_their_counts(tmp_path: Path) -> None:
    def report(matched: int, gold: int, accepted: int, wrong_pages: int) -> dict:
        def metric(m: int, p: int) -> dict:
            return {"matched": m, "predicted": p, "gold": gold}

        return {
            "summary": {
                "facts": metric(matched, gold),
                "flat_facts": metric(gold, gold),
                "rows": {"matched": 1, "predicted": 1, "gold": 1},
                "autoaccepted_facts": metric(accepted - 1, accepted),
                "pages": 2,
                "page_exact": 1,
                "headers_correct": 2,
                "autoaccepted_pages": 1,
                "wrong_autoaccepted_pages": wrong_pages,
            }
        }

    (tmp_path / "geometry").mkdir()
    reports = {"holdout-2": report(90, 100, 10, 1), "holdout": report(20, 20, 5, 0)}
    for corpus, data in reports.items():
        (tmp_path / "geometry" / f"{corpus}.json").write_text(json.dumps(data))
    assert row("geometry", [load(tmp_path, "geometry", c) for c in reports]) == (
        "| geometry | 91.67% | 100.00% | 100.00% | 2/4 | 4/4 | 2 | 1 | 2 of 15 |"
    )
    assert "### all corpora" not in tables(tmp_path)
