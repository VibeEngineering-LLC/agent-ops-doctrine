Write a single Python 3 test file `test_subagent_last_answer.py`. Output ONLY Python code, no markdown fences, no prose.

It tests a script `subagent_last_answer.py` located in the SAME directory as the test file, by running it as a subprocess: `[sys.executable, str(SCRIPT), <path>]`, capturing stdout as bytes and stderr, with env containing PYTHONIOENCODING=utf-8. Target script path: `SCRIPT = pathlib.Path(__file__).with_name("subagent_last_answer.py")`; the target may be overridden by the first command line argument (`sys.argv[1]` if given) — this is used for mutation testing.

Use only the standard library (json, os, pathlib, subprocess, sys, tempfile). No pytest; plain functions called from a runner. Each test writes its transcript into a fresh temporary directory (tempfile.mkdtemp), file name `agent-a1b2c3.jsonl`, lines joined with "\n" and encoded UTF-8 (use json.dumps(obj, ensure_ascii=False) for each record).

Helper records:
- A(text) = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
- U(text) = {"type": "user", "message": {"role": "user", "content": text}}

Test cases (each returns True/False). Output line per case, where N is the case number 1..12 below: "CASE N: PASS <name>" or "CASE N: FAIL <name>: <details>". A case that raises an exception counts as FAIL (catch it in the runner and print the FAIL line).
1. t_last_of_three: records U("бриф"), A("первый"), A("второй"), A("## Итог\nТретий ответ — кириллица, «кавычки».") -> exit 0, stdout bytes == the third text encoded UTF-8 exactly.
2. t_skip_tool_only: A("отчёт"), then assistant record whose content is [{"type":"tool_use","id":"x","name":"Bash","input":{}}] -> exit 0, stdout == "отчёт".
3. t_skip_whitespace: A("настоящий"), A("   \n  ") -> exit 0, stdout == "настоящий".
4. t_concat_blocks: one assistant record with content [{"type":"text","text":"часть1 "},{"type":"thinking","thinking":"скрыто"},{"type":"text","text":"часть2"}] -> exit 0, stdout == "часть1 часть2".
5. t_string_content: {"type":"assistant","message":{"content":"строкой"}} -> exit 0, stdout == "строкой".
6. t_user_not_counted: A("ответ"), U("позднее сообщение пользователя") -> exit 0, stdout == "ответ".
7. t_u2028_inside: A("до после") -> exit 0, stdout == "до после" encoded UTF-8.
8. t_garbage_lines: file content = b"not json\n" + A("годный") line + b"\n\xff\xfe broken\n" -> exit 0, stdout == "годный".
9. t_no_answer: only U("бриф") -> exit 3, stdout empty.
10. t_missing_file: path to a non-existent file in the temp dir -> exit 2.
11. t_no_args: run with no path argument at all -> exit 2.
12. t_no_trailing_newline: A("ровно") -> stdout == "ровно".encode("utf-8") exactly and stdout does not end with b"\n".

IMPORTANT: create temp dirs as `tmpdir = tempfile.mkdtemp()` — a plain call, NEVER `with tempfile.mkdtemp()` (it returns a str, not a context manager). Expected stdout in every case is EXACTLY the full text given to A(...) in that case, character for character (case 1: the whole string "## Итог\nТретий ответ — кириллица, «кавычки»." including the heading, the newline and the final period). Define each case's text once in a variable and reuse that variable both in A(...) and in the expected value.

IMPORTANT: bytes literals b"..." may contain ONLY ASCII characters (Python syntax rule). Build every expected Cyrillic byte string as "<text>".encode("utf-8"), never as b"<cyrillic>". For case 8 build the file content as b"not json\n" + json.dumps(A("годный"), ensure_ascii=False).encode("utf-8") + b"\n\xff\xfe broken\n".

Runner: run all tests in order, count failures, print a line exactly "итог: N/12" where N is the number passed. If all 12 passed, print a final line exactly "SELFTEST OK" and exit 0; otherwise do NOT print "SELFTEST OK" anywhere and exit 1. Call sys.stdout.reconfigure(encoding="utf-8") at start.
