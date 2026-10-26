"""Row hierarchy (design S3a/S5): indentation levels to a tree of groups, members and totals."""

import re
from collections.abc import Sequence
from dataclasses import replace

from jpfs.model import Role, Row
from jpfs.text import normalize

_TOTAL_RE = re.compile(r"計$")  # 合計, 小計, 資産計
_NET = "純額"
_CLOSING = (Role.TOTAL, Role.NET)


def build_structure(rows: Sequence[Row]) -> tuple[tuple[Row, ...], tuple[str, ...]]:
    """Link rows into a tree from their levels and assign roles; warn about unclosed groups."""
    parents = _parents(_tree_levels(rows))
    children = [tuple(j for j, p in enumerate(parents) if p == i) for i in range(len(rows))]
    roles = _roles(rows, parents, children)
    paths: list[tuple[str, ...]] = []
    for row, parent in zip(rows, parents, strict=True):
        paths.append((paths[parent] if parent is not None else ()) + (normalize(row.label),))

    linked = tuple(
        replace(row, parent=parents[i], children=children[i], role=roles[i], path=paths[i])
        for i, row in enumerate(rows)
    )
    warnings = tuple(
        f"group '{row.label}' has no closing total on this page"
        for row in linked
        if row.children and linked[row.children[-1]].role not in _CLOSING
    )
    return linked, warnings


def _tree_levels(rows: Sequence[Row]) -> list[int]:
    """Printed levels, except that a total printed right after a total at the same level closes
    the enclosing level: 負債純資産合計 after 純資産合計 sums the whole sheet, not 純資産の部."""
    levels = [row.level for row in rows]
    for i in range(1, len(rows)):
        if rows[i].level == rows[i - 1].level > 0 and _is_total(rows[i]) and _is_total(rows[i - 1]):
            levels[i] -= 1
    return levels


def _is_total(row: Row) -> bool:
    return any(row.cells) and bool(_TOTAL_RE.search(normalize(row.label)))


def _parents(levels: Sequence[int]) -> list[int | None]:
    parents: list[int | None] = []
    stack: list[int] = []
    for i, level in enumerate(levels):
        while stack and levels[stack[-1]] >= level:
            stack.pop()
        parents.append(stack[-1] if stack else None)
        stack.append(i)
    return parents


def _roles(
    rows: Sequence[Row], parents: Sequence[int | None], children: Sequence[tuple[int, ...]]
) -> list[Role]:
    roles = [_own_role(row, bool(kids)) for row, kids in zip(rows, children, strict=True)]
    for i, parent in enumerate(parents):
        under_gross = parent is not None and roles[parent] is Role.GROSS
        closes_by_rule = (
            parent is not None
            and children[parent][-1] == i
            and rows[i].rule_above
            and roles[i] in (Role.ITEM, Role.CONTRA)
        )
        if roles[i] is Role.NET and not under_gross:
            roles[i] = Role.ITEM  # a net line without its gross is an ordinary member
        elif closes_by_rule:
            roles[i] = Role.NET if under_gross else Role.TOTAL
    return roles


def _own_role(row: Row, has_children: bool) -> Role:
    amounts = [cell.amount for cell in row.cells if cell is not None]
    if has_children:
        return Role.GROSS if amounts else Role.SECTION
    if not amounts:
        return Role.SECTION
    label = normalize(row.label)
    if _NET in label:
        return Role.NET
    if _TOTAL_RE.search(label):
        return Role.TOTAL
    signed = [a for a in amounts if not a.nil]
    if signed and all(a.negative for a in signed):
        return Role.CONTRA
    return Role.ITEM
