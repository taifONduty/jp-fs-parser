"""Parse pages of Japanese financial-statement PDFs into verified tables of typed facts."""

from jpfs.pipeline import Result, parse_pdf

__all__ = ["Result", "parse_pdf"]
