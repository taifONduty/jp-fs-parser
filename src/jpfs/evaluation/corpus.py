"""Run the frozen, explicitly annotated public-filing corpus. See docs/benchmark.md."""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from jpfs.engines import ENGINES, parser_for
from jpfs.model import PageState
from jpfs.pipeline import Result
from jpfs.render import to_markdown, to_record
from jpfs.text import normalize

ACCEPTED = {PageState.VERIFIED, PageState.ACCEPTED_WITH_WARNINGS}
ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data/benchmark"


def typed(raw: str) -> tuple[str, Decimal, bool]:
    """Gold decoder: nil, exact decimal magnitude and printed sign (including △0)."""
    text = normalize(raw)
    if text in {"-", "―", "—", "−", "–"}:
        return "nil", Decimal(0), False
    negative = text.startswith(("△", "▲", "-", "−", "("))
    number = text.lstrip("△▲-−(").rstrip(")").replace(",", "")
    return "amount", Decimal(number), negative


def expected(spec: dict, directory: Path) -> tuple[Counter, Counter]:
    """Explicit paths and column contexts, without calling the parser's tree or amount decoder."""
    rows, facts = Counter(), Counter()
    with (directory / spec["gold"]).open(encoding="utf-8") as stream:
        for fields in csv.reader(
            (line for line in stream if not line.startswith("#")), delimiter="\t"
        ):
            path, unit, *values = fields
            path = tuple(normalize(part) for part in path.split("/"))
            if len(values) != len(spec["columns"]):
                raise ValueError(f"{spec['gold']}: wrong number of values in {path}")
            rows[path] += 1
            for column, raw in zip(spec["columns"], values, strict=True):
                date.fromisoformat(column["end"])
                if column["start"]:
                    date.fromisoformat(column["start"])
                if raw:
                    facts[
                        (
                            path,
                            column["start"],
                            column["end"],
                            column["dimension"],
                            unit,
                            typed(raw),
                        )
                    ] += 1
    return rows, facts


def observed(results: list[Result]) -> tuple[Counter, Counter, Counter]:
    rows, facts, headers = Counter(), Counter(), Counter()
    for result in results:
        if result.table is None:
            continue
        table = result.table
        periods = [
            (p.label, str(p.start) if p.start else None, str(p.end) if p.end else None, None)
            for p in table.periods
        ]
        header = table.header
        headers[
            (header.title, header.consolidated, header.correction, header.unit, tuple(periods))
        ] += 1
        for row in table.rows:
            rows[row.path] += 1
            for column, cell in zip(periods, row.cells, strict=True):
                if cell is None:
                    continue
                amount = cell.amount
                value = (
                    "nil" if amount.nil else "amount",
                    Decimal(amount.magnitude),
                    amount.negative,
                )
                unit = row.unit or header.unit
                facts[(row.path, column[1], column[2], None, unit, value)] += 1
    return rows, facts, headers


def prf(predicted: Counter, gold: Counter) -> dict:
    matched, n_predicted, n_gold = (predicted & gold).total(), predicted.total(), gold.total()
    return counts(matched, n_predicted, n_gold)


def counts(matched: int, predicted: int, gold: int) -> dict:
    precision = matched / predicted if predicted else 0.0
    recall = matched / gold if gold else 0.0
    return {
        "matched": matched,
        "predicted": predicted,
        "gold": gold,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * matched / (predicted + gold), 4) if predicted + gold else 0.0,
    }


def flatten(facts: Counter) -> Counter:
    flat = Counter()
    for (path, *context), n in facts.items():
        flat[(path[-1], *context)] += n
    return flat


def score_page(case: dict, results: list[Result], directory: Path) -> dict:
    gold_rows, gold_facts, gold_headers = Counter(), Counter(), Counter()
    for spec in case["tables"]:
        rows, facts = expected(spec, directory)
        gold_rows.update(rows)
        gold_facts.update(facts)
        columns = tuple((c["label"], c["start"], c["end"], c["dimension"]) for c in spec["columns"])
        gold_headers[
            (spec["title"], spec["consolidated"], spec["correction"], spec["unit"], columns)
        ] += 1
    rows, facts, headers = observed(results)
    accepted = [r for r in results if r.state in ACCEPTED]
    accepted_facts = observed(accepted)[1]
    checks = [c for r in results if r.verification for c in r.verification.checks]
    page_exact = rows == gold_rows and facts == gold_facts and headers == gold_headers
    return {
        "id": case["id"],
        "source": case["source"],
        "page": case["page"],
        "complexity": case["complexity"],
        "features": case["features"],
        "rows": prf(rows, gold_rows),
        "facts": prf(facts, gold_facts),
        "flat_facts": prf(flatten(facts), flatten(gold_facts)),
        "header_correct": headers == gold_headers,
        "page_exact": page_exact,
        "states": [r.state for r in results],
        "autoaccepted_page": bool(results) and len(accepted) == len(results),
        "autoaccepted_facts": prf(accepted_facts, gold_facts),
        "checks": {"passed": sum(c.passed for c in checks), "total": len(checks)},
        "reasons": [reason for r in results for reason in r.reasons],
        "missing": list((gold_facts - facts).elements()),
        "unexpected": list((facts - gold_facts).elements()),
    }


def source_pdf(source: dict, directory: Path, download: bool) -> Path:
    path = directory / f"{source['id']}.pdf"
    if not path.exists() and download:
        content = subprocess.check_output(
            [
                "curl",
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--retry",
                "2",
                "--connect-timeout",
                "10",
                "--max-time",
                "30",
                source["url"],
            ]
        )
        if hashlib.sha256(content).hexdigest() != source["sha256"]:
            raise ValueError(f"{source['id']}: downloaded PDF hash differs from the manifest")
        path.write_bytes(content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError(f"{path}: PDF hash differs from the manifest")
    return path


def run(
    manifest: dict, directory: Path, out: Path, download: bool, engine: str = "geometry"
) -> dict:
    parse_pdf = parser_for(engine)
    sources = out / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    pages = []
    for source in manifest["sources"]:
        cases = [case for case in manifest["cases"] if case["source"] == source["id"]]
        path = source_pdf(source, sources, download)
        results = parse_pdf(path, [case["page"] for case in cases])
        for case in cases:
            selected = [r for r in results if r.source.page == case["page"]]
            pages.append(score_page(case, selected, directory))
            (out / f"{case['id']}.json").write_text(dumps([to_record(r) for r in selected]))
            (out / f"{case['id']}.md").write_text("\n\n".join(to_markdown(r) for r in selected))
    summary = {
        metric: counts(
            *(sum(p[metric][key] for p in pages) for key in ("matched", "predicted", "gold"))
        )
        for metric in ("facts", "flat_facts", "rows", "autoaccepted_facts")
    }
    summary.update(
        {
            "pages": len(pages),
            "page_exact": sum(p["page_exact"] for p in pages),
            "headers_correct": sum(p["header_correct"] for p in pages),
            "autoaccepted_pages": sum(p["autoaccepted_page"] for p in pages),
            "wrong_autoaccepted_pages": sum(
                p["autoaccepted_page"] and not p["page_exact"] for p in pages
            ),
        }
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    parser_files = sorted((ROOT / "src/jpfs").glob("*.py"))
    if engine != "geometry":
        parser_files += sorted((ROOT / "src/jpfs/engines").glob("*.py"))
    digest = hashlib.sha256(
        b"".join(p.name.encode() + p.read_bytes() for p in parser_files)
    ).hexdigest()
    return {
        "engine": engine,
        "revision": revision,
        "parser_sha256": digest,
        "annotation_sha256": hashlib.sha256(
            b"".join(p.name.encode() + p.read_bytes() for p in sorted(directory.iterdir()))
        ).hexdigest(),
        "selection": manifest["selection"],
        "annotation": manifest["annotation"],
        "summary": summary,
        "pages": pages,
    }


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="download missing source PDFs")
    parser.add_argument("--manifest", type=Path, default=CORPUS / "manifest.json")
    parser.add_argument("--out", type=Path, default=ROOT / "out/benchmark")
    parser.add_argument("--engine", choices=ENGINES, default="geometry")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    report = run(manifest, args.manifest.parent, args.out, args.download, args.engine)
    (args.out / "report.json").write_text(dumps(report))
    print(dumps(report["summary"]), end="")


if __name__ == "__main__":
    main()
