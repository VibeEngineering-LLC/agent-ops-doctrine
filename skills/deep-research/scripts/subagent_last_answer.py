# Последний текстовый ответ субагента из транскрипта харнесса -> stdout (UTF-8), байт в байт.
# Транскрипт: <home>\.claude\projects\<проект>\<сессия>\subagents\agent-<id>.jsonl
# Использование: subagent_last_answer.py <agent-<id>.jsonl>. Коды: 0 ок, 2 аргументы/нет файла, 3 нет ответа.

import json
import pathlib
import sys

def text_of(rec):
    msg = rec.get("message") or {}
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""

def main(argv):
    if len(argv) != 2 or not pathlib.Path(argv[1]).is_file():
        print("использование: subagent_last_answer.py <agent-<id>.jsonl>", file=sys.stderr)
        return 2
    last = None
    with open(argv[1], "rb") as f:
        for line in f.read().split(b"\n"):
            if not line:
                continue
            try:
                rec = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(rec, dict) and rec.get("type") == "assistant":
                txt = text_of(rec)
                if txt.strip():
                    last = txt
    if last is None:
        print("в транскрипте нет текстового ответа assistant", file=sys.stderr)
        return 3
    sys.stdout.buffer.write(last.encode("utf-8"))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
