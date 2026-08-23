---
name: markitdown
description: "Документ → Markdown: PDF, Office (docx/xlsx/pptx), изображения, HTML, Outlook .msg, CSV, аудио. Дефолт §19 для чтения и цитирования документов. Триггеры: «прочитай PDF», «преобразуй документ», «извлеки текст из файла». Сложные формулы/сканы → `unlimited-ocr`."
---

# markitdown — документ → Markdown

Единый инструмент конвертации готовых документов (PDF, Office, изображения, HTML,
Outlook `.msg`, CSV, аудио) в Markdown/текст — для чтения, цитирования и подачи в
контекст. **Дефолт для всех контуров** по правилу §19 глобального `CLAUDE.md`.

Источник: Microsoft markitdown (https://github.com/microsoft/markitdown), MIT.

## Когда применять (дефолт-ON)

Любая задача «превратить готовый документ в Markdown/текст»: прочитать PDF/Office,
процитировать кусок, подать содержимое в контекст модели, быстро глянуть таблицу из
xlsx. Вместо ad-hoc парсера на ходу — `markitdown`.

## Когда НЕ применять (карв-ауты — markitdown НЕ заменяет специализированное)

| Случай | Чем делать |
|---|---|
| OCR скан rus+eng, legacy `.doc/.ppt/.rtf` | скилл `doc-extract` |
| Семантический поиск по личным докам | скилл `docs-rag` |
| Спецификация из чертежей | скилл `drawings-spec` |
| СОЗДАНИЕ/правка документов с форматированием | `docx`/`xlsx`/`pptx`/`pdf` (markitdown только читает→md, писать не умеет) |

## Способы вызова

### MCP (внутри сессий Claude Code)
Инструмент `convert_to_markdown(uri)` — после старта сессии виден как
`mcp__markitdown__convert_to_markdown`. `uri` принимает схемы **`http:` / `https:` /
`file:` / `data:`**. Пример для локального файла: `file:///D:/path/to/doc.pdf`.

### CLI
`C:\Users\<you>\.local\bin\markitdown.exe`
- `markitdown <файл>` → вывод в stdout
- `markitdown <файл> -o out.md` → в файл
- `cat <файл> | markitdown` или `markitdown < <файл>` → чтение из stdin
- `-x <ext>` — подсказка расширения при чтении из stdin
- `-v` версия, `-h` справка

## Поддерживаемые форматы
PDF, Word `.docx`, PowerPoint `.pptx`, Excel `.xlsx`/`.xls`, изображения (EXIF + OCR),
HTML, текстовые (CSV/JSON/XML), Outlook `.msg`, ZIP (рекурсивно), EPub, YouTube-URL
(транскрипт), аудио `.mp3`/`.wav`/`.m4a` (EXIF + транскрипция — **требует ffmpeg**).

## Аудио / ffmpeg
Аудио-ветка (`pydub` + `SpeechRecognition`) требует ffmpeg. Установлен **ffmpeg 8.1.1**
(`Gyan.FFmpeg`, winget), прописан в **User PATH**:
`C:\Users\<you>\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin`

NB: дочерний процесс `markitdown-mcp` наследует PATH от Claude Code на старте — **аудио
заработает только после перезапуска Claude Code**. Прочие форматы ffmpeg не требуют.

## Ключевые файлы / пути
| Что | Путь |
|---|---|
| CLI | `C:\Users\<you>\.local\bin\markitdown.exe` |
| MCP-server shim | `C:\Users\<you>\.local\bin\markitdown-mcp.exe` |
| MCP-конфиг (Claude Code) | `C:\Users\<you>\.claude.json` → корневой `mcpServers.markitdown` (scope user, type stdio) |
| Исходник MCP-инструмента | `C:\Users\<you>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\uv\tools\markitdown-mcp\Lib\site-packages\markitdown_mcp\__main__.py` |
| ffmpeg `bin` | см. раздел «Аудио / ffmpeg» |

## Версии (на 2026-06-19)
- markitdown **0.1.5** (extras `[all]`)
- markitdown-mcp **0.0.1a4** (mcp 1.8.1)
- ffmpeg **8.1.1**-full_build

## Установка / переустановка
uv tool (изолированно):
```
uv tool install "markitdown[all]"
uv tool install --with "markitdown[all]" markitdown-mcp
uv tool update-shell
```
MCP-регистрация (user scope — для всех контуров):
```
claude mcp add markitdown -s user -- C:\Users\<you>\.local\bin\markitdown-mcp.exe
```
ffmpeg: `winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements`
Проверка: `claude mcp list` → `markitdown ✓ Connected`; `claude mcp get markitdown`.

## Провенанс (verify-by-fact, проверено 2026-06-19)
- Имя/сигнатура инструмента: `markitdown_mcp\__main__.py:20` → `async def convert_to_markdown(uri: str) -> str`; регистрация `@mcp.tool()` (стр. 19); `FastMCP("markitdown")` (стр. 16); docstring (стр. 21) — «Convert a resource described by an http:, https:, file: or data: URI to markdown».
- Реализация: `__main__.py:22` → `MarkItDown().convert_uri(uri).markdown`.
- STDIO по умолчанию: `__main__.py:113-114` (`mcp.run()`); HTTP/SSE — флаг `--http` (по умолчанию `127.0.0.1:3001`).
- CLI-синтаксис: из `markitdown --help` (positional `filename`, опции `-o/-x/-v/-h`, stdin если filename пуст).
- ffmpeg: winget-лог 2026-06-19 «Успешно установлено»; `ffmpeg.exe -version` → `ffmpeg version 8.1.1-full_build-www.gyan.dev`.

## Хранение скилла (политика §20 глобального CLAUDE.md)
- **Реальная папка:** `<your-shared-drive-root>\Skills\markitdown\` (бэкап Google Drive) + локальный git + GitHub.
- **Загрузка Claude Code:** `C:\Users\<you>\.claude\skills\markitdown` — **junction** на папку выше (Claude Code грузит по C-пути, данные физически на D:).
- Пересоздать junction при необходимости:
  ```
  New-Item -ItemType Junction -Path "C:\Users\<you>\.claude\skills\markitdown" -Target "<your-shared-drive-root>\Skills\markitdown"
  ```
