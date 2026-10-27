"""Extraction engines, selectable by name.

geometry: the design's path A, reading tables from the PDF text layer and vector rules.
docling-tableformer and docling-glmocr: Docling's models read the tables instead; everything after
table reading is shared. They need the optional extras (`uv sync --extra docling`, plus
`--extra glmocr` for GLM-OCR on Apple silicon).
"""

from collections.abc import Callable, Collection
from functools import partial
from pathlib import Path

from jpfs.pipeline import Result, parse_pdf

Parser = Callable[[str | Path, Collection[int] | None], list[Result]]
ENGINES = ("geometry", "docling-tableformer", "docling-glmocr")


def parser_for(name: str) -> Parser:
    if name not in ENGINES:
        raise ValueError(f"unknown engine {name!r}; choose from {', '.join(ENGINES)}")
    if name == "geometry":
        return parse_pdf
    extra = "glmocr" if name == "docling-glmocr" else "docling"
    try:
        from jpfs.engines import docling_models, document

        model = docling_models.GlmOcr() if extra == "glmocr" else docling_models.TableFormer()
    except ImportError as error:
        raise RuntimeError(f"engine {name!r} needs `uv sync --extra {extra}`") from error
    return partial(document.parse_pdf, engine=model)
