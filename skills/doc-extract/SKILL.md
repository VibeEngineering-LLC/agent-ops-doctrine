---
name: doc-extract
description: "Corpus-agnostic примитивы для извлечения plain text из документов: PDF (text layer + scan detect), сканированный PDF через OCR (PyMuPDF + Tesseract rus+eng), legacy Office (.doc/.ppt/.rtf через LibreOffice), .pptx, .csv, spreadsheets (.xls/.xlsx). Importable-функции, своего корпуса нет. Use when a pipeline needs arbitrary office/PDF → text и базового docx/txt/md-экстрактора `docs-rag` не хватает."
---

# doc-extract

Per-файловые **примитивы извлечения текста**, вынесенные из `radon-library`
(2026-06-18) для переиспользования между скиллами. Скилл — это **библиотека функций**,
он не хранит корпус, не пишет отчёты и ничего не оркеструет: walk/реестры/`*_report.json`
остаются в скилле-потребителе (например `radon-library`).

## Слой

```
docs-rag        базовый extract_text: .docx / .txt / .md  (фундамент)
   └─ doc-extract   + PDF (текст-слой + детект скана), OCR скана,
                      legacy .doc/.ppt/.rtf (LibreOffice), .pptx, .csv, .xls/.xlsx/.xlsm
```
doc-extract сидит НАД docs-rag: для .docx/.txt/.md по-прежнему вызывайте
`docs-rag.extract.extract_text`, doc-extract его не дублирует.

## markitdown — turnkey «что угодно → markdown» (+ MCP-сервер)

С 2026-06-19 в окружении есть **Microsoft markitdown 0.1.5** (установлен через `uv tool`):
CLI `C:\Users\<you>\.local\bin\markitdown.exe`, пакет в
`...\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\uv\tools\markitdown\`.
Это готовый конвертер БЕЗ кода: `markitdown <in> -o <out.md>` (или stdout).
Покрытие конвертеров (проверено по `converters\*.py`): docx, pptx, xlsx, pdf, html,
epub, csv, image (EXIF + опц. LLM-caption), outlook `.msg`, ipynb, zip, rss, wikipedia,
youtube, bing-serp, audio (транскрипция). docx→md round-trip проверен на нашем отчёте —
GFM-таблицы, кириллица, escape целы.

**MCP-сервер `markitdown-mcp`** зарегистрирован в `C:\Users\<you>\.claude.json` →
`mcpServers.markitdown` (transport **stdio**, `command` = `...\.local\bin\markitdown-mcp.exe`).
Tool `convert_to_markdown` (принимает `http:`/`https:`/`file:`/`data:` URI) доступен в
**новых** сессиях Claude Code (сессия, стартовавшая до регистрации, его не видит —
тот же эффект, что был с pandoc-PATH). Опц. HTTP-режим: `markitdown-mcp --http`
(127.0.0.1:3001).

- **MCP-tool проверен вызовом** (2026-06-19): `mcp__markitdown__convert_to_markdown` с
  `file:///.../doc-extract/README.md` вернул корректный markdown (заголовки / код-блоки /
  ссылки целы) — отвечает сам MCP-tool, не только CLI. В свежей сессии tool приходит
  **deferred** → грузить `ToolSearch "select:mcp__markitdown__convert_to_markdown"` перед
  первым вызовом. Схема: `convert_to_markdown(uri: str) -> str`. Windows-`file:` URI —
  `file:///C:/...` (forward-slash, тройной слэш; кириллицу в пути — percent-encode).

**Граница markitdown ↔ doc-extract (проверено по исходникам, не по памяти):**

| Случай | Чем брать | Почему |
|---|---|---|
| docx/pptx/xlsx/html/epub/csv/msg, PDF с **текст-слоем** | **markitdown** (turnkey) | Широкое покрытие, structured md, table-aware PDF (pdfplumber). |
| **Скан-PDF (без текст-слоя), русский** | **doc-extract** (`ocr_pdf`) | markitdown-PDF = pdfplumber+pdfminer, **локального OCR НЕТ** (его OCR — только облачный Azure Doc Intelligence, не Tesseract). |
| **Легаси-бинарь `.doc`/`.ppt`/`.rtf`** | **doc-extract** (LibreOffice) | markitdown конвертеров под старый бинарный Office не имеет (только OOXML). |
| Нужен **флаг скана** (is_scan) / детект «текст или картинка» | **doc-extract** (`pdf_text_and_scanflag`) | markitdown такого сигнала не отдаёт. |
| Аудио-транскрипция (mp3/wav/m4a…) | **markitdown** (в новых сессиях) | Требует **ffmpeg** — установлен (8.1.1, в User PATH, 2026-06-19). Процесс, стартовавший до установки, ffmpeg на PATH ещё не видит → аудио-ветка заработает после перезапуска сессий. |

Итог: markitdown — предпочтительный первый шаг для штатных форматов и PDF-с-текстом;
doc-extract сохраняет уникальную ценность на **скан-RU-PDF (Tesseract rus+eng)**,
**легаси-бинарном Office (LibreOffice)** и **детекте скана**. Они дополняют друг друга,
не заменяют. (Возможная будущая интеграция — markitdown как первичный конвертер в
`convert.py` с fallback на doc-extract-OCR для сканов — пока НЕ сделана, это отдельная
задача через IRON MODE.)

## Зависимости

PyMuPDF (`fitz`), `pytesseract` + Tesseract-OCR (языки `rus`+`eng`), `python-pptx`,
`openpyxl`, `xlrd` (для старого .xls), LibreOffice (headless, `soffice`).
Пути к Tesseract/LibreOffice зашиты в модулях (Windows-окружение оператора).

## API

```python
import sys
sys.path.insert(0, r"C:\Users\<you>\.claude\skills\doc-extract\scripts")
from doc_extract import (
    pdf_text_and_scanflag, pptx_text, csv_text, sheet_text,   # форматы
    ocr_pdf, check_langs,                                      # OCR
    run_libreoffice, SOFFICE,                                  # legacy
)
# чистые алиасы: extract_pdf / extract_pptx / extract_csv / extract_sheet
```

| Функция | Сигнатура | Возврат |
|---|---|---|
| `pdf_text_and_scanflag` | `(path: Path, max_pages=200)` | `(text: str, is_scan: bool, n_pages: int)` |
| `pptx_text` | `(path: Path)` | `str` (слайды через `\n\n---\n\n`, заметки с префиксом `Notes: `) |
| `csv_text` | `(path: Path, max_lines=3000)` | `str` (срезает BOM, utf-8 `replace`) |
| `sheet_text` | `(path: Path, max_rows=5000)` | `str` (`.xls`→xlrd, `.xlsx/.xlsm`→openpyxl; заголовки `## Sheet: <name>`) |
| `ocr_pdf` | `(path: Path, dpi=300, max_pages=120, lang="rus+eng")` | `(text: str, pages: int)` (маркеры `<!-- page N -->`) |
| `check_langs` | `()` | `list[str]` (печатает доступность rus/eng в stderr) |
| `run_libreoffice` | `(src: Path, target: str, outdir_base: Path, idx: int, timeout=180, soffice=None)` | `Path | None` |
| `SOFFICE` | константа `Path` | резолвит `soffice.com`, иначе `soffice.exe` |

**Детект скана** (`pdf_text_and_scanflag`): `is_scan=True`, если
`(n_pages>0 и total_chars==0)` ИЛИ `(осмотрено>0 и (avg_chars_per_page<50 или доля_пустых>0.7))`.
Текст возвращается всегда (даже для скана — частичный текст-слой, если он есть).

## Тонкости (важно)

- `ocr_pdf` и `pdf_text_and_scanflag` возвращают **кортеж** — распаковывать
  (`text, is_scan, n = ...` / `text, pages = ocr_pdf(...)`), не трактовать как строку.
- `run_libreoffice` на каждый вызов создаёт **уникальный** профиль `prof_{idx}`/
  выход `out_{idx}` под `outdir_base` и поллит файл до стабилизации размера (~180 с).
  Потребитель сам передаёт `idx` (обычно индекс элемента) и базовый staging-каталог.
- MuPDF шумит в stderr (`cmsOpenProfileFromMem failed`, `No default Layer config`) —
  это **не фатально**, извлечение текста проходит, exit 0.
- На Windows `soffice.com` блокирует до завершения (нужно), `soffice.exe` — нет;
  `SOFFICE` это уже учитывает.
- Любой Python, печатающий не-ASCII, — с `PYTHONIOENCODING=utf-8`.

## Обратная конвертация: markdown/текст → docx/pdf/html (pandoc)

Извлечение здесь — это «документ → текст». **Обратное направление** («markdown →
готовый документ», экспорт отчётов/сводок) делает **pandoc** — отдельный бинарь, не
Python-зависимость скилла, но логически парный инструмент того же контура.

- Бинарь: `C:\Users\<you>\AppData\Local\Pandoc\pandoc.exe`, версия **3.10**. Прописан в
  **User PATH** (реестр) → в новых сессиях/терминалах резолвится по имени `pandoc`.
  Сессия, стартовавшая ДО установки, видит его только по полному пути (PATH процесса
  не обновляется на лету) — тогда зови `& "C:\Users\<you>\AppData\Local\Pandoc\pandoc.exe" ...`.
- Установлен **один раз, общий для всех контуров** (стоячая директива оператора
  «скачай один раз для всех», 2026-06-18). Не дублировать установку в проектах.
- Канонический вызов (GitHub-flavored markdown → Word с оглавлением):
  ```powershell
  pandoc -f gfm -t docx --toc -o "<out.docx>" "<in.md>"
  ```
  PDF — `-t pdf` (нужен LaTeX-движок) либо `-t docx` → печать в PDF; HTML — `-t html5 -s`.
- Кириллица/числа проходят без правок (проверено на отчёте 25.8 КБ, 4 таблицы,
  заголовки/числа целы). На вход GFM-таблицы → на выходе нативные таблицы Word.

`python-docx` 1.2.0 тоже доступен — для программной правки уже готового `.docx`
(стили, вставка строк), когда pandoc-конвертации из markdown недостаточно.

## Провенанс / целостность

Модули `formats.py`/`ocr.py`/`legacy.py` сгенерированы из спек `scripts/_spec_*.md`
через Ollama `qwen3-coder:30b` (`workflow/scripts/gen_code.py`) и доказаны
**побайтово-идентичными** оригинальным radon-примитивам на 160 реальных файлах корпуса
(`scripts/_smoke_identity.py`: `checked=160 mismatches=0`). После выноса `radon-library`
импортирует эти функции отсюда; его оркестрация (`convert_item`/`write_md`/`main`)
осталась без изменений (проверено AST-идентичностью), индекс 179 док/4760 чанков —
CONSISTENT.

## Ключевые файлы

| Файл | Назначение |
|---|---|
| `scripts/doc_extract/__init__.py` | экспорт: примитивы + алиасы `extract_*` |
| `scripts/doc_extract/formats.py` | `pdf_text_and_scanflag`, `pptx_text`, `csv_text`, `sheet_text` |
| `scripts/doc_extract/ocr.py` | `ocr_pdf`, `check_langs` (+ конфиг Tesseract на импорте) |
| `scripts/doc_extract/legacy.py` | `run_libreoffice`, `SOFFICE` |
| `scripts/_spec_*.md` | спеки кодогенерации (источник истины для регенерации) |
| `scripts/_smoke_identity.py` | проверка идентичности примитивов против radon-оригиналов |

## Тест-план

```powershell
$env:PYTHONIOENCODING='utf-8'
# 1. Импорт + резолв SOFFICE
python -c "import sys; sys.path.insert(0,r'C:\Users\<you>\.claude\skills\doc-extract\scripts'); import doc_extract as d; print('OK', d.SOFFICE.exists())"
# 2. Идентичность примитивов против radon-оригиналов (нужен radon-library корпус)
python "C:\Users\<you>\.claude\skills\doc-extract\scripts\_smoke_identity.py"   # ждём mismatches=0
```

## Регенерация

Правка примитива → правишь `scripts/_spec_<mod>.md` → 
`python C:\Users\<you>\.claude\skills\workflow\scripts\gen_code.py scripts\_spec_<mod>.md scripts\doc_extract\<mod>.py`
(IRON MODE: код пишет Ollama, не Claude) → прогнать `_smoke_identity.py`.