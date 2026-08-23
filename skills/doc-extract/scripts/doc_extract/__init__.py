# -*- coding: utf-8 -*-
"""doc_extract - corpus-agnostic document text-extraction primitives.
Relocated from radon-library (2026-06-18) for reuse across skills.
Clean names + radon-legacy aliases are both exported."""
from .formats import pdf_text_and_scanflag, pptx_text, csv_text, sheet_text
from .ocr import ocr_pdf, check_langs
from .legacy import run_libreoffice, SOFFICE

extract_pdf = pdf_text_and_scanflag
extract_pptx = pptx_text
extract_csv = csv_text
extract_sheet = sheet_text

__all__ = ["pdf_text_and_scanflag", "pptx_text", "csv_text", "sheet_text",
           "ocr_pdf", "check_langs", "run_libreoffice", "SOFFICE",
           "extract_pdf", "extract_pptx", "extract_csv", "extract_sheet"]
