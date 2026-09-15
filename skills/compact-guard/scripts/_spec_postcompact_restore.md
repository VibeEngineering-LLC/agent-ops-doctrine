You are writing ONE complete Python module file named `postcompact_restore.py`.

OUTPUT RULES (critical):
- Output ONLY the Python source code. No markdown fences, no ``` , no explanation, no commentary before or after.
- The VERY FIRST line of your output must be exactly: #!/usr/bin/env python3
- The SECOND line must be exactly: # -*- coding: utf-8 -*-
- Python 3.11+ on Windows. Standard library ONLY (json, os, sys, datetime, pathlib).
- Keep it under ~150 lines. Write real bodies for every function (no `pass`, no TODO).

PURPOSE:
This is a Claude Code **SessionStart hook** registered with matcher `compact` — it fires right
AFTER the conversation context has been compacted. Its stdout `additionalContext` is injected into
the model's context, which makes it the ONLY reliable channel to hand the freshly-compacted agent a
pointer back to what it just lost.

It reads the snapshot written moments earlier by the companion `precompact_snapshot.py` (PreCompact
hook) and emits a short, actionable notice: where the full snapshot lives, what the operator's last
instructions were, which files were being edited, and a hard requirement to reconcile with the
project's SESSION-STATE.md before doing anything else.

It must be FAIL-SAFE (any error → exit 0 with valid output, never break session start), QUIET (if
there is no fresh snapshot it stays silent), and it must NEVER dump the whole snapshot into context
(that would defeat the purpose of compacting) — only a compact pointer plus the few highest-value
facts.

EXACT CONTENT TO PRODUCE:

1. After the two header lines, a triple-quoted module docstring (in Russian) explaining: this is a
   SessionStart hook with matcher `compact`, firing right after context compaction. It reads the
   snapshot left by precompact_snapshot.py and injects into the agent's context a SHORT pointer:
   path to the full snapshot, the operator's last instructions, the files in flight, and a
   requirement to read SESSION-STATE.md and reconcile before continuing. Deliberately does NOT
   inject the whole snapshot — that would refill the context we just freed.

2. Imports: `json, os, sys`, `from datetime import datetime`, `from pathlib import Path`.

3. Right after imports, the stdout reconfiguration guard (identical rationale to the other hooks —
   the notice contains Cyrillic and would die under a cp1251 console):
   ```
   try:
       sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
   except Exception:
       pass
   ```

4. Module constants:
   - `SNAP_DIR = Path(os.path.expanduser("~")) / ".claude" / "compact-snapshots"`
   - `LATEST = SNAP_DIR / "latest.json"`
   - `MAX_AGE_MIN = 30` — a snapshot older than this is NOT from the compaction that just happened
     (it is a leftover from an earlier session), so it must be ignored rather than presented as
     current. This staleness guard is the whole reason we record `ts`.
   - `MAX_PROMPTS_SHOWN = 3`, `MAX_FILES_SHOWN = 8`

5. Function `emit(result: dict) -> None`:
   - `print(json.dumps(result, ensure_ascii=False))`, and on `UnicodeEncodeError` retry with
     `ensure_ascii=True` (last-resort so the notice still reaches the model as \uXXXX escapes).
   - Wrap the whole thing so it can never raise.

6. Function `silent() -> None`: calls `emit({"suppressOutput": True})`.

7. Function `load_latest() -> dict`:
   - Return `{}` if `LATEST` is not a file.
   - Read + `json.loads` it; return `{}` if the result is not a dict or on any exception.

8. Function `is_fresh(ts_str: str) -> bool`:
   - Parse `ts_str` with `datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")`.
   - Return True when `(datetime.now() - parsed).total_seconds() <= MAX_AGE_MIN * 60` AND the value
     is not negative beyond a small tolerance (allow up to 60 s of clock skew into the future).
   - Any parsing failure → return False (fail closed: better silent than presenting a stale
     snapshot as current).

9. Function `extract_sections(md_path: str) -> dict`:
   - Read the snapshot markdown at `md_path` (utf-8, `errors="replace"`); on failure return `{}`.
   - Pull out two lists by simple line scanning (do NOT use regex-heavy parsing):
     - `prompts`: lines that start with `"> "` inside the section that begins with the heading line
       starting `"## Последние указания оператора"` and ends at the next line starting with `"## "`.
       Strip the leading `"> "`. Keep the LAST `MAX_PROMPTS_SHOWN`.
     - `files`: lines that start with `"- \`"` inside the section beginning with the heading line
       starting `"## Файлы"` and ending at the next `"## "`. Strip the leading `"- "` and any
       surrounding backticks. Keep the LAST `MAX_FILES_SHOWN`.
   - Implement with a simple state variable (`current_section = None`), iterating over
     `text.splitlines()`; set `current_section` when a line starts with `"## "`.
   - Return `{"prompts": [...], "files": [...]}`.

10. Function `build_notice(latest: dict, sections: dict) -> str`:
    Compose the injected text in RUSSIAN. Keep it SHORT — this lands in a freshly-freed context.
    Structure:
    ```
    ⚠️ КОНТЕКСТ ТОЛЬКО ЧТО СЖАТ ({trigger}). История диалога усечена — часть фактов ты уже не помнишь.

    Механический снапшот состояния (записан хуком ДО сжатия, читать при любом сомнении):
    {snap_path}

    Последние указания оператора перед сжатием:
    {prompts}

    Файлы в работе на момент сжатия:
    {files}

    ОБЯЗАТЕЛЬНО ПЕРВЫМ ДЕЙСТВИЕМ:
    1. Прочитать SESSION-STATE.md в корне проекта ({cwd}) — там смысл работы, решения и план.
       Снапшот выше содержит ТОЛЬКО механику (что правилось/запускалось), не замысел.
    2. Свериться: совпадает ли состояние на диске с тем, что записано. Расхождение — проверять
       фактом (командой/чтением файла), НЕ достраивать по памяти: после сжатия память ненадёжна.
    3. Если SESSION-STATE.md устарел или его нет — обновить/создать СЕЙЧАС, до продолжения работы.
    4. Не начинать новых крупных задач, пока пункты 1-3 не закрыты.
    ```
    Details:
    - `trigger`: `latest.get("trigger")`; render `auto` as `"автоматически, контекст переполнился"`
      and `manual` as `"по команде оператора /compact"`, anything else as the raw value.
    - `snap_path`: `latest.get("path", "?")`.
    - `cwd`: `latest.get("cwd") or "текущий проект"`.
    - `prompts`: numbered list, each line as `N. «текст»`. If empty → `_(не найдены)_`.
    - `files`: bullet list in backticks. If empty → `_(нет)_`.

11. Function `main() -> int`:
    - Read and discard stdin safely (the payload is not needed beyond confirming the event; still
      consume it so the writing end never blocks): wrap `sys.stdin.read()` in try/except.
    - `latest = load_latest()`; if falsy → `silent()`, return 0.
    - If `not is_fresh(str(latest.get("ts") or ""))` → `silent()`, return 0.
    - `md_path = str(latest.get("path") or "")`; `sections = extract_sections(md_path) if md_path else {}`.
    - Build the notice and emit:
      ```
      emit({
          "hookSpecificOutput": {
              "hookEventName": "SessionStart",
              "additionalContext": notice,
          },
          "suppressOutput": True,
      })
      ```
    - Return 0. The entire body must sit inside try/except that, on any exception, calls `silent()`
      and returns 0.

12. Final block:
    ```
    if __name__ == "__main__":
        try:
            sys.exit(main())
        except Exception:
            silent()
            sys.exit(0)
    ```

Now output the complete postcompact_restore.py source, starting with the shebang line.
