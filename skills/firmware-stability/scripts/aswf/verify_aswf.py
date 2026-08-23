#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Независимая проверка целостности .aswf файлов (v1-v5).
Скрипт не использует wf_pull_client.py — полностью независимая проверка.
Источник алгоритма: ASWF_FORMAT.md проекта atomspectra-waterfall-esp32.
Сохранён по итогам супертеста «Фундамент» (Codeaudit, 2026-08-20) как переиспользуемый инструмент.
"""

import sys
import json
import struct
import zlib
from pathlib import Path
import argparse


def read_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def verify(path: Path) -> dict:
    result = {
        "file": str(path),
        "size": path.stat().st_size,
        "ok": True,
        "header": {},
        "n_rows": None,
        "tail_bytes": 0,
        "saved_rows_header": None,
        "crc_ok": 0,
        "crc_bad": 0,
        "errors": []
    }

    try:
        buf = read_bytes(path)
    except Exception as e:
        result["ok"] = False
        result["errors"].append(f"Ошибка чтения файла: {e}")
        return result

    if len(buf) < 8:
        result["ok"] = False
        result["errors"].append("Файл слишком короткий для ASWF")
        return result

    # Проверка magic
    if buf[:4] != b"ASWF":
        result["ok"] = False
        result["errors"].append("Неверный magic: не ASWF")
        return result

    hlen = struct.unpack_from("<I", buf, 4)[0]
    if len(buf) < 8 + hlen:
        result["ok"] = False
        result["errors"].append("Файл слишком короткий для заголовка JSON")
        return result

    try:
        header_bytes = buf[8:8+hlen]
        header_str = header_bytes.decode("utf-8", errors="strict")
        hdr = json.loads(header_str)
        result["header"] = hdr
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        result["ok"] = False
        result["errors"].append(f"Ошибка парсинга JSON заголовка: {e}")
        return result

    # Вычисление baseline_bytes
    baseline_channels = hdr.get("baseline", {}).get("channels") or hdr.get("baseline", {}).get("count") or 0
    baseline_bytes = baseline_channels * 4

    payload_off = 8 + hlen + baseline_bytes
    payload = buf[payload_off:]

    # Проверка сжатия
    if hdr.get("compressed", False):
        result["errors"].append("Файл сжат (RLE), CRC проверка пропущена")
        result["n_rows"] = None
        return result

    # Определение stride
    version = hdr.get("version", 1)
    if version == 1:
        stride = hdr.get("channels", 0) * 2
    elif version == 2:
        stride = hdr.get("row_stride", hdr.get("channels", 0) * 2)
    else:  # v3+
        stride = hdr.get("row_stride", 0)

    if not stride:
        result["ok"] = False
        result["errors"].append("Неверный row_stride")
        return result

    n_rows = len(payload) // stride
    tail = len(payload) % stride

    if tail != 0:
        result["errors"].append(f"Усечённый хвост: {tail} байт не входят в строки")

    saved_rows = hdr.get("saved_rows")
    if saved_rows is not None and saved_rows != 0 and saved_rows != n_rows:
        result["errors"].append(f"Количество строк в заголовке ({saved_rows}) не совпадает с фактическим ({n_rows})")

    result["n_rows"] = n_rows
    result["tail_bytes"] = tail
    result["saved_rows_header"] = saved_rows

    # Проверка CRC для v3+
    if version >= 3 and "row_fields" in hdr:
        fields = {f["name"]: f for f in hdr["row_fields"]}
        crc_field = fields.get("crc32")
        if crc_field:
            for i in range(n_rows):
                row_bytes = payload[i*stride:(i+1)*stride]
                stored_crc = struct.unpack_from("<I", row_bytes, crc_field["offset"])[0]
                covers = crc_field.get("covers", len(row_bytes))
                computed_crc = zlib.crc32(row_bytes[:covers]) & 0xFFFFFFFF
                if computed_crc != stored_crc:
                    result["crc_bad"] += 1
                    result["errors"].append(
                        f"Строка {i}: CRC не совпадает (ожидается: 0x{stored_crc:08X}, вычислено: 0x{computed_crc:08X})"
                    )
                else:
                    result["crc_ok"] += 1

    # Итоговый результат
    if not result["ok"]:
        return result

    if result["crc_bad"] > 0:
        result["ok"] = False

    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Независимая проверка целостности .aswf файлов")
    parser.add_argument("path", help="Путь к .aswf файлу")
    parser.add_argument("--json", action="store_true", help="Вывод в формате JSON")

    args = parser.parse_args()
    result = verify(Path(args.path))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Файл: {result['file']}")
        print(f"Размер: {result['size']} байт")
        if "version" in result["header"]:
            print(f"Версия: {result['header']['version']}")
        if "row_stride" in result["header"]:
            print(f"Row stride: {result['header']['row_stride']}")
        print(f"Количество строк: {result['n_rows']}")
        print(f"Хвост: {result['tail_bytes']} байт")
        print(f"CRC OK: {result['crc_ok']}, CRC BAD: {result['crc_bad']}")
        for err in result["errors"]:
            print(f"  ! {err}")
        print(f"РЕЗУЛЬТАТ: {'OK' if result['ok'] else 'ОШИБКА'}")

    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
