"""Lexical cues of Japanese statements: amounts, dates, units, titles, rounding notes."""

import re
import unicodedata
from datetime import date

from jpfs.model import UNIT_SCALES, Amount, Correction, Period, Rounding, StatementKind


def normalize(text: str) -> str:
    """NFKC without whitespace: folds full-width forms, Kangxi radicals and 均等割付 spacing."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


NIL_MARKS = frozenset("-‐–—―−ー")  # '－' and 'ｰ' fold into this set under NFKC
_DIGITS = r"\d{1,3}(?:,\d{3})+|\d+"
_SIGNED_RE = re.compile(rf"(?P<sign>[△▲\-−])?(?P<digits>{_DIGITS})")
_BRACKETED_RE = re.compile(rf"\((?P<digits>{_DIGITS})\)")


def parse_amount(text: str) -> Amount | None:
    """Typed amount for a value-cell token, or None if the token is not an amount."""
    t = normalize(text)
    if t in NIL_MARKS:
        return Amount(0, nil=True)
    if m := _SIGNED_RE.fullmatch(t):
        return Amount(int(m["digits"].replace(",", "")), negative=m["sign"] is not None)
    if m := _BRACKETED_RE.fullmatch(t):
        return Amount(int(m["digits"].replace(",", "")), negative=True)
    return None


_DATE_RE = re.compile(
    r"(?:(?P<era>令和|平成|昭和)(?P<era_year>\d{1,2}|元)|(?P<year>\d{4}))"
    r"年(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
)
_ERA_OFFSET = {"令和": 2018, "平成": 1988, "昭和": 1925}


def parse_dates(text: str) -> list[date]:
    """Gregorian and 和暦 dates in order of appearance."""
    dates = []
    for m in _DATE_RE.finditer(normalize(text)):
        if m["era"]:
            year = _ERA_OFFSET[m["era"]] + (1 if m["era_year"] == "元" else int(m["era_year"]))
        else:
            year = int(m["year"])
        dates.append(date(year, int(m["month"]), int(m["day"])))
    return dates


_PERIOD_RE = re.compile(
    r"[前当][^()]*(?:年度末?|期間末?|期末|期)"
)  # the longest phrase before its date


def parse_period(header: str) -> Period | None:
    """Period from a column header such as 当連結会計年度(2026年3月31日) or (自…至…).

    None when the header names no period, e.g. a 注記 column. The label is the period phrase
    itself, so stray header words such as 注記 do not become part of it.
    """
    t = normalize(header)
    phrase = _PERIOD_RE.search(t)
    if not (phrase or _DATE_RE.search(t)):
        return None
    dates = parse_dates(t)
    label = phrase[0] if phrase else re.sub(r"[()自至~〜]", "", _DATE_RE.sub("", t))
    if len(dates) > 1:
        return Period(label, end=dates[-1], start=dates[0])
    return Period(label, end=dates[0] if dates else None)


_UNIT_RE = re.compile("単位:?(" + "|".join(sorted(UNIT_SCALES, key=len, reverse=True)) + ")")


def find_unit(text: str) -> str | None:
    m = _UNIT_RE.search(normalize(text))
    return m[1] if m else None


_STATEMENTS = {  # longest names first, so combined titles win
    "損益及び包括利益計算書": StatementKind.INCOME_STATEMENT,
    "キャッシュ・フロー計算書": StatementKind.CASH_FLOWS,
    "株主資本等変動計算書": StatementKind.CHANGES_IN_EQUITY,
    "包括利益計算書": StatementKind.COMPREHENSIVE_INCOME,
    "財政状態計算書": StatementKind.BALANCE_SHEET,
    "持分変動計算書": StatementKind.CHANGES_IN_EQUITY,
    "貸借対照表": StatementKind.BALANCE_SHEET,
    "損益計算書": StatementKind.INCOME_STATEMENT,
}
_TITLE_RE = re.compile(
    r"(?:要約)?(?:中間|四半期)?(?:連結)?(?P<name>" + "|".join(map(re.escape, _STATEMENTS)) + ")"
)


def find_title(line: str) -> tuple[str, StatementKind] | None:
    """Statement title in a heading line; notes headings such as （連結貸借対照表関係） are not."""
    t = normalize(line)
    m = _TITLE_RE.search(t)
    if m is None or "関係" in t:
        return None
    return m[0], _STATEMENTS[m["name"]]


def find_correction(text: str) -> Correction | None:
    """The 訂正前 / 訂正後 marker closest to the end of the text, i.e. nearest above a table."""
    t = normalize(text)
    after, before = t.rfind("訂正後"), t.rfind("訂正前")
    if after == before:
        return None
    return Correction.AFTER if after > before else Correction.BEFORE


def declared_rounding(text: str) -> Rounding | None:
    """Rounding stated in the filing, e.g. （百万円未満切捨て）; None if absent or mixed."""
    t = normalize(text)
    truncate = re.search(r"未満を?切り?捨", t) is not None
    round_ = "四捨五入" in t
    if truncate == round_:
        return None
    return Rounding.TRUNCATE if truncate else Rounding.ROUND


NOTE_RE = re.compile(r"※\d*|[*＊]\d+")  # footnote markers next to labels or amounts


def audit_text_layer(text: str) -> tuple[list[str], list[str]]:
    """Text-layer problems as (untrusted, warnings): untrusted means route to the vision path."""
    untrusted, warnings = [], []
    if "(cid:" in text:
        untrusted.append("glyphs without a Unicode mapping (cid)")
    if "\ufffd" in text:
        untrusted.append("replacement characters in the text layer")
    if any("\ue000" <= ch <= "\uf8ff" for ch in text):
        untrusted.append("private-use code points in the text layer")
    if any("\u2e80" <= ch <= "\u2fdf" for ch in text):
        warnings.append("look-alike radical code points (normalised by NFKC)")
    return untrusted, warnings
