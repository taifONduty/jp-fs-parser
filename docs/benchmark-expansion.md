# Second benchmark: new issuers, older dates and partial text layers

Measured on 27 October 2026. The extraction and verification source is still identical to
`cc6a4fe`; only the benchmark runner gained a manifest argument. The original batch and its
annotations remain unchanged.

**Four new issuers, 14 new pages and 741 additional printed values.** This batch scores **91.93%
strict fact F1**, with **6/14 exact pages**. The higher score reflects different test cases, not a
parser improvement. Together the two batches cover **25 pages, eight issuers and 1,333 values**.

## Sources

| Filing | PDF pages scored | New coverage |
|---|---|---|
| [Hatena, July 2025](https://www2.jpx.co.jp/disc/39300/140120250909555393.pdf) | 10, 11, 12, 15 | Non-consolidated statements, 千円, gross/contra/net assets, deep retained-earnings nesting, balance sheet and cash flow |
| [Capcom, March 2016](https://www.capcom.co.jp/ir/news/pdf/160509a.pdf) | 10, 11, 12, 13, 16, 17 | Heisei dates, balance sheet across two pages, comprehensive income, cash flow across two pages, nil versus numeric zero |
| [Rakuten, Q1 2025](https://corp.rakuten.co.jp/investors/assets/doc/documents/25Q1tanshin_J.pdf) | 12, 13 | Quarterly IFRS dates and labels, 要約 titles, negative decimal EPS, whole balance sheet on one page |
| [Bank of Japan, FY140](https://www.boj.or.jp/about/account/data/zai2505a.pdf) | 5, 6 | Natural account-form balance sheet and income statement, one period, exact yen, Reiwa dates, figures drawn as vector outlines |

Hatena was downloaded from the [Kabutec mirror](https://www.kabutec.jp/pdf/202509/140120250909555393.pdf).
A download from the official JPX URL above was independently hash-checked and is byte-identical.
The manifest records the actual download URL and each source's SHA-256. Page numbers are 1-based
PDF positions, not footer numbers.

The pages were selected and all annotations written and hashed before the first parser run on
them. Every rendered page was inspected. As in the first batch, these are single-assistant
annotations, with source text as a transcription aid and explicit paths, periods and units.
They have not received independent human adjudication or XBRL validation. The BOJ values were
transcribed from the rendered pages because those values are absent from selectable text.

## Accuracy

The [first benchmark's scoring rules](benchmark.md#gold-and-scoring) are unchanged. Strict facts
require the complete row path, dated period, unit, column dimension and typed value. Exact pages
also require all rows and literal normalised header fields to match. Missing pages remain in
the denominator. Every table emitted on a selected page is scored.

| Measure | First batch | New batch | Combined |
|---|---:|---:|---:|
| Annotated pages | 11 | 14 | **25** |
| Gold values | 592 | 741 | **1,333** |
| Correct strict facts | 420 | 632 | **1,052** |
| Predicted facts | 574 | 634 | **1,208** |
| Strict precision | 73.17% | 99.68% | **87.09%** |
| Strict recall | 70.95% | 85.29% | **78.92%** |
| Strict F1 | 72.04% | 91.93% | **82.80%** |
| Flat fact F1, ignoring hierarchy | 91.94% | 91.93% | **91.93%** |
| Exact pages | 3/11 | 6/14 | **9/25 (36%)** |
| Correct headers | 8/11 | 7/14 | **15/25** |
| Auto-accepted pages | 2 | 3 | **5** |
| Auto-accepted pages with incorrect headers | 1 | 1 | **2** |

The 258 auto-accepted facts across both batches all match the fact key, but two of their five
pages lack statement metadata. Fact precision alone therefore overstates acceptance quality.
These figures are descriptive results on purposively selected pages, not a production error-rate
estimate.

| New page | Correct / gold | Fact F1 | Exact page | State |
|---|---:|---:|---|---|
| Hatena 10: assets | 52/52 | 100% | Yes | verified |
| Hatena 11: liabilities/equity | 52/52 | 100% | No | needs_review |
| Hatena 12: income | 52/52 | 100% | Yes | needs_review |
| Hatena 15: cash flow | 86/86 | 100% | Yes | needs_review |
| Capcom 10: assets | 60/60 | 100% | Yes | verified |
| Capcom 11: liabilities/equity | 58/58 | 100% | No | verified |
| Capcom 12: income | 56/56 | 100% | Yes | needs_review |
| Capcom 13: comprehensive income | 16/16 | 100% | Yes | needs_review |
| Capcom 16: cash flow, first page | 64/66 | 96.97% | No | needs_review |
| Capcom 17: cash flow, continuation | 24/24 | 100% | No | needs_review |
| Rakuten 12: balance sheet | 84/84 | 100% | No | needs_review |
| Rakuten 13: income/EPS | 28/32 | 93.33% | No | needs_review |
| BOJ 5: account-form balance sheet | 0/58 | 0% | No | failed |
| BOJ 6: account-form income | 0/45 | 0% | No | failed |

The 12 new pages with selectable amounts, excluding the two BOJ pages, have 99.37% fact F1
(632/638 gold facts matched). This is a diagnostic subset defined by text-layer availability;
the headline score includes all 14 pages. All 109 missing facts in this batch are accounted for:
103 BOJ amounts, four negative decimal EPS values, and two values detached from their wrapped
Capcom label. The latter also produce two unexpected empty-label facts.

## What the additional cases establish

- **Routine text extraction is stronger than the first stress-heavy batch suggested.** The
  parser recovers the full fact sets on all four Hatena pages, five Capcom pages and Rakuten's
  balance sheet. Heisei dates and 千円 work on real documents, including deep nesting and signed
  subtotals. This does not resolve the segment and equity-matrix failures in the first batch.
- **Continuation metadata is still lost.** Hatena 11 and Capcom 11/17 have correct fact sets but
  no statement title. Capcom 11 repeats the first batch's incorrect `verified` acceptance; the
  [acceptance fix](#acceptance-fix) sends all three pages to review, and
  [cross-page assembly](#cross-page-assembly) then restores their titles.
- **Quarterly headers lose literal information.** Rakuten's printed 要約 prefix is omitted, and
  period labels such as 当第1四半期連結会計期間末 are cut short. Dates on its balance-sheet facts
  are nevertheless correct. These header differences explain why its 84/84 fact score is not
  an exact-page result; they are distinct from an incorrect amount or date. Both are
  [fixed](#header-reading), and the balance sheet is now an exact page.
- **A text-bearing page can still require vision.** BOJ's labels are selectable text while its
  monetary digits are vector outlines. Both selected BOJ pages correctly end as `failed` with
  no value columns found. This tests a natural PDF failure mode, rather than a synthetic scan.
- **Verification needs work in both directions.** Correct Hatena/Capcom income tables trigger
  incorrect tax-sum constraints, while some correctly transcribed cash-flow cells are uncovered.
  A passing arithmetic check remains insufficient to establish correct extraction.

## Complete-document ingestion check

The CLI was also run over **all 114 pages of the four new PDFs**, without page selection. It
completed with exit code 0, producing 62 result records. The records for all 14 annotated pages
were byte-for-byte equivalent after JSON parsing to the page-selected run, including verification
states. This is a check of ingestion and selection consistency, not an accuracy score for the
remaining 100 pages.

| Document | PDF pages | Result records |
|---|---:|---:|
| Hatena | 22 | 13 |
| Capcom | 23 | 16 |
| Rakuten | 32 | 18 |
| BOJ | 37 | 15 |

**An additional acceptance defect was found outside the held-out pages.** BOJ PDF page 17 contains
three asset-note tables with visible values. Its mixed text/vector layer yields a table with
13 rows, **zero periods and zero facts**, yet the state is `accepted_with_warnings`. Both the
rendered source and output were inspected. This page was inspected after the full-document run,
so it is recorded as a post-hoc state probe and is not silently added to the 14-page accuracy
denominator. It shows why an empty output must not count as successfully accepted extraction.
After the [acceptance fix](#acceptance-fix) it fails, and its unbound amounts are listed.

The [ingestion results](benchmark-document-smoke.json) record document hashes, state counts,
selection-consistency checks and the empty accepted output. Other unannotated outputs, including
notes and summaries, have not been judged for accuracy or false-positive rates.

## Acceptance fix

Commit `e24966b` changes acceptance only. A table without its statement title needs review, and a
table with no amount bound to a period fails. Figures under a column header that names no period
are reported as lost facts, unless the column is 注記; they were previously filed as note
references, which is how BOJ 17 lost all its values without a warning. Both batches and the
full-document check were re-run on this commit. The baseline snapshots above are unchanged. The
new results are in the [first-batch](benchmark-results-acceptance-fix.json),
[second-batch](benchmark-expansion-results-acceptance-fix.json) and
[ingestion](benchmark-document-smoke-acceptance-fix.json) snapshots.

| Measure, both batches | Before | After |
|---|---:|---:|
| Strict fact F1 | 82.80% | 82.80% |
| Exact pages | 9/25 | 9/25 |
| Auto-accepted pages | 5 | **3** |
| Auto-accepted pages with incorrect headers | 2 | **0** |
| Auto-accepted facts, all correct | 258 | 158 |
| Accepted empty outputs in the 114-page check | 1 | **0** |

Extraction did not change: every page has the same rows, facts and headers as before. The
remaining auto-accepted pages, Nintendo 7, Hatena 10 and Capcom 10, are all exact. States changed
on four pages:

| Page | Before | After | Reason |
|---|---|---|---|
| Nintendo 8: liabilities | verified | needs_review | No statement title on the page |
| Capcom 11: liabilities/equity | verified | needs_review | No statement title on the page |
| BOJ 17 (ingestion probe): asset notes | accepted_with_warnings | failed | No amount bound to a period; its figures are listed as lost |
| Hatena 3 (ingestion probe): table of contents | needs_review | failed | Page numbers form a column but bind to no period |

MUFG 7, Hatena 11 and Capcom 17 were already in review and now also carry the missing-title
reason. On Nintendo 11, 16 equity-matrix amounts that had been filed as note references are now
reported as lost facts. The Hatena table of contents is a false-positive table on a page with no
statement; it was never accepted, and suppressing such tables belongs to segmentation work.
Continuation pages can only be accepted once cross-page assembly carries the title forward;
[that came next](#cross-page-assembly).

The full-document run still exits with code 0 and produces 62 records over 114 pages. All 14
annotated pages match the page-selected run. States per document: Hatena 11 review, 1 verified,
1 failed; Capcom 10 review, 1 verified, 5 failed; Rakuten 15 review, 1 verified, 2 failed; BOJ
6 review, 9 failed.

## Cross-page assembly

Commit `5da3e66` implements the design's cross-page assembly for statement metadata. Pages are
split at statement titles, so only a page's first table can be untitled. That table continues
the statement that ends the previous page when the evidence agrees: the same dated periods and
the same unit. It then inherits the title, statement type and scope, and `continued_from`
records the page they came from. Untitled pages in between are followed back, up to four pages,
while their columns agree. Earlier pages are read whether or not they were selected, so the
page-selected and full-document runs still agree. The results are in the
[first-batch](benchmark-results-cross-page.json), [second-batch](benchmark-expansion-results-cross-page.json)
and [ingestion](benchmark-document-smoke-cross-page.json) snapshots; earlier snapshots are kept.

| Measure, both batches | Baseline | Acceptance fix | Cross-page assembly |
|---|---:|---:|---:|
| Strict fact F1 | 82.80% | 82.80% | 82.80% |
| Exact pages | 9/25 | 9/25 | **14/25** |
| Correct headers | 15/25 | 15/25 | **20/25** |
| Auto-accepted pages | 5 | 3 | **5** |
| Auto-accepted pages with incorrect headers | 2 | 0 | **0** |
| Auto-accepted facts, all correct | 258 | 158 | 258 |

Strict facts do not include the statement title, so fact F1 is unchanged; the gain shows in
headers and exact pages. All five continuation pages now have exact headers:

| Page | Title inherited from | State |
|---|---|---|
| Nintendo 8: liabilities | PDF page 7 | verified (was needs_review) |
| MUFG 7: liabilities | PDF page 6 | needs_review: two subtotal constraints fail |
| Hatena 11: liabilities/equity | PDF page 10 | needs_review: 4 cells covered by no constraint |
| Capcom 11: liabilities/equity | PDF page 10 | verified (was needs_review) |
| Capcom 17: cash flow, continuation | PDF page 16 | needs_review: 8 cells covered by no constraint |

The five auto-accepted pages, Nintendo 7 and 8, Hatena 10 and Capcom 10 and 11, are all exact.
Nintendo 8 and Capcom 11 were wrongly accepted in the baseline because their headers were
incomplete; they are now accepted with complete ones.

Over all 114 pages of the full-document run, titles were carried over on four pages: the three
annotated continuations of this batch and Rakuten 17, an unannotated cash-flow continuation whose
財務活動 section follows page 16's 投資活動 section under a repeated header. That page was inspected;
it stays in review for an unlabelled row and 8 uncovered cells. The run still exits with code 0,
with 62 records, all 14 annotated pages identical to the page-selected run, and no accepted empty
output.

Totals whose members sit on another page are still checked page by page. Rakuten's headers remained
inexact because its 要約 title prefix and long quarterly period labels were shortened, a separate
header-reading issue [fixed next](#header-reading).

## Header reading

Commit `acf45bd` fixes two header-reading bugs that the Rakuten pages exposed. Statement titles
may start with 要約, which the title pattern dropped. The period phrase was matched lazily and
stopped at the first 期, so 当第1四半期連結会計期間末 became 当第1四半期. It now takes the longest
phrase before the column's date, still leaving out stray header words such as 注記. Every title
and period label in both batches' gold headers now reads back exactly. The results are in the
[first-batch](benchmark-results-header-reading.json),
[second-batch](benchmark-expansion-results-header-reading.json) and
[ingestion](benchmark-document-smoke-header-reading.json) snapshots.

| Measure, both batches | Baseline | Acceptance fix | Cross-page assembly | Header reading |
|---|---:|---:|---:|---:|
| Strict fact F1 | 82.80% | 82.80% | 82.80% | 82.80% |
| Exact pages | 9/25 | 9/25 | 14/25 | **15/25** |
| Correct headers | 15/25 | 15/25 | 20/25 | **22/25** |
| Auto-accepted pages | 5 | 3 | 5 | 5 |
| Auto-accepted pages with incorrect headers | 2 | 0 | 0 | 0 |
| Auto-accepted facts, all correct | 258 | 158 | 258 | 258 |

Only the two Rakuten pages change. The balance sheet, Rakuten 12, now has an exact header and
becomes an exact page with 84/84 facts. The income statement, Rakuten 13, has an exact header,
but its four decimal EPS values are still unsupported, so it stays inexact. Both remain in review
for their arithmetic checks, whose reasons now name the full period labels. No other page's
scores, states or reasons change. The first batch is unaffected.

The three remaining incorrect headers are the Nintendo equity matrix, whose component columns are
read as periods, and the two BOJ pages, whose figures are vector outlines. In the full-document
run every Rakuten statement now reads with its 要約 prefix, including the cash-flow continuation
on page 17. State counts, record counts and selected-page consistency are unchanged, and no empty
output is accepted.

## Reproduce

```bash
uv run python -m jpfs.evaluation.corpus --download \
  --manifest data/benchmark-expansion/manifest.json --out out/benchmark-expansion

uv run jpfs parse out/benchmark-expansion/sources/*.pdf \
  -o out/benchmark-expansion/full-document
```

The [new baseline snapshot](benchmark-expansion-results.json) records page scores, reasons and
parser/annotation fingerprints. As before, the generated report in `out/` additionally lists
every missing and unexpected fact. A fresh download of all four pinned sources reproduced the
full selected-page report; the official Hatena JPX copy matches the mirror hash. The offline
test suite validates both corpora without network access.

The parser has deliberately not been tuned on these results. Subsequent fixes should retain
both snapshots and use these pages as regression cases. Raster scans/OCR and independently
adjudicated whole-filing accuracy are still untested.
