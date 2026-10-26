"""Command line: `jpfs parse` turns filings into verified tables; `jpfs evaluate` scores a page."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pdfplumber.utils.exceptions import PdfminerException

from jpfs.evaluation import evaluate_page
from jpfs.pipeline import Result, parse_pdf
from jpfs.render import to_facts, to_markdown, to_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jpfs", description=__doc__)
    commands = parser.add_subparsers(required=True)

    parse = commands.add_parser("parse", help="extract and verify every statement table")
    parse.add_argument("pdfs", nargs="+", type=Path)
    parse.add_argument("-o", "--out", type=Path, default=Path("out"))
    parse.add_argument("-p", "--pages", type=_pages, help="1-based pages, e.g. 4,5 (default: all)")
    parse.set_defaults(run=_parse)

    evaluate = commands.add_parser("evaluate", help="score one page against a gold transcription")
    evaluate.add_argument("pdf", type=Path)
    evaluate.add_argument("gold", type=Path)
    evaluate.add_argument("-p", "--page", type=int, default=1)
    evaluate.set_defaults(run=_evaluate)

    args = parser.parse_args(argv)
    return args.run(args)


def _pages(spec: str) -> list[int]:
    try:
        return [int(part) for part in spec.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"expected comma-separated page numbers: {spec!r}"
        ) from error


def _parse(args: argparse.Namespace) -> int:
    status = 0
    for pdf in args.pdfs:
        try:
            results = parse_pdf(pdf, args.pages)
        except (OSError, ValueError, PdfminerException) as error:
            print(f"{pdf}: {error}", file=sys.stderr)
            status = 1
            continue
        _write(results, args.out / pdf.stem)
        for result in results:
            print(f"{pdf.name}\t{_summary(result)}")
        if not results:
            print(f"{pdf.name}\tno statement tables found")
    return status


def _write(results: list[Result], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    seen: Counter[int] = Counter()
    for result in results:
        seen[result.source.page] += 1
        stem = directory / f"p{result.source.page}-{seen[result.source.page]}"
        stem.with_suffix(".md").write_text(to_markdown(result), encoding="utf-8")
        stem.with_suffix(".json").write_text(_json(to_record(result)), encoding="utf-8")
        facts = "".join(_json(fact, indent=None) + "\n" for fact in to_facts(result))
        stem.with_suffix(".facts.jsonl").write_text(facts, encoding="utf-8")


def _summary(result: Result) -> str:
    page = f"p{result.source.page}"
    if result.table is None or result.verification is None:
        return f"{page}\t{result.state}\t{'; '.join(result.reasons)}"
    checks = result.verification.checks
    facts = sum(cell is not None for row in result.table.rows for cell in row.cells)
    return "\t".join(
        [
            page,
            result.table.header.title or "untitled",
            f"{len(result.table.rows)} rows",
            f"{facts} facts",
            f"{sum(c.passed for c in checks)}/{len(checks)} checks",
            result.state,
        ]
    )


def _evaluate(args: argparse.Namespace) -> int:
    try:
        report = evaluate_page(args.pdf, args.gold, args.page)
    except (OSError, ValueError, PdfminerException) as error:
        print(f"{args.pdf}: {error}", file=sys.stderr)
        return 1
    print(_json(report))
    return 0


def _json(data: object, indent: int | None = 1) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)


if __name__ == "__main__":
    sys.exit(main())
