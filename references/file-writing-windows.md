# Сохранение файлов/скриптов на Windows — полное тело

> **Примечание к публичной копии.** Файл выгружен из приватной рабочей конфигурации: имена контуров заменены ролями, личные пути — плейсхолдерами. Ссылки на файлы, отсутствующие в этом репозитории (реестры скиллов и инструментов, журналы инцидентов, история), указывают на приватные части конфигурации и намеренно не публикуются.

Reference для правила «ВСЕ скрипты — в проект» (CLAUDE.md секция 16).
История инцидентов: `<home>\.claude\doctrine-history-2026-06-15.md`.

Читать когда пишешь скрипт ≥25 строк (особенно с кириллицей).

---

## Правило (HARD)

Любой Python/PowerShell/bash-скрипт, который **может пригодиться повторно**
(создание артефакта, smoke-test, helper парсинга, snapshot, миграционный
скрипт) — **сохраняется в папку проекта**, а НЕ выполняется одноразово через
`Bash heredoc` или `python -c "..."`.

**Что считается «может пригодиться повторно»** (любой из):
- Создаёт файл-артефакт (docx-шаблон, json-реестр, конфиг).
- Smoke-test (рендер + проверка ключевых полей) для шаблона/функции.
- Парсит/извлекает данные из формата (docx → text, pdf → json, registry-builder).
- Helper для устойчиво повторяющейся операции (extract_docx_text,
  fetch_company_inn, normalize_passport).
- Любой скрипт ≥30 строк (порог сложности).

**Одноразовое выполнение допустимо ТОЛЬКО для**:
- Тривиальных ad-hoc запросов (`ls`, `wc -l`, `grep -c`, разовый `Test-Path`).
- Однострочных проверок состояния (PID, размер файла, наличие пути).
- Inline-кода <10 строк без логики артефакта (вроде проверки `len(text)`).

---

## Структура сохранённого скрипта (минимум)

```python
"""Кратко: что делает + когда применять.

Usage:
    python <script>.py [args]
"""
from __future__ import annotations
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")  # см. UTF-8 правило
except Exception:
    pass
# ... тело ...
if __name__ == "__main__":
    main()
```

Желательно: docstring с purpose+usage, idempotent (можно перезапустить
безопасно), exit-code 0/1, кириллица в strings без эскейпа.

---

## Anti-patterns правила «в проект» (не делать)

- ❌ `Bash << 'PYEOF' ... PYEOF` для создания docx-шаблона (≥50 строк работы
  потеряны после прогона).
- ❌ `python -c "<длинный inline>"` для smoke-test'а функции.
- ❌ «потом сохраню если пригодится» — НЕ потом, СРАЗУ. Цена сохранения ≈ 0.
- ❌ Сохранять в `AppData/Local/Temp/` или `/tmp/` финальные скрипты.

---

## Способ #1: python-stdin-writer — DEFAULT для скриптов ≥25 строк (HARD, 2026-06-10, updated)

**Зафиксировано оператором 2026-06-10**: «это тоже всегда сразу
делай не дожидаясь когда в ограничения упрешься» + (после повторного падения
`cat > file <<'EOF'` на bg_pipeline.py) «устранить навсегда. сразу
применять правильный способ».

**История**: сначала `Write` блокируется IRON MODE hook'ом для кода ≥25
строк → перешли на `cat > path <<'PYEOF' ... PYEOF`. Затем `cat`+heredoc сам
**падает** на некоторых байтах внутри тела скрипта (`unexpected EOF while
looking for matching '`): MSYS-bash на Windows иногда некорректно парсит
многострочные heredoc'и с комбинацией UTF-8 кириллицы в путях + f-string'и
с одинарными кавычками + длинные блоки. Корень — bash-парсер ОТКРЫВАЕТ
квотированный режим где не должен; quoted-delimiter heredoc (`<<'EOF'`)
теоретически защищает, но на практике под MSYS НЕТ.

**Бронебойный способ навсегда** (HARD default для скрипта ≥25 строк, готового
к сохранению):

```bash
python -c "
import sys, pathlib
pathlib.Path(r'D:\absolute\path\to\script.py').write_text(sys.stdin.read(), encoding='utf-8')
" <<'SCRIPT_EOF'
<...тело скрипта целиком, любые кавычки/f-string/кириллица...>
SCRIPT_EOF
```

Почему это работает всегда:
- **Outer Python-wrapper** использует `"..."` (double-quote), внутри только
  `r'...'` raw-strings и `sys.stdin.read()`. Никаких `$`, backtick,
  `!`, `*` — bash-parser ничего не интерполирует.
- **Heredoc-content** идёт через stdin Python'а. Bash-парсер видит контент
  только как «opaque bytes between `<<'SCRIPT_EOF'` and `SCRIPT_EOF`». Любые
  одиночные кавычки, тройные кавычки, кириллица, f-string'и, скобки — **не
  пересекаются** с bash-режимом.
- **`SCRIPT_EOF`** — уникальное имя терминатора (не `EOF`, не `PYEOF`, не
  путать с возможным содержимым).

**Правило применения** (HARD):

1. Скрипт ≥25 строк, тело **уже продумано** → сразу python-stdin-writer.
   Не пробовать `Write` первым (IRON MODE), не пробовать `cat > path` первым
   (MSYS-bash hereoc-bug). Сэкономишь два неудачных tool-call'a.
2. Скрипт <25 строк, без кавычек/f-string/кириллицы → можно `Write` (hook
   пропустит) или `cat > path <<'EOF'` (heredoc не упадёт на коротком блоке).
3. Скрипт ≥25 строк, **код ещё не продуман** → делегировать на
   Ollama через `guarded_generate()` (Local-First rule). Ollama пишет
   через свой helper, который использует python-writer внутри.
4. Запись чанками через `cat >> path` остаётся валидным fallback'ом, если
   stdin-writer вдруг не сработал (хотя не должен) — каждый чанк ≤50 строк.

**Anti-patterns** (НИКОГДА для скриптов ≥25 строк):
- ❌ `cat > path <<'PYEOF' ... PYEOF` как первый способ — heredoc-bug на
  bash MSYS под Windows. Уже падали на этом дважды (step7_charfit_v2.py +
  bg_pipeline.py 2026-06-10).
- ❌ `Write` tool — IRON MODE блокирует, лишний tool-call.
- ❌ `python -c "<длинный inline>"` — однострочный python, теряется при
  смене окна; и кавычки всё равно ломаются.
- ❌ Дожидаться удара в `PreToolUse:Write hook error` или
  `unexpected EOF while looking for matching` — это **процесс-баг**, обе
  ошибки полностью предсказуемы, использовать правильный способ СРАЗУ.

**Граница**: если код **ещё не продуман** и его надо **сгенерировать** —
делегируй на Ollama через `guarded_generate()` (правило
Local-First / IRON MODE), результат → python-stdin-writer в проект.
Сохранение через stdin-writer — это file-plumbing, не code-generation,
hook на него не сработает.

---

## Способ #2: PowerShell here-string — co-default наравне с python-stdin-writer (HARD, 2026-06-12)

**Зафиксировано оператором 2026-06-12**: «Использую PowerShell с
here-string — он не страдает этим багом. Зафиксируй навсегда».

Триггер — повторное падение `python -c "...sys.stdin.read()..." <<'SCRIPT_EOF'`
паттерна при записи `gatt_enum.h` (196 строк, кириллица в комментариях, сессия контура прошивок).
MSYS-bash на Windows при чтении heredoc'а с UTF-8 кириллицей иногда выдаёт
`UnicodeEncodeError: surrogates not allowed` (символ `\udc98` и подобные) —
heredoc-content проходит через bash-stage, который мангает UTF-8 байты в
surrogate-pair'ы. python-stdin-writer защищает от bash-парсера КАВЫЧЕК, но НЕ
от UTF-8 mangling **внутри** heredoc-body. Это второй известный класс багов
MSYS-bash на этой машине после `unexpected EOF while looking for matching '`.

### Ещё три бага Bash-транспорта (2026-08-21, из петли самообучения)

Пойманы субагентом при написании хуков; разнесены сюда как доктринальные — касаются
любого контура, пишущего файлы через Bash на этой машине.

1. **Bash-транспорт съедает один уровень обратного слэша.** `\\n` в исходнике доходит
   до Python как `\n` и становится РЕАЛЬНЫМ переводом строки — файл не компилируется.
   Обход: в теле записываемого файла держать **ноль** символов `\` — многострочные
   тексты тройными кавычками с настоящими переносами, пути через прямой слэш,
   служебные переносы через `chr(10)`; в writer-скрипт врезать `assert chr(92) not in CODE`.

2. **Длинная Bash-команда молча обрезается (~5–6 КБ).** Bash падает с
   `unexpected EOF while looking for matching '` на строке у конца — **симптом
   читается как ошибка кавычек, а не как усечение**, и уводит отладку не туда
   (ложный след — самое дорогое в этом баге). Обход: файлы >~3 КБ писать несколькими
   вызовами (первый с `"w"`, остальные `"a"`), в конце `py_compile` как гейт целостности.

3. **`/tmp/...` из Git Bash не виден Windows-питону** — у msys и CPython разные корни.
   Обход: в любых кросс-инструментальных перекидках файлов использовать только
   Windows-путь (`C:/Users/...`), даже внутри bash-строк.

**Бронебойный способ #2** (полноценная замена python-stdin-writer, не fallback):

```powershell
$content = @'
<...тело файла целиком, любые кавычки/f-string/кириллица/тройные кавычки...>
'@
[System.IO.File]::WriteAllText(
    'D:\absolute\path\to\file.ext',
    $content,
    [System.Text.UTF8Encoding]::new($false)   # BOM-less UTF-8
)
```

Почему это работает всегда:
- **PowerShell — native Windows tool**, прямой вызов .NET `[System.IO.File]::WriteAllText`.
  Никакого MSYS-bash прослойки, никакого UTF-8 → cp1251 → surrogate mangling.
- **`@'...'@` single-quoted here-string** — literal, без интерполяции `$var` /
  backtick. Любые `$`, `'`, `"`, `\u`, кириллица, греческие — записываются как есть.
- **`UTF8Encoding::new($false)`** — UTF-8 без BOM (важно для YAML/JSON/Python — BOM ломает
  esphome config и `#!/usr/bin/env python` shebang).
- **PowerShell tool в этом Claude Code build уже доступен** без префикса.

---

## Какой способ когда (оба HARD-default, не fallback друг друга)

| Условие | Способ |
|---|---|
| Файл ≥25 строк, тело уже продумано, **есть кириллица в теле или путях** | PowerShell `@'...'@` + `WriteAllText` |
| Файл ≥25 строк, тело уже продумано, **только ASCII** | python-stdin-writer ИЛИ PowerShell (equivalent) |
| Файл ≥25 строк, **выполняется на чисто-Linux хосте** (CI, Pi через ssh) | python-stdin-writer (PowerShell нет) |
| Файл <25 строк, без кавычек/кириллицы | `Write` tool ОК |
| Subagent-бриф, агент работает в Bash-only сессии | python-stdin-writer (PowerShell может быть недоступен) |

**Правило (HARD)**: если в **теле скрипта или в целевом пути** есть кириллица
или Unicode-математика (`→`, `≈`, `Δ`, `μ`) — **первая попытка = PowerShell
here-string**, не python-stdin-writer. Python-stdin-writer оставляем для
ASCII-only тел и для Linux-хостов.

**Anti-patterns способа записи** (НИКОГДА):
- ❌ Пытаться python-stdin-writer на файл с кириллицей в Windows-сессии «потому что
  раньше работало». Surrogate-baг повторится. Сразу PowerShell.
- ❌ `@"..."@` (double-quoted here-string) — интерполирует `$var` и breaks на знаках
  `$`. Использовать ТОЛЬКО `@'...'@` (single-quote).
- ❌ `Set-Content -Path X -Value $content -Encoding UTF8` — пишет BOM (UTF-8 with BOM)
  по умолчанию. Ломает YAML/JSON/.env. Использовать только `[System.IO.File]::WriteAllText`
  с явным `UTF8Encoding::new($false)`.
- ❌ `Out-File -Encoding UTF8` — то же самое: BOM. Не использовать.

---

## Инструкция для subagent-брифов

Для задачи со скриптом ≥25 строк бриф ОБЯЗАН воспроизводить паттерн дословно:

- **ASCII-тело / Linux-хост**: секция «**Сохранение скрипта**:
  `python -c "...stdin..." <<'SCRIPT_EOF' ... SCRIPT_EOF` шаблон в
  `<project>/scripts/<subdir>/<name>.py`».
- **Кириллица в теле/пути (Windows)**: секция «**Сохранение скрипта**: PowerShell
  `@'...'@` + `[System.IO.File]::WriteAllText` с UTF-8-без-BOM в
  `<project>/scripts/<subdir>/<name>.ext`. Альтернатива (если хост Linux):
  python-stdin-writer».

Бриф без этой секции для скрипт-задачи = process-bug (субагент наступит на ту же грабли).

---

## Прочие carve-outs

- Для нового кода ≥25 строк, который нужно ещё спроектировать, —
  делегировать на Ollama через `guarded_generate` (правило
  IRON MODE), результат сохранять в проект.
- Subagent-брифы должны явно указывать путь сохранения в проект (не Temp,
  не `/tmp/`, не `AppData\Local\Temp\`).


---

## Целевые пути по проектам (из CLAUDE.md §16)

Куда сохранять скрипт в зависимости от проекта/контекста:

| Проект | Папка |
|---|---|
| секретарь — авторинг шаблонов | `<work-root>\секретарь\_Служебное\scripts\templates_authoring\` |
| секретарь — smoke-tests | `<work-root>\секретарь\_Служебное\scripts\smoke_tests\` |
| секретарь — общие helpers | `<work-root>\секретарь\_Служебное\scripts\utils\` |
| секретарь — Ollama-обработка | `<work-root>\секретарь\_Служебное\scripts\ollama\` |
| RE-сессии (BLE / протокол) | `<home>\.claude\skills\<skill-name>\scripts\` |
| надзорный / домашняя-автоматика | `<project>\scripts\` (создать при отсутствии) |
| gamma — per-run скрипты | `<project>\1_Version\<ver>\analysis_runs\<run>\scripts\` (state .json/.npy уровнем выше) |
| gamma — общие helpers | `<project>\scripts\` |
| Любой проект без `scripts/` | создать `<project>\scripts\<subcategory>\` |