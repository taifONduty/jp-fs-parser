"""The Docling engines: each turns one PDF page into Grids.

docling-tableformer: Docling's layout model and TableFormer over the PDF text layer.
docling-glmocr: Docling's layout model finds each table; GLM-OCR reads the table crop from pixels
into an HTML table, whose rows are grounded to the text layer for their indentation only.
"""

import tempfile
from collections.abc import Iterator
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium
from docling.datamodel.base_models import InputFormat
from docling.datamodel.document import DoclingDocument
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import TableItem, TextItem

from jpfs.engines.grid import Grid, GridCell, grounded, parse_html_table

GLMOCR_REPO = "mlx-community/GLM-OCR-bf16"
GLMOCR_PROMPT = "Table Recognition:"
GLMOCR_MAX_TOKENS = 6000
RENDER_SCALE = 2.5  # pixels per point for the crops GLM-OCR reads
CROP_MARGIN = 4.0  # pt around the table box the layout model returns


def _converter(table_structure: bool) -> DocumentConverter:
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=table_structure)
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.table_structure_options.do_cell_matching = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _tables_with_context(doc: DoclingDocument) -> Iterator[tuple[TableItem, str]]:
    """Each table with the page text read since the previous table (titles, unit lines)."""
    context: list[str] = []
    for item, _ in doc.iterate_items():
        if isinstance(item, TableItem):
            yield item, "\n".join(context)
            context = []
        elif isinstance(item, TextItem):
            context.append(item.text)


class TableFormer:
    def __init__(self) -> None:
        self.converter = _converter(table_structure=True)

    def grids(self, pdf: str, page: int) -> list[Grid]:
        doc = self.converter.convert(pdf, page_range=(page, page)).document
        return [
            Grid(
                tuple(
                    tuple(GridCell(cell.text, cell.bbox.l if cell.bbox else None) for cell in row)
                    for row in table.data.grid
                ),
                context,
            )
            for table, context in _tables_with_context(doc)
        ]


class GlmOcr:
    def __init__(self) -> None:
        from mlx_vlm import load
        from mlx_vlm.prompt_utils import apply_chat_template

        self.converter = _converter(table_structure=False)
        self.model, self.processor = load(GLMOCR_REPO)
        self.prompt = apply_chat_template(
            self.processor, self.model.config, GLMOCR_PROMPT, num_images=1
        )

    def grids(self, pdf: str, page: int) -> list[Grid]:
        doc = self.converter.convert(pdf, page_range=(page, page)).document
        height = doc.pages[page].size.height
        image = pdfium.PdfDocument(pdf)[page - 1].render(scale=RENDER_SCALE).to_pil()
        with pdfplumber.open(pdf) as document:
            words = document.pages[page - 1].extract_words(x_tolerance=1.5)
        grids = []
        for table, context in _tables_with_context(doc):
            box = table.prov[0].bbox.to_top_left_origin(page_height=height)
            top, bottom = box.t - CROP_MARGIN, box.b + CROP_MARGIN
            left, right = box.l - CROP_MARGIN, box.r + CROP_MARGIN
            crop = image.crop(tuple(round(v * RENDER_SCALE) for v in (left, top, right, bottom)))
            inside = [w for w in words if top <= w["top"] <= bottom and left <= w["x0"] <= right]
            grids.append(Grid(grounded(parse_html_table(self._read(crop)), inside), context))
        return grids

    def _read(self, crop) -> str:
        from mlx_vlm import generate

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "table.png"
            crop.save(path)
            out = generate(
                self.model,
                self.processor,
                self.prompt,
                [str(path)],
                max_tokens=GLMOCR_MAX_TOKENS,
                temperature=0.0,
                verbose=False,
            )
        return out.text if hasattr(out, "text") else out
