---
name: dev-env
description: "Инструменты рабочего окружения Windows: mcp-pwsh как дефолтный транспорт PowerShell-запусков с кириллицей и сложным escaping, graphify install — установка графа знаний проекта. Триггеры: «запусти PowerShell с русским текстом», «нужно сохранить cwd между вызовами», «поставь graphify», «граф проекта». Вынесено из CLAUDE.md §21/§27."
---

# dev-env — транспорт команд и граф проекта

Два правила оператора. Раньше — §27 и §21 глобального `CLAUDE.md`, перенесены дословно.

## 1. mcp-pwsh — дефолтный транспорт pwsh-запусков без escaping (§27, глобально, 2026-07-10)

**Установлено оператором 2026-07-10 «глобально для всех»** (репо `github.com/Am6er/mcp-pwsh`, публичный open-source MCP-сервер). MCP-сервер user-scope в `C:\Users\<you>\.claude.json` (`✓ Connected`); exe `C:\Users\<you>\AppData\Roaming\Python\Python314\Scripts\mcp-pwsh.exe`. Доступен любой сессии после старта; уже открытые — после перезапуска Claude Code.

**ИМПЕРАТИВ:** pwsh-запуск с кириллицей / сложным escaping / нуждой в persistent state (cwd/env между вызовами) — дефолтом через `mcp__pwsh__pwsh`, а не ad-hoc встроенный PowerShell tool с ручным экранированием. Решает три Windows-боли сразу: escaping не нужен (команды base64), persistent pwsh 7 сессия (state переживает вызовы), UTF-8 вывод (Console in/out = UTF8, кириллица без mojibake).

Tools: `pwsh(command, session, timeout=60)` · `pwsh_list()` · `pwsh_close(session)` · `pwsh_reset(session)` · `pwsh_kill_all()`.

**Граница:** mcp-pwsh — pwsh-канал, НЕ bash, НЕ drop-in замена Bash tool. Bash-специфика (MSYS/git-bash, ssh→Pi §1, POSIX-heredoc, bash-only утилиты) остаётся на встроенном Bash tool. Встроенный PowerShell/Bash tool — для простого ASCII-one-liner или когда MCP-tool недоступен (до-рестарт). Fallback python-stdout UTF-8 без MCP — раннер `py.ps1` (§2).

**Безопасность:** sandbox/allowlist нет, exec доверенный (коллаборант, класс = встроенный shell-tool). Снять: `claude mcp remove pwsh -s user`. Тело, tools, смок, обкатка: `C:\Users\<you>\.claude\references\mcp-pwsh.md`.

## 2. graphify claude install — после успешного прогона (§21, НАВСЕГДА, 2026-06-22)

**Зафиксировано оператором 2026-06-22:** «после успешного прогона выполнять `graphify claude install` — он положит инструкцию в `.claude/` папки, каждая будущая сессия здесь будет открывать проект через граф автоматически».

**ИМПЕРАТИВ:** после **первого зелёного значимого прогона** (полный pytest зелёный, end-to-end pipeline отработал, milestone закрыт) — если в `<project>/.claude/` ещё нет graphify-skill инструкции — `Set-Location "<путь>"; graphify install --platform claude` (CLI `C:\Users\<you>\.local\bin\graphify.exe` в PATH). После — подтвердить оператору явный путь установленных файлов (§18).

**НЕ ставить:** уже установлено (тогда `graphify update <project>`); прогон не зелёный/частичный; чужая зона (§12); сторонние/публичные репо без согласования.

**Не рефакторить graphify-generated (REF-1, 2026-07-10):** скилл, установленный `graphify install` (`SKILL.md` с маркером `.graphify_version`) — локально НЕ рефакторить (перетрётся при `graphify update`); контекст-правки — через регенерацию графа. Тело, когда-не, что-даёт, граф-MCP: `C:\Users\<you>\.claude\references\graphify-install.md`.

## 3. Скачивание ML-моделей: Xet вешает загрузку (перенято 2026-08-15)

**Источник:** внешний проект RAG для OpenCode (машина Amber) и `INSTALL.md` MinerU — обе инструкции независимо описывают одну и ту же грабку. Разбор: `skills\docs-rag\references\external-rag-opencode-2026-08-15.md`.

**ИМПЕРАТИВ:** перед скачиванием весов с HuggingFace ставить `HF_HUB_DISABLE_XET=1`. Дефолтный Xet-бэкенд на некоторых сетях **виснет намертво посреди файла** (у автора — стоп на 511 МБ из 2,2 ГБ) либо застревает на нуле байт. С обычным CDN качается стабильно.

```powershell
$env:HF_HUB_DISABLE_XET = "1"
```

Смежное: `HF_HUB_ENABLE_HF_TRANSFER` в актуальном `huggingface_hub` **игнорируется** — его заменил Xet, старый совет про ускорение больше не работает.

Если HuggingFace рвётся целиком — у моделей MinerU есть зеркало Alibaba, часто стабильнее: `$env:MINERU_MODEL_SOURCE = "modelscope"`.

**Обрывы больших загрузок вообще** (инсталляторы, колёса pip): качать резюмируемо через BITS, а не одним потоком — `Start-BitsTransfer -Source <URL> -Destination <файл> -Asynchronous`, на обрыве `Get-BitsTransfer | Resume-BitsTransfer`, по готовности `Complete-BitsTransfer`.

Актуально для наших весов: `unlimited-ocr` тянет 6,67 ГБ, MinerU — около 2,3 ГБ.

## Смежное, что остаётся в ядре CLAUDE.md

Кодировка (§2 — `PYTHONIOENCODING=utf-8`, раннер `py.ps1`) и SSH→Pi с кириллицей (§1) живут в глобальном файле: они нужны до первого действия, а не по триггеру. Здесь — только транспорт и граф.
