# СПЕКА: docs_inventory.py — инвентаризация md-документации через Ollama

## Назначение
CLI-скрипт: принимает список путей к markdown-файлам, для КАЖДОГО файла вызывает
локальную Ollama (qwen3-coder:30b) через guarded_generate и извлекает структурированную
инвентаризацию. Результат — один JSON на stdout (и в файл, если задан --out).

## Импорт донора (дословно, по §33)
```python
import sys
sys.path.insert(0, r"<home>\.claude\skills\workflow\scripts")
from vram_guard_reference import guarded_generate
```

## CLI
```
python docs_inventory.py FILE1.md [FILE2.md ...] [--out OUT.json]
```

## Кодировки (ЖЁСТКО, Windows/cp1251)
- Первые строки: `sys.stdout.reconfigure(encoding="utf-8")` и то же для stderr.
- Все open() с `encoding="utf-8", errors="replace"`.
- json.dump с `ensure_ascii=False, indent=2`.

## Обработка каждого файла
1. Прочитать файл. Если длиннее 30000 символов — резать на куски по ~25000 символов
   по границам строк, каждый кусок обрабатывать отдельным вызовом, результаты
   объединять (списки конкатенировать).
2. Промпт (русский, дословно):

```
Ты извлекаешь факты из документации проекта. Верни СТРОГО JSON без пояснений, схема:
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
<содержимое куска>
```

3. Вызов (сигнатура сверена с донором, использовать ровно так):
   ```python
   resp = guarded_generate(
       "qwen3-coder:30b", prompt,
       want_gpu=True, priority=50,
       project="example", agent="docs_inventory",
       fmt="json", temperature=0.0, num_ctx=32768,
       extra_options={"num_predict": 4096},
   )
   text = resp["response"]
   ```
4. Ответ `text` распарсить json.loads. При JSONDecodeError — одна повторная попытка с тем же
   промптом + строкой "ВЕРНИ ТОЛЬКО ВАЛИДНЫЙ JSON.". Вторая неудача — в результат
   записать {"_ollama_failure": {"file": путь, "error": текст ошибки}} и продолжить
   со следующим файлом (НЕ падать).

## Выходной JSON (stdout всегда, --out опционально)
```json
{
  "generated_by": "docs_inventory.py via qwen3-coder:30b",
  "files": {
    "<путь>": { ...схема выше..., "_chunks": N }
  },
  "failures": [ ...список _ollama_failure если были... ]
}
```

## Прочее
- Прогресс печатать в stderr: "[i/N] файл (K символов, M кусков)".
- Никаких сторонних библиотек кроме стандартных (json, sys, argparse, pathlib).
- Скрипт идемпотентен, ничего не пишет кроме --out.
