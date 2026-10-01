#!/usr/bin/env python3
"""extract_bash_commands.py: Extract Bash tool calls and results from Claude Code JSONL transcripts."""

import json
import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def extract_bash_data(input_path):
    """
    Reads a JSONL file and extracts Bash commands and their results.
    
    Returns:
        tuple: (commands_list, total_count, error_count, missing_result_count)
            - commands_list: list of dicts with keys: number, timestamp, description, command, result_text, is_error, has_result
            - total_count: int
            - error_count: int
            - missing_result_count: int
    """
    # Step 3: Collect Bash calls
    bash_calls = []
    
    # Step 4: Collect results map (tool_use_id -> result info)
    results_map = {}
    
    try:
        with open(input_path, "rb") as f:
            for line_bytes in f:
                # Decode with replace to handle bad bytes
                line_str = line_bytes.decode("utf-8", errors="replace")
                
                # Parse JSON
                try:
                    record = json.loads(line_str)
                except (json.JSONDecodeError, ValueError):
                    continue
                
                if not isinstance(record, dict):
                    continue
                    
                # Check for message and content
                message = record.get("message")
                if not isinstance(message, dict):
                    continue
                    
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                
                record_type = record.get("type")
                
                # Step 3: Collect Bash calls (assistant type)
                if record_type == "assistant":
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use" and block.get("name") == "Bash":
                            tool_id = block.get("id", "")
                            input_data = block.get("input", {})
                            command = input_data.get("command", "") if isinstance(input_data, dict) else ""
                            description = input_data.get("description", None) if isinstance(input_data, dict) else None
                            timestamp = record.get("timestamp", None)
                            
                            bash_calls.append({
                                "id": tool_id,
                                "command": command if command else "",
                                "description": description,
                                "timestamp": timestamp
                            })
                
                # Step 4: Collect results (user type)
                elif record_type == "user":
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_result":
                            tool_use_id = block.get("tool_use_id", "")
                            if not tool_use_id:
                                continue
                            
                            # Only take first occurrence
                            if tool_use_id in results_map:
                                continue
                            
                            # Extract text content
                            result_content = block.get("content")
                            is_error = block.get("is_error", False)
                            
                            if isinstance(result_content, str):
                                text = result_content
                            elif isinstance(result_content, list):
                                texts = []
                                for item in result_content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        texts.append(item.get("text", ""))
                                text = "".join(texts)
                            else:
                                text = ""
                            
                            results_map[tool_use_id] = {
                                "text": text,
                                "is_error": bool(is_error)
                            }
    
    except OSError as e:
        print(f"Error reading file: {e}", file=sys.stdout)
        sys.exit(3)
    
    # Step 5: Merge calls with results
    commands_list = []
    error_count = 0
    missing_result_count = 0
    
    for idx, call in enumerate(bash_calls, start=1):
        tool_id = call["id"]
        result_info = results_map.get(tool_id)
        
        if result_info:
            result_text = result_info["text"]
            is_error = result_info["is_error"]
            has_result = True
        else:
            result_text = "результат не найден в транскрипте"
            is_error = False
            has_result = False
            missing_result_count += 1
        
        if is_error:
            error_count += 1
        
        commands_list.append({
            "number": idx,
            "timestamp": call["timestamp"],
            "description": call["description"],
            "command": call["command"],
            "result_text": result_text,
            "is_error": is_error,
            "has_result": has_result
        })
    
    return commands_list, len(commands_list), error_count, missing_result_count


def generate_markdown(commands_list, total_count, error_count, missing_result_count, input_path):
    """Generate Markdown content from extracted data."""
    lines = []
    
    # Header
    abs_input_path = os.path.abspath(input_path)
    lines.append("# Bash-команды транскрипта")
    lines.append("")
    lines.append(f"Источник: `{abs_input_path}`")
    lines.append(f"Всего команд: {total_count}")
    lines.append(f"Из них с ошибкой (is_error=true): {error_count}")
    lines.append(f"Без результата в транскрипте: {missing_result_count}")
    lines.append("")
    
    # Commands
    for cmd in commands_list:
        timestamp = cmd["timestamp"] if cmd["timestamp"] else "время неизвестно"
        description = cmd["description"] if cmd["description"] else "—"
        
        lines.append(f"## {cmd['number']}. {timestamp}")
        lines.append(f"**Описание:** {description}")
        lines.append("")
        lines.append("**Команда:**")
        lines.append("```")
        lines.append(cmd["command"])
        lines.append("```")
        lines.append("")
        
        # Determine result status label
        if not cmd["has_result"]:
            status_label = "не найден"
        elif cmd["is_error"]:
            status_label = "ошибка"
        else:
            status_label = "успех"
        
        result_text = cmd["result_text"]
        original_len = len(result_text)
        
        # Truncate if needed
        if len(result_text) > 2000:
            truncated = result_text[:2000] + "[...обрезано]"
            lines.append(f"**Результат** ({status_label}, {original_len} символов, обрезано до 2000):")
        else:
            truncated = result_text
            lines.append(f"**Результат** ({status_label}, {original_len} символов):")
        
        lines.append("```")
        lines.append(truncated)
        lines.append("```")
        lines.append("")
    
    return "\n".join(lines)


def main():
    # Reconfigure stdout for UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    
    args = sys.argv[1:]
    
    # Check for --selftest
    if "--selftest" in args:
        if len(args) != 1:
            print("Usage: python extract_bash_commands.py <path_to_transcript.jsonl> [-o OUTPUT_FILE.md]")
            print("       python extract_bash_commands.py --selftest")
            sys.exit(2)
        
        selftest()
        return
    
    # Check for positional argument
    if len(args) == 0:
        print("Usage: python extract_bash_commands.py <path_to_transcript.jsonl> [-o OUTPUT_FILE.md]")
        sys.exit(2)
    
    input_path = args[0]
    output_path = None
    
    # Parse optional -o argument
    i = 1
    while i < len(args):
        if args[i] == "-o" and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        else:
            i += 1
    
    # Check if input file exists and is readable
    if not os.path.exists(input_path):
        print(f"Input file does not exist: {input_path}")
        sys.exit(3)
    
    try:
        with open(input_path, "rb") as f:
            pass  # Just check readability
    except OSError as e:
        print(f"Cannot read input file: {e}")
        sys.exit(3)
    
    # Determine output path if not specified
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.with_name(p.stem + "-bash-commands.md"))
    
    # Extract data
    commands_list, total_count, error_count, missing_result_count = extract_bash_data(input_path)
    
    # Generate Markdown
    md_content = generate_markdown(commands_list, total_count, error_count, missing_result_count, input_path)
    
    # Write output file
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)
    except OSError as e:
        print(f"Error writing output file: {e}")
        sys.exit(3)
    
    # Print summary to stdout
    print(f"Report written to: {output_path}")
    print(f"Summary: {total_count} commands, {error_count} errors, {missing_result_count} missing results")
    
    sys.exit(0)


def selftest():
    """Run self-tests and return exit code (0 for success, 1 for failure)."""
    tmpdir = tempfile.mkdtemp()
    passed_all = True
    
    try:
        # Test 1: Basic functionality with various scenarios
        result1 = test_basic_functionality(tmpdir)
        if not result1:
            passed_all = False
        
        # Test 2: No Bash commands
        result2 = test_no_bash_commands(tmpdir)
        if not result2:
            passed_all = False
        
        # Test 3: Non-existent file
        result3 = test_nonexistent_file()
        if not result3:
            passed_all = False
        
        # Test 4: No arguments
        result4 = test_no_arguments()
        if not result4:
            passed_all = False
        
        # Test 5: Binary garbage in lines
        result5 = test_binary_garbage(tmpdir)
        if not result5:
            passed_all = False
        
        if passed_all:
            print("SELFTEST OK")
            return 0
        else:
            print("SELFTEST FAILED")
            return 1
    
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_basic_functionality(tmpdir):
    """Test basic extraction with various scenarios."""
    print("Running test: Basic functionality")
    
    transcript_path = os.path.join(tmpdir, "test_transcript.jsonl")
    output_path = os.path.join(tmpdir, "output.md")
    
    # Create synthetic JSONL transcript
    lines = []
    
    # 1. Garbage non-JSON line
    lines.append("this is not json at all\n")
    
    # 2. JSON but not dict
    lines.append("[1, 2, 3]\n")
    
    # 3. Bash call #1 with result (string content, cyrillic)
    bash_call_1 = {
        "type": "assistant",
        "timestamp": "2026-08-30T12:26:58.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_001",
                    "name": "Bash",
                    "input": {
                        "command": "echo привет",
                        "description": "Тест 1"
                    }
                }
            ]
        }
    }
    lines.append(json.dumps(bash_call_1, ensure_ascii=False) + "\n")
    
    # Result for bash_call_1
    result_1 = {
        "type": "user",
        "timestamp": "2026-08-30T12:26:59.000Z",
        "message": {
            "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_001",
                    "type": "tool_result",
                    "content": "привет мир\n",
                    "is_error": False
                }
            ]
        }
    }
    lines.append(json.dumps(result_1, ensure_ascii=False) + "\n")
    
    # 4. Non-Bash tool call (should be ignored)
    non_bash_call = {
        "type": "assistant",
        "timestamp": "2026-08-30T12:27:00.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_002",
                    "name": "Read",
                    "input": {"file": "test.txt"}
                }
            ]
        }
    }
    lines.append(json.dumps(non_bash_call) + "\n")
    
    # 5. Bash call #2 without description, with list content result, is_error=true
    bash_call_2 = {
        "type": "assistant",
        "timestamp": "2026-08-30T12:27:01.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_003",
                    "name": "Bash",
                    "input": {
                        "command": "ls -la"
                    }
                }
            ]
        }
    }
    lines.append(json.dumps(bash_call_2) + "\n")
    
    # Result for bash_call_2 with list content
    result_2 = {
        "type": "user",
        "timestamp": "2026-08-30T12:27:02.000Z",
        "message": {
            "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_003",
                    "type": "tool_result",
                    "content": [
                        {"type": "text", "text": "total 0\n"},
                        {"type": "text", "text": "drwxr-xr-x"}
                    ],
                    "is_error": True
                }
            ]
        }
    }
    lines.append(json.dumps(result_2) + "\n")
    
    # 6. Bash call #3 with no result
    bash_call_3 = {
        "type": "assistant",
        "timestamp": "2026-08-30T12:27:03.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_004",
                    "name": "Bash",
                    "input": {
                        "command": "sleep 999"
                    }
                }
            ]
        }
    }
    lines.append(json.dumps(bash_call_3) + "\n")
    
    # 7. Bash call #4 with long result (>2000 chars)
    bash_call_4 = {
        "type": "assistant",
        "timestamp": "2026-08-30T12:27:04.000Z",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_005",
                    "name": "Bash",
                    "input": {
                        "command": "cat large_file.txt"
                    }
                }
            ]
        }
    }
    lines.append(json.dumps(bash_call_4) + "\n")
    
    # Long result for bash_call_4
    long_text = "A" * 2500
    result_4 = {
        "type": "user",
        "timestamp": "2026-08-30T12:27:05.000Z",
        "message": {
            "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_005",
                    "type": "tool_result",
                    "content": long_text,
                    "is_error": False
                }
            ]
        }
    }
    lines.append(json.dumps(result_4) + "\n")
    
    # Write transcript file
    with open(transcript_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line)
    
    # Run the script
    try:
        result = subprocess.run(
            [sys.executable, __file__, transcript_path, "-o", output_path],
            capture_output=True,
            encoding="utf-8",
            errors="replace"
        )
    except Exception as e:
        print(f"FAIL Basic functionality: subprocess failed with {e}")
        return False
    
    if result.returncode != 0:
        print(f"FAIL Basic functionality: non-zero exit code {result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        return False
    
    # Read output file
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"FAIL Basic functionality: cannot read output file: {e}")
        return False
    
    # Check total commands count
    if "Всего команд: 4" not in content:
        print("FAIL Basic functionality: expected 'Всего команд: 4'")
        return False
    
    # Check error count
    if "Из них с ошибкой (is_error=true): 1" not in content:
        print("FAIL Basic functionality: expected 'Из них с ошибкой (is_error=true): 1'")
        return False
    
    # Check missing result count
    if "Без результата в транскрипте: 1" not in content:
        print("FAIL Basic functionality: expected 'Без результата в транскрипте: 1'")
        return False
    
    # Check cyrillic command and result
    if "echo привет" not in content:
        print("FAIL Basic functionality: missing 'echo привет' command")
        return False
    
    if "привет мир" not in content:
        print("FAIL Basic functionality: missing cyrillic result")
        return False
    
    # Check description placeholder for bash call #2
    if "**Описание:** —" not in content:
        print("FAIL Basic functionality: missing description placeholder '—'")
        return False
    
    # Check concatenated text blocks for bash call #2
    expected_concat = "total 0\ndrwxr-xr-x"
    if expected_concat not in content:
        print(f"FAIL Basic functionality: missing concatenated result '{expected_concat}'")
        return False
    
    # Check missing result marker for bash call #3
    # Find the section for sleep 999 and check it contains "результат не найден в транскрипте"
    sections = content.split("## ")
    found_sleep_section = False
    for section in sections:
        if "sleep 999" in section:
            found_sleep_section = True
            if "результат не найден в транскрипте" not in section:
                print("FAIL Basic functionality: sleep 999 section missing 'результат не найден в транскрипте'")
                return False
            break
    
    if not found_sleep_section:
        print("FAIL Basic functionality: could not find sleep 999 section")
        return False
    
    # Check truncation for long result
    if "[...обрезано]" not in content:
        print("FAIL Basic functionality: missing truncation marker '[...обрезано]'")
        return False
    
    # Verify that the full 2500 chars are NOT present (only truncated version)
    if "A" * 2500 in content:
        print("FAIL Basic functionality: full long text should not be present")
        return False
    
    print("PASS Basic functionality")
    return True


def test_no_bash_commands(tmpdir):
    """Test with no Bash commands."""
    print("Running test: No Bash commands")
    
    transcript_path = os.path.join(tmpdir, "no_bash.jsonl")
    output_path = os.path.join(tmpdir, "no_bash_output.md")
    
    # Create transcript with only non-Bash content
    lines = []
    user_msg = {
        "type": "user",
        "timestamp": "2026-08-30T12:00:00.000Z",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "Hello"}]
        }
    }
    lines.append(json.dumps(user_msg) + "\n")
    
    with open(transcript_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line)
    
    try:
        result = subprocess.run(
            [sys.executable, __file__, transcript_path, "-o", output_path],
            capture_output=True,
            encoding="utf-8",
            errors="replace"
        )
    except Exception as e:
        print(f"FAIL No Bash commands: subprocess failed with {e}")
        return False
    
    if result.returncode != 0:
        print(f"FAIL No Bash commands: non-zero exit code {result.returncode}")
        return False
    
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"FAIL No Bash commands: cannot read output file: {e}")
        return False
    
    if "Всего команд: 0" not in content:
        print("FAIL No Bash commands: expected 'Всего команд: 0'")
        return False
    
    print("PASS No Bash commands")
    return True


def test_nonexistent_file():
    """Test with non-existent input file."""
    print("Running test: Non-existent file")
    
    try:
        result = subprocess.run(
            [sys.executable, __file__, "/nonexistent/path/file.jsonl"],
            capture_output=True,
            encoding="utf-8",
            errors="replace"
        )
    except Exception as e:
        print(f"FAIL Non-existent file: subprocess failed with {e}")
        return False
    
    if result.returncode != 3:
        print(f"FAIL Non-existent file: expected exit code 3, got {result.returncode}")
        return False
    
    print("PASS Non-existent file")
    return True


def test_no_arguments():
    """Test with no arguments."""
    print("Running test: No arguments")
    
    try:
        result = subprocess.run(
            [sys.executable, __file__],
            capture_output=True,
            encoding="utf-8",
            errors="replace"
        )
    except Exception as e:
        print(f"FAIL No arguments: subprocess failed with {e}")
        return False
    
    if result.returncode != 2:
        print(f"FAIL No arguments: expected exit code 2, got {result.returncode}")
        return False
    
    # Check that usage message is printed
    if "Usage:" not in result.stdout and "Usage:" not in result.stderr:
        print("FAIL No arguments: missing usage message")
        return False
    
    print("PASS No arguments")
    return True


def test_binary_garbage(tmpdir):
    """Test with binary garbage in lines."""
    print("Running test: Binary garbage")
    
    transcript_path = os.path.join(tmpdir, "binary_garbage.jsonl")
    output_path = os.path.join(tmpdir, "binary_output.md")
    
    # Create file with mixed content including binary garbage
    with open(transcript_path, "wb") as f:
        # Valid JSON line
        valid_line = json.dumps({
            "type": "assistant",
            "timestamp": "2026-08-30T12:00:00.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_001",
                        "name": "Bash",
                        "input": {"command": "echo test"}
                    }
                ]
            }
        }) + "\n"
        f.write(valid_line.encode("utf-8"))
        
        # Binary garbage line (non-UTF-8 bytes)
        f.write(b"\xff\xfe\x98\x99\n")
        
        # Another valid JSON line with result
        result_line = json.dumps({
            "type": "user",
            "timestamp": "2026-08-30T12:00:01.000Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "tool_use_id": "toolu_001",
                        "type": "tool_result",
                        "content": "test output",
                        "is_error": False
                    }
                ]
            }
        }) + "\n"
        f.write(result_line.encode("utf-8"))
    
    try:
        result = subprocess.run(
            [sys.executable, __file__, transcript_path, "-o", output_path],
            capture_output=True,
            encoding="utf-8",
            errors="replace"
        )
    except Exception as e:
        print(f"FAIL Binary garbage: subprocess failed with {e}")
        return False
    
    if result.returncode != 0:
        print(f"FAIL Binary garbage: non-zero exit code {result.returncode}")
        return False
    
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"FAIL Binary garbage: cannot read output file: {e}")
        return False
    
    if "Всего команд: 1" not in content:
        print("FAIL Binary garbage: expected 'Всего команд: 1'")
        return False
    
    if "echo test" not in content:
        print("FAIL Binary garbage: missing command")
        return False
    
    print("PASS Binary garbage")
    return True


if __name__ == "__main__":
    main()
