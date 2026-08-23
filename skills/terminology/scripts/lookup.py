# -*- coding: utf-8 -*-
"""Поиск по терминологическому словарю контура.

Вызов:
    python lookup.py ПОДСТРОКА [--domain КОД] [--lang ru|en] [--exact] [--json]

Ищет по term, synonyms_ok, synonyms_bad и definition (подстрока, без регистра).
Найденный в synonyms_bad помечается: это запрещённая подмена, показывается канон.
Пустой словарь — честное сообщение, не пустой вывод.
"""
import argparse
import json
import pathlib
import sys

# Консоль на этой машине может быть в cp1251/cp866 (не UTF-8) — без этого print()
# эмодзи (✅/⛔/≈) и не-ASCII падает UnicodeEncodeError. errors="replace" гарантирует,
# что скрипт не упадёт даже если сама консоль не может отрисовать символ.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "terms.jsonl"


def load():
    if not DATA.is_file() or DATA.stat().st_size == 0:
        return []
    out = []
    with open(DATA, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"⚠ terms.jsonl:{n}: битая строка ({e})", file=sys.stderr)
    return out


def match(rec, q, exact):
    q = q.lower()
    fields = [("term", rec.get("term", ""))]
    fields += [("synonyms_ok", s) for s in rec.get("synonyms_ok", [])]
    fields += [("synonyms_bad", s) for s in rec.get("synonyms_bad", [])]
    for kind, val in fields:
        v = val.lower()
        if (q == v) if exact else (q in v):
            return kind, val
    if not exact and q in rec.get("definition", "").lower():
        return "definition", ""
    return None


def show(rec, hit_kind, hit_val):
    head = f"{rec['term']}  [{rec.get('language','?')}/{rec.get('domain','?')}]"
    if hit_kind == "synonyms_bad":
        head = f"⛔ «{hit_val}» — запрещённая подмена → канон: " + head
    elif hit_kind == "synonyms_ok":
        head = f"≈ «{hit_val}» → " + head
    print(head)
    if rec.get("unit"):
        print(f"   единица: {rec['unit']}")
    print(f"   {rec.get('definition','(нет определения)')}")
    src = rec.get("source") or {}
    ref = ", ".join(str(v) for k, v in src.items() if v) or "(источник не указан!)"
    print(f"   источник: {ref}")
    if rec.get("equivalent"):
        print(f"   эквивалент: {rec['equivalent']}")
    if rec.get("note"):
        print(f"   note: {rec['note']}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Поиск термина в словаре контура")
    ap.add_argument("query")
    ap.add_argument("--domain", help="фильтр по коду домена")
    ap.add_argument("--lang", choices=["ru", "en"], help="фильтр по языку")
    ap.add_argument("--exact", action="store_true", help="точное совпадение вместо подстроки")
    ap.add_argument("--json", action="store_true", help="вывод записей как JSONL")
    a = ap.parse_args()

    terms = load()
    if not terms:
        print(f"Словарь пуст ({DATA}). Наполнение — этап 1 плана ARCH-PLAN-TERMINOLOGY.")
        return 1

    found = 0
    for rec in terms:
        if a.domain and rec.get("domain") != a.domain:
            continue
        if a.lang and rec.get("language") != a.lang:
            continue
        m = match(rec, a.query, a.exact)
        if m:
            found += 1
            if a.json:
                print(json.dumps(rec, ensure_ascii=False))
            else:
                show(rec, *m)
    print(f"— найдено {found} из {len(terms)} записей", file=sys.stderr)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
