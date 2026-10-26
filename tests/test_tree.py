from jpfs.checks import derive_constraints, evaluate
from jpfs.model import Cell, Header, Period, Role, Rounding, Row, Table
from jpfs.structure import build_structure
from jpfs.text import parse_amount


def _table(*specs: tuple, ruled: frozenset[str] = frozenset()) -> Table:
    """Rows as (level, label, printed value or None); labels in `ruled` have a rule above."""
    rows = [
        Row(
            label,
            (0.0, 0.0, 0.0, 0.0),
            (None if value is None else Cell(parse_amount(value), value, (0, 0, 0, 0)),),
            level=level,
            rule_above=label in ruled,
        )
        for level, label, value in specs
    ]
    linked, warnings = build_structure(rows)
    header = Header("連結貸借対照表", None, True, None, "千円", 1000)
    return Table(header, (Period("当期", None),), linked, warnings=warnings)


def _constraints(table: Table) -> dict[str, list[str]]:
    return {c.name: [table.rows[t].label for t in c.terms] for c in derive_constraints(table.rows)}


def test_tree_roles_paths_and_constraints() -> None:
    table = _table(
        (0, "資産の部", None),
        (1, "流動資産", None),
        (2, "現金及び預金", "100"),
        (2, "その他", "21"),
        (2, "貸倒引当金", "△0"),
        (2, "流動資産合計", "121"),
        (1, "有形固定資産", None),
        (2, "建物", "50"),
        (3, "減価償却累計額", "△30"),
        (3, "建物（純額）", "19"),
        (2, "その他", "5"),
        (2, "有形固定資産合計", "25"),
        (1, "資産合計", "146"),
    )
    roles = {row.label: row.role for row in table.rows}
    assert roles["資産の部"] is Role.SECTION
    assert roles["建物"] is Role.GROSS
    assert roles["減価償却累計額"] is Role.CONTRA
    assert roles["建物（純額）"] is Role.NET
    assert roles["資産合計"] is Role.TOTAL
    assert table.rows[3].path == ("資産の部", "流動資産", "その他")
    assert table.rows[10].path == ("資産の部", "有形固定資産", "その他")

    assert _constraints(table) == {
        "sum:流動資産合計": ["現金及び預金", "その他", "貸倒引当金"],
        "net:建物(純額)": ["建物", "減価償却累計額"],
        "sum:有形固定資産合計": ["建物（純額）", "その他"],
        "sum:資産合計": ["流動資産合計", "有形固定資産合計"],
    }
    assert all(
        check.passed for check in evaluate(table, derive_constraints(table.rows), Rounding.TRUNCATE)
    )
    assert not table.warnings


def test_subtotal_chains_and_ruled_closing_row() -> None:
    table = _table(
        (0, "営業活動によるキャッシュ・フロー", None),
        (1, "税金等調整前当期純利益", "100"),
        (1, "減価償却費", "20"),
        (1, "小計", "120"),
        (1, "法人税等の支払額", "△30"),
        (1, "営業活動によるキャッシュ・フロー", "90"),
        ruled=frozenset({"営業活動によるキャッシュ・フロー"}),
    )
    assert table.rows[-1].role is Role.TOTAL
    assert _constraints(table) == {
        "sum:小計": ["税金等調整前当期純利益", "減価償却費"],
        "sum:営業活動によるキャッシュ・フロー": ["小計", "法人税等の支払額"],
    }


def test_unclosed_group_is_flagged_and_blocks_its_parent() -> None:
    table = _table(
        (0, "資産の部", None),
        (1, "流動資産", None),
        (2, "現金及び預金", "100"),
        (1, "固定資産", None),
        (2, "土地", "50"),
        (2, "固定資産合計", "50"),
        (1, "資産合計", "150"),
    )
    assert table.warnings == ("group '流動資産' has no closing total on this page",)
    assert _constraints(table) == {"sum:固定資産合計": ["土地"]}


def test_net_line_without_its_gross_is_an_ordinary_member() -> None:
    table = _table(
        (0, "有形固定資産", None),
        (1, "建物（純額）", "20"),
        (1, "土地", "5"),
        (1, "有形固定資産合計", "25"),
    )
    assert table.rows[1].role is Role.ITEM
    assert _constraints(table) == {"sum:有形固定資産合計": ["建物（純額）", "土地"]}
