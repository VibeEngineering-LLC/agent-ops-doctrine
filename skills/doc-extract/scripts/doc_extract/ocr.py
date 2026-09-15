# -*- coding: utf-8 -*-
import sys, os, io
from pathlib import Path
import fitz
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ.setdefault("TESSDATA_PREFIX", r"C:\Users\<you>\AppData\Local\tessdata")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def check_langs() -> list[str]:
    try:
        langs = pytesseract.get_languages(config="")
        print("Available languages:", ", ".join(langs), file=sys.stderr)
        if "rus" in langs:
            print("Russian language available", file=sys.stderr)
        else:
            print("Russian language NOT available", file=sys.stderr)
        if "eng" in langs:
            print("English language available", file=sys.stderr)
        else:
            print("English language NOT available", file=sys.stderr)
        return langs
    except Exception as e:
        print(f"Error checking languages: {e}", file=sys.stderr)
        return []

def ocr_pdf(path: Path, dpi: int = 300, max_pages: int = 120, lang: str = "rus+eng") -> tuple[str, int]:
    try:
        doc = fitz.open(str(path))
        n = min(doc.page_count, max_pages)
        parts = []
        for i in range(n):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            txt = pytesseract.image_to_string(img, lang=lang)
            if txt.strip():
                parts.append(f"<!-- page {i+1} -->\n{txt.strip()}")
        doc.close()
        return ("\n\n".join(parts), n)
    except Exception as e:
        print(f"Error OCRing {path}: {e}", file=sys.stderr)
        return ("", 0)
