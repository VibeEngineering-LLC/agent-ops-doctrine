#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Это хук SessionStart с матчером `compact`, срабатывающий сразу после компактизации контекста.
Он читает снапшот, оставленный хуком precompact_snapshot.py, и внедряет в контекст агента
КОРОТКИЙ указатель: путь к полному снапшоту, последние инструкции оператора, файлы в работе,
и обязательное требование прочитать SESSION-STATE.md перед продолжением.

Снапшот не внедряется целиком — это противоречило бы цели компактизации.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass
try:
    # См. precompact_snapshot.py — тот же класс бага (stdin не форсирован на
    # UTF-8 на cp1251-консоли). Здесь payload не используется (только читается
    # и отбрасывается), но форсируем для консистентности и защиты.
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SNAP_DIR = Path(os.path.expanduser("~")) / ".claude" / "compact-snapshots"
LATEST = SNAP_DIR / "latest.json"
MAX_AGE_MIN = 30
MAX_PROMPTS_SHOWN = 3
MAX_FILES_SHOWN = 8


def emit(result: dict) -> None:
    try:
        print(json.dumps(result, ensure_ascii=False))
    except UnicodeEncodeError:
        try:
            print(json.dumps(result, ensure_ascii=True))
        except Exception:
            pass


def silent() -> None:
    emit({"suppressOutput": True})


def load_latest() -> dict:
    if not LATEST.is_file():
        return {}
    try:
        with open(LATEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def is_fresh(ts_str: str) -> bool:
    try:
        parsed = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = (now - parsed).total_seconds()
        # -60 с: допуск на рассинхрон часов (снапшот может оказаться "из будущего"
        # на секунды). Верхняя граница — защита от протухшего снапшота прошлой
        # сессии: выдать его за текущий хуже, чем промолчать.
        return -60 <= diff <= MAX_AGE_MIN * 60
    except Exception:
        return False


def extract_sections(md_path: str) -> dict:
    try:
        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return {}

    prompts = []
    files = []
    current_section = None

    for line in text.splitlines():
        if line.startswith("## "):
            if line.startswith("## Последние указания оператора"):
                current_section = "prompts"
                prompts.clear()
            elif line.startswith("## Файлы"):
                current_section = "files"
                files.clear()
            else:
                current_section = None
        elif current_section == "prompts" and line.startswith("> "):
            prompts.append(line[2:].strip())
        elif current_section == "files" and line.startswith("- `"):
            # Извлекаем содержимое между `- ` и '`'
            idx = line.find("`")
            if idx != -1:
                rest = line[idx+1:]
                end_idx = rest.find("`")
                if end_idx != -1:
                    file_name = rest[:end_idx].strip()
                    files.append(file_name)
    prompts = prompts[-MAX_PROMPTS_SHOWN:]
    files = files[-MAX_FILES_SHOWN:]
    return {"prompts": prompts, "files": files}


def build_notice(latest: dict, sections: dict) -> str:
    trigger = latest.get("trigger", "")
    if trigger == "auto":
        trigger = "автоматически, контекст переполнился"
    elif trigger == "manual":
        trigger = "по команде оператора /compact"
    else:
        trigger = str(trigger)

    snap_path = latest.get("path", "?")
    cwd = latest.get("cwd") or "текущий проект"

    prompts = sections.get("prompts", [])
    if not prompts:
        prompts_str = "_(не найдены)_"
    else:
        prompts_str = "\n".join(f"{i+1}. «{p}»" for i, p in enumerate(prompts))

    files = sections.get("files", [])
    if not files:
        files_str = "_(нет)_"
    else:
        files_str = "\n".join(f"- `{f}`" for f in files)

    notice = f"""⚠️ КОНТЕКСТ ТОЛЬКО ЧТО СЖАТ ({trigger}). История диалога усечена — часть фактов ты уже не помнишь.

Механический снапшот состояния (записан хуком ДО сжатия, читать при любом сомнении):
{snap_path}

Последние указания оператора перед сжатием:
{prompts_str}

Файлы в работе на момент сжатия:
{files_str}

ОБЯЗАТЕЛЬНО ПЕРВЫМ ДЕЙСТВИЕМ:
1. Прочитать SESSION-STATE.md в корне проекта ({cwd}) — там смысл работы, решения и план.
   Снапшот выше содержит ТОЛЬКО механику (что правилось/запускалось), не замысел.
2. Свериться: совпадает ли состояние на диске с тем, что записано. Расхождение — проверять
   фактом (командой/чтением файла), НЕ достраивать по памяти: после сжатия память ненадёжна.
3. Если SESSION-STATE.md устарел или его нет — обновить/создать СЕЙЧАС, до продолжения работы.
4. Не начинать новых крупных задач, пока пункты 1-3 не закрыты."""
    return notice


def main() -> int:
    try:
        sys.stdin.buffer.read()  # байты; payload не используется, просто дренируем
    except Exception:
        pass

    latest = load_latest()
    if not latest:
        silent()
        return 0

    if not is_fresh(str(latest.get("ts") or "")):
        silent()
        return 0

    md_path = str(latest.get("path") or "")
    sections = extract_sections(md_path) if md_path else {}

    notice = build_notice(latest, sections)
    emit({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": notice,
        },
        "suppressOutput": True,
    })
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        silent()
        sys.exit(0)
