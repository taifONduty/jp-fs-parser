"""Row hierarchy (design S3a/S5): indentation levels to a tree of groups, members and totals."""

import re
from collections.abc import Sequence
from dataclasses import replace

from jpfs.model import Role, Row
from jpfs.text import normalize, unit_marker

_TOTAL_RE = re.compile(r"計$")  # 合計, 小計, 資産計
_NET = "純額"
_CLOSING = (Role.TOTAL, Role.NET)


def build_structure(rows: Sequence[Row]) -> tuple[tuple[Row, ...], tuple[str, ...]]:
    """Link rows into a tree from their levels, assign roles and per-row units, and warn about
    unclosed groups. A unit printed in a label, such as （円）, holds for the row and its children;
    otherwise a row keeps the unit of any unit line printed above it."""
    parents = _parents(_tree_levels(rows))
    children = [tuple(j for j, p in enumerate(parents) if p == i) for i in range(len(rows))]
    roles = _roles(rows, parents, children)
    paths: list[tuple[str, ...]] = []
    units: list[str | None] = []
    for row, parent in zip(rows, parents, strict=True):
        paths.append((paths[parent] if parent is not None else ()) + (normalize(row.label),))
        inherited = units[parent] if parent is not None else None
        units.append(unit_marker(row.label) or inherited or row.unit)

    linked = tuple(
        replace(
            row,
            parent=parents[i],
            children=children[i],
            role=roles[i],
            path=paths[i],
            unit=units[i],
        )
        for i, row in enumerate(rows)
    )
    warnings = tuple(
        f"group '{row.label}' has no closing total on this page"
        for row in linked
        if row.children and linked[row.children[-1]].role not in _CLOSING
    )
    return linked, warnings


def _tree_levels(rows: Sequence[Row]) -> list[int]:
    """Printed levels, corrected where the totals say the indentation does not express the tree.

    A total that names a heading closes it (流動資産合計 closes 流動資産), so the rows between
    belong to that heading even when printed at its indentation. A compound heading such as
    負債及び資本 encloses the sections it names even when its own total is on a later page. A
    total printed right after a total at the same level, naming no heading, closes the enclosing
    level: 負債純資産合計 after 純資産合計 sums the whole sheet, not 純資産の部.
    """
    levels = [row.level for row in rows]
    closed = _close_named_headings(rows, levels)
    _enclose_compound_headings(rows, levels, closed)
    for i in range(1, len(rows)):
        if (
            i not in closed
            and rows[i].level == rows[i - 1].level > 0
            and _is_total(rows[i])
            and _is_total(rows[i - 1])
        ):
            levels[i] -= 1
    return levels


def _close_named_headings(rows: Sequence[Row], levels: list[int]) -> set[int]:
    """Make each total that names a heading that heading's last child, nesting the rows between
    beneath the heading when they were printed at its level; innermost first. Returns the totals."""
    closed: set[int] = set()
    for total, row in enumerate(rows):
        name = _named_heading(row)
        heading = next(
            (
                k
                for k in range(total - 1, -1, -1)
                if not any(rows[k].cells) and _section(rows[k].label) == name
            ),
            None,
        )
        if name is None or heading is None:
            continue
        between = range(heading + 1, total)
        if between and (lowest := min(levels[k] for k in between)) <= levels[heading]:
            for k in between:
                levels[k] += levels[heading] + 1 - lowest
        levels[total] = levels[heading] + 1
        closed.add(total)
    return closed


def _enclose_compound_headings(rows: Sequence[Row], levels: list[int], closed: set[int]) -> None:
    """A heading such as 負債及び資本, directly followed at its own level by one of the sections it
    names, encloses those sections and their totals even when its own total is not on the page."""
    named = {_named_heading(rows[t]) for t in closed}
    for heading, row in enumerate(rows):
        parts = _parts(row.label)
        first = heading + 1
        if (
            any(row.cells)
            or len(parts) < 2
            or _section(row.label) in named
            or first >= len(rows)
            or levels[first] > levels[heading]
            or _section(rows[first].label) not in parts
        ):
            continue
        end = next(
            (
                k
                for k in range(first, len(rows))
                if levels[k] <= levels[heading]
                and _section(rows[k].label) not in parts
                and _named_heading(rows[k]) not in parts
            ),
            len(rows),
        )
        for k in range(first, end):
            levels[k] += 1


def _section(label: str) -> str:
    """A heading's name for matching against totals: 資産の部 is the section 資産."""
    return normalize(label).removesuffix("の部")


def _named_heading(row: Row) -> str | None:
    """The heading a total names: 流動資産合計 names 流動資産, 資産の部合計 names 資産."""
    label = normalize(row.label)
    if not any(row.cells) or not label.endswith("合計"):
        return None
    return _section(label.removesuffix("合計")) or None


def _parts(label: str) -> list[str]:
    """The sections a compound heading names: 負債及び資本 names 負債 and 資本."""
    return [_section(part) for part in re.split("及び|並びに", normalize(label)) if part]


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
