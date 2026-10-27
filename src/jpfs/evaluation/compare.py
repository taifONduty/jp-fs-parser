"""Compare engines on the benchmark corpora: one markdown table per corpus and one pooled.

usage: python -m jpfs.evaluation.compare ROOT
ROOT holds <engine>/<corpus>/report.json from the runner, or <engine>/<corpus>.json snapshots.
"""

import json
import sys
from pathlib import Path

from jpfs.engines import ENGINES

CORPORA = ("holdout-2", "holdout", "first", "expansion")
HEADER = (
    "| Engine | Strict fact F1 | Flat fact F1 | Row-path F1 | Exact pages | Correct headers "
    "| Auto-accepted pages | Wrong accepted pages | Wrong accepted facts |\n"
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
)


def load(root: Path, engine: str, corpus: str) -> dict | None:
    for path in (root / engine / corpus / "report.json", root / engine / f"{corpus}.json"):
        if path.exists():
            return json.loads(path.read_text())
    return None


def row(engine: str, reports: list[dict]) -> str:
    def total(metric: str, key: str) -> int:
        return sum(r["summary"][metric][key] for r in reports)

    def f1(metric: str) -> str:
        matched, predicted, gold = (total(metric, k) for k in ("matched", "predicted", "gold"))
        return f"{200 * matched / (predicted + gold):.2f}%" if predicted + gold else "-"

    def count(key: str) -> int:
        return sum(r["summary"][key] for r in reports)

    accepted = total("autoaccepted_facts", "predicted")
    wrong = accepted - total("autoaccepted_facts", "matched")
    pages = count("pages")
    return (
        f"| {engine} | {f1('facts')} | {f1('flat_facts')} | {f1('rows')} "
        f"| {count('page_exact')}/{pages} | {count('headers_correct')}/{pages} "
        f"| {count('autoaccepted_pages')} | {count('wrong_autoaccepted_pages')} "
        f"| {wrong} of {accepted} |"
    )


def tables(root: Path) -> str:
    sections = [(corpus, [corpus]) for corpus in CORPORA] + [("all corpora", list(CORPORA))]
    out = []
    for title, corpora in sections:
        lines = []
        for engine in ENGINES:
            reports = [load(root, engine, corpus) for corpus in corpora]
            if all(reports):
                lines.append(row(engine, reports))
        if lines:
            out.append(f"### {title}\n\n{HEADER}\n" + "\n".join(lines))
    return "\n\n".join(out) + "\n"


if __name__ == "__main__":
    print(tables(Path(sys.argv[1])), end="")
