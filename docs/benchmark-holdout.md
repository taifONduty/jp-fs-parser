# Fresh holdout: new issuers, annual reports and new layout families

Measured on 27 October 2026. The two earlier batches were used to develop the fixes after
`cc6a4fe`, so their scores are no longer unbiased. This holdout measures the current parser on
filings it was never developed on.

**Result: 86.41% strict fact F1 and 8/12 exact pages, with every header correct; but one of the
four auto-accepted pages is wrong.** Its values are right and its labels are not, which arithmetic
cannot see.

## Protocol

1. Four issuers new to the corpus were chosen for layout families the parser had not seen.
2. Pages were selected from text-layer titles and rendered pages, and transcribed, without
   running the parser on these files.
3. The annotations were committed and pushed in `c5c5283` before the first parser run, with
   annotation fingerprint `f6a90316…`.
4. The parser ran once, unchanged since `3858431`; its fingerprint equals that of the
   [per-share snapshot](benchmark-results-per-share.json). The runner downloaded all four PDFs
   into a fresh cache and checked them against the pinned hashes.

Nothing was changed after the run. Scoring rules are those of the [first batch](benchmark.md#gold-and-scoring).

## Sources

| Filing | Producer | PDF pages scored | Coverage |
|---|---|---|---|
| [Japan Securities Finance, annual securities report FY2026/3](https://data.swcms.net/file/jsf/dam/jcr:bece3864-c3b9-4b5e-b322-5e35419e9a63/S100YIQY.pdf) | EDINET | 61, 62, 63 | Japanese GAAP, securities-finance accounts, footnote markers inside value cells |
| [NRI, annual securities report FY2026/3](https://data.swcms.net/file/nri-ir/dam/jcr:f076fdc6-dd40-450e-82a0-870ae62ccbbd/S100YBM8.pdf) | EDINET | 81, 82, 83 | IFRS, 注記 column, totals at the heading's indentation, single-statement comprehensive income |
| [ARE Holdings, annual securities report FY2026/3](https://www.are-holdings.com/Portals/0/images/ir/library/securities/20260615_securities_BDUU0.pdf) | Antenna House | 57, 58, 59 | IFRS, full-width note numbers, expenses printed as negatives, EPS in 円 |
| [Shin Nihon Construction, 決算短信 FY2026/3](https://www.shinnihon-c.co.jp/common/img/ir/library/2026/20260512_01.pdf) | TAKARA PRINTING | 6, 7, 8 | Japanese GAAP, construction accounts, revenue and cost split by business |

Each source contributes its consolidated balance sheet over both pages and its income or
comprehensive income statement: 12 pages and 618 values. Annotations are single-assistant
transcriptions checked against every rendered page. A text-layer listing independent of `jpfs`
served only as a transcription aid. The gold's own totals were checked against their members
within display rounding. They have not been independently human-adjudicated or validated against
XBRL.

## Accuracy

| Measure | Holdout | Development set, after fixes |
|---|---:|---:|
| Pages | 12 | 25 |
| Strict fact F1 | **86.41%** (534/618) | 82.86% |
| Flat fact F1, ignoring hierarchy | 97.73% | 92.27% |
| Row-path F1 | 86.38% | 81.59% |
| Correct headers | **12/12** | 22/25 |
| Exact pages | **8/12** | 16/25 |
| Auto-accepted pages | 4 | 5 |
| Auto-accepted pages that are wrong | **1** | 0 |
| Auto-accepted facts, wrong | **6 of 224** | 0 of 258 |

| Page | Correct / gold | Strict F1 | Flat F1 | Exact page | State |
|---|---:|---:|---:|---|---|
| JSF 61: assets | 54/60 | 90.00% | 90.00% | No | **verified** |
| JSF 62: liabilities, continuation | 70/70 | 100% | 100% | Yes | verified |
| JSF 63: income | 94/94 | 100% | 100% | Yes | needs_review |
| NRI 81: assets | 26/32 | 81.25% | 100% | No | needs_review |
| NRI 82: liabilities and equity, continuation | 0/54 | 0% | 100% | No | needs_review |
| NRI 83: comprehensive income | 30/48 | 62.50% | 83.33% | No | needs_review |
| ARE 57: assets | 34/34 | 100% | 100% | Yes | needs_review |
| ARE 58: liabilities and equity, continuation | 46/46 | 100% | 100% | Yes | needs_review |
| ARE 59: income with EPS | 36/36 | 100% | 100% | Yes | needs_review |
| Shin Nihon 6: assets | 46/46 | 100% | 100% | Yes | verified |
| Shin Nihon 7: liabilities, continuation | 48/48 | 100% | 100% | Yes | verified |
| Shin Nihon 8: income | 50/50 | 100% | 100% | Yes | needs_review |

## Wrong acceptance

JSF 61 is `verified` with six wrong facts. Their values, periods, units and hierarchy are correct,
but three labels carry stray commas: 有価証券,, 営業貸付金,, 投資有価証券,,,. Those rows have
footnote markers inside their value cells, such as ※１,※５. The parser removes the ※ markers but
leaves the commas between them in the label. All 14 accounting checks pass, because the numbers
are right and no check reads label text. The design names this blind spot: label errors are
invisible to arithmetic.

| Wrong-acceptance rate | Observed | 95% interval (Clopper-Pearson) |
|---|---:|---|
| Auto-accepted pages, holdout | 1/4 = 25% | 0.6% to 80.6% |
| Auto-accepted pages, development and holdout | 1/9 = 11% | 0.3% to 48.2% |
| Auto-accepted facts, holdout | 6/224 = 2.7% | 1.0% to 5.7% |

The fact-level interval assumes independent facts; all six come from one page, so the real
uncertainty is wider. On any reading the design's target of 0.1% wrong among accepted facts is not
met, and it cannot be demonstrated on samples this small.

## Errors by cause

| Cause | Facts missed | Pages | Accepted? |
|---|---:|---|---|
| Commas from in-cell footnote markers left in labels | 6 | JSF 61 | **Yes** |
| Totals printed at their section heading's indentation | 6 | NRI 81 | No |
| Section headings at the same indentation (負債及び資本 above 負債) | 54 | NRI 82 | No |
| Labels wrapped with the value on the middle line; OCI items at their subsection heading's indentation | 18 | NRI 83 | No |

Values are almost always read correctly (97.73% ignoring hierarchy); the misses are row identity.
Five exact pages were still sent to review. On JSF 63 and Shin Nihon 8, a wrongly derived
法人税等合計 constraint fails. On the ARE pages, comma-separated note numbers such as ７,32 are
flagged as unreadable figures. Automation on correct pages is therefore 3 of 8.

## What generalised and what did not

- **Generalised:** headers on every page, including the four continuation pages, which inherit
  their titles; EPS in 円 with decimals (ARE 59 is exact); expenses printed as negatives;
  construction and securities-finance accounts; EDINET and Antenna House layouts when indentation
  expresses the hierarchy.
- **Did not:** footnote markers inside value cells, which reach labels and were accepted;
  hierarchy that indentation does not express (NRI); wrapped labels; note-number lists; flat
  tax lines.

## Reproduce

```bash
uv run python -m jpfs.evaluation.corpus --download \
  --manifest data/benchmark-holdout/manifest.json --out out/benchmark-holdout
```

The [snapshot](benchmark-holdout-results.json) records page scores, verifier reasons and the parser
and annotation fingerprints. The generated report in `out/` also lists every missing and unexpected
fact.

This holdout is now spent. Fixing the JSF labels would be development on these pages, which would
turn them into regression cases. An unbiased measurement of the next parser needs another fresh
holdout or XBRL-aligned gold, as section 7 of the design proposes.
