# СПЕКА: verify_aswf.py — независимая проверка целостности .aswf (v1-v5)

## Назначение
CLI-скрипт: принимает путь к .aswf файлу, разбирает СВОИМ парсером (не импортирует
wf_pull_client.py — независимая проверка не должна опираться на код, который проверяет),
печатает сводку и код возврата 0 (валиден) / 1 (ошибка).

## Источник алгоритма — ASWF_FORMAT.md проекта atomspectra-waterfall-esp32
Формат: `ASWF`(4 байта magic) + `hlen`(uint32 LE) + JSON-шапка(hlen байт, дополнена
пробелами) + baseline(опционально, `baseline.channels × 4` байт, uint32 LE) + N строк
по `row_stride` байт. Версии 1-5 отличаются набором полей, для v3+ офсеты полей БРАТЬ
ИЗ `row_fields` шапки (не хардкодить), `row_stride` — тоже из шапки.

CRC32 (только v4+, если в `row_fields` есть дескриптор `crc32`): стандартный
zlib-совместимый — `zlib.crc32(row_bytes[:covers]) & 0xFFFFFFFF == stored_crc`, где
`covers` и `offset` берутся из дескриптора `crc32` в `row_fields`.

## CLI
```
python verify_aswf.py <путь.aswf> [--json]
```

## Кодировки (Windows/cp1251, ЖЁСТКО)
- `sys.stdout.reconfigure(encoding="utf-8")` первой строкой.
- Чтение файла — бинарное (`read_bytes()`), декодирование JSON-шапки — `errors` НЕ
  глотать молча: при `UnicodeDecodeError`/`json.JSONDecodeError` — вернуть структурную
  ошибку, не падать трейсбеком.

## Логика разбора (функция `verify(path: Path) -> dict`)
1. Прочитать файл целиком (`read_bytes`).
2. Проверить magic `buf[:4] == b"ASWF"` — если нет, вернуть `{"ok": False, "errors": [...]}`
   и остановиться (дальше разбирать нечего).
3. `hlen = struct.unpack_from("<I", buf, 4)[0]`, распарсить JSON `buf[8:8+hlen]` как
   UTF-8 → `hdr`. Ошибка парсинга — структурная ошибка, `ok=False`, вернуться.
4. Вычислить `baseline_bytes`: если `"baseline"` в `hdr` — `(hdr["baseline"].get("channels")
   or hdr["baseline"].get("count") or 0) * 4`, иначе 0.
5. `payload_off = 8 + hlen + baseline_bytes`; `payload = buf[payload_off:]`.
6. Если `hdr.get("compressed", False)` — это RLE-формат, построчную CRC-проверку
   пропустить (декодер не реализуем в этой версии), записать в errors предупреждающую
   строку, `n_rows=None`, вернуть результат (не считать это фатальной ошибкой сама по
   себе — просто не проверено).
7. Определить `stride`: `version==1` → `hdr["channels"]*2`; `version==2` →
   `hdr.get("row_stride", hdr["channels"]*2)`; иначе (v3+) → `hdr.get("row_stride", 0)`.
   Если `stride` в итоге 0/falsy — структурная ошибка `ok=False`.
8. `n_rows = len(payload) // stride`; `tail = len(payload) % stride`. Если `tail != 0` —
   добавить в errors предупреждение про усечённый хвост (НЕ обязательно фатально —
   см. п.10 про то, какие ошибки делают `ok=False`).
9. Сверить `saved_rows` из шапки: если оно НЕ `None`, НЕ `0` и НЕ равно `n_rows` —
   добавить предупреждение (0 — штатная конвенция firmware #FW-14, не ошибка).
10. Если `version >= 3` и в `hdr` есть `"row_fields"`: построить `fields = {f["name"]: f
    for f in hdr["row_fields"]}`. Если среди них есть `"crc32"` — для каждой из `n_rows`
    строк вычислить CRC (см. алгоритм выше), сравнить с полем `crc32` строки
    (`struct.unpack_from("<I", row_bytes, crc_field["offset"])[0]`). Несовпадение →
    `crc_bad += 1` + запись в errors с номером строки и обоими значениями (hex).
    Совпадение → `crc_ok += 1`.
11. **Итоговый `ok`**: `False`, если (а) была структурная ошибка (magic/JSON/stride), ИЛИ
    (б) `crc_bad > 0`. Наличие ТОЛЬКО предупреждения про `tail` или `saved_rows` НЕ делает
    результат `ok=False` — это известные штатные варианты, не дефекты.
12. Вернуть словарь: `{"file": str, "size": int, "ok": bool, "header": dict, "n_rows": int|None,
    "tail_bytes": int, "saved_rows_header": int|None, "crc_ok": int, "crc_bad": int,
    "errors": [str, ...]}`.

## main()
- argparse: позиционный `path`, флаг `--json`.
- Вызвать `verify(Path(args.path))`.
- Если `--json` — напечатать `json.dumps(result, ensure_ascii=False, indent=2)`.
- Иначе — человекочитаемый вывод: путь, размер, версия/stride/n_rows/tail из header (если
  есть), CRC ok/bad, каждую строку из `errors` с префиксом `"  ! "`, и последней строкой
  `"РЕЗУЛЬТАТ: OK"` или `"РЕЗУЛЬТАТ: ОШИБКА"`.
- `sys.exit(0 if result["ok"] else 1)`.

## Docstring модуля (для будущих читателей)
Указать назначение, что это НЕЗАВИСИМАЯ проверка (не переиспользует код приёмника/прошивки),
источник алгоритма (ASWF_FORMAT.md проекта atomspectra-waterfall-esp32), и что скрипт
сохранён по итогам супертеста «Фундамент» (аудит-кода, 2026-08-20) как переиспользуемый
инструмент.

## Приёмочные эталоны (для проверки ПОСЛЕ генерации, не включать в сам скрипт)
Два реальных файла с уже известным правильным результатом (сверить вручную после
генерации, до принятия скрипта):
- `<work-root>\аудит-кода\reports_local\supertest-foundation\stage2\seg_00000_real_fixture.aswf`
  → ожидается: version=5, row_stride=16410, n_rows=4, tail_bytes=0, crc_ok=4, crc_bad=0, ok=True.
- (второй эталон — сшитый файл после первого сквозного прохода приёмника, путь узнать
  через `ls` scratchpad `e2e/seam.aswf` на момент проверки) → ожидается n_rows=6, tail=0,
  crc_ok=6, crc_bad=0, ok=True.
