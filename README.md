# jp-fs-parser

Parses Japanese financial-statement PDFs (決算短信, 有価証券報告書) into structured tables.
Each printed amount is tied to its row hierarchy, period, unit and sign. Accounting checks
report which tables can be accepted and which need review.

Three extraction engines are available. **Geometry is the default and performed best on the
49-page benchmark:** 94.73% strict fact F1 and 43 exact pages. The Docling engines are comparison
paths; passing their accounting checks does not guarantee correct labels or hierarchy.

The [design document](docs/design.pdf) explains the pipeline and evaluation approach. The
[engine comparison](docs/benchmark-engines.md) contains the complete results and failure cases.

## Quick start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv sync --locked
uv run jpfs parse data/balance_sheet_p4.pdf -o out/geometry
uv run jpfs evaluate data/balance_sheet_p4.pdf data/balance_sheet_p4.gold.tsv
```

The included PDF is the original corrected balance-sheet sample. To parse your own filings:

```bash
uv run jpfs parse filing.pdf --pages 4,5 --engine geometry -o out/geometry
```

Page numbers are 1-based PDF positions. Omit `--pages` to process the whole document; pass
multiple PDF paths to process several filings.

### Choose an engine

| Engine | Table extraction | Requirements |
|---|---|---|
| `geometry` | PDF text positions, indentation and vector rules | Default installation; no model weights |
| `docling-tableformer` | Docling layout detection and TableFormer in accurate mode, using PDF text | `docling` extra; downloads model weights on first use |
| `docling-glmocr` | Docling table crops read by GLM-OCR; PDF text supplies context and indentation | `glmocr` extra; Apple silicon macOS, using MLX |

```bash
uv run --extra docling jpfs parse data/balance_sheet_p4.pdf \
  --engine docling-tableformer -o out/tableformer

uv run --extra glmocr jpfs parse data/balance_sheet_p4.pdf \
  --engine docling-glmocr -o out/glmocr
```

All three use the same typed table representation, hierarchy builder, cross-page assembly and
verifier. Engine selection is explicit; there is no automatic fallback. The GLM-OCR adapter
reads table contents from pixels but still depends on PDF text, so it is not a scan-only parser.
The implemented GLM-OCR backend supports Apple silicon only.

### Outputs

Each detected table produces three files under `<out>/<pdf-stem>/`:

| File | Content |
|---|---|
| `p<page>-<n>.facts.jsonl` | One fact per printed cell: row path, period, typed value, yen scale, source and verification |
| `p<page>-<n>.md` | Readable table and review reasons |
| `p<page>-<n>.json` | Full table record, accounting checks, uncovered cells and reasons |

States are `verified`, `accepted_with_warnings`, `needs_review` and `failed`. The first two are
counted as auto-accepted in the benchmark. They describe the checks performed, not a guarantee
that the extraction matches the PDF. The CLI exit code reports command errors; inspect the
exported states to decide which tables need review.

## Benchmark results

Measured on 27 October 2026: **49 pages, 2,765 gold facts, 16 issuers**, with the same frozen
annotations for every engine. All 12 engine/corpus runs completed.

| Engine | Strict fact F1 | Exact pages | Wrong / auto-accepted pages | Wrong / accepted facts |
|---|---:|---:|---:|---:|
| Geometry | **94.73%** | **43/49** | **0/15** | **0/866** |
| Docling + TableFormer | 90.47% | 33/49 | 1/15 | 36/752 |
| Docling + GLM-OCR | 76.61% | 5/49 | 11/13 | 42/682 |

These pooled scores include pages used to develop the parser and should be read as regression
results. The [latest holdout](docs/benchmark-holdout-2.md) was selected and annotated before its
first geometry run: on those 12 pages, geometry scores **99.51% strict fact F1 and 11/12 exact
pages**, versus 99.20% and 10/12 for TableFormer, and 78.30% and 1/12 for GLM-OCR in this comparison.
That holdout contains plainer earnings releases than the first holdout's annual reports.

Geometry accepted 15/49 pages. The rest need review or were marked `failed`. Zero wrong accepts
at this coverage does not establish a production error rate. TableFormer merged two valid headings on
one accepted page, changing 36 fact paths. GLM-OCR produced plausible but incorrect Japanese
labels while preserving amounts, so arithmetic still passed. These results compare the
implemented pipelines on the selected documents, not the underlying models in general.

The annotations were transcribed by one assistant and checked against rendered pages. They
have not been independently human-adjudicated or validated against XBRL. See the
[full comparison](docs/benchmark-engines.md) for per-corpus scores, model settings, report
snapshots and reproduction commands. Earlier measurements remain in the
[first batch](docs/benchmark.md), [expansion](docs/benchmark-expansion.md),
[first holdout](docs/benchmark-holdout.md) and [second holdout](docs/benchmark-holdout-2.md) reports.

### What is scored

- **Strict fact F1:** exact row path, period, column dimension, display unit and typed value.
  Duplicate predictions count against precision. Missing tables count against recall.
- **Flat fact F1:** the same key using only the leaf label, to distinguish hierarchy errors
  from other extraction errors.
- **Exact page:** every row path, fact and header matches, including statement title,
  consolidated scope, correction status, units and period labels/dates.
- **Wrong acceptance:** an auto-accepted page that is not exact, or an accepted fact that
  does not match the strict key.

A dash means a presented line with no balance; a blank means no presented value; △0 is a
negative amount below one display unit. These are different facts. Repeated labels such as
その他 are distinguished by their full paths.

### Reproduce

Print the comparison from the checked-in snapshots without downloading PDFs or model weights:

```bash
uv run python -m jpfs.evaluation.compare docs/benchmark-engines
```

Run the default engine on the latest holdout:

```bash
uv run python -m jpfs.evaluation.corpus --download --engine geometry \
  --manifest data/benchmark-holdout-2/manifest.json \
  --out out/engines/geometry/holdout-2
```

The runner downloads the public filings, checks their pinned SHA-256 values and writes page
records, rendered tables and `report.json`. Generated outputs and cached PDFs stay in `out/`,
which is ignored by Git. The [comparison guide](docs/benchmark-engines.md#reproduce) covers all
three engines and four corpora.

## How it works

| Stage | Implementation |
|---|---|
| Extract tables | `layout.py` for geometry; `engines/docling_models.py` and `engines/grid.py` for model tables |
| Build row hierarchy and roles | `structure.py`: indentation, named closing totals and wrapped labels |
| Parse metadata and values | `text.py`: Japanese/Gregorian dates, units, notes, signs and exact decimals |
| Assemble continuation pages | `assembly.py`: inherit statement metadata when periods and units match |
| Check and decide | `checks.py`, `verdict.py`: accounting constraints, coverage, damaged labels and page state |
| Export | `render.py`: facts, Markdown and full records from the same typed rows |

Geometry clusters the right edges of amounts to find columns, separates note references from
values, and distinguishes correction underlines from summation rules. Its text audit flags
unusable text layers. Model tables enter the common representation through separate adapters.

The verifier derives sums and gross-to-net constraints from the table's own hierarchy, without
per-company rules. A printed number represents an interval of possible values under truncation
or rounding. Checks compare those intervals rather than demand exact displayed sums. A filing's
rounding note takes precedence; otherwise the parser infers the mode from residuals or flags it
as unknown. The [design](docs/design.pdf) gives the interval definitions and inference method.

On the original development page, geometry extracts all 43 rows and 74 facts, recovers both
correction underlines, and passes 20 constraints with every cell covered. Mutation testing on
that page detects 94.8% of digit substitutions and every tested lost sign, but only 45.5% of
adjacent-row swaps. This measures the checks' sensitivity on one table, not extraction accuracy
on new filings. Correct arithmetic can coexist with wrong labels, paths or metadata.

## Limitations

- Account-form layouts, equity matrices and some semantic groups remain unsupported. The
  Bank of Japan's two account-form pages score zero strict matches for every engine here.
- Cross-page assembly carries metadata; it does not verify totals whose members span pages.
- Parent rows followed by breakdowns, unnamed subtotals and income-statement step-downs can
  produce incomplete or incorrect constraints, even when extracted values are correct.
- Label checks detect visible damage, not plausible substitutions. Wrong labels and hierarchy
  can pass verification, as the model runs demonstrate.
- TableFormer uses the text layer with OCR disabled. The GLM-OCR adapter also needs PDF text
  for context and indentation. A model can miss a table entirely; the benchmark still scores
  the selected page. Neither adapter preserves complete cell boxes or correction underlines.
- There is no taxonomy mapping, XBRL cross-check or agreement-based arbitration between engines.
  Scan-only accuracy and arbitrary financial tables have not been established.

## Development

```bash
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run pytest -q
```

The tests are offline; they do not download filings or load model weights. The optional model
engines were exercised separately by the benchmark runs. The frozen annotations live in
`data/benchmark*/`; evaluation and comparison commands live in `src/jpfs/evaluation/`.

The project [chat log](docs/chatlog.md) is also available.
