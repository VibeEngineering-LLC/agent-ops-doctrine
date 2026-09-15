#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Линтер отчёта в Markdown (пригодность для чтения и печати на A4).

Запуск: python report_lint.py ОТЧЁТ.md [--width 90] [--max-cols 4] [--cell 120]
       [--para 900] [--json] [--quiet] [--no-source-section] [--dict ПУТЬ]

Коды правил:
Ш-1: строка длиннее заданного значения
Ш-2: строка таблицы длиннее 110 символов
Ш-3: таблица имеет больше колонок, чем допустимо
Ш-4: ячейка таблицы длиннее заданного значения
К-1: количество заголовков первого уровня не равно 1
К-2: пропущен уровень заголовка
К-3: отсутствует раздел «Источники» или «Литература»
К-4: заголовок оканчивается точкой
Ч-1: абзац длиннее заданного значения
Ч-2: абзац содержит больше предложений, чем допустимо
С-1: в тексте есть голый URL
С-2: подпись ссылки — заглушка или слишком короткая
С-3: путь к файлу в тексте
Я-1: замены из словарей стиля и терминологии
Я-2: латинские слова в русском тексте
Т-1: десятичная точка в числе вместо запятой
Т-2: программистские кавычки
Т-3: дефис между пробелами вместо тире
Т-4: знак процента без пробела после числа
Т-5: эмодзи или декоративный символ

Область проверки:
1. В огороженном блоке кода проверяется ТОЛЬКО Ш-1: длинная строка кода так же уезжает за
   поле A4, как и строка текста.
2. Кодовые вставки в обратных кавычках маскируются для Т-1…Т-5, Я-1, Я-2 — это правила о
   прозе, код цитируется дословно. Для С-1 и С-3 обратные кавычки НЕ маскируются: путь в
   обратных кавычках посреди текста — ровно тот случай, который правило запрещает.
3. YAML-шапка в начале файла не проверяется.
4. Правило Я-1 питается двумя внешними словарями JSON Lines; отсутствие обоих отключает
   правило, но не роняет программу.
"""

import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ERROR = "ОШИБКА"
WARN = "ПРЕДУПРЕЖДЕНИЕ"
TABLE_LINE_MAX = 110
MAX_SENTENCES = 6
MAX_LIST_DEPTH = 2
MIN_LINK_TEXT = 12

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STYLE_JSONL = os.path.join(SKILL_ROOT, "references", "style-replacements.jsonl")
DEFAULT_TERMS_JSONL = r"<home>\.claude\skills\terminology\data\terms.jsonl"

RE_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
RE_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
RE_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
RE_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
RE_INLINE_CODE = re.compile(r"`+[^`]*`+")
RE_MD_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(([^)\s]*)(?:\s+\"[^\"]*\")?\)")
RE_FOOTNOTE_DEF = re.compile(r"^\s*\[\^[^\]]+\]:")
RE_URL = re.compile(r"https?://[^\s<>\"'`)\]]+")
RE_SOURCE_HEAD = re.compile(r"^[\s\d.)*_#§-]*(источник|литератур)", re.IGNORECASE)
RE_WIN_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/][^\s`|)»\"']*")
RE_UNIX_PATH = re.compile(r"(?<![\w.])/(?:home|mnt|etc|usr|var|opt|root|srv)/[^\s`|)»\"']*")
RE_FILENAME = re.compile(r"(?<![\w/\\.])[\w\-]+\.(?:pdf|md|csv|json|xml|py)\b", re.IGNORECASE)
RE_LATIN = re.compile(r"[A-Za-z]{4,}")
RE_CYR_WORD = re.compile(r"[А-Яа-яЁё]+")
# латинское слово любой длины — для сверки со словарём Я-1 (в отличие от RE_LATIN,
# который ловит слова длиннее трёх букв для предупреждения Я-2)
RE_LAT_WORD = re.compile(r"[A-Za-z]+")
RE_T1 = re.compile(r"(?<![\w.])\d+\.\d")
RE_T3_BAD = re.compile(r"(?<=\s)-(?=\s)")
RE_T4_BAD = re.compile(r"\d%")
RE_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}")
# ссылка на раздел, пункт, таблицу, рисунок: «Раздел 16.5», «§ 2.3», «в таблице 4.2» —
# это нумерация, а не десятичная дробь
RE_SECREF = re.compile(
    r"(?:§\s*|\b(?:раздел|пункт|глав|таблиц|рисун|рис|прилож|формул|график|схем)\w*\s+"
    r"|\bп\.\s*|\bгл\.\s*|\bтабл\.\s*|\bрис\.\s*)\d+(?:\.\d+)+",
    re.IGNORECASE)
# идентификатор с двоеточием: arXiv:2203.07441, doi:10.1007/... — не десятичная дробь
RE_IDENT = re.compile(r"\b[A-Za-z][A-Za-z0-9]*:\S+")
# многосоставный номер: две и более точки подряд между числами
RE_MULTIDOT = re.compile(r"\b\d+(?:\.\d+){2,}\b")
RE_SECNUM = re.compile(r"^(?:\s{0,3}#{1,6}\s*|\s{0,6})\d+(?:\.\d+)*\.?(?=\s)")
RE_T5 = re.compile(
    "["
    "\u2190-\u21FF"
    "\u2600-\u27BF"
    "\u2900-\u297F"
    "\u2B00-\u2BFF"
    "\uFE0F"
    "\U0001F000-\U0001FAFF"
    "]"
)

PLACEHOLDERS = {"здесь", "ссылка", "тут", "источник", "pdf", "link", "сюда",
                "ссылке", "читать", "подробнее", "here"}
LATIN_OK = {"keV", "MeV", "GeV", "eV", "Bq", "Gy", "Sv", "mSv", "uSv", "nSv",
            "cps", "cpm", "ppm", "ppb"}
ABBREV = {"т", "г", "гг", "в", "вв", "с", "стр", "рис", "табл", "см", "п", "пп",
          "др", "им", "акад", "проф", "ул", "д", "обл", "руб", "тыс", "млн",
          "млрд", "мбк", "бк", "кэв", "мэв", "прим", "изд", "ред"}
ENDINGS = {"", "а", "ам", "ами", "ах", "е", "ей", "ем", "ею", "и", "ии", "ий",
           "им", "ими", "их", "о", "ов", "ого", "ом", "ому", "ою", "ы", "ые",
           "ый", "ым", "ыми", "ых", "у", "ую", "ь", "ю", "я", "ям", "ями",
           "ях", "ая", "ое", "ой", "ие", "ев", "ём", "её", "ен", "ена", "ено",
           "ены", "ный", "ная", "ное", "ные", "ных", "ным", "ными", "нее",
           "ить", "ил", "ила", "ило", "или", "ит", "ите", "ишь", "ят", "ать",
           "ал", "ала", "ало", "али", "ает", "ают", "аю", "аем", "аете", "ул",
           "ула", "уть", "нут", "уешь", "ует", "уем", "уете", "уют", "овать"}

class Violation:
    __slots__ = ("file", "line", "code", "level", "message")

    def __init__(self, file, line, code, level, message):
        self.file = file
        self.line = line
        self.code = code
        self.level = level
        self.message = message

    def as_dict(self):
        return {
            "file": self.file,
            "line": self.line,
            "code": self.code,
            "level": self.level,
            "message": self.message
        }

    def as_text(self):
        return "%s:%d: %s: %s" % (self.file, self.line, self.code, self.message)

def load_style_replacements(path, notes):
    replacements = []
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    notes.append("ошибка чтения словаря стиля: %s:%d" % (path, i))
                    continue
                bad = obj.get("bad", "").strip()
                good = obj.get("good", "").strip()
                if not bad or not good:
                    continue
                status = obj.get("status", "")
                level = ERROR if status == "canon" else WARN
                kind = "phrase" if " " in bad else "stem"
                domain = obj.get("domain", "")
                origin = "словарь стиля"
                if domain:
                    origin += ", домен " + domain
                replacements.append((kind, bad.lower(), good, level, origin))
    except Exception as e:
        notes.append("ошибка чтения словаря стиля: %s — %s" % (path, str(e)))
    return replacements

def load_terminology(path, notes):
    replacements = []
    conflicts = set()
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    notes.append("ошибка чтения терминологии: %s:%d" % (path, i))
                    continue
                term = obj.get("term", "").strip()
                if not term:
                    continue
                bads = obj.get("synonyms_bad", [])
                if not bads:
                    continue
                domain = obj.get("domain", "")
                origin = "терминология"
                if domain:
                    origin += ", домен " + domain
                for bad in bads:
                    # очистка
                    pos = bad.find(" (")
                    if pos != -1:
                        bad = bad[:pos]
                    bad = bad.strip('\'" \t')
                    if not bad:
                        continue
                    level = ERROR
                    good = term
                    kind = "phrase" if " " in bad else "stem"
                    replacements.append((kind, bad.lower(), good, level, origin))
    except Exception as e:
        notes.append("ошибка чтения терминологии: %s — %s" % (path, str(e)))
        return []
    # Взаимно противоречивые пары: запись X запрещает Y, а запись Y запрещает X
    # (в словаре терминологии так стоят «пик полного поглощения» и «фотопик»).
    # Выполнить такую пару невозможно — нарушителем окажется любой текст,
    # поэтому отбрасываются ОБЕ стороны.
    pairs = set((r[1].lower(), r[2].lower()) for r in replacements)
    dropped, kept = [], []
    for r in replacements:
        if (r[2].lower(), r[1].lower()) in pairs:
            dropped.append(r[1])
        else:
            kept.append(r)
    if dropped:
        notes.append("терминология: отброшено %d взаимно противоречивых замен (%s)"
                     % (len(dropped), ", ".join(sorted(set(dropped)))))
    return kept

def load_replacements(paths, notes):
    replacements = []
    for path in paths:
        if not os.path.exists(path):
            notes.append("словарь не найден: %s" % path)
            continue
        base = os.path.basename(path)
        if base == "terms.jsonl":
            replacements.extend(load_terminology(path, notes))
        else:
            replacements.extend(load_style_replacements(path, notes))
    # сортировка: сначала phrase, потом по длине pattern (убывание)
    def sort_key(x):
        kind, pattern, good, level, origin = x
        return (0 if kind == "phrase" else 1, -len(pattern), pattern)
    replacements.sort(key=sort_key)
    return replacements, notes

def mask_inline_code(text):
    return RE_INLINE_CODE.sub(lambda m: " " * len(m.group(0)), text)

# С-3 (решение оператора 12.09.2026): нарушение — только путь с разделителем каталогов.
RE_PATH_START = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/]|(?<![\w.])/(?:home|mnt|etc|usr|var|opt|root|srv)/")
RE_EXT_CHAIN = re.compile(r"(?:\.[A-Za-z0-9]{1,5})+(?![A-Za-z0-9\\/])")
PATH_STOP = "`|()«»\"'<>"
TRAIL_PUNCT = ".,;:!?"

def _path_extent(text, start):
    """Конец пути от позиции start. Имена каталогов могут содержать пробелы, поэтому
    путь тянется до первого расширения файла; без расширения — до первого пробела.
    Хвостовые знаки препинания в путь не входят."""
    end = start
    while end < len(text) and text[end] not in PATH_STOP:
        end += 1
    cand = text[start:end]
    ext = RE_EXT_CHAIN.search(cand)
    ws = re.search(r"\s", cand)
    cut = ext.end() if ext else (ws.start() if ws else len(cand))
    return start + len(cand[:cut].rstrip().rstrip(TRAIL_PUNCT))

def find_paths(line):
    """Пути с разделителем каталогов: список (начало, конец, путь целиком).
    Путь в обратных кавычках берётся всем содержимым вставки."""
    found = []
    for m in RE_INLINE_CODE.finditer(line):
        inner = m.group(0).strip("`").strip()
        if inner and RE_PATH_START.match(inner):
            a = line.index(inner, m.start())
            p = inner.rstrip(TRAIL_PUNCT)
            found.append((a, a + len(p), p))
    masked = mask_inline_code(line)
    for m in RE_PATH_START.finditer(masked):
        end = _path_extent(masked, m.start())
        found.append((m.start(), end, masked[m.start():end]))
    return sorted(found)

def mask_links_and_paths(text):
    # сначала ссылки
    def sub_link(m):
        return " " * len(m.group(0))
    text = RE_MD_LINK.sub(sub_link, text)
    # затем URL
    text = RE_URL.sub(lambda m: " " * len(m.group(0)), text)
    # пути с разделителем каталогов, в том числе с пробелами в именах
    for a, b, _p in find_paths(text):
        text = text[:a] + " " * (b - a) + text[b:]
    # имена файлов
    text = RE_FILENAME.sub(lambda m: " " * len(m.group(0)), text)
    return text

def split_cells(line):
    s = line.strip()
    parts = re.split(r"(?<!\\)\|", s)
    if parts and not parts[0].strip():
        parts.pop(0)
    if parts and not parts[-1].strip():
        parts.pop()
    return parts

def is_table_line(line):
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 2

def is_delimiter_row(line):
    line = line.strip()
    m = re.fullmatch(r"\|[\s:|-]+\|?", line)
    if not m:
        return False
    return "-" in line

def count_sentences(text):
    n = 0
    for m in re.finditer(r"[.!?…]+[\"»)\]]?", text):
        tail = text[m.end():]
        if tail and not tail[0].isspace():
            continue
        head = text[:m.start()]
        token = re.split(r"[\s(«\"]", head)[-1] if head else ""
        token = token.strip(".,;:()«»\"").lower()
        if token in ABBREV:
            continue
        if len(token) == 1 and token.isalpha():
            continue
        if token.isdigit():
            continue
        nxt = tail.lstrip()
        if nxt and not (nxt[0].isupper() or nxt[0] in "«\"—-–*#>" or nxt[0].isdigit()):
            continue
        n += 1
    return n

def match_replacement(word, reps):
    low = word.lower().replace("ё","е")
    for kind, pattern, good, level, origin in reps:
        if kind == "stem":
            st = pattern.replace("ё","е")
            if low.startswith(st):
                rest = low[len(st):]
                if rest in ENDINGS or (rest.endswith(("ся", "сь")) and rest[:-2] in ENDINGS):
                    return (pattern, good, level, origin)
    return None

def lint_file(path, opts, replacements):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if lines and not lines[-1]:
        lines.pop()
    violations = []
    def add(lineno, code, level, msg):
        violations.append(Violation(path, lineno, code, level, msg))

    n = len(lines)
    front_matter = [False] * n
    if lines and lines[0].strip() == "---":
        front_matter[0] = True
        for i in range(1, n):
            front_matter[i] = True
            if lines[i].strip() in ("---", "..."):
                break

    in_fence = [False] * n
    fence_marker = None
    for i in range(n):
        if front_matter[i]:
            continue
        m = RE_FENCE.match(lines[i])
        if m:
            marker = m.group(1)[0]
            if fence_marker is None:
                fence_marker = marker
                in_fence[i] = True
                continue
            if marker == fence_marker:
                fence_marker = None
                in_fence[i] = True
                continue
        in_fence[i] = fence_marker is not None

    # заголовки
    headings = []
    for i in range(n):
        if front_matter[i] or in_fence[i]:
            continue
        m = RE_HEADING.match(lines[i])
        if m:
            level = len(m.group(1))
            text = m.group(2)
            headings.append((i, level, text))

    # раздел «Источники»
    in_source = [False] * n
    for i, level, text in headings:
        if RE_SOURCE_HEAD.match(text):
            j = i
            while j < n:
                if front_matter[j] or in_fence[j]:
                    j += 1
                    continue
                if j > i and RE_HEADING.match(lines[j]):
                    hlevel = len(RE_HEADING.match(lines[j]).group(1))
                    if hlevel <= level:
                        break
                in_source[j] = True
                j += 1

    # структура
    h1_count = sum(1 for i, l, t in headings if l == 1)
    if h1_count != 1:
        add(1, "К-1", ERROR, "заголовков первого уровня %d, должен быть ровно один" % h1_count)

    prev_level = None
    for i, level, text in headings:
        if prev_level is not None and level > prev_level + 1:
            add(i+1, "К-2", ERROR, "пропущен уровень заголовка: после H%d сразу H%d" % (prev_level, level))
        prev_level = level

    for i, level, text in headings:
        if text.rstrip().endswith(".") and not text.rstrip().endswith("..."):
            add(i+1, "Т-6", ERROR, "точка в конце заголовка: «%s»" % text.strip())

    if not opts.no_source_section:
        has_source = any(RE_SOURCE_HEAD.match(text) for _, _, text in headings)
        if not has_source:
            add(1, "К-3", ERROR, "нет раздела «Источники» (или «Литература»)")

    # таблицы
    i = 0
    while i < n:
        if not is_table_line(lines[i]) or front_matter[i] or in_fence[i]:
            i += 1
            continue
        group_start = i
        while i < n and is_table_line(lines[i]) and not front_matter[i] and not in_fence[i]:
            i += 1
        group_end = i
        first_line = lines[group_start]
        cols = len(split_cells(first_line))
        if cols > opts.max_cols:
            add(group_start+1, "Ш-3", ERROR, "в таблице %d колонок, допустимо %d" % (cols, opts.max_cols))
        for j in range(group_start, group_end):
            line = lines[j]
            if len(line) > TABLE_LINE_MAX:
                add(j+1, "Ш-2", ERROR, "строка таблицы %d символов, допустимо 110" % len(line))
            if not is_delimiter_row(line):
                cells = split_cells(line)
                for k, cell in enumerate(cells, 1):
                    if len(cell.strip()) > opts.cell:
                        add(j+1, "Ш-4", ERROR, "ячейка %d длиной %d символов, допустимо %d" % (k, len(cell.strip()), opts.cell))

    # построчные проверки
    list_stack = []
    for i in range(n):
        line = lines[i]
        if front_matter[i]:
            continue
        # Ш-1 — единственная проверка, работающая и внутри огороженного блока кода:
        # длинная строка кода уезжает за поле A4 так же, как строка текста.
        # Строки таблиц исключены — их ширину проверяет Ш-2.
        if not is_table_line(line) and len(line) > opts.width:
            add(i+1, "Ш-1", ERROR, "строка %d символов, допустимо %d" % (len(line), opts.width))
        if in_fence[i]:
            continue

        # вложенность списков
        m = RE_LIST.match(line)
        if m:
            indent = len(m.group(1).replace("\t", "    "))
            while list_stack and indent < list_stack[-1]:
                list_stack.pop()
            if not list_stack or indent > list_stack[-1]:
                list_stack.append(indent)
            depth = len(list_stack)
            if depth > MAX_LIST_DEPTH:
                add(i+1, "Ч-3", WARN, "вложенность списка %d уровня, допустимо 2" % depth)
        elif line.strip() and not line.startswith((" ", "\t")):
            list_stack.clear()

        # С-1: голый URL
        if not in_source[i] and not RE_FOOTNOTE_DEF.match(line):
            s1 = RE_MD_LINK.sub(lambda m: " " * len(m.group(0)), line)
            if RE_URL.search(s1):
                add(i+1, "С-1", ERROR, "голый адрес в тексте: URL — в тексте должно стоять название, адрес — в разделе «Источники»")

        # С-2: подпись ссылки
        for m in RE_MD_LINK.finditer(line):
            if m.group(1) == "!":
                continue  # картинка
            plain = m.group(2).strip()
            if not plain:
                continue
            if plain.startswith("^"):
                continue  # сноска
            url = m.group(3)
            if plain == url or RE_URL.match(plain):
                add(i+1, "С-2", ERROR, "подпись совпадает с адресом — подписью ссылки должно быть название источника")
            elif plain.lower() in PLACEHOLDERS:
                add(i+1, "С-2", ERROR, "подпись-заглушка «%s» — подписью ссылки должно быть название источника" % plain)
            elif len(plain) < MIN_LINK_TEXT:
                add(i+1, "С-2", ERROR, "подпись «%s» короче 12 символов — подписью ссылки должно быть название источника" % plain)

        # С-3: пути к файлам
        if not in_source[i]:
            # Только путь с разделителем каталогов; голое имя файла (md2html.py) —
            # не нарушение (решение оператора 12.09.2026). Путь называется целиком.
            for _a, _b, p in find_paths(line):
                add(i+1, "С-3", ERROR,
                    "путь к файлу в тексте: %s — пути собираются в раздел «Источники»" % p)

        # Я-1 и Я-2
        prose = mask_inline_code(line)
        lang = mask_links_and_paths(prose)

        # Я-1: фразовые замены
        matched_patterns = set()
        for kind, pattern, good, level, origin in replacements:
            if kind == "phrase":
                escaped = re.escape(pattern)
                regex = r"(?<![\wА-Яа-яЁё])%s(?![\wА-Яа-яЁё])" % escaped
                if re.search(regex, lang.lower()):
                    if pattern not in matched_patterns:
                        add(i+1, "Я-1", level, "«%s» → «%s» (%s)" % (pattern, good, origin))
                        matched_patterns.add(pattern)
            else:  # stem: сверяются и русские, и латинские слова — словарь
                   # терминологии содержит запрещённые варианты на обоих языках
                for m in list(RE_CYR_WORD.finditer(lang)) + list(RE_LAT_WORD.finditer(lang)):
                    word = m.group(0)
                    match = match_replacement(word, [(kind, pattern, good, level, origin)])
                    if match:
                        if pattern not in matched_patterns:
                            add(i+1, "Я-1", level, "«%s» → «%s» (%s)" % (word, good, origin))
                            matched_patterns.add(pattern)
                        break

        # Я-2: латинские слова
        if not in_source[i] and not is_table_line(line):
            seen_latin = set()
            for m in RE_LATIN.finditer(lang):
                word = m.group(0)
                if word.isupper() or word in LATIN_OK or word in seen_latin:
                    continue
                add(i+1, "Я-2", WARN, "латинское слово «%s» в русском тексте" % word)
                seen_latin.add(word)

        # Т-1: десятичная точка.
        # Точка между цифрами встречается не только в десятичной дроби. Гасим всё,
        # что ею не является, иначе правило даёт сплошь ложные срабатывания
        # (проверено на боевых отчётах: 14 срабатываний, 14 ложных):
        #   - адреса и пути (DOI 10.1007/..., arXiv:2203.07441 внутри ссылки);
        #   - даты 12.09.2026;
        #   - нумерация раздела в начале строки и в ссылке «Раздел 16.5», «§ 2.3»;
        #   - многосоставный номер с двумя и более точками (16.2.5).
        t1 = mask_links_and_paths(prose)
        for rx in (RE_IDENT, RE_DATE, RE_SECNUM, RE_SECREF, RE_MULTIDOT):
            t1 = rx.sub(lambda m: " " * len(m.group(0)), t1)
        m = RE_T1.search(t1)
        if m:
            add(i+1, "Т-1", ERROR, "десятичная точка в числе: %s — разделитель запятая" % m.group(0))

        # Т-2: программистские кавычки
        if '"' in prose:
            add(i+1, "Т-2", ERROR, "программистские кавычки \" — нужны «ёлочки»")

        # Т-3: дефис между пробелами
        m = RE_T3_BAD.search(prose)
        if m and prose[:m.start()].strip() and not prose[:m.start()].strip().endswith("|"):
            add(i+1, "Т-3", ERROR, "дефис между пробелами вместо тире")

        # Т-4: знак процента без пробела
        if RE_T4_BAD.search(prose):
            add(i+1, "Т-4", ERROR, "знак процента без пробела после числа")

        # Т-5: эмодзи или декоративный символ
        m = RE_T5.search(prose)
        if m:
            char = m.group(0)
            code = hex(ord(char))[2:].upper().zfill(4)
            add(i+1, "Т-5", ERROR, "эмодзи или декоративный символ U+%s (%s)" % (code, char))

    # абзацы
    para = []
    para_start = 0

    def flush_para():
        if not para:
            return
        text = " ".join(x.strip() for x in para).strip()
        if not text:
            return
        if len(text) > opts.para:
            add(para_start + 1, "Ч-1", ERROR,
                "абзац %d символов, допустимо %d" % (len(text), opts.para))
        sents = count_sentences(mask_inline_code(text))
        if sents > MAX_SENTENCES:
            add(para_start + 1, "Ч-2", WARN,
                "в абзаце %d предложений, допустимо %d" % (sents, MAX_SENTENCES))

    for i in range(n):
        raw = lines[i]
        if front_matter[i] or in_fence[i] or is_table_line(raw) \
                or RE_HEADING.match(raw) or RE_HR.match(raw) or not raw.strip():
            flush_para()
            para = []
            continue
        if RE_LIST.match(raw) or RE_FOOTNOTE_DEF.match(raw):
            flush_para()
            para = [raw]
            para_start = i
            continue
        if not para:
            para_start = i
        para.append(raw)
    flush_para()

    violations.sort(key=lambda v: (v.line, v.code))
    return violations

def build_parser():
    parser = argparse.ArgumentParser(prog="report_lint.py", description="Линтер отчёта в Markdown")
    parser.add_argument("files", nargs="+", metavar="ОТЧЁТ.md")
    parser.add_argument("--width", type=int, default=90)
    parser.add_argument("--max-cols", type=int, default=4, dest="max_cols")
    parser.add_argument("--cell", type=int, default=120)
    parser.add_argument("--para", type=int, default=900)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--no-source-section", action="store_true", dest="no_source_section")
    parser.add_argument("--dict", action="append", dest="dicts", default=None, metavar="ПУТЬ",
                        help="путь к словарю (можно повторять)")
    return parser

def main(argv=None):
    opts = build_parser().parse_args(argv)
    notes = []
    paths = opts.dicts if opts.dicts is not None else [DEFAULT_STYLE_JSONL, DEFAULT_TERMS_JSONL]
    replacements, notes = load_replacements(paths, notes)
    if not replacements:
        notes.append("правило Я-1 не работает: ни один словарь не загружен")

    all_violations = []
    for path in opts.files:
        if not os.path.isfile(path):
            print("ВНИМАНИЕ: файл не найден: %s" % path, file=sys.stderr)
            continue
        violations = lint_file(path, opts, replacements)
        all_violations.extend(violations)

    if opts.json:
        print(json.dumps([v.as_dict() for v in all_violations], ensure_ascii=False, indent=2))
        if notes:
            for note in notes:
                print("Примечания: %s" % note, file=sys.stderr)
        return 1 if any(v.level == ERROR for v in all_violations) else 0

    if not opts.quiet:
        for v in all_violations:
            print(v.as_text())
    # Ключ --quiet убирает только построчный перечень; сводка печатается всегда.
    if all_violations:
        print()
        print("Сводка по кодам:")
        codes = {}
        for v in all_violations:
            key = (v.code, v.level)
            codes[key] = codes.get(key, 0) + 1
        for code, level in sorted(codes.keys()):
            count = codes[(code, level)]
            if count > 0:
                print("  %-4s %-14s %4d" % (code, level, count))
        print()
    error_count = sum(1 for v in all_violations if v.level == ERROR)
    warning_count = sum(1 for v in all_violations if v.level == WARN)
    file_count = len(opts.files)
    print("Нарушений: %d (%s %d, %s %d), файлов: %d" % (
        error_count + warning_count, ERROR, error_count, WARN, warning_count, file_count))
    if notes:
        print("Примечания:")
        for note in notes:
            print("  %s" % note)
    return 1 if error_count > 0 else 0

if __name__ == "__main__":
    sys.exit(main())
