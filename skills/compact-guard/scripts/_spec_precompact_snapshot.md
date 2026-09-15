You are writing ONE complete Python module file named `precompact_snapshot.py`.

OUTPUT RULES (critical):
- Output ONLY the Python source code. No markdown fences, no ``` , no explanation, no commentary before or after.
- The VERY FIRST line of your output must be exactly: #!/usr/bin/env python3
- The SECOND line must be exactly: # -*- coding: utf-8 -*-
- Python 3.11+ on Windows. Standard library ONLY (json, os, sys, re, subprocess, datetime, pathlib).
- Keep it under ~210 lines. Write real bodies for every function (no `pass`, no TODO).

PURPOSE:
This is a Claude Code **PreCompact hook**. It fires immediately BEFORE the conversation context is
compacted (both `auto` — when the context window fills — and `manual` — when the operator types
/compact). Its job is to write a MECHANICAL snapshot of session state to a file, so that after the
compaction (which discards most of the conversation) the agent can recover concrete facts it would
otherwise have lost. It captures ONLY what a script can know for certain by reading the transcript
and the filesystem — never interpretation, never summary of intent.

It must be FAIL-SAFE (any error → exit 0, never block a compaction), QUIET (no stdout noise beyond
the hook result JSON), and READ-MOSTLY (writes exactly one snapshot file, plus a `latest.json`
pointer; touches nothing else).

CRITICAL BEHAVIOURAL RULE: this hook must NEVER block the compaction (never `exit 2`, never
`"continue": false`). An auto-compaction fires precisely when the context is full; blocking it
would wedge the session. Always exit 0.

EXACT CONTENT TO PRODUCE:

1. After the two header lines, a triple-quoted module docstring (in Russian) explaining: this is a
   PreCompact hook that writes a mechanical snapshot of session state before context compaction
   (auto or manual) — the facts the agent will lose when history is discarded: which files were
   edited, which commands were run, the operator's last instructions, git state, context fill.
   It NEVER blocks compaction (an auto-compact fires when context is already full; blocking would
   wedge the session) and it NEVER interprets — only records what is mechanically verifiable.
   The companion `postcompact_restore.py` (SessionStart hook, matcher `compact`) reads it back.

2. Imports: `json, os, re, subprocess, sys`, `from datetime import datetime`, `from pathlib import Path`.

3. Right after imports, wrap stdout reconfiguration in try/except (same reason as the other hooks —
   Windows console may be cp1251 and the output contains Cyrillic):
   ```
   try:
       sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
   except Exception:
       pass
   ```

4. Module constants:
   - `SNAP_DIR = Path(os.path.expanduser("~")) / ".claude" / "compact-snapshots"`
   - `MAX_TAIL_BYTES = 2_000_000` (how much of the transcript tail to read — 2 MB is plenty for the
     recent activity we care about, and bounds memory on a huge transcript)
   - `MAX_FILES = 25`, `MAX_CMDS = 20`, `MAX_USER_MSGS = 5` (caps on what goes into the snapshot)
   - `MAX_SNAPSHOTS_KEEP = 40` (retention: older snapshot files get pruned)

5. Function `read_tail(path: str, nbytes: int = MAX_TAIL_BYTES) -> str`:
   - Wrapped so it never raises: on any exception return `""`.
   - `size = os.path.getsize(path)`; open binary, `f.seek(max(0, size - nbytes))`, read, decode
     `utf-8` with `"replace"`.

6. Function `iter_records(tail: str)`:
   - A generator: for each line in `tail.splitlines()`, strip it, skip empties, try `json.loads`,
     skip lines that fail to parse (the first line of a mid-file tail is usually a partial record),
     `yield` the parsed dict.

7. Function `collect_from_transcript(tail: str) -> dict`:
   Walk the records ONCE (in order) and accumulate. Return a dict with keys
   `files`, `commands`, `user_msgs`, `ctx_tokens`, `compact_seen`.
   - `files`: list of file paths edited/written this session. Detect by scanning assistant records:
     a record with `rec.get("type") == "assistant"`, whose `rec["message"]["content"]` is a list;
     for each item in that list where `item.get("type") == "tool_use"` and
     `item.get("name")` is one of `{"Write", "Edit", "NotebookEdit"}`, take
     `item.get("input", {}).get("file_path")` if truthy. Keep insertion order, de-duplicated
     (use a dict or an `if x not in list` check), keep only the LAST `MAX_FILES` entries.
   - `commands`: same walk, for `item.get("name") == "Bash"`, take
     `item.get("input", {}).get("description") or item.get("input", {}).get("command")`.
     Truncate each to 120 chars. Keep the LAST `MAX_CMDS`, in order.
   - `user_msgs`: records where `rec.get("type") == "user"`. The content may be a plain string
     (`rec["message"]["content"]` is a str) or a list of blocks (take blocks with
     `b.get("type") == "text"` and join their `b.get("text", "")`). SKIP any message whose text
     contains `"<local-command-"` or starts with `"[SYSTEM NOTIFICATION"` or contains
     `"tool_use_id"` (those are harness plumbing, not operator words). Truncate each to 400 chars.
     Keep the LAST `MAX_USER_MSGS`.
   - `ctx_tokens`: from the LAST assistant record that has usage — sum of
     `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` from
     `rec["message"]["usage"]` (missing keys → 0). Keep updating as you walk, so the final value is
     the most recent one.
   - `compact_seen`: set to True if any record has `rec.get("type") == "system"` and
     `rec.get("subtype") == "compact_boundary"` (means this session was already compacted before —
     useful context for the reader).
   - The whole body must be wrapped so a malformed record can never abort the walk: put the
     per-record processing in a `try/except Exception: continue`.

8. Function `git_state(cwd: str) -> dict`:
   - Returns `{}` if `cwd` is falsy or `(Path(cwd) / ".git").exists()` is False (many of this
     operator's project folders are deliberately NOT git repos — that is normal, not an error).
   - Otherwise run three commands with
     `subprocess.run([...], cwd=cwd, capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")`:
     - `["git", "rev-parse", "--abbrev-ref", "HEAD"]` → `branch`
     - `["git", "rev-parse", "--short", "HEAD"]` → `head`
     - `["git", "status", "--porcelain"]` → split stdout lines, keep first 30 → `dirty`
   - Each in its own try/except; on failure omit that key. Wrap the whole function so it returns
     `{}` on any unexpected error. Never raise.

9. Function `prune_old(keep: int = MAX_SNAPSHOTS_KEEP) -> None`:
   - List `SNAP_DIR.glob("snap_*.md")`, sort by `st_mtime` descending, and `unlink()` everything
     past the first `keep`. Wrap in try/except and swallow errors (retention is best-effort).

10. Function `build_markdown(payload: dict, collected: dict, git: dict, ts: str) -> str`:
    Compose the snapshot document. It is written in RUSSIAN (the operator's language) and is meant
    to be read by the post-compact agent. Structure (use exactly these headings):
    ```
    # Снапшот перед сжатием контекста

    - **Когда:** {ts}
    - **Триггер:** {trigger}  (`auto` = контекст переполнился сам, `manual` = оператор набрал /compact)
    - **Сессия:** {session_id}
    - **Рабочая папка:** {cwd}
    - **Контекст на момент сжатия:** ~{ctx_k}k токенов
    - **Сессия уже сжималась ранее:** да/нет

    ## Последние указания оператора (дословно, свежие внизу)
    ...

    ## Файлы, которые правились в этой сессии
    ...

    ## Последние команды
    ...

    ## Git
    ...

    ---
    ⚠️ Это МЕХАНИЧЕСКИЙ снапшот: только то, что скрипт видит достоверно. Он НЕ заменяет
    SESSION-STATE.md — смысл работы, решения и планы там. Сверься с обоими.
    ```
    Details:
    - `trigger` from `payload.get("trigger")` (fallback `"?"`).
    - `session_id` from `payload.get("session_id")` (fallback `"?"`).
    - `cwd` from `payload.get("cwd")` (fallback `"?"`).
    - `ctx_k` = `round(collected["ctx_tokens"] / 1000)`; if it is 0, write `неизвестно` instead of `~0k токенов`.
    - «Сессия уже сжималась ранее» → `да` if `collected["compact_seen"]` else `нет`.
    - Operator messages: numbered list, each as a blockquote line (`> текст`). If the list is empty,
      write `_(в хвосте транскрипта не найдено)_`.
    - Files: bullet list of paths in backticks. Empty → `_(нет)_`.
    - Commands: numbered list, each in backticks. Empty → `_(нет)_`.
    - Git: if `git` is empty → `_(не git-репозиторий)_`. Otherwise lines for branch and head, then
      if `dirty` is non-empty a fenced code block listing those porcelain lines with the heading
      `Незакоммиченные изменения:`; if `dirty` is empty write `Рабочее дерево чистое.`

11. Function `main() -> int`:
    - Read stdin fully; `json.loads` it; on any failure use `{}`.
    - `tp = payload.get("transcript_path") or ""`.
    - `tail = read_tail(tp) if tp and os.path.isfile(tp) else ""`.
    - `collected = collect_from_transcript(tail)`.
    - `git = git_state(str(payload.get("cwd") or ""))`.
    - `ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")`.
    - `SNAP_DIR.mkdir(parents=True, exist_ok=True)`.
    - Build a filename-safe session tag: take `str(payload.get("session_id") or "unknown")`, keep
      only its first 8 chars after removing non-alphanumeric/dash characters via
      `re.sub(r"[^A-Za-z0-9\-]", "", ...)`.
    - `fname = f"snap_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{tag}.md"`.
    - Write `build_markdown(...)` to `SNAP_DIR / fname` with `encoding="utf-8"`.
    - Also write a pointer file `SNAP_DIR / "latest.json"` containing
      `{"path": str(SNAP_DIR / fname), "ts": ts, "session_id": ..., "cwd": ..., "trigger": ...}`
      via `json.dump(..., ensure_ascii=False, indent=2)`.
    - Call `prune_old()`.
    - Print `json.dumps({"suppressOutput": True})` and return 0.
    - The ENTIRE body of main must be inside a try/except that, on any exception, still prints
      `{"suppressOutput": True}` and returns 0.

12. Final block:
    ```
    if __name__ == "__main__":
        try:
            sys.exit(main())
        except Exception:
            try:
                print(json.dumps({"suppressOutput": True}))
            except Exception:
                pass
            sys.exit(0)
    ```

Now output the complete precompact_snapshot.py source, starting with the shebang line.
