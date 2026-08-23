# -*- coding: utf-8 -*-
"""Markdown → HTML в вёрстке документа (стиль MS Word).

Вызов:
    python md2html.py ФАЙЛ [ФАЙЛ ...] [--preset doc|article] [--title "Заголовок"]
                      [--out ПУТЬ] [--toc] [--nbsp] [--stdout]

Умолчания: --preset doc, выход рядом с исходником (.md → .html), заголовок из первого H1.
Кодировка на чтение и запись — UTF-8 явно (умолчание Windows портит кириллицу).
"""
import argparse
import pathlib
import re
import sys

try:
    import markdown
except ImportError:
    sys.exit("Нет пакета markdown. Установить: uv pip install markdown  (или pip install markdown)")

# --- Пресеты вёрстки -------------------------------------------------------
# doc     — внутренний документ, отчёт, конспект: плотнее, шире, как страница Word.
# article — публикуемый текст: уже колонка и крупнее кегль, комфортнее для чтения подряд.
PRESETS = {
    "doc": {"width": "1400px", "size": "15px", "lead": "1.55", "h1": "26px", "h2": "20px", "h3": "17px"},
    "article": {"width": "1100px", "size": "17px", "lead": "1.62", "h1": "30px", "h2": "23px", "h3": "19px"},
}

CSS = """
:root {{ color-scheme: light; }}
body {{ font-family: "Segoe UI", Calibri, "Helvetica Neue", sans-serif;
       font-size: {size}; line-height: {lead}; color: #222;
       max-width: {width}; margin: 0 auto; padding: 40px 56px; background: #fff; }}
h1 {{ font-size: {h1}; font-weight: 600; margin: 0 0 18px; }}
h2 {{ font-size: {h2}; font-weight: 600; margin: 34px 0 12px;
     border-bottom: 2px solid #2f5b8f; padding-bottom: 4px; }}
h3 {{ font-size: {h3}; font-weight: 600; margin: 24px 0 8px; color: #2f5b8f; }}
h4 {{ font-size: 1em; font-weight: 600; margin: 18px 0 6px; color: #444; }}
p, li, dd {{ text-align: justify; text-justify: inter-word;
           -webkit-hyphens: auto; -ms-hyphens: auto; hyphens: auto;
           orphans: 2; widows: 2; }}
td {{ text-align: left; }}
li {{ margin-bottom: 4px; }}
ul, ol {{ padding-left: 26px; }}
table {{ border-collapse: collapse; width: 100%; margin: 14px 0 22px;
        display: block; overflow-x: auto; }}
th {{ background: #2f5b8f; color: #fff; text-align: left; padding: 7px 11px;
     font-weight: 600; font-size: 0.93em; }}
td {{ border: 1px solid #c9d4e0; padding: 7px 11px; vertical-align: top; font-size: 0.93em; }}
tr:nth-child(even) td {{ background: #f3f6fa; }}
code {{ font-family: Consolas, "Cascadia Mono", monospace; font-size: 0.87em;
       background: #f0f0ec; padding: 0 4px; border-radius: 3px; }}
pre {{ background: #f6f6f2; border: 1px solid #ddd; border-radius: 6px;
      padding: 12px 16px; overflow-x: auto; }}
pre code {{ background: none; padding: 0; font-size: 0.85em; }}
blockquote {{ border-left: 4px solid #d9a62e; background: #fdf6e3;
             margin: 16px 0; padding: 8px 16px; }}
blockquote p {{ margin: 6px 0; }}
img {{ max-width: 100%; height: auto; }}
hr {{ border: none; border-top: 1px solid #ccc; margin: 28px 0; }}
a {{ color: #2f5b8f; }}
sup {{ line-height: 0; }}
.toc {{ background: #f7f9fc; border: 1px solid #dbe3ec; border-radius: 6px;
       padding: 10px 18px; margin: 0 0 26px; font-size: 0.95em; }}
.toc ul {{ margin: 6px 0; }}
.footnote {{ font-size: 0.9em; color: #555; border-top: 1px solid #ddd; margin-top: 32px; }}
@media (max-width: 1000px) {{ body {{ padding: 24px 18px; }} }}
@media print {{
  body {{ max-width: none; padding: 0; font-size: 11pt; }}
  h1, h2, h3, h4 {{ page-break-after: avoid; }}
  table, pre, blockquote, img {{ page-break-inside: avoid; }}
  a {{ color: #000; text-decoration: none; }}
  @page {{ margin: 20mm 18mm; }}
}}
"""

TPL = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""

EXTENSIONS = ["tables", "fenced_code", "sane_lists", "toc", "attr_list",
              "def_list", "footnotes", "admonition", "smarty", "md_in_html"]

# Кавычки-ёлочки и тире вместо англоязычных умолчаний smarty.
EXT_CONFIG = {
    "smarty": {"substitutions": {
        "left-double-quote": "&laquo;", "right-double-quote": "&raquo;",
        "left-single-quote": "&bdquo;", "right-single-quote": "&ldquo;",
        "ndash": "&ndash;", "mdash": "&mdash;",
    }},
    "toc": {"permalink": False},
}

# Неразрывный пробел: число↔единица, инициалы, «стр. 12», «рис. 3», «§ 4».
NBSP_RULES = [
    (re.compile(r"(?<=\d)\s+(%|‰|°C|К|кг|г|мг|мкг|т|км|м|см|мм|мкм|нм|"
                r"ч|мин|с|мс|мкс|нс|Гц|кГц|МГц|ГГц|"
                r"эВ|кэВ|МэВ|ГэВ|Бк|кБк|МБк|Ки|Зв|мЗв|мкЗв|Гр|мГр|"
                r"В|кВ|мВ|А|мА|мкА|Вт|кВт|Дж|кДж|Па|кПа|МПа|л|мл|м²|м³|имп|шт|руб)(?=[\s.,;:)\]/]|$)"), "\u00a0\\1"),
    (re.compile(r"\b(стр|рис|табл|гл|разд|прил|п|пп|см|ср)\.\s+(?=\d)"), "\\1.\u00a0"),
    (re.compile(r"(§+)\s+(?=\d)"), "\\1\u00a0"),
]


def apply_nbsp(text: str) -> str:
    """Расставить неразрывные пробелы вне кодовых блоков и inline-кода."""
    parts = re.split(r"(```.*?```|`[^`\n]*`)", text, flags=re.S)
    for i in range(0, len(parts), 2):          # чётные — вне кода
        for rx, repl in NBSP_RULES:
            parts[i] = rx.sub(repl, parts[i])
    return "".join(parts)


def extract_title(text: str, fallback: str) -> str:
    m = re.search(r"^\#\s+(.+?)\s*$", text, flags=re.M)
    if m:
        return re.sub(r"[*`_]", "", m.group(1)).strip()
    return fallback


def convert(src: pathlib.Path, preset: str, title: str | None,
            out: pathlib.Path | None, toc: bool, nbsp: bool) -> str:
    text = src.read_text(encoding="utf-8")
    doc_title = title or extract_title(text, src.stem)
    if nbsp:
        text = apply_nbsp(text)
    if toc:
        text = "[TOC]\n\n" + text

    md = markdown.Markdown(extensions=EXTENSIONS, extension_configs=EXT_CONFIG)
    body = md.convert(text)
    if toc:
        body = body.replace('<div class="toc">', '<div class="toc"><b>Содержание</b>', 1)

    html = TPL.format(title=doc_title, css=CSS.format(**PRESETS[preset]), body=body)
    if out is None:
        return html
    out.write_text(html, encoding="utf-8")
    return html


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown → HTML в вёрстке документа")
    ap.add_argument("files", nargs="+", help="исходные .md")
    ap.add_argument("--preset", choices=sorted(PRESETS), default="doc",
                    help="doc — внутренний документ (по умолчанию), article — публикуемый текст")
    ap.add_argument("--title", help="заголовок вкладки; по умолчанию первый H1")
    ap.add_argument("--out", help="путь выхода (только при одном входном файле)")
    ap.add_argument("--toc", action="store_true", help="вставить оглавление")
    ap.add_argument("--nbsp", action="store_true", help="неразрывные пробелы: число↔единица, стр. 12, § 4")
    ap.add_argument("--stdout", action="store_true", help="печатать HTML вместо записи файла")
    a = ap.parse_args()

    files = [pathlib.Path(f) for f in a.files]
    missing = [f for f in files if not f.is_file()]
    if missing:
        return print("Нет файла:", *missing, sep="\n  ") or 2
    if a.out and len(files) > 1:
        return print("--out допустим только при одном входном файле") or 2

    for f in files:
        out = None if a.stdout else (pathlib.Path(a.out) if a.out else f.with_suffix(".html"))
        html = convert(f, a.preset, a.title, out, a.toc, a.nbsp)
        if a.stdout:
            sys.stdout.write(html)
        else:
            print(f"OK  {out}  ({len(html)} Б, пресет {a.preset})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
