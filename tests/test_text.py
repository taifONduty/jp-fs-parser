from datetime import date
from decimal import Decimal

import pytest

from jpfs.model import Amount, Period, Rounding, StatementKind
from jpfs.text import (
    NOTE_RE,
    audit_text_layer,
    declared_rounding,
    find_title,
    find_unit,
    label_defect,
    normalize,
    note_markers,
    parse_amount,
    parse_period,
)


@pytest.mark.parametrize(
    ("printed", "amount"),
    [
        ("2,002,429", Amount(2002429)),
        ("1,212.88", Amount(Decimal("1212.88"))),
        ("△2,979", Amount(2979, negative=True)),
        ("△0", Amount(0, negative=True)),
        ("▲5", Amount(5, negative=True)),
        ("(1,234)", Amount(1234, negative=True)),
        ("１，２３４", Amount(1234)),
        ("－", Amount(0, nil=True)),
        ("―", Amount(0, nil=True)),
        ("※1", None),
        ("1,23", None),
        ("(2025", None),
    ],
)
def test_parse_amount(printed: str, amount: Amount | None) -> None:
    assert parse_amount(printed) == amount


def test_nil_and_negative_zero_are_distinct_facts() -> None:
    nil, negative_zero = parse_amount("－"), parse_amount("△0")
    assert nil != negative_zero
    assert nil.value == negative_zero.value == 0


@pytest.mark.parametrize(
    ("header", "period"),
    [
        ("当連結会計年度(2026年３月31日)", Period("当連結会計年度", date(2026, 3, 31))),
        (
            "前中間連結会計期間（自 令和6年4月1日 至 令和6年9月30日）",
            Period("前中間連結会計期間", date(2024, 9, 30), start=date(2024, 4, 1)),
        ),
        (
            "当第１四半期連結会計期間末(2025年３月31日)",
            Period("当第1四半期連結会計期間末", date(2025, 3, 31)),
        ),
        (
            "前第１四半期連結累計期間(自 2024年１月１日 至 2024年３月31日)",
            Period("前第1四半期連結累計期間", date(2024, 3, 31), start=date(2024, 1, 1)),
        ),
        ("前期", Period("前期", None)),
        ("注記", None),
    ],
)
def test_parse_period(header: str, period: Period | None) -> None:
    assert parse_period(header) == period


def test_find_unit() -> None:
    assert find_unit("（単位：百万円）") == "百万円"
    assert find_unit("（単位：千円）") == "千円"
    assert find_unit("連結貸借対照表") is None


@pytest.mark.parametrize(
    ("line", "title"),
    [
        ("（１）連結貸借対照表", ("連結貸借対照表", StatementKind.BALANCE_SHEET)),
        ("中間連結財政状態計算書", ("中間連結財政状態計算書", StatementKind.BALANCE_SHEET)),
        (
            "（１）要約四半期連結財政状態計算書",
            ("要約四半期連結財政状態計算書", StatementKind.BALANCE_SHEET),
        ),
        (
            "連結損益及び包括利益計算書",
            ("連結損益及び包括利益計算書", StatementKind.INCOME_STATEMENT),
        ),
        ("（連結貸借対照表関係）", None),
        ("３．連結財務諸表及び主な注記", None),
    ],
)
def test_find_title(line: str, title: tuple[str, StatementKind] | None) -> None:
    assert find_title(line) == title


@pytest.mark.parametrize(
    ("text", "rounding"),
    [
        ("（百万円未満切捨て）", Rounding.TRUNCATE),
        ("記載金額は、千円未満を切り捨てて表示しております。", Rounding.TRUNCATE),
        ("（百万円未満四捨五入）", Rounding.ROUND),
        ("（百万円未満切捨て）（百万円未満四捨五入）", None),
        ("連結貸借対照表", None),
    ],
)
def test_declared_rounding(text: str, rounding: Rounding | None) -> None:
    assert declared_rounding(text) == rounding


def test_footnote_marker_lists_are_one_note_reference() -> None:
    assert NOTE_RE.fullmatch(normalize("※１,※５"))
    assert note_markers("※１、※４、※５") == ["※1", "※4", "※5"]
    assert NOTE_RE.sub("", "有価証券※１,※５") == "有価証券"
    assert not NOTE_RE.fullmatch("96,241")


@pytest.mark.parametrize(
    ("label", "damaged"),
    [
        ("有価証券,,", True),
        ("現金及び現金同等物7,31", True),
        ("建物（純額", True),
        ("受取手形※", True),
        ("建物及び構築物（純額）", False),
        ("１年内返済予定の長期借入金", False),
        ("親会社の所有者に帰属する１株当たり四半期損失（△）：", False),
    ],
)
def test_label_defects(label: str, damaged: bool) -> None:
    assert (label_defect(label) is not None) is damaged


def test_text_layer_audit() -> None:
    assert audit_text_layer("現金及び預金") == ([], [])
    untrusted, _ = audit_text_layer("(cid:1234)及び預金")
    assert untrusted
    kangxi_gold = "\u2fa6"  # KANGXI RADICAL GOLD, drawn like 金
    _, warnings = audit_text_layer(f"現{kangxi_gold}")
    assert warnings
    assert normalize(f"現{kangxi_gold}") == "現金"
