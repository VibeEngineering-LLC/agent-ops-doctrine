# doc-extract

Corpus-agnostic примитивы извлечения текста из документов. Это **библиотека
функций** (importable), вынесенная из `radon-library` 2026-06-18 для
переиспользования между скиллами; своего корпуса / данных / отчётов не держит.

Одновременно это рантайм-скилл Claude Code: канонический путь —
`~/.claude/skills/doc-extract/`. Этот репозиторий — бэкап, история и
версионирование (push отсюда восстанавливает скилл на чистой машине).

## Слой

```
<rag-skill>     базовый extract_text: .docx / .txt / .md   (фундамент)
   └─ doc-extract   + PDF (текст-слой + детект скана), OCR скана,
                      legacy .doc/.ppt/.rtf (LibreOffice), .pptx, .csv, .xls/.xlsx/.xlsm
```

doc-extract сидит НАД приватным RAG-скиллом (`<rag-skill>`, не публикуется) и его не
дублирует: для `.docx/.txt/.md` по-прежнему вызывается `<rag-skill>.extract.extract_text`.

## API

```python
import sys
sys.path.insert(0, r"<path>/skills/doc-extract/scripts")
from doc_extract import (
    pdf_text_and_scanflag, pptx_text, csv_text, sheet_text,   # форматы
    ocr_pdf, check_langs,                                      # OCR
    run_libreoffice, SOFFICE,                                  # legacy
)
# чистые алиасы: extract_pdf / extract_pptx / extract_csv / extract_sheet
```

Полная таблица сигнатур, тонкости (кортежи на возврате, профили LibreOffice,
шум MuPDF в stderr), тест-план и регенерация — в [`SKILL.md`](SKILL.md).

## markitdown (turnkey-альтернатива) + MCP

С 2026-06-19 доступен **Microsoft markitdown 0.1.5** (`C:\Users\<you>\.local\bin\markitdown.exe`)
— готовый конвертер «что угодно → markdown» (docx/pptx/xlsx/pdf-с-текстом/html/epub/csv/
image/msg/…) и MCP-сервер `markitdown-mcp` (stdio, зарегистрирован в `.claude.json`,
tool `convert_to_markdown` — в новых сессиях). markitdown — предпочтительный первый шаг
для штатных форматов; **doc-extract сохраняет уникальную ценность на скан-RU-PDF (Tesseract
OCR), легаси-бинарном `.doc/.ppt/.rtf` (LibreOffice) и детекте скана** — markitdown этого
не умеет (его PDF = только текст-слой, OCR — лишь облачный Azure). Таблица границы — в
[`SKILL.md`](SKILL.md) → «markitdown».

## Обратная конвертация (экспорт)

Извлечение — это «документ → текст». Обратное направление «markdown → docx/pdf/html»
делает **pandoc 3.10** (`C:\Users\<you>\AppData\Local\Pandoc\pandoc.exe`, в User PATH,
общий для всех контуров). Канонично: `pandoc -f gfm -t docx --toc -o out.docx in.md`.
Подробности и тонкости PATH — в [`SKILL.md`](SKILL.md) → «Обратная конвертация».

## Зависимости

PyMuPDF (`fitz`), `pytesseract` + Tesseract-OCR (`rus`+`eng`), `python-pptx`,
`openpyxl`, `xlrd` (старый `.xls`), LibreOffice (headless `soffice`).
Пути к Tesseract / LibreOffice зашиты под Windows-окружение оператора.
Pandoc (экспорт, см. выше) — отдельный бинарь, не Python-зависимость.

## Провенанс

Модули `formats.py` / `ocr.py` / `legacy.py` сгенерированы из спек
`scripts/_spec_*.md` через Ollama `qwen3-coder:30b` и доказаны
**побайтово-идентичными** оригинальным radon-примитивам на 160 реальных файлах
корпуса (`scripts/_smoke_identity.py`: `checked=160 mismatches=0`).

## Потребители

- `radon-library` (приватный репозиторий) — `from doc_extract import ...`