# -*- coding: utf-8 -*-
"""Форматирование самого Markdown-файла в вид документа: абзацы выключены по ширине,
таблицы выровнены по колонкам, отступы и пустые строки приведены к единому виду.

Вызов:
    python mdfmt.py ФАЙЛ [ФАЙЛ ...] [--width 90] [--ragged] [--out ПУТЬ] [--stdout]

Умолчания: ширина 90 знаков, выключка по формату (оба края ровные), запись поверх файла
с резервной копией `.bak`. Кодировка чтения и записи — UTF-8 явно.

Не трогает: огороженные блоки кода, YAML-шапку, ссылки-сноски, HTML-вставки.
"""
import argparse
import pathlib
import re
import sys

RX_FENCE = re.compile(r"^\s*(```|~~~)")
RX_HEAD = re.compile(r"^\s{0,3}#{1,6}\s")
RX_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
RX_TABLE = re.compile(r"^\s*\|.*\|\s*$")
RX_LI = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$")
RX_QUOTE = re.compile(r"^\s*>\s?")
RX_HTML = re.compile(r"^\s*<")
RX_ATOM = re.compile(r"`[^`]*`")          # inline-код рвать нельзя


def visible_len(s: str) -> int:
    return len(s)


def wrap_words(words, width, indent=""):
    """Разбить слова на строки не длиннее width с учётом отступа."""
    lines, cur = [], []
    room = width - len(indent)
    for w in words:
        cand = len(w) if not cur else sum(len(x) for x in cur) + len(cur) + len(w)
        if cur and cand > room:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def justify(line_words, width, indent, last):
    """Выключка по формату: добить пробелы между словами до ровного правого края."""
    text = " ".join(line_words)
    if last or len(line_words) == 1:
        return indent + text
    room = width - len(indent)
    gaps = len(line_words) - 1
    extra = room - sum(len(w) for w in line_words)
    if extra <= gaps or extra > gaps * 4:      # слишком мало или слишком рвано
        return indent + text
    base, rest = divmod(extra, gaps)
    out = ""
    for i, w in enumerate(line_words[:-1]):
        out += w + " " * (base + (1 if i < rest else 0))
    return indent + out + line_words[-1]


def format_para(text, width, indent="", ragged=False):
    # inline-код и ссылки не должны рваться по пробелу внутри обратных кавычек
    holds = {}
    def hold(m):
        key = f"\x00{len(holds)}\x00"
        holds[key] = m.group(0)
        return key
    text = RX_ATOM.sub(hold, text)
    words = text.split()
    lines = wrap_words(words, width, indent)
    out = []
    for i, lw in enumerate(lines):
        last = (i == len(lines) - 1)
        out.append(indent + " ".join(lw) if ragged else justify(lw, width, indent, last))
    res = "\n".join(out)
    for k, v in holds.items():
        res = res.replace(k, v)
    return res


def format_table(rows):
    """Выровнять колонки таблицы по ширине содержимого."""
    grid = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    ncol = max(len(r) for r in grid)
    grid = [r + [""] * (ncol - len(r)) for r in grid]
    sep_i = 1 if len(grid) > 1 and all(set(c) <= set("-: ") and c for c in grid[1]) else None
    aligns = ["l"] * ncol
    if sep_i is not None:
        for j, c in enumerate(grid[sep_i]):
            aligns[j] = ("c" if c.startswith(":") and c.endswith(":") else
                         "r" if c.endswith(":") else "l")
    widths = [max(visible_len(grid[i][j]) for i in range(len(grid)) if i != sep_i)
              for j in range(ncol)]
    widths = [max(w, 3) for w in widths]

    def cell(text, w, a):
        if a == "r":
            return text.rjust(w)
        if a == "c":
            pad = w - len(text)
            return " " * (pad // 2) + text + " " * (pad - pad // 2)
        return text.ljust(w)

    out = []
    for i, row in enumerate(grid):
        if i == sep_i:
            parts = []
            for j, w in enumerate(widths):
                a = aligns[j]
                parts.append(":" + "-" * (w - 1) if a == "l" else
                             ":" + "-" * (w - 2) + ":" if a == "c" else
                             "-" * (w - 1) + ":")
            out.append("| " + " | ".join(parts) + " |")
        else:
            out.append("| " + " | ".join(cell(row[j], widths[j], aligns[j])
                                         for j in range(ncol)) + " |")
    return out


def format_md(src: str, width: int, ragged: bool) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    out, i, in_fence, fence_tok = [], 0, False, ""
    while i < len(lines):
        ln = lines[i]

        m = RX_FENCE.match(ln)
        if m:
            in_fence = not in_fence if (not in_fence or m.group(1) == fence_tok) else in_fence
            fence_tok = m.group(1) if in_fence else ""
            out.append(ln.rstrip())
            i += 1
            continue
        if in_fence:
            out.append(ln.rstrip("\n"))
            i += 1
            continue

        if not ln.strip():
            out.append("")
            i += 1
            continue

        if RX_HEAD.match(ln) or RX_HR.match(ln) or RX_HTML.match(ln):
            out.append(ln.rstrip())
            i += 1
            continue

        if RX_TABLE.match(ln):
            block = []
            while i < len(lines) and RX_TABLE.match(lines[i]):
                block.append(lines[i])
                i += 1
            out.extend(format_table(block))
            continue

        if RX_QUOTE.match(ln):
            block = []
            while i < len(lines) and RX_QUOTE.match(lines[i]):
                block.append(RX_QUOTE.sub("", lines[i]))
                i += 1
            inner = format_md("\n".join(block), width - 2, ragged)
            out.extend(("> " + x).rstrip() for x in inner.split("\n"))
            continue

        m = RX_LI.match(ln)
        if m:
            lead, marker, rest = m.groups()
            body = [rest]
            i += 1
            while i < len(lines) and lines[i].strip() and not RX_LI.match(lines[i]) \
                    and not RX_TABLE.match(lines[i]) and not RX_HEAD.match(lines[i]) \
                    and not RX_FENCE.match(lines[i]):
                body.append(lines[i].strip())
                i += 1
            hang = lead + " " * (len(marker) + 1)
            text = format_para(" ".join(body), width, hang, ragged)
            parts = text.split("\n")
            out.append(lead + marker + " " + parts[0].lstrip())
            out.extend(parts[1:])
            continue

        # обычный абзац
        block = []
        while i < len(lines) and lines[i].strip() and not RX_HEAD.match(lines[i]) \
                and not RX_TABLE.match(lines[i]) and not RX_FENCE.match(lines[i]) \
                and not RX_LI.match(lines[i]) and not RX_QUOTE.match(lines[i]) \
                and not RX_HR.match(lines[i]):
            block.append(lines[i].strip())
            i += 1
        out.append(format_para(" ".join(block), width, "", ragged))

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description="Форматирование Markdown в вид документа")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--width", type=int, default=90, help="ширина колонки в знаках (умолчание 90)")
    ap.add_argument("--ragged", action="store_true", help="без выключки: ровный только левый край")
    ap.add_argument("--out", help="путь выхода (только при одном входном файле)")
    ap.add_argument("--stdout", action="store_true", help="печатать результат вместо записи")
    a = ap.parse_args()

    files = [pathlib.Path(f) for f in a.files]
    missing = [f for f in files if not f.is_file()]
    if missing:
        return print("Нет файла:", *missing, sep="\n  ") or 2
    if a.out and len(files) > 1:
        return print("--out допустим только при одном входном файле") or 2

    for f in files:
        src = f.read_text(encoding="utf-8")
        res = format_md(src, a.width, a.ragged)
        if a.stdout:
            sys.stdout.write(res)
            continue
        out = pathlib.Path(a.out) if a.out else f
        if out == f:
            f.with_suffix(f.suffix + ".bak").write_text(src, encoding="utf-8")
        out.write_text(res, encoding="utf-8")
        print(f"OK  {out}  ширина {a.width}, "
              f"{'левый край' if a.ragged else 'выключка по формату'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
