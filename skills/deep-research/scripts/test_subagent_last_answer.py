import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT = pathlib.Path(__file__).with_name("subagent_last_answer.py")
if len(sys.argv) > 1:
    SCRIPT = pathlib.Path(sys.argv[1])

def A(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}
    
def U(text):
    return {"type": "user", "message": {"role": "user", "content": text}}

def run_test(case_name, records, expected_exit_code, expected_stdout=None):
    tmpdir = tempfile.mkdtemp()
    try:
        filepath = os.path.join(tmpdir, "agent-a1b2c3.jsonl")
        with open(filepath, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            [sys.executable, str(SCRIPT), filepath],
            capture_output=True,
            text=False,
            env=env
        )
        
        if result.returncode != expected_exit_code:
            return False, f"exit code {result.returncode}, expected {expected_exit_code}"
            
        if expected_stdout is not None and result.stdout != expected_stdout:
            return False, f"stdout mismatch: got {result.stdout!r}, expected {expected_stdout!r}"
            
        return True, ""
    finally:
        import shutil
        shutil.rmtree(tmpdir)

def test_t_last_of_three():
    text = "## Итог\nТретий ответ — кириллица, «кавычки»."
    records = [
        U("бриф"),
        A("первый"),
        A("второй"),
        A(text)
    ]
    return run_test("t_last_of_three", records, 0, text.encode("utf-8"))

def test_t_skip_tool_only():
    text = "отчёт"
    records = [
        A(text),
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type":"tool_use","id":"x","name":"Bash","input":{}}]}}
    ]
    return run_test("t_skip_tool_only", records, 0, text.encode("utf-8"))

def test_t_skip_whitespace():
    text = "настоящий"
    records = [
        A("настоящий"),
        A("   \n  ")
    ]
    return run_test("t_skip_whitespace", records, 0, text.encode("utf-8"))

def test_t_concat_blocks():
    text = "часть1 часть2"
    records = [
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type":"text","text":"часть1 "},{"type":"thinking","thinking":"скрыто"},{"type":"text","text":"часть2"}]}}
    ]
    return run_test("t_concat_blocks", records, 0, text.encode("utf-8"))

def test_t_string_content():
    text = "строкой"
    records = [
        {"type": "assistant", "message": {"content": text}}
    ]
    return run_test("t_string_content", records, 0, text.encode("utf-8"))

def test_t_user_not_counted():
    text = "ответ"
    records = [
        A(text),
        U("позднее сообщение пользователя")
    ]
    return run_test("t_user_not_counted", records, 0, text.encode("utf-8"))

def test_t_u2028_inside():
    text = "до после"
    records = [
        A(text)
    ]
    return run_test("t_u2028_inside", records, 0, text.encode("utf-8"))

def test_t_garbage_lines():
    text = "годный"
    records = [
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type":"text","text":"not json"}]}},
        A(text),
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type":"text","text":"\xff\xfe broken"}]}}
    ]
    # Build file content manually
    content = b"not json\n" + json.dumps(A(text), ensure_ascii=False).encode("utf-8") + b"\n\xff\xfe broken\n"
    tmpdir = tempfile.mkdtemp()
    try:
        filepath = os.path.join(tmpdir, "agent-a1b2c3.jsonl")
        with open(filepath, "wb") as f:
            f.write(content)
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            [sys.executable, str(SCRIPT), filepath],
            capture_output=True,
            text=False,
            env=env
        )
        
        if result.returncode != 0:
            return False, f"exit code {result.returncode}, expected 0"
            
        if result.stdout != text.encode("utf-8"):
            return False, f"stdout mismatch: got {result.stdout!r}, expected {text.encode('utf-8')!r}"
            
        return True, ""
    finally:
        import shutil
        shutil.rmtree(tmpdir)

def test_t_no_answer():
    records = [
        U("бриф")
    ]
    return run_test("t_no_answer", records, 3, b"")

def test_t_missing_file():
    tmpdir = tempfile.mkdtemp()
    try:
        filepath = os.path.join(tmpdir, "nonexistent.jsonl")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            [sys.executable, str(SCRIPT), filepath],
            capture_output=True,
            text=False,
            env=env
        )
        
        if result.returncode != 2:
            return False, f"exit code {result.returncode}, expected 2"
            
        return True, ""
    finally:
        import shutil
        shutil.rmtree(tmpdir)

def test_t_no_args():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=False,
        env=env
    )
    
    if result.returncode != 2:
        return False, f"exit code {result.returncode}, expected 2"
        
    return True, ""

def test_t_no_trailing_newline():
    text = "ровно"
    records = [
        A(text)
    ]
    tmpdir = tempfile.mkdtemp()
    try:
        filepath = os.path.join(tmpdir, "agent-a1b2c3.jsonl")
        with open(filepath, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False))
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        result = subprocess.run(
            [sys.executable, str(SCRIPT), filepath],
            capture_output=True,
            text=False,
            env=env
        )
        
        if result.returncode != 0:
            return False, f"exit code {result.returncode}, expected 0"
            
        if result.stdout != text.encode("utf-8"):
            return False, f"stdout mismatch: got {result.stdout!r}, expected {text.encode('utf-8')!r}"
            
        if result.stdout.endswith(b"\n"):
            return False, "stdout ends with newline"
            
        return True, ""
    finally:
        import shutil
        shutil.rmtree(tmpdir)

def main():
    tests = [
        test_t_last_of_three,
        test_t_skip_tool_only,
        test_t_skip_whitespace,
        test_t_concat_blocks,
        test_t_string_content,
        test_t_user_not_counted,
        test_t_u2028_inside,
        test_t_garbage_lines,
        test_t_no_answer,
        test_t_missing_file,
        test_t_no_args,
        test_t_no_trailing_newline
    ]
    
    passed = 0
    
    for i, test in enumerate(tests, 1):
        try:
            success, details = test()
        except Exception as e:
            success = False
            details = str(e)
            
        if success:
            print(f"CASE {i}: PASS {test.__name__}")
            passed += 1
        else:
            print(f"CASE {i}: FAIL {test.__name__}: {details}")
    
    print(f"итог: {passed}/12")
    
    if passed == 12:
        print("SELFTEST OK")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
