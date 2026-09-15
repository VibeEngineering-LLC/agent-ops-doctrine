# -*- coding: utf-8 -*-
import sys
from pathlib import Path
sys.path.insert(0, r"<home>\.claude\skills\doc-extract\scripts")
sys.path.insert(0, r"<home>\.claude\skills\radon-library\scripts")
import doc_extract as dx, convert as cv, corpus
F = {".pdf": "pdf_text_and_scanflag", ".xls": "sheet_text", ".xlsx": "sheet_text",
     ".xlsm": "sheet_text", ".pptx": "pptx_text", ".csv": "csv_text"}
checked = mism = 0
for it in corpus.walk_corpus():
    fn = F.get(it.ext)
    if not fn:
        continue
    a = getattr(dx, fn)(it.path); b = getattr(cv, fn)(it.path)
    checked += 1
    if a != b:
        mism += 1; print("MISMATCH", it.doc_id, file=sys.stderr)
print(f"SOFFICE_exists={dx.SOFFICE.exists()} checked={checked} mismatches={mism}")
