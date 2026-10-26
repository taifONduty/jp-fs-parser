# jp-fs-parser

Turns pages of Japanese financial-statement PDFs (決算短信, 有価証券報告書) into tables of typed
facts, and says how far each table can be trusted.

The design, the catalogue of what breaks on real filings, and the evaluation plan are in
[docs/design.pdf](docs/design.pdf). This repository implements the design's digital-PDF path end to
end: geometry extraction, accounting checks derived from each table's own hierarchy, an explicit
state for every table, and the evaluation harness.

Two [external benchmark batches](docs/benchmark-expansion.md) now cover **25 pages from eight
issuers and 1,333 annotated values: 82.80% strict fact F1 and 14/25 exact pages**. The perfect
development-sample score below does not generalise to these layouts. The
[first batch](docs/benchmark.md) scores 72.04% F1. The benchmark found two acceptance defects:
continuation pages verified without their statement title, and an empty table accepted. After
[the fix](docs/benchmark-expansion.md#acceptance-fix) and
[cross-page assembly](docs/benchmark-expansion.md#cross-page-assembly), **every auto-accepted
page is exact**: 5 pages and 258 facts. Before, 2 of the 5 accepted pages had incorrect headers.

## What "correct" means

A table is correct when its facts are. A fact is a printed amount bound to its row path, its period,
its unit and its typed value:

- **Path, not label.** The sample page has four rows labelled その他 and four labelled 減価償却累計額.
- **Typed values.** A dash (－) means the line exists with no balance, a blank means it is not
  presented, and △0 is a negative amount smaller than one display unit. These are different facts.
- **Metadata is part of correctness.** Statement, consolidated scope, 訂正前/訂正後, unit and dated
  periods are all scored.

The headline metrics are fact precision, recall and F1, and the page-exact rate. In production
there is no gold, so the operating point is the share of facts auto-accepted together with the
error rate among them. Grid similarity (TEDS, GriTS) is a diagnostic only. pdfplumber's own table
finder reproduces all 43 body rows of the sample page, yet it drops both period dates, the unit
and the hierarchy, so it cannot answer "what was cash at 31 March 2026, in yen?".

## Quick start

```bash
uv sync
uv run jpfs parse data/balance_sheet_p4.pdf -o out
uv run jpfs evaluate data/balance_sheet_p4.pdf data/balance_sheet_p4.gold.tsv
uv run pytest
```

`parse` accepts many PDFs and `--pages 4,5`. For each statement table it finds, it writes:

| File | Content |
|---|---|
| `p<page>-<n>.facts.jsonl` | One fact per printed cell: path, period, value and its interval in yen, bbox provenance, the constraints that vouch for it. The schema is the [design's Appendix A](docs/design.pdf), minus the fields of stages not built yet (taxonomy concept, second-path agreement, XBRL match) |
| `p<page>-<n>.md` | The rendered table, derived from the same rows |
| `p<page>-<n>.json` | The full record (rows, checks, uncovered cells, reasons), for review |

## Pipeline

| Stage | Where | Status |
|---|---|---|
| S0 Ingest: content hash, page selection | `pipeline.py` | done |
| S1 Triage: text-layer audit (cid glyphs, U+FFFD, private use, Kangxi look-alikes) | `text.py` | done. Pages without text fail and are routed to S3b |
| S2 Segmentation: split pages at statement titles | `layout.py` | done. Account-form (勘定式) split not yet |
| S3a Geometry over the text layer | `layout.py` | done |
| S3b Vision over pixels | | designed |
| S4 Cross-page assembly: continuation pages inherit their statement's title | `assembly.py` | done. Totals spanning pages not yet checked |
| S5 Normalise: periods (和暦 and Gregorian, instant and duration), units, signs, roles | `text.py`, `structure.py` | done. Taxonomy mapping not yet |
| S6 Verify: tree constraints, interval arithmetic, rounding inference, page state | `checks.py`, `verdict.py` | done. XBRL comparison not yet |
| S7 Facts and rendered table | `render.py` | done |

Decisions that matter:

- **Columns are read as right-aligned.** Value columns come from clustering the right edges of
  amounts. A column owns the space back to the previous column's right edge, which is how a
  centred header binds to right-aligned figures. A 注記 column yields note references; figures
  under any other header that names no period are reported as lost facts.
- **Only visible ink counts.** Rules are filtered by colour, because the sample page paints rule
  segments in the band colour and a colour-blind parser would read them as cell borders. Correction
  underlines (訂正箇所) are told apart from summation rules by width.
- **Constraints come from the table itself.** A total sums the members above it, back to and
  including the previous total of its group, so 小計 chains work. A net (純額) adds its contra rows
  to the gross. There are no per-company rules.
- **Intervals, not tolerances.** A printed amount stands for the true values it could have come
  from, and a constraint holds when the interval of the total overlaps the interval sum of its
  terms. These are the intervals of XBRL Calculations 1.1: closed `[v-½, v+½]` under rounding
  (§5.2.3), and half-open under truncation, including the bound nearer zero (§5.2.4): `[v, v+1)`
  and `(-v-1, -v]` for △v. The △ convention makes the zero case sharper than the spec's: △0 is
  `(-1, 0)`, an unsigned 0 is `[0, 1)`, and － is `{0}`. On the sample page, exact equality would
  raise 13 false alarms out of 20.
- **The rounding mode is inferred from evidence.** A note in the filing (百万円未満切捨て) wins.
  Otherwise a sign test runs over every table in the document. Take the residuals (printed total
  minus printed sum) for which exactly one of r and −r fits the truncation interval. Rounding errors
  are symmetric, so under rounding the observed residual is the one that misfits half the time;
  under truncation it never is. Finding almost no misfits (p < 0.01) therefore means truncation.
  Choosing whichever mode passes would let real errors hide in the slack. Without evidence, the
  checks use the hull of both modes and the table is flagged.
- **Abstain explicitly.** Every table ends as `verified`, `accepted_with_warnings`, `needs_review`
  or `failed`. A failed constraint, a cell that no constraint covers, a printed figure that could
  not be bound to a cell, or a missing statement title sends the table to review. A table with no
  bound amount fails, as does a page that names a statement but yields no table, or has no usable
  text layer. Nothing is dropped silently.

## Results on the sample page

| Measure | Result |
|---|---|
| Header: 連結貸借対照表, consolidated, 訂正後, 千円, two dated periods | correct |
| Rows (label and hierarchy path), F1 | 1.00 (43/43) |
| Facts (path, period, typed value), F1 | 1.00 (74/74) |
| Constraints derived from the tree, passing | 20/20, every cell covered |
| Rounding | truncation, inferred: 13 informative residuals, none misfit (p = 2⁻¹³) |
| Correction underlines | 2/2 (投資有価証券, 関係会社株式, current year) |
| Page state | verified |
| pdfplumber, ruling lines | 43/43 body rows, no period dates, no unit, no hierarchy |
| pdfplumber, text alignment | 39/43 body rows; splits labels (現 \| 金及び預金) and drops characters (定資 \| 産) |

### What do the accounting checks detect?

`jpfs evaluate` injects one realistic error at a time into the gold table (4,199 mutants) and
counts how often at least one check fails:

| Injected error | Truncation inferred | Mode unknown |
|---|---:|---:|
| Any digit substitution | 94.8% | 90.6% |
| OCR-confusable digit (3↔8, 5↔6, …) | 96.3% | 91.2% |
| Digit at 10千円 or above | 100% | 100% |
| Units digit (1千円) | 70.7% | 46.9% |
| Dropped digit | 100% | 100% |
| Lost △ | 100% | 100% |
| Period columns swapped | 100% | 100% |
| Adjacent rows swapped | 45.5% | 45.5% |

On this sample, the checks detect every tested single digit error at 10千円 or above. Passing them
does not establish extraction accuracy: units-digit errors, swaps within a sum and missing metadata
can survive. Those blind spots are why the design adds a second extraction path and XBRL comparison.
Knowing the rounding mode improves detection of sampled units-digit errors by 23.8 percentage points.

## Limitations

The parser was developed on one page. The [25-page benchmark](docs/benchmark-expansion.md) now
measures where it generalises and where it fails. Section 7 of the design describes a larger
evaluation with XBRL-aligned gold, stratified by layout family. Known gaps:

- Labels wrapped over two lines.
- Totals placed at the section heading's own indentation.
- Account-form pages.
- Multi-page statements are checked page by page: a continuation page inherits its statement's
  title, but totals whose members sit on another page are not verified.
- Per-share decimals. These are reported as unplaced rather than parsed.
- Arithmetic that is not a tree, such as income-statement step-downs, which needs taxonomy
  calculation links.

Such pages are sent to `needs_review` or end as `failed`. A continuation page inherits its title
only when its periods and unit match the statement it continues; otherwise it is reviewed.

## Layout

```
src/jpfs/
  model.py        immutable IR: Amount, Cell, Period, Row, Header, Table
  text.py         lexical cues: amounts, 和暦 dates, units, titles, rounding notes, text audit
  layout.py       geometry path: page -> statement tables
  structure.py    indentation -> tree -> roles
  checks.py       constraints, interval arithmetic, rounding inference
  assembly.py     cross-page assembly: continuation pages keep their statement
  verdict.py      page states
  pipeline.py     document flow
  render.py       facts, markdown, record
  cli.py
  evaluation/     gold loader, fact metrics, mutation test, baseline
data/             the sample page and its gold transcription, made by hand from the rendered page
docs/design.pdf   the pipeline design
```
