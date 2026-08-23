#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Это PreCompact хук, который записывает механический снапшот состояния сессии
перед сжатием контекста (авто или вручную). Он сохраняет факты, которые агент
потеряет при очистке истории: какие файлы редактировались, какие команды
выполнялись, последние указания оператора, состояние git, заполнение контекста.
Хук НИКОГДА не блокирует сжатие (авто-сжатие срабатывает, когда контекст уже полон;
блокировка привела бы к застывшей сессии) и НИКОГДА не интерпретирует — только
записывает то, что можно механически проверить. Сопутствующий postcompact_restore.py
(хук SessionStart, матчер compact) читает его обратно.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass
try:
    # Хук получает JSON-payload от Claude Code через stdin. На cp1251-консоли
    # Windows sys.stdin по умолчанию декодирует НЕ как UTF-8 -> кириллица в
    # cwd/путях превращается в суррогаты -> падение при записи файла
    # (найдено 2026-08-15 на реальном срабатывании, cwd содержал "Цензор").
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SNAP_DIR = Path(os.path.expanduser("~")) / ".claude" / "compact-snapshots"
MAX_TAIL_BYTES = 2_000_000
MAX_FILES = 25
MAX_CMDS = 20
MAX_USER_MSGS = 5
MAX_SNAPSHOTS_KEEP = 40


def read_tail(path: str, nbytes: int = MAX_TAIL_BYTES) -> str:
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - nbytes))
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def iter_records(tail: str):
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def collect_from_transcript(tail: str) -> dict:
    files = []
    commands = []
    user_msgs = []
    ctx_tokens = 0
    compact_seen = False
    seen_files = set()
    seen_msgs = set()
    cwd = ""

    def add_user_msg(text: str) -> None:
        text = text.strip()
        if not text:
            return
        key = text[:400]
        if key in seen_msgs:
            return
        seen_msgs.add(key)
        user_msgs.append(key)
        if len(user_msgs) > MAX_USER_MSGS:
            user_msgs.pop(0)

    for rec in iter_records(tail):
        try:
            # cwd из транскрипта — надёжный источник. В stdin-payload он приходит
            # с порчей: заглавные после обратного слэша превращаются в
            # "\N{CYRILLIC CAPITAL LETTER ER}абочая" (боевое срабатывание 16:15
            # 2026-08-15). В транскрипте те же 4614 записей — целые.
            rec_cwd = rec.get("cwd")
            if isinstance(rec_cwd, str) and rec_cwd.strip():
                cwd = rec_cwd
            if rec.get("type") == "assistant":
                content = rec.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "tool_use":
                            name = item.get("name")
                            if name in {"Write", "Edit", "NotebookEdit"}:
                                path = item.get("input", {}).get("file_path")
                                if path:
                                    if path not in seen_files:
                                        files.append(path)
                                        seen_files.add(path)
                                    if len(files) > MAX_FILES:
                                        removed = files.pop(0)
                                        seen_files.discard(removed)
                            elif name == "Bash":
                                desc = item.get("input", {}).get("description") or item.get("input", {}).get("command")
                                if desc:
                                    commands.append(desc[:120])
                                    if len(commands) > MAX_CMDS:
                                        commands.pop(0)
                usage = rec.get("message", {}).get("usage")
                if usage:
                    ctx_tokens = (
                        usage.get("input_tokens", 0) +
                        usage.get("cache_read_input_tokens", 0) +
                        usage.get("cache_creation_input_tokens", 0)
                    )
            elif rec.get("type") == "user":
                # Промпты оператора живут в user-записях со СТРОКОВЫМ content —
                # такая запись пишется сразу при отправке сообщения. Записи со
                # списковым content — tool_result-блоки, их пропускаем.
                # (P-003, 2026-08-15: раньше брали только last-prompt, а тот пишется
                # лениво — на СЛЕДУЮЩЕМ ходе, из-за чего самая свежая фраза
                # оператора в снапшот не попадала.)
                content = rec.get("message", {}).get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                text = content.strip()
                if (text.startswith("<local-command") or
                    text.startswith("<command-") or
                    text.startswith("<task-notification") or
                    text.startswith("[SYSTEM") or
                    text.startswith("This session is being continued") or
                    text.startswith("Continue from where")):
                    continue
                if text.startswith("<!-- attach -->"):
                    lines = text.splitlines()
                    filtered_lines = [
                        line for line in lines
                        if not (line.lstrip().startswith(">") or "<!-- attach -->" in line)
                    ]
                    text = "\n".join(filtered_lines)
                add_user_msg(text)
            elif rec.get("type") == "last-prompt":
                # Запасной источник (пишется с лагом в один ход) — дубликаты гасит add_user_msg.
                text = rec.get("lastPrompt")
                if not isinstance(text, str) or not text.strip():
                    continue
                text = text.strip()
                if "<local-command-" in text or text.startswith("[SYSTEM NOTIFICATION"):
                    continue
                add_user_msg(text)
            elif rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
                compact_seen = True
        except Exception:
            continue

    return {
        "files": files,
        "commands": commands,
        "user_msgs": user_msgs,
        "ctx_tokens": ctx_tokens,
        "compact_seen": compact_seen,
        "cwd": cwd
    }


def git_state(cwd: str) -> dict:
    if not cwd or not (Path(cwd) / ".git").exists():
        return {}
    
    result = {}
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0:
            result["branch"] = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0:
            result["head"] = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace"
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            result["dirty"] = lines[:30]
    except Exception:
        pass

    return result


def prune_old(keep: int = MAX_SNAPSHOTS_KEEP) -> None:
    try:
        files = list(SNAP_DIR.glob("snap_*.md"))
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[keep:]:
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass


def build_markdown(payload: dict, collected: dict, git: dict, ts: str) -> str:
    trigger = payload.get("trigger", "?")
    session_id = payload.get("session_id", "?")
    # Транскрипт приоритетнее payload: см. комментарий в collect_from_transcript.
    cwd = collected.get("cwd") or payload.get("cwd", "?")
    ctx_k = round(collected["ctx_tokens"] / 1000)
    if ctx_k == 0:
        ctx_str = "неизвестно"
    else:
        ctx_str = f"~{ctx_k}k токенов"

    compact_seen_str = "да" if collected["compact_seen"] else "нет"

    user_msgs = "\n".join(f"> {msg}" for msg in collected["user_msgs"])
    if not user_msgs:
        user_msgs = "_(в хвосте транскрипта не найдено)_"

    files = "\n".join(f"- `{f}`" for f in collected["files"])
    if not files:
        files = "_(нет)_"

    commands = "\n".join(f"{i+1}. `{cmd}`" for i, cmd in enumerate(collected["commands"]))
    if not commands:
        commands = "_(нет)_"

    git_section = ""
    if not git:
        git_section = "_(не git-репозиторий)_"
    else:
        git_section += f"- Ветка: {git.get('branch', 'неизвестно')}\n"
        git_section += f"- Хэш: {git.get('head', 'неизвестно')}\n"
        if git.get("dirty"):
            git_section += "Незакоммиченные изменения:\n```\n" + "\n".join(git["dirty"]) + "\n```\n"
        else:
            git_section += "Рабочее дерево чистое.\n"

    return f"""# Снапшот перед сжатием контекста

- **Когда:** {ts}
- **Триггер:** {trigger}  (`auto` = контекст переполнился сам, `manual` = оператор набрал /compact)
- **Сессия:** {session_id}
- **Рабочая папка:** {cwd}
- **Контекст на момент сжатия:** {ctx_str}
- **Сессия уже сжималась ранее:** {compact_seen_str}

## Последние указания оператора (дословно, свежие внизу)
{user_msgs}

## Файлы, которые правились в этой сессии
{files}

## Последние команды
{commands}

## Git
{git_section}

---
⚠️ Это МЕХАНИЧЕСКИЙ снапшот: только то, что скрипт видит достоверно. Он НЕ заменяет
SESSION-STATE.md — смысл работы, решения и планы там. Сверься с обоими.
"""


def main() -> int:
    # Разбор payload — в СВОЁМ try: битый JSON на входе не должен отменять
    # запись снапшота (лучше снапшот с "?" в шапке, чем молчаливое ничего).
    payload = {}
    try:
        # Байты, а не текст: reconfigure выше мог не примениться (например если
        # stdin — не TextIOWrapper). Байтовый путь не зависит от кодировки консоли
        # вообще — единый стандарт для всех хуков после FR-006.
        stdin_data = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        if stdin_data and stdin_data.strip():
            parsed = json.loads(stdin_data)
            if isinstance(parsed, dict):
                payload = parsed
    except Exception:
        payload = {}

    try:
        tp = payload.get("transcript_path") or ""
        tail = read_tail(tp) if tp and os.path.isfile(tp) else ""
        collected = collect_from_transcript(tail)
        git = git_state(str(collected.get("cwd") or payload.get("cwd") or ""))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        
        session_id = str(payload.get("session_id") or "unknown")
        tag = re.sub(r"[^A-Za-z0-9\-]", "", session_id)[:8]
        
        fname = f"snap_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{tag}.md"
        full_path = SNAP_DIR / fname
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(build_markdown(payload, collected, git, ts))
        
        latest_path = SNAP_DIR / "latest.json"
        latest_data = {
            "path": str(full_path),
            "ts": ts,
            "session_id": session_id,
            "cwd": str(collected.get("cwd") or payload.get("cwd") or ""),
            "trigger": str(payload.get("trigger") or "?")
        }
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(latest_data, f, ensure_ascii=False, indent=2)
        
        prune_old()
        
        print(json.dumps({"suppressOutput": True}))
        return 0
    except Exception:
        try:
            print(json.dumps({"suppressOutput": True}))
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        try:
            print(json.dumps({"suppressOutput": True}))
        except Exception:
            pass
        sys.exit(0)
