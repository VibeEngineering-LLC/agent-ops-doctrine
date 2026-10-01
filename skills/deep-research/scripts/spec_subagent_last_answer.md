Write a single Python 3 file `subagent_last_answer.py`. Output ONLY the Python code, no markdown fences, no prose.

Purpose: extract the LAST non-empty text answer of an assistant from a Claude Code subagent transcript (JSONL file) and write it to stdout as UTF-8 bytes, byte for byte.

Top comment (3 lines, Russian, exactly):
# Последний текстовый ответ субагента из транскрипта харнесса -> stdout (UTF-8), байт в байт.
# Транскрипт: <home>\.claude\projects\<проект>\<сессия>\subagents\agent-<id>.jsonl
# Использование: subagent_last_answer.py <agent-<id>.jsonl>. Коды: 0 ок, 2 аргументы/нет файла, 3 нет ответа.

Requirements:
1. Imports: only `json`, `pathlib`, `sys`. No other modules.
2. Function `text_of(rec: dict) -> str`: take `rec.get("message")` (treat None/non-dict as {}), then its "content".
   - if content is a str -> return it;
   - if content is a list -> return concatenation of `b.get("text") or ""` for every element b that is a dict with b.get("type") == "text"; other elements (tool_use, thinking, strings) are ignored;
   - anything else -> return "".
3. Function `main(argv: list) -> int`:
   - if len(argv) != 2 or argv[1] is not an existing regular file: print "использование: subagent_last_answer.py <agent-<id>.jsonl>" to stderr, return 2.
   - read the file as BYTES; split ONLY on b"\n" (do NOT use splitlines: U+2028 may appear inside text).
   - for each line: try json.loads(line.decode("utf-8")); on ValueError (this includes UnicodeDecodeError and JSONDecodeError) skip the line.
   - a record counts if it is a dict, rec.get("type") == "assistant", and text_of(rec).strip() is non-empty; keep the text of the LAST such record (unstripped, exactly as text_of returned it).
   - if none: print "в транскрипте нет текстового ответа assistant" to stderr, return 3.
   - else write last.encode("utf-8") to sys.stdout.buffer (no trailing newline added), return 0.
4. At module bottom: `if __name__ == "__main__": sys.exit(main(sys.argv))`.
5. Keep it short: at most 30 lines total. No classes, no argparse, no logging.
