# Extraction-engine comparison

Measured on 27 October 2026. All three engines ran on the same **49 selected pages from
16 issuers**, with **2,765 gold facts**. Geometry achieved the highest strict fact F1 and the
most exact pages. Its verifier accepted 15 pages, all exact in this run. TableFormer accepted
one incorrect page; GLM-OCR accepted 11 incorrect pages out of 13 accepted.

The [report snapshots](benchmark-engines/) contain every page score, missing and unexpected
fact, verifier reason, and parser/annotation fingerprint. They are exact copies of the 12
completed runner reports, not rounded table transcriptions. All record parser revision
`5ebf99c53c1bcecae53d52b03a44a6cc59543864`; publication and comparison tooling do not change
the extraction code used for these measurements.

## Compared pipelines

| Engine | Table reader | Common stages |
|---|---|---|
| `geometry` | pdfplumber words and vector rules; right-aligned amounts, indentation and named totals | Typed values, hierarchy, continuation metadata, rounding inference, accounting checks and export |
| `docling-tableformer` | Docling layout detection and TableFormer `ACCURATE`; cell matching enabled, OCR disabled | Same stages after the grid is converted to typed rows |
| `docling-glmocr` | Docling layout detects crops; GLM-OCR reads HTML tables from their pixels; PDF text supplies context and row indentation | Same stages after the grid is converted to typed rows |

This is a comparison of the implemented adapters and their shared downstream stages. It does
not isolate model accuracy from layout detection, grid conversion or hierarchy construction.
The GLM-OCR path is not scan-only: its context and indentation still depend on PDF text.

### Environment and settings

The run used macOS on Apple silicon and Python 3.12.11, with pdfplumber 0.11.10, Docling 2.143.0
and mlx-vlm 0.7.10. The [environment record](benchmark-engines/environment.json) includes the
other installed package versions and the lockfile hash.

GLM-OCR used `mlx-community/GLM-OCR-bf16` through MLX, the prompt `Table Recognition:`,
temperature 0, and a 6,000-token output limit. Table crops were rendered at 2.5 pixels per PDF
point with a 4-point margin. The cached model revision was
`24f15402e83baa0a80eeeaecf5480e172abc6f2e`.

The adapter loads model weights by repository name, not a pinned revision. The cached revision
is recorded for inspection; a future upstream model change can alter a rerun despite the same
Python lockfile. This benchmark measures correctness, not latency, memory or cost.

## Corpora and scoring

| Report key | Manifest | Pages | Gold facts | Interpretation |
|---|---|---:|---:|---|
| `first` | `data/benchmark/manifest.json` | 11 | 592 | Original challenge batch; later used for development |
| `expansion` | `data/benchmark-expansion/manifest.json` | 14 | 741 | Harder layouts, quarterly statements and account-form pages; later used for development |
| `holdout` | `data/benchmark-holdout/manifest.json` | 12 | 618 | First unseen-issuer batch; later used for label and hierarchy fixes |
| `holdout-2` | `data/benchmark-holdout-2/manifest.json` | 12 | 814 | Latest geometry holdout, selected and annotated before its first parser run |

Each manifest pins source URLs, PDF hashes, selected pages and annotation conventions. The
[original scoring protocol](benchmark.md#gold-and-scoring) defines the strict fact key:
full row path, period dates, column dimension, display unit and typed value. Flat matching
keeps only the leaf label. A page is exact only when all rows, facts and headers match.
Missing outputs remain in the denominator; duplicates count against precision.

Auto-accepted means `verified` or `accepted_with_warnings`. A wrong accepted page is an
accepted page that is not exact. Wrong accepted facts are unmatched strict facts emitted
by accepted tables. A page can be wrong solely because of its headers, so these are separate
counts. F1 is pooled from matched, predicted and gold counts, not averaged across pages or
corpora.

The latest holdout's first geometry measurement remains in its
[original report](benchmark-holdout-2.md). The other three corpora have informed parser fixes;
their current scores, and the pooled comparison below, are regression results. These are
purposively selected pages, not a representative sample of all Japanese filings. The gold
was transcribed by one assistant and checked against rendered pages, without independent
human adjudication or XBRL validation.

## Results

The following tables are generated from the checked-in JSON snapshots with
`python -m jpfs.evaluation.compare docs/benchmark-engines`.

### holdout-2

| Engine | Strict fact F1 | Flat fact F1 | Row-path F1 | Exact pages | Correct headers | Auto-accepted pages | Wrong accepted pages | Wrong accepted facts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| geometry | 99.51% | 100.00% | 99.57% | 11/12 | 12/12 | 5 | 0 | 0 of 318 |
| docling-tableformer | 99.20% | 99.69% | 99.25% | 10/12 | 12/12 | 3 | 0 | 0 of 184 |
| docling-glmocr | 78.30% | 89.61% | 80.04% | 1/12 | 11/12 | 2 | 2 | 8 of 148 |

### holdout

| Engine | Strict fact F1 | Flat fact F1 | Row-path F1 | Exact pages | Correct headers | Auto-accepted pages | Wrong accepted pages | Wrong accepted facts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| geometry | 100.00% | 100.00% | 100.00% | 12/12 | 12/12 | 4 | 0 | 0 of 224 |
| docling-tableformer | 90.32% | 99.10% | 90.73% | 8/12 | 12/12 | 6 | 1 | 36 of 260 |
| docling-glmocr | 86.75% | 91.36% | 89.38% | 0/12 | 9/12 | 5 | 5 | 18 of 206 |

### first

| Engine | Strict fact F1 | Flat fact F1 | Row-path F1 | Exact pages | Correct headers | Auto-accepted pages | Wrong accepted pages | Wrong accepted facts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| geometry | 85.13% | 92.99% | 89.81% | 8/11 | 10/11 | 2 | 0 | 0 of 88 |
| docling-tableformer | 82.04% | 95.77% | 86.36% | 8/11 | 10/11 | 3 | 0 | 0 of 138 |
| docling-glmocr | 73.59% | 89.79% | 76.95% | 2/11 | 10/11 | 3 | 2 | 8 of 158 |

### expansion

| Engine | Strict fact F1 | Flat fact F1 | Row-path F1 | Exact pages | Correct headers | Auto-accepted pages | Wrong accepted pages | Wrong accepted facts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| geometry | 92.53% | 92.53% | 87.41% | 12/14 | 12/14 | 4 | 0 | 0 of 236 |
| docling-tableformer | 87.27% | 91.35% | 80.92% | 7/14 | 11/14 | 3 | 0 | 0 of 170 |
| docling-glmocr | 68.09% | 75.72% | 63.56% | 2/14 | 9/14 | 3 | 2 | 8 of 170 |

### all corpora

| Engine | Strict fact F1 | Flat fact F1 | Row-path F1 | Exact pages | Correct headers | Auto-accepted pages | Wrong accepted pages | Wrong accepted facts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| geometry | 94.73% | 96.58% | 94.37% | 43/49 | 46/49 | 15 | 0 | 0 of 866 |
| docling-tableformer | 90.47% | 96.59% | 89.64% | 33/49 | 45/49 | 15 | 1 | 36 of 752 |
| docling-glmocr | 76.61% | 86.50% | 76.81% | 5/49 | 39/49 | 13 | 11 | 42 of 682 |

## What failed

**Wrong labels can pass arithmetic.** GLM-OCR read `建設仮勘定` as `設設仮勘定`,
`資本剰余金` as `資本剩余金`, and `現金及び現金同等物` as `現金及現金同等物`.
These are clean-looking labels, and their amounts can still balance. Across all corpora,
42 of its 682 accepted facts fail strict matching, on 11 incorrectly accepted pages.

**Merged headings change many facts at once.** On `holdout/nri_liabilities`, TableFormer
merged `負債` and `流動負債` into `負債流動負債`. Only 18 of 54 strict facts matched, yet
the page was accepted. Its 36 incorrect paths account for all of TableFormer's incorrect
accepted facts in this run.

**Reading numbers does not recover every hierarchy.** Geometry's latest holdout has 100%
flat fact F1 but 99.51% strict fact F1. Four facts on DISCO's combined income/comprehensive
income page belong to a same-indent （内訳） group whose children the parser did not nest.
The page stayed in review. Other hierarchy and dimensional-column errors remain in the
older batches.

**Pixels do not solve every difficult page.** Every engine scores zero strict matches on
the Bank of Japan's two account-form pages. GLM-OCR also scores zero on Capcom's first cash
flow page and Rakuten's income page. Some model runs miss a table entirely; the benchmark
still scores those selected pages rather than dropping them.

**Acceptance coverage is limited.** Geometry's zero incorrect accepts covers 15/49 pages
and 866 accepted facts, not all 49 pages. Many exact pages remain in review because the
verifier cannot establish their accounting relationships. This result does not establish
a safe acceptance threshold for new filings.

## Reproduce

To print the saved results, no PDF downloads or model weights are needed:

```bash
uv sync --locked
uv run python -m jpfs.evaluation.compare docs/benchmark-engines
```

To repeat all 12 runs, use Apple silicon macOS, Python 3.12+, uv and curl. The `glmocr` extra
includes the dependencies for both model engines. First use downloads model weights and
public PDFs; subsequent runs check and reuse cached PDFs.

```bash
uv sync --locked --extra glmocr

for spec in first:benchmark expansion:benchmark-expansion holdout:benchmark-holdout holdout-2:benchmark-holdout-2; do
  corpus=${spec%%:*}
  manifest="data/${spec#*:}/manifest.json"
  for engine in geometry docling-tableformer docling-glmocr; do
    uv run --locked --extra glmocr python -m jpfs.evaluation.corpus --download \
      --engine "$engine" --manifest "$manifest" --out "out/engines/$engine/$corpus"
  done
done

uv run python -m jpfs.evaluation.compare out/engines
```

On another platform, run geometry or TableFormer separately, for example:

```bash
uv run --locked --extra docling python -m jpfs.evaluation.corpus --download \
  --engine docling-tableformer --manifest data/benchmark-holdout-2/manifest.json \
  --out out/engines/docling-tableformer/holdout-2
```

The runner verifies each source PDF against its manifest, retains missing pages in scoring,
and records parser and annotation hashes. Outputs remain under ignored `out/`; only the
frozen annotations and report snapshots are checked in. The default test suite runs offline
and does not load model weights. Rerunning extraction is separate from printing these saved
scores.
