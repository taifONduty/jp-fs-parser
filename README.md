# jp-fs-parser

Parses Japanese financial-statement PDFs (決算短信, 有価証券報告書) into structured tables.
Each printed amount is tied to its row hierarchy, period, unit and sign. Accounting checks
report which tables can be accepted and which need review.

Three extraction engines are available. **Geometry is the default and performed best on the
49-page benchmark:** 94.73% strict fact F1 and 43 exact pages. The Docling engines are comparison
paths; passing their accounting checks does not guarantee correct labels or hierarchy.

The [pipeline design](#pipeline-design) below describes the current implementation. The
[engine comparison](docs/benchmark-engines.md) contains the complete results and failure cases.

## Pipeline design

JPFS reconstructs **financial facts from page evidence**, then checks the accounting
relationships between them. The architecture below follows the design's evidence, typed
representation and verification boundaries. Solid paths describe the implemented geometry
pipeline; dashed blocks and links are proposed extensions.

[![JPFS architecture: page evidence feeds geometry and typed financial identity; continuation context and rounding evidence feed tree-derived accounting checks, followed by explicit states and provenance-bearing exports. Dashed paths show proposed independent vision, taxonomy, XBRL and review feedback.](docs/assets/pipeline.svg)](docs/assets/pipeline.svg)

[Editable Figma source](https://www.figma.com/design/L0qkwSYvyNdRy4lzsIm9Xp?node-id=2-2)
· [Lucide icon license](docs/assets/LICENSE-lucide.txt)

### Page evidence and table reconstruction

The parser hashes the PDF, selects pages and reads the document text. On each selected page,
it de-duplicates glyphs, filters background-coloured content and audits the extracted Unicode.
Words retain their coordinates; dark vector rules supply layout and correction cues. This
page evidence is held in memory and carried into the extracted cells, rather than kept in a
separate persistent evidence store.

Statement titles split pages into table regions. Right-edge clusters of numeric tokens
identify amount columns, which are bound to period headers. The parser separates note markers,
rejoins supported wrapped labels and distinguishes correction underlines from summation rules.
A statement page without usable text or value columns is reported as `failed`.

### Financial identity in one typed representation

The output of reconstruction is a `Table` with a `Header`, dated `Period` columns, and `Row`
objects containing typed `Cell` values. A cell keeps its printed text, exact decimal magnitude,
sign, nil state, correction flag and bounding box. A blank is no cell; a dash is a nil amount;
△0 retains a negative sign. Table units can be overridden by a row, such as EPS in 円 inside
a 百万円 statement.

Rows form a tree. Indentation supplies the first structure, and named closing totals correct
it: `流動資産合計` closes `流動資産`, even when the printed indentation is flat. Roles distinguish
sections, ordinary items, gross values, contras, net amounts and totals. Repeated labels such
as その他 therefore have distinct identities through their complete paths.

For example, a cash value belongs to `資産の部 / 流動資産 / 現金及び預金`, one dated column and
one unit. Reading its digits correctly is insufficient if any of those bindings is wrong.

### Document context and rounding evidence

An untitled continuation can inherit statement metadata from up to four preceding pages,
provided its dated columns and unit agree. The source page is recorded. This carries metadata;
it does not join accounting constraints across pages.

Document-wide rounding notes take precedence. Otherwise, a sign test over the recovered
tables' accounting residuals may establish truncation. If the evidence is insufficient, the
mode remains unknown and checks use the hull of rounding and truncation intervals.

### Accounting verification and coverage

The recovered tree supplies constraints: a closing total sums its members' contributions,
while a net amount combines its gross value and contra rows. This works without a company
account list, but it depends on recovering the correct hierarchy and roles.

Each printed amount represents an interval of possible underlying values. Under truncation,
a positive integer `v` in display units represents `[v, v+1)`. A sum passes when the total's
interval overlaps the sum of its members' intervals. The original sample's current-assets
total exceeds its ten printed components by 2千円; interval checks allow that valid truncation
difference without an arbitrary fixed tolerance.

The verdict also considers incomplete headers, unbound figures, uncovered cells, damaged-looking
labels and the text audit. An arithmetic pass cannot establish that a plausible label or parent
is correct. Each result keeps the checks, uncovered cells and reasons behind its state:

| State | Condition |
|---|---|
| `verified` | All implemented checks pass, with no review reasons or warnings. |
| `accepted_with_warnings` | No review reason remains, but a soft warning is recorded. |
| `needs_review` | A constraint fails or the available evidence is incomplete. |
| `failed` | No amount is bound to a period, or a statement page could not be read. |

### Facts, provenance and proposed extensions

The same typed rows produce JSONL facts, a Markdown table and a full JSON audit record. Geometry
facts include the source PDF hash, page, cell box, correction flags and passing constraints.
Review reasons remain in the output. A cell's box establishes where the text was read; it does
not independently confirm that the PDF's Unicode mapping matches its pixels.

The broader [design](docs/design.pdf), Sections 4–7, proposes additional checks and feedback.
These capabilities are **not implemented**:

| Extension | What it would add |
|---|---|
| Independent vision and grounding | Recognised pixel tokens with boxes, per-cell agreement, and repair restricted to candidates an extractor actually read. |
| Taxonomy concepts and calculation links | Semantic identity and accounting relationships that are not recoverable as simple tree sums. |
| XBRL and prior-filing comparison | Independent checks of values, periods and scale, with restatements handled explicitly. |
| Review feedback | Stored corrections and confirmed mappings for later filings. |

The existing TableFormer and GLM-OCR adapters are **alternative readers for comparison**. They
feed the shared representation and verifier, but do not provide automatic routing, independent
path agreement or constraint-guided repair. Their usage and results are documented below.

| Responsibility | Source |
|---|---|
| Document flow and continuation context | [`pipeline.py`](src/jpfs/pipeline.py), [`assembly.py`](src/jpfs/assembly.py) |
| Page evidence and geometry reconstruction | [`layout.py`](src/jpfs/layout.py) |
| Typed values, dates and row hierarchy | [`model.py`](src/jpfs/model.py), [`text.py`](src/jpfs/text.py), [`structure.py`](src/jpfs/structure.py) |
| Constraints, interval checks and verdict | [`checks.py`](src/jpfs/checks.py), [`verdict.py`](src/jpfs/verdict.py) |
| Provenance and export | [`render.py`](src/jpfs/render.py) |
| Optional comparison readers | [`engines/`](src/jpfs/engines/) |

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

## Limitations

- Account-form layouts, equity matrices and some semantic groups remain unsupported. The
  Bank of Japan's two account-form pages score zero strict matches for every engine here.
- Cross-page assembly looks back up to four pages to recover metadata. It does not verify
  totals whose members span pages.
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

The [design PDF](docs/design.pdf) contains the broader architecture and research. The pipeline
section above distinguishes the implemented subset from its proposed extensions. The project
[chat log](docs/chatlog.md) is also available.
