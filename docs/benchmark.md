# Public-filing benchmark

Measured on 27 October 2026 with the parser frozen at `cc6a4fe`. No extraction or verification
code was changed during this evaluation. The original development sample is excluded.

**Result: 72.04% strict fact F1, 3/11 exact pages.** This is substantially weaker than the perfect
result on the development sample. The parser reads many unfamiliar amounts correctly, but semantic
hierarchy, wrapped rows, matrix columns and metadata on continuation pages remain unreliable.

## Sources and selection

Four official Japanese filings, totalling 134 PDF pages, were downloaded. Eleven pages were selected
for layout coverage before the first parser run; this is a purposive challenge set, not a random
sample of filings. Difficulty describes the layout, not the observed score.

| Issuer and filing | Selected PDF pages | Features |
|---|---|---|
| [Nintendo, FY ended March 2025](https://www.nintendo.co.jp/ir/pdf/2025/250508.pdf) | 7, 8, 9, 11, 13 | Standard assets, liabilities continuation, income, two equity panels, cash flow with a wrapped label |
| [Toyota, FY ended March 2025](https://global.toyota/pages/global_toyota/ir/financial-results/2025_4q_summary_jp.pdf) | 11, 19 | IFRS assets with gross-to-net subtotal; automotive/finance/elimination/consolidated asset sections |
| [MUFG, FY ended March 2025](https://www.mufg.jp/dam/ir/fs/2024/pdf/summary2503_ja.pdf) | 6, 7 | Bank assets with breakdowns below their totals; dense liabilities/equity continuation |
| [Fast Retailing, FY ended August 2025](https://www.fastretailing.com/jp/ir/library/pdf/tanshin202508_4q.pdf) | 9, 11 | IFRS balance sheet with note-number column; negative expenses, note lists and decimal EPS in yen |

Page numbers above are **1-based PDF positions**, not the numbers printed in footers. The manifest
pins every URL, source SHA-256, page, feature and column context. Sources are cached locally under
`out/benchmark/sources/`; the repository contains the download manifest and annotations.

Sony was considered but its server returned HTTP 403. It was excluded before parsing. No score was
used to decide which pages to include.

## Gold and scoring

There are **592 printed values, 334 rows and 12 annotated table panels** across the 11 pages.
Each TSV stores an explicit semantic row path, a unit and the printed values in manifest column
order. The equity page has two five-column panels: those columns identify equity components, not
five different periods. The four EPS values remain decimals in yen; they are included in the
denominator even though the parser currently supports integer amounts only.

Annotations were made by one assistant, checked against every rendered page, with the original PDF
text used as a transcription aid. They were completed and their hashes recorded before looking at
parser output. They do not use the parser's hierarchy builder or amount decoder. This provides an
inspectable reference; it is **not independently human-adjudicated or validated against XBRL**.
Semantic parent choices are explicit, particularly where indentation does not express nesting.

- **Strict facts:** exact `(row path, period start, period end, equity-column dimension, display
  unit, typed reported value)`. A typed value keeps nil, numeric zero, negative zero and exact
  decimal magnitude apart. Dates, units and dimensions must agree; no rounding tolerance is used
  to excuse transcription errors.
- **Flat facts:** the same key with only the leaf label instead of the full path. This diagnoses
  hierarchy errors; it is not the headline accuracy measure.
- **Exact page:** every row path, fact and header must match. Headers include statement title,
  consolidated scope, correction status, unit, period labels/dates and column dimensions.
- All counts use **multisets**. Duplicate predictions count against precision. Missing tables or
  empty outputs stay in the denominator with zero recall. All parser tables on a selected page
  are scored, including spurious ones. Headers on continuation pages are expected to retain the
  document's statement and scope, even though cross-page assembly is not implemented yet.

Full original PDFs are passed to `parse_pdf` with the selected pages grouped by document. The
pipeline can read document-wide rounding notes; no preceding-page metadata is supplied by the
benchmark. This measures the current page-selection API rather than a new assembly implementation.

## Results

| Measure | Result |
|---|---:|
| Strict facts matched | 420 / 592 |
| Predicted facts | 574 |
| Strict precision / recall / F1 | 73.17% / 70.95% / **72.04%** |
| Flat precision / recall / F1 | 93.38% / 90.54% / **91.94%** |
| Row-path F1 | 75.98% |
| Exact pages | **3 / 11 (27.3%)** |
| Correct headers | 8 / 11 |
| Auto-accepted pages | 2 / 11 |
| Auto-accepted facts | 88 / 592 (14.9% coverage) |

The 88 auto-accepted facts all match the strict fact key. However, **one of the two accepted pages
has an incomplete header**, so it is not an exact page. On so few accepted pages, these figures do
not estimate a production error rate or establish a safe acceptance threshold.

| Page | Difficulty | Correct / gold values | Strict F1 | Flat F1 | Exact page | Parser state |
|---|---|---:|---:|---:|---|---|
| Nintendo 7: assets | Simple | 46 / 46 | 100% | 100% | Yes | verified |
| Nintendo 8: liabilities | Medium | 42 / 42 | 100% | 100% | No | verified |
| Nintendo 9: income | Medium | 52 / 52 | 100% | 100% | Yes | needs_review |
| Toyota 11: assets | Medium | 48 / 50 | 95.05% | 95.05% | No | needs_review |
| MUFG 6: assets | Medium | 54 / 54 | 100% | 100% | Yes | needs_review |
| Nintendo 13: cash flow | Hard | 62 / 64 | 96.88% | 96.88% | No | needs_review |
| Toyota 19: segment assets | Hard | 0 / 46 | 0% | 100% | No | needs_review |
| MUFG 7: liabilities | Hard | 84 / 84 | 100% | 100% | No | needs_review |
| Fast Retailing 9: balance sheet | Hard | 0 / 70 | 0% | 100% | No | needs_review |
| Fast Retailing 11: income/EPS | Hard | 32 / 36 | 94.12% | 94.12% | No | needs_review |
| Nintendo 11: equity matrix | Stress | 0 / 48 | 0% | 0% | No | needs_review |

Pooled strict F1 by difficulty: simple **100%** (one page), medium **98.74%** (four pages), hard
**59.73%** (five pages), stress **0%** (one page). These are descriptive strata, not confidence
intervals or a claim about all PDFs in each category.

## What failed

1. **Header completeness is not an acceptance gate.** Nintendo 8 returns `verified` with all 42
   values correct but no statement title or consolidated scope. MUFG 7 also loses its header,
   though accounting failures send that page to review. Cross-page metadata and a completeness
   check are needed before treating `verified` as document-level correctness.
2. **Geometry alone misses semantic parents.** Toyota's segment page puts the automotive and
   finance headings to the right of their subsections, breaking an indentation-only tree.
   Fast Retailing's 資産 heading is omitted and 負債及び資本/負債 nesting is not recovered.
   These two pages account for all **116 additional matches** obtained by dropping hierarchy.
   Their values, leaf labels, dates and units are correct; their strict scores are zero because
   the row paths are wrong.
3. **Wrapped labels are split away from their values.** Nintendo's investment-sale cash receipt
   loses its label for two periods. Toyota's two-line accumulated-depreciation label does too.
   The numbers survive on empty-label rows. Page footer digits also become spurious content on
   Toyota and Fast Retailing pages.
4. **Equity components are mistaken for period columns.** The two panels on Nintendo 11 are not
   segmented or interpreted correctly; all 48 dimensional facts are missed. Several spurious
   facts are emitted. This case needs a richer column schema and segmentation.
5. **Decimal EPS and comma-separated note lists are unsupported.** Fast Retailing's four EPS
   values are absent. The note list `５,７` is flagged as an unreadable figure. These values and
   notes must be distinguished, and units must be allowed to change within a table.
6. **The verifier rejects some correctly extracted tables.** Nintendo's income page is exact,
   yet the inferred tax-total constraint sums unrelated rows. MUFG's asset breakdowns put totals
   before their details, so no check covers its 54 correct facts. The liabilities page also
   exposes incorrect subtotal chaining. Arithmetic coverage measures the constraints recovered,
   not whether the extracted table is correct.

The next work should address header gating, wrapped-row assembly and semantic grouping, then
decimal/per-row units and matrix columns. Preserve this snapshot when fixing those issues: once
used for development, these pages are regression cases and a fresh holdout is needed.

## Reproduce

From a source checkout (`curl` is required for downloads):

```bash
uv sync --locked
uv run python -m jpfs.evaluation.corpus --download
```

The command downloads missing PDFs, checks their pinned hashes, runs the pipeline and writes
`out/benchmark/report.json`, plus each page's full parser record and rendered Markdown table.
Cached sources are hash-checked on later runs. A changed source file fails instead of silently
changing the benchmark. `--out /another/directory` runs against a separate cache.

The checked-in [baseline results](benchmark-results.json) contain page scores, every verifier
reason, and fingerprints of the parser and annotations. The generated report additionally lists
every missing and unexpected fact. The download command can be resumed after a network failure;
already cached PDFs are kept and checked. The benchmark tests are offline; CI does not depend on
the issuers' websites.

A fresh-cache run downloaded all four pinned PDFs and reproduced the full report exactly. One
Fast Retailing connection timed out and succeeded on curl's retry.

This run covers selected digital financial-statement pages only. It does not evaluate scans/OCR,
natural account-form balance sheets, tables elsewhere in the 134 pages, or entire-filing recall.
