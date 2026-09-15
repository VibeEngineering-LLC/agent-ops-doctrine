You are writing ONE complete Python module named `ocr.py` inside the package `doc_extract`.

OUTPUT RULES (critical):
- Output ONLY the Python source code. No markdown fences, no ``` , no explanation.
- The VERY FIRST line must be exactly: # -*- coding: utf-8 -*-
- Target Python 3.11+ on Windows. Real bodies. Keep under ~60 lines.

PURPOSE:
`doc_extract.ocr` holds corpus-agnostic OCR primitives relocated verbatim from radon-library/scripts/ocr.py.
ONLY the two pure functions below: NO write_md, NO main, NO argparse, NO corpus import. Preserve EXACT
logic (byte-compared against the originals).

IMPORTS AND SETUP (do exactly this):
- `import sys, os, io`; `from pathlib import Path`.
- `import fitz`; `import pytesseract`; `from PIL import Image`.
- At module load:
    `pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"`
    `os.environ.setdefault("TESSDATA_PREFIX", r"C:\Users\<you>\AppData\Local\tessdata")`
- Wrap `sys.stdout.reconfigure(encoding="utf-8")` in try/except Exception: pass.

FUNCTIONS TO IMPLEMENT (exact logic):

1. `check_langs() -> list[str]`
   - try: `langs = pytesseract.get_languages(config="")`; print `"Available languages:", ", ".join(langs)` to `sys.stderr`;
     if "rus" in langs print "Russian language available" else "Russian language NOT available" (to stderr);
     if "eng" in langs print "English language available" else "English language NOT available" (to stderr); return langs.
   - except Exception as e: print `f"Error checking languages: {e}"` to stderr; return [].

2. `ocr_pdf(path: Path, dpi: int = 300, max_pages: int = 120, lang: str = "rus+eng") -> tuple[str, int]`
   - try: `doc = fitz.open(str(path))`; `n = min(doc.page_count, max_pages)`; `parts = []`.
     For `i in range(n)`: `page = doc.load_page(i)`; `pix = page.get_pixmap(dpi=dpi)`;
       `img = Image.open(io.BytesIO(pix.tobytes("png")))`; `txt = pytesseract.image_to_string(img, lang=lang)`;
       if `txt.strip()`: `parts.append(f"<!-- page {i+1} -->\n{txt.strip()}")`.
     `doc.close()`; return `("\n\n".join(parts), n)`.
   - except Exception as e: print `f"Error OCRing {path}: {e}"` to stderr; return `("", 0)`.

Now output the complete ocr.py source, starting with the coding line.