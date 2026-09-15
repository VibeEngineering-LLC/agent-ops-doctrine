import sys
import json
import argparse
from pathlib import Path

# Импорт guarded_generate из указанного пути
sys.path.insert(0, r"<home>\.claude\skills\workflow\scripts")
from vram_guard_reference import guarded_generate

# Настройка кодировок
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

def read_file_safely(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def split_text(text, max_chunk_size=25000):
    if len(text) <= max_chunk_size:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_chunk_size:
            chunks.append(text)
            break
        
        # Ищем границу строки
        split_pos = text.rfind('\n', 0, max_chunk_size)
        if split_pos == -1 or split_pos < max_chunk_size // 2:
            split_pos = max_chunk_size
        
        chunk = text[:split_pos]
        chunks.append(chunk)
        text = text[split_pos:].lstrip()
    
    return chunks

def process_file(filepath, prompt_template):
    content = read_file_safely(filepath)
    chunks = split_text(content)
    
    all_results = {
        "user_functions": [],
        "interfaces": [],
        "file_formats": [],
        "limits_and_known_issues": [],
        "test_evidence": []
    }
    
    for i, chunk in enumerate(chunks):
        prompt = prompt_template.replace("<содержимое куска>", chunk)
        
        try:
            resp = guarded_generate(
                "qwen3-coder:30b", prompt,
                want_gpu=True, priority=50,
                project="example", agent="docs_inventory",
                fmt="json", temperature=0.0, num_ctx=32768,
                extra_options={"num_predict": 4096},
            )
            text = resp["response"]
            
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                # Повторная попытка с инструкцией
                prompt += "\nВЕРНИ ТОЛЬКО ВАЛИДНЫЙ JSON."
                resp = guarded_generate(
                    "qwen3-coder:30b", prompt,
                    want_gpu=True, priority=50,
                    project="example", agent="docs_inventory",
                    fmt="json", temperature=0.0, num_ctx=32768,
                    extra_options={"num_predict": 4096},
                )
                text = resp["response"]
                try:
                    result = json.loads(text)
                except json.JSONDecodeError as e:
                    return {"_ollama_failure": {"file": str(filepath), "error": str(e)}}
            
            for key in all_results:
                if key in result:
                    all_results[key].extend(result[key])
        
        except Exception as e:
            return {"_ollama_failure": {"file": str(filepath), "error": str(e)}}
    
    all_results["_chunks"] = len(chunks)
    return all_results

def main():
    parser = argparse.ArgumentParser(description="Инвентаризация md-документации через Ollama")
    parser.add_argument("files", nargs="+", help="Пути к markdown-файлам")
    parser.add_argument("--out", help="Выходной JSON файл (опционально)")
    
    args = parser.parse_args()
    
    prompt_template = '''Ты извлекаешь факты из документации проекта. Верни СТРОГО JSON без пояснений, схема:
{
  "user_functions": [{"name": "...", "what": "...", "source_quote": "..."}],
  "interfaces": [{"name": "...", "kind": "web-ui|cli|ble|usb|wifi|file|api", "what": "..."}],
  "file_formats": [{"name": "...", "what": "..."}],
  "limits_and_known_issues": [{"what": "...", "source_quote": "..."}],
  "test_evidence": [{"what": "...", "source_quote": "..."}]
}
Правила: user_functions - только то, что видит/делает ПОЛЬЗОВАТЕЛЬ устройства или
оператор ПК-клиента (не внутренние механизмы). source_quote - короткая дословная
цитата из текста (до 120 символов), подтверждающая пункт. Не выдумывай: нет в
тексте - не включай. Пустые списки допустимы.

ТЕКСТ ДОКУМЕНТА:
<содержимое куска>'''
    
    result = {
        "generated_by": "docs_inventory.py via qwen3-coder:30b",
        "files": {},
        "failures": []
    }
    
    total_files = len(args.files)
    
    for i, file_path in enumerate(args.files):
        sys.stderr.write(f"[{i+1}/{total_files}] файл {file_path} ")
        
        content = read_file_safely(file_path)
        char_count = len(content)
        chunks = split_text(content)
        chunk_count = len(chunks)
        
        sys.stderr.write(f"({char_count} символов, {chunk_count} кусков)\n")
        
        processed_result = process_file(file_path, prompt_template)
        
        if "_ollama_failure" in processed_result:
            result["failures"].append(processed_result["_ollama_failure"])
        else:
            result["files"][str(Path(file_path))] = processed_result
    
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    print(output_json)
    
    if args.out:
        with open(args.out, "w", encoding="utf-8", errors="replace") as f:
            f.write(output_json)

if __name__ == "__main__":
    main()
