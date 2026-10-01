#!/usr/bin/env python3
"""
mutation_runner_selftest.py

Универсальный мутационный раннер для self-contained скриптов с --selftest.
"""

import sys
import json
import subprocess
from pathlib import Path

def main():
    # Настройка вывода stdout для корректной работы с UTF-8 на Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # reconfigure может отсутствовать в старых версиях Python, но обычно есть в 3.7+

    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <target.py> <mutants.json>")
        sys.exit(2)

    target_path = Path(sys.argv[1])
    mutants_json_path = Path(sys.argv[2])

    # Проверка существования файлов
    if not target_path.exists():
        print(f"ERROR: Target file '{target_path}' does not exist.")
        sys.exit(2)
    
    if not mutants_json_path.exists():
        print(f"ERROR: Mutants JSON file '{mutants_json_path}' does not exist.")
        sys.exit(2)

    # 1. Прочитать target.py как текст
    try:
        original_text = target_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: Failed to read target file: {e}")
        sys.exit(2)

    # 2. Базовая линия
    print("Running baseline test...")
    try:
        baseline_result = subprocess.run(
            [sys.executable, "-B", str(target_path), "--selftest"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180
        )
    except subprocess.TimeoutExpired:
        print("BASELINE FAILED: Timeout")
        sys.exit(3)
    except Exception as e:
        print(f"BASELINE FAILED: {e}")
        sys.exit(3)

    if baseline_result.returncode != 0 or "SELFTEST OK" not in baseline_result.stdout:
        print("BASELINE FAILED")
        print("--- STDOUT ---")
        print(baseline_result.stdout)
        print("--- STDERR ---")
        print(baseline_result.stderr)
        sys.exit(3)
    
    print("Baseline passed.")

    # 3. Прочитать mutants.json
    try:
        with open(mutants_json_path, 'r', encoding='utf-8') as f:
            mutants = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse mutants JSON: {e}")
        sys.exit(2)

    if not isinstance(mutants, list):
        print("ERROR: mutants.json must contain a list of objects.")
        sys.exit(2)

    # 4. Обработка мутаций
    killed = 0
    survived = 0
    errors = 0
    total_valid = 0
    
    stem = target_path.stem
    parent_dir = target_path.parent

    for mutant in mutants:
        if not isinstance(mutant, dict):
            print("ERROR: Invalid mutant entry (not a dict)")
            errors += 1
            continue
            
        name = mutant.get("name", "unknown")
        old_str = mutant.get("old")
        new_str = mutant.get("new")

        if old_str is None or new_str is None:
            print(f"MUTANT {name}: ERROR missing 'old' or 'new' field")
            errors += 1
            continue

        # Проверка количества вхождений old
        count = original_text.count(old_str)
        if count != 1:
            print(f"MUTANT {name}: ERROR old-occurrences={count}")
            continue
        
        total_valid += 1

        # Создание временного файла
        temp_file_path = parent_dir / f"{stem}.mut-{name}.py"
        
        try:
            # Замена и запись
            mutated_text = original_text.replace(old_str, new_str, 1)
            temp_file_path.write_text(mutated_text, encoding="utf-8")

            # Запуск мутанта
            result = subprocess.run(
                [sys.executable, "-B", str(temp_file_path), "--selftest"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180
            )

            # Критерий "убита": код возврата != 0 ИЛИ нет "SELFTEST OK" в stdout
            is_killed = (result.returncode != 0) or ("SELFTEST OK" not in result.stdout)

            if is_killed:
                print(f"MUTANT {name}: KILLED")
                killed += 1
            else:
                print(f"MUTANT {name}: SURVIVED (BAD)")
                survived += 1

        except subprocess.TimeoutExpired:
            print(f"MUTANT {name}: ERROR Timeout")
            errors += 1
        except OSError as e:
            print(f"MUTANT {name}: ERROR {e}")
            errors += 1
        except Exception as e:
            print(f"MUTANT {name}: ERROR {e}")
            errors += 1
        finally:
            # Удаление временного файла
            try:
                if temp_file_path.exists():
                    temp_file_path.unlink()
            except Exception:
                pass

    # 6. Итог
    print(f"\nMutation results:")
    print(f"Killed: {killed}")
    print(f"Survived: {survived}")
    print(f"Errors in mutants: {errors}")
    
    if survived == 0 and killed > 0:
        print(f"MUTATION OK: {killed}/{total_valid}")
        sys.exit(0)
    else:
        print(f"MUTATION FAILED: {killed}/{total_valid}")
        sys.exit(1)

if __name__ == "__main__":
    main()
