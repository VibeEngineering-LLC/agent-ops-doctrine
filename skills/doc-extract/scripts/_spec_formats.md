You are writing ONE complete Python module named `formats.py` inside the package `doc_extract`.

OUTPUT RULES (critical):
- Output ONLY the Python source code. No markdown fences, no ``` , no explanation before or after.
- The VERY FIRST line must be exactly: # -*- coding: utf-8 -*-
- Target Python 3.11+ on Windows. Write real bodies (no TODO/pass). Keep under ~120 lines.

PURPOSE:
`doc_extract.formats` holds corpus-agnostic, per-file text-extraction primitives relocated verbatim
from radon-library/scripts/convert.py. Each function takes a pathlib.Path and returns text, with NO
project/corpus dependency. Preserve the EXACT logic below: these outputs are byte-compared against the
originals and any deviation is a regression.

IMPORTS AND SETUP (do exactly this):
- `import sys`; `from pathlib import Path`.
- `import fitz`  (PyMuPDF), at module top.
- Wrap `sys.stdout.reconfigure(encoding="utf-8")` in try/except Exception: pass.
- python-pptx, xlrd, openpyxl are imported LAZILY inside the functions that need them, never at module top.

FUNCTIONS TO IMPLEMENT (exact logic):

1. `pdf_text_and_scanflag(path: Path, max_pages: int = 200) -> tuple[str, bool, int]`
   Wrap the WHOLE body in try/except Exception returning ("", True, 0).
   - `doc = fitz.open(str(path))`; `n_pages = doc.page_count`.
   - `text_parts = []`; `empty_pages = 0`.
   - For `i in range(min(n_pages, max_pages))`:
       `page_text = doc.load_page(i).get_text("text")`; `stripped_text = page_text.strip()`.
       if stripped_text: `text_parts.append(stripped_text)` else: `empty_pages += 1`.
   - `joined_text = "\n\n".join(text_parts)`; `total_chars = len(joined_text)`; `pages_examined = min(n_pages, max_pages)`.
   - `is_scan = False`.
     if `n_pages > 0 and total_chars == 0`: `is_scan = True`.
     elif `pages_examined > 0`: `avg_chars_per_page = total_chars / pages_examined if pages_examined > 0 else 0`;
       `empty_ratio = empty_pages / pages_examined`; if `avg_chars_per_page < 50 or empty_ratio > 0.7`: `is_scan = True`.
   - `doc.close()`; return `(joined_text, is_scan, n_pages)`.

2. `pptx_text(path: Path) -> str`
   - try: `from pptx import Presentation`; `prs = Presentation(str(path))`; `slides_text = []`.
     For `slide in prs.slides`: `slide_text = []`.
        For `shape in slide.shapes`: if `hasattr(shape, "has_text_frame") and shape.has_text_frame`:
           for `paragraph in shape.text_frame.paragraphs`: if `paragraph.text.strip()`: `slide_text.append(paragraph.text)`.
        if `slide.notes_slide and slide.notes_slide.notes_text_frame`:
           for `paragraph in slide.notes_slide.notes_text_frame.paragraphs`: if `paragraph.text.strip()`:
              `slide_text.append(f"Notes: {paragraph.text}")`.
        `slides_text.append("\n".join(slide_text))`.
     return `"\n\n---\n\n".join(slides_text)`.
   - `except ImportError: return ""`; `except Exception: return ""`.

3. `csv_text(path: Path, max_lines: int = 3000) -> str`
   - try: open `path` in "rb", read into `content`. If `content.startswith(b"\xef\xbb\xbf")`: `content = content[3:]`.
     `text = content.decode("utf-8", errors="replace")`. `lines = text.splitlines()[:max_lines]`. return `"\n".join(lines)`.
   - except Exception: return "".

4. `sheet_text(path: Path, max_rows: int = 5000) -> str`
   Wrap the WHOLE body in try/except Exception returning "".
   - `ext = path.suffix.lower()`; `parts = []`.
   - if `ext == ".xls"`: `import xlrd`; `book = xlrd.open_workbook(str(path))`; for `sheet in book.sheets()`:
       `parts.append(f"## Sheet: {sheet.name}")`; for `r in range(min(sheet.nrows, max_rows))`:
         `cells = [str(sheet.cell_value(r, c)) for c in range(sheet.ncols)]`;
         `non_empty_cells = [c.strip() for c in cells if c is not None and c.strip()]`;
         if non_empty_cells: `parts.append("\t".join(non_empty_cells))`.
   - else (.xlsx/.xlsm): `import openpyxl`; `wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)`;
       for `ws in wb.worksheets`: `parts.append(f"## Sheet: {ws.title}")`;
         for `row in ws.iter_rows(values_only=True)`: `cells = [str(c) for c in row if c is not None and str(c).strip()]`;
           if cells: `parts.append("\t".join(cells))`; then after the loop `wb.close()`.
   - return `"\n".join(parts)`.

Now output the complete formats.py source, starting with the coding line.