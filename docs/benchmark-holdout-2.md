# Second fresh holdout: half-year releases and a new typesetting system

Measured on 27 October 2026. The first holdout was spent on the label fix and the hierarchy rules,
so this one measures the parser at `479c8fd`, unchanged, on filings it has never seen. Three of
the four were published in October 2026, after every parser change so far.

**Result: 99.51% strict fact F1 and 11/12 exact pages, with every header correct. Five pages were
auto-accepted, and all five are exact.** The four missed values sit in a （内訳） group whose items
are printed at the group heading's indentation. Every value was read correctly.

## Protocol

1. Four issuers new to the corpus were chosen, along with page types the first holdout lacked:
   half-year (中間) statements, cash flow statements, a February year-end, a non-consolidated
   securities company and a second typesetting system, PRONEXUS WORKS.
2. Pages were selected from text-layer titles and rendered pages, and transcribed, without
   running the parser on these files.
3. The annotations were committed in `f1fd87a` before the first parser run, with annotation
   fingerprint `b0863c24…`.
4. The parser ran once, with the same fingerprint as the
   [hierarchy snapshot](benchmark-holdout-results-hierarchy.json). The runner downloaded all
   four PDFs into a fresh cache and checked them against the pinned hashes.

Nothing was changed after the run. Scoring rules are those of the [first batch](benchmark.md#gold-and-scoring).

## Sources

| Filing | Producer | PDF pages scored | Coverage |
|---|---|---|---|
| [Ajinomoto, 決算短信 FY2026/3](https://data.swcms.net/file/ajinomoto-ir/dam/jcr:6bedb9ff-8b48-4642-94eb-4f066a05fe11/140120260501516433.pdf) | PRONEXUS WORKS | 10, 11, 16 | IFRS, boxed layout, held-for-sale lines under a 小計, three wrapped labels |
| [Seven & i, 中間決算短信 FY2027/2](https://www.release.tdnet.info/inbs/140120261007547460.pdf) | PRONEXUS WORKS | 10, 11, 14 | Japanese GAAP, February year-end, banking lines in the cash flow, three wrapped labels |
| [DISCO, 中間決算短信 FY2027/3](https://www.disco.co.jp/jp/ir/library/doc/fr/fr20261022.pdf) | TAKARA PRINTING | 5, 6, 7 | Japanese GAAP, combined income and comprehensive income, two （内訳） groups |
| [Kosei Securities, 中間決算短信 FY2027/3](https://www.release.tdnet.info/inbs/140120261021554066.pdf) | TAKARA PRINTING | 6, 7, 8 | Non-consolidated securities company, parent rows with breakdowns, 計 totals |

Each source contributes three statement pages: 12 pages and 814 values. Annotations are
single-assistant transcriptions checked against every rendered page, using the same conventions
as the earlier batches. The gold's own totals were checked against their members within display
rounding. They have not been independently human-adjudicated or validated against XBRL.

## Accuracy

| Measure | Result |
|---|---:|
| Strict facts matched | 810 / 814 |
| Strict precision / recall / F1 | 99.51% / 99.51% / **99.51%** |
| Flat fact F1 | 100% |
| Row-path F1 | 99.57% |
| Exact pages | **11 / 12** |
| Correct headers | 12 / 12 |

| Page | Correct / gold values | Exact | Parser state | Checks passed |
|---|---:|---|---|---:|
| Ajinomoto 10: financial position, assets | 36 / 36 | Yes | verified | 8/8 |
| Ajinomoto 11: liabilities and equity | 62 / 62 | Yes | needs_review | 10/12 |
| Ajinomoto 16: cash flow, operating | 48 / 48 | Yes | verified | 4/4 |
| Seven & i 10: balance sheet, assets | 66 / 66 | Yes | verified | 14/14 |
| Seven & i 11: liabilities and net assets | 82 / 82 | Yes | verified | 14/14 |
| Seven & i 14: cash flow | 86 / 86 | Yes | verified | 6/6 |
| DISCO 5: balance sheet | 78 / 78 | Yes | needs_review | 18/20 |
| DISCO 6: income and comprehensive income | 72 / 76 | No | needs_review | 10/12 |
| DISCO 7: cash flow | 74 / 74 | Yes | needs_review | 8/8 |
| Kosei 6: balance sheet, assets | 72 / 72 | Yes | needs_review | 2/2 |
| Kosei 7: liabilities and net assets | 76 / 76 | Yes | needs_review | 16/16 |
| Kosei 8: income | 58 / 58 | Yes | needs_review | 6/6 |

DISCO 6 prints its first （内訳） heading at the indentation of the two items it breaks down. The
gold nests them under it, as in the earlier batches; the parser follows the indentation and
places them at the top level.

## Wrong acceptance

Five pages and 318 facts were auto-accepted, and all are exact. Zero wrong pages out of five has a
95% interval of 0% to 52.2%. Across the first runs of both holdouts, one of nine accepted pages
was wrong, an interval of 0.3% to 48.2%. Six of 542 accepted facts were wrong, 0.4% to 2.4%.
These intervals are still too wide to set an acceptance threshold.

The whole run over all 62 pages of the four filings
([summary](benchmark-holdout-2-full-documents.json)) produced 47 tables. Only the five annotated
pages above were accepted, and every annotated page gives the same output when parsed alone or
within its filing.

## Why the other pages are in review

Each of these is a page whose values are right but which the verifier could not prove, so the
cost is review effort, not wrong data:

- **Kosei 6 to 8** print a parent row with its own value and a breakdown below it, with no
  closing total (トレーディング商品 1,506, then 商品有価証券等 and デリバティブ取引). The tree
  reads these as groups without a closing total, so 66 of 72 cells on page 6 are not covered by
  any check.
- **Ajinomoto 11** prints 親会社の所有者に帰属する持分 as a subtotal without 合計 in its name, so
  資本合計's check counts it twice.
- **DISCO 5** prints both sides of the balance sheet on one page, and the check for 負債純資産合計
  also counts 資産合計 among its members.
- **DISCO 6** fails 法人税等合計, an income-statement step-down that is not a sum of the rows
  above it, as on earlier pages.

## What this adds

This holdout is easier than the first. Earnings releases set statements more plainly than annual
securities reports, and the first holdout's unbiased run scored 86.41% on an older parser. The two
results cannot separate the effect of the fixes from the effect of the layouts. What this one
does show is that the hierarchy rules and wrapped-label joining carried over to a typesetting
system they were not written on. All seven wrapped labels, six of them typeset by Pronexus, and
every total printed at its heading's indentation came out right.

## Reproduce

```bash
uv run python -m jpfs.evaluation.corpus --download \
  --manifest data/benchmark-holdout-2/manifest.json --out out/benchmark-holdout-2

uv run jpfs parse out/benchmark-holdout-2/sources/*.pdf -o out/benchmark-holdout-2/full-document
```

The [snapshot](benchmark-holdout-2-results.json) records page scores, verifier reasons and the
parser and annotation fingerprints. Once any fix is made by looking at these pages, this holdout
becomes a regression set like the first.
