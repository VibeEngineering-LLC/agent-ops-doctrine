import sys, os, json, argparse, re, time, hashlib, traceback
from json import JSONDecodeError

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
# guarded_generate живёт в скилле workflow (см. skills/workflow/scripts в этом репозитории).
# По умолчанию ищем его рядом с этим файлом (../skills/workflow/scripts); переопределить —
# переменной окружения WORKFLOW_SCRIPTS_DIR, если раскладка своя.
_here = os.path.dirname(os.path.abspath(__file__))
_workflow_scripts = os.environ.get(
    "WORKFLOW_SCRIPTS_DIR",
    os.path.join(os.path.dirname(_here), "skills", "workflow", "scripts"))
sys.path.insert(0, _workflow_scripts)
try:
    from vram_guard_reference import guarded_generate
except ImportError as e:
    sys.exit(f"Не найден guarded_generate в {_workflow_scripts!r}. Укажите верный путь "
             f"через переменную окружения WORKFLOW_SCRIPTS_DIR (исходная ошибка: {e})")

# Номера разделов, которые ЗАКОННО ссылаются наружу аудируемого документа (например, на общую
# доктрину проекта) — под них НЕ поднимается broken_ref. Подогнать под свою нумерацию.
EXTERNAL_SECTIONS = {"8", "12", "20", "28", "30", "31", "33", "34"}

# Корни каталогов для файлов, на которые документ ссылается ОТНОСИТЕЛЬНЫМИ путями. Пусто по
# умолчанию; заполнить через переменную окружения AUDIT_CONTOUR_ROOTS (пути через os.pathsep).
CONTOUR_ROOTS = [p for p in os.environ.get("AUDIT_CONTOUR_ROOTS", "").split(os.pathsep) if p]

# Порог «подозрительно быстро»: ответ за меньшее время на документе в сотни строк —
# признак того, что модель не читала его, а вернула пустоту
SUSPICIOUS_FAST_S = 5.0

LENSES = {
    "contradictions": (
        "Внутренние противоречия",
        "Найди внутренние противоречия: места, где документ требует одного в одном разделе и несовместимого с этим в другом. Только противоречия внутри текста, не сверяй с внешними источниками."
    ),
    "executability": (
        "Исполнимость",
        "Ты инженер, которому поручено построить описанное строго по этому документу, без права задавать вопросы автору. Перечисли конкретные места, где инструкции недостаточно для исполнения: что именно не определено, какое решение придётся выдумать."
    ),
    "ambiguity": (
        "Неоднозначность",
        "Найди формулировки, допускающие два и более несовместимых прочтения исполнителями. Для каждой приведи оба прочтения."
    ),
    "unenforceable": (
        "Невыполнимость",
        "Найди требования, соблюдение которых нельзя проверить: нет механизма, критерия или ответственного. Правило, которое некому и нечем проверить, считается находкой."
    ),
    "loopholes": (
        "Лазейки",
        "Ты недобросовестный исполнитель, желающий формально соблюсти документ, но сделать по-своему. Опиши конкретные лазейки: что можно сделать, не нарушив букву текста, но нарушив очевидное намерение."
    )
}

def structural_checks(text, base_dir=None):
    # base_dir — каталог документа: относительные .md-ссылки резолвятся от него,
    # а не от cwd (иначе ложные missing_file при запуске из другого каталога)
    findings = []
    lines = text.splitlines()
    
    # Сбор заголовков
    section_numbers = set()
    for i, line in enumerate(lines):
        match = re.match(r'^## (\S+?)\.', line)
        if match:
            section_numbers.add(match.group(1))
    
    # Битые перекрёстные ссылки
    for i, line in enumerate(lines, 1):
        for ref in re.findall(r'(?:§§?)(\d+\w*)', line):
            if ref not in section_numbers and ref not in EXTERNAL_SECTIONS:
                findings.append({
                    "kind": "broken_ref",
                    "line": i,
                    "quote": line[:200],
                    "detail": f"Ссылка на несуществующий раздел §{ref}"
                })
    
    # Несуществующие файлы
    for i, line in enumerate(lines, 1):
        for path in re.findall(r'`([^`]+\.md)`', line) + re.findall(r'(?:[CDE]:\\[^ \n]+)', line):
            # Плейсхолдеры-шаблоны — не файлы: <контур>, YYYYMMDD, многоточие в пути,
            # суффиксы вроде .read.md. Без этого фильтра проверка даёт только ложные срабатывания
            if ("<" in path or "YYYY" in path or "..." in path
                    or path.startswith(".") or "*" in path):
                continue
            # Относительный путь ищем в каталоге документа И в CONTOUR_ROOTS: документ может
            # легитимно ссылаться на файлы соседних проектов относительным путём — без второй
            # базы это сплошь ложные срабатывания
            probes = [path]
            if not os.path.isabs(path):
                probes = []
                if base_dir:
                    probes.append(os.path.join(base_dir, path))
                for root in CONTOUR_ROOTS:
                    probes.append(os.path.join(root, path))
            if not any(os.path.exists(p) for p in probes):
                # Различать «точно нет» и «не смог разрешить»: для абсолютного пути отсутствие
                # доказано, для относительного — лишь не найден среди известных баз (файл может
                # лежать в контуре, который назван в тексте словами, а не путём). Смешивать их
                # нельзя: ложное «файла нет» про существующий файл приучает игнорировать проверку
                absolute = os.path.isabs(path)
                findings.append({
                    "kind": "missing_file" if absolute else "unresolved_relative_path",
                    "line": i,
                    "quote": line[:200],
                    "detail": (f"Файл не существует: {path}" if absolute else
                               f"Относительный путь не разрешён среди известных баз "
                               f"(нужна ручная проверка): {path}")
                })
    
    # Пустые разделы
    section_pattern = re.compile(r'^## (\S+?)\.')
    section_starts = []
    for i, line in enumerate(lines):
        match = section_pattern.match(line)
        if match:
            section_starts.append(i)
    
    section_starts.append(len(lines))
    for i in range(len(section_starts) - 1):
        start = section_starts[i]
        end = section_starts[i+1]
        content_lines = [lines[j] for j in range(start+1, end) if lines[j].strip()]
        if len(content_lines) < 2:
            findings.append({
                "kind": "empty_section",
                "line": start + 1,
                "quote": lines[start][:200],
                "detail": f"Пустой раздел: {lines[start]}"
            })
    
    # Обещания без адреса
    for i, line in enumerate(lines, 1):
        if re.search(r'(см\. ниже|см\. выше|описано в)', line, re.IGNORECASE) and not re.search(r'(§|\w+\.md)', line):
            findings.append({
                "kind": "dangling_pointer",
                "line": i,
                "quote": line[:200],
                "detail": "Обещание без адреса"
            })
    
    return findings

_DASH_QUOTE_MAP = str.maketrans({
    "—": "-", "–": "-",           # em/en dash -> hyphen
    "«": '"', "»": '"', "„": '"', "“": '"', "”": '"',
    "’": "'", "‘": "'",
})

def _norm_quote(s):
    # Снять markdown-разметку, привести типографские тире/кавычки к простым, схлопнуть
    # пробелы: модель цитирует смысл, а не байты. Без первого валидатор меряет ФОРМУ, а не
    # содержание (ловушка №4 measure-methodology: 20/31 «галлюцинаций» -> 29/31 после снятия
    # разметки). Без второго (найдено внешним аудитом, #AUDIT-1, 2026-08-24) — валидная цитата
    # с em-dash получает quote_verified: False из-за одного символа, не относящегося к делу.
    s = (s or "").translate(_DASH_QUOTE_MAP)
    return " ".join(re.sub(r"[\*\`_]", "", s).split())


def verify_quotes(findings, doc_text, probe_len=60):
    # Проверка СОБСТВЕННОГО критерия приёмки из промпта: находка обязана указывать
    # дословное место в документе. Промпт этого требовал, а стенд не проверял —
    # отсюда пустой блок «требует толкования» при непроверенных цитатах.
    docn = _norm_quote(doc_text)
    verified = 0
    for f in findings:
        if not isinstance(f, dict):
            continue
        q = _norm_quote(f.get("quote", ""))[:probe_len]
        ok = bool(q) and q in docn
        f["quote_verified"] = ok
        verified += 1 if ok else 0
    return verified


def build_prompt(doc_text, lens_name, lens_title, lens_instruction):
    prompt = f"""Ты проводишь независимую экспертизу документа. Ты не видел ничьих других замечаний
и не должен ни с кем соглашаться.

ЗАДАЧА: {lens_instruction}

КРИТЕРИЙ ПРИЁМКИ: каждая находка обязана указывать конкретное место в документе
(номер раздела или дословную цитату). Находка без привязки к тексту недопустима.
Если по твоей задаче находок нет — верни пустой список, это нормальный результат.

Верни СТРОГО JSON вида:
{{"findings":[{{"section":"<номер или заголовок раздела>","quote":"<дословная цитата до 200 символов>","problem":"<в чём проблема>","suggestion":"<что конкретно изменить>","severity":"high|medium|low"}}]}} 

ДОКУМЕНТ:
{doc_text}"""
    return prompt

def run_lens(model, doc_text, lens_name, lens_title, lens_instruction):
    prompt = build_prompt(doc_text, lens_name, lens_title, lens_instruction)
    try:
        resp = guarded_generate(
            model=model,
            prompt=prompt,
            fmt="json",
            temperature=0.0,
            num_ctx=65536,
            want_gpu=True,
            priority=50,
            max_wait_s=900,
            extra_options={"num_predict": 8000},
            project=os.environ.get("AUDIT_PROJECT_LABEL", "audit_doctrine"),
            agent="audit_doctrine"
        )
        response_text = resp.get("response", "") if isinstance(resp, dict) else str(resp)
        try:
            data = json.loads(response_text)
        except JSONDecodeError:
            # Попытка извлечь JSON из текста
            first_brace = response_text.find('{')
            last_brace = response_text.rfind('}')
            if first_brace != -1 and last_brace != -1:
                try:
                    data = json.loads(response_text[first_brace:last_brace+1])
                except JSONDecodeError:
                    return {"kind": "lens_failed", "lens": lens_name, "detail": response_text[:300]}
            else:
                return {"kind": "lens_failed", "lens": lens_name, "detail": response_text[:300]}
        if isinstance(data, dict) and "findings" in data:
            return data["findings"]
        else:
            return []
    except Exception as e:
        return {"kind": "lens_failed", "lens": lens_name, "detail": str(e)[:300]}

def compute_totals(lens_results, structural_findings):
    # Вынесено из main() (внешний аудит #AUDIT-1, 2026-08-24): пока эта логика жила только в
    # main(), selftest не мог её проверить без реальной Ollama, и регрессия (len() от словаря
    # lens_failed) прошла незамеченной. main() и selftest теперь зовут одну функцию.
    return {
        "structural": len(structural_findings),
        "model": sum(len(v["findings"]) for v in lens_results.values() if isinstance(v["findings"], list)),
        "failed_lenses": sum(1 for v in lens_results.values()
                             if isinstance(v["findings"], dict) and v["findings"].get("kind") == "lens_failed"),
        "quotes_verified": sum(v.get("quotes_verified", 0) for v in lens_results.values()),
        "quotes_total": sum(v.get("quotes_total", 0) for v in lens_results.values()),
        "retried_lenses": [ln for ln, v in lens_results.items() if v.get("retried")],
    }


def compute_anomalies(lens_results, totals, total_seconds, line_count):
    anomalies = []
    if all(len(v["findings"]) == 0 for v in lens_results.values() if isinstance(v["findings"], list)):
        anomalies.append("все линзы вернули 0 находок")
    if totals["failed_lenses"] > 0:
        anomalies.append(f"{totals['failed_lenses']} проваленных линз")
    if totals["retried_lenses"]:
        anomalies.append(f"перезапущены после тихого отказа: {', '.join(totals['retried_lenses'])} — "
                         f"проверить стабильность модели")
    if total_seconds < 5:
        anomalies.append("суммарный прогон занял менее 5 секунд")
    for _ln, _v in lens_results.items():
        _f = _v.get("findings")
        if isinstance(_f, list) and len(_f) == 0:
            anomalies.append(f"линза '{_ln}' вернула 0 находок — честный ноль или тихий отказ?")
        if _v.get("seconds", 999) < 5:
            anomalies.append(f"линза '{_ln}' отработала за {_v.get('seconds')} с — "
                             f"успела ли модель прочитать документ?")
    # Leave-one-out медиана (внешний аудит #AUDIT-1, 2026-08-24, контрпример [20,90,22,21,23]:
    # прежняя версия считала медиану ПО ВСЕМ вызовам без первого, включая сам проверяемый —
    # выброс раздувал свой же порог сравнения и маскировал себя, 90 против медианы 23 не
    # проходило ×4). Медиана каждого вызова — по ОСТАЛЬНЫМ, кроме него самого и кроме первого
    # (первый — холодный старт с загрузкой весов, не проверяется).
    _secs = [v.get("seconds", 0) for v in lens_results.values()]
    _keys = list(lens_results.keys())
    if len(_secs) > 2:
        for _i in range(1, len(_secs)):
            _others = [_secs[j] for j in range(1, len(_secs)) if j != _i]
            if not _others:
                continue
            _med = sorted(_others)[len(_others) // 2]
            if _med > 0 and _secs[_i] > _med * 4:
                anomalies.append(f"линза '{_keys[_i]}' шла {_secs[_i]} с при медиане остальных "
                                 f"{_med} с — зацикливание или конкуренция за GPU?")
    _counts = [len(v["findings"]) for v in lens_results.values() if isinstance(v["findings"], list)]
    if len(_counts) > 1 and len(set(_counts)) == 1:
        anomalies.append(f"все линзы вернули одинаковое число находок ({_counts[0]}) — "
                         f"различают ли они что-нибудь?")
    if totals["model"] == 0 and line_count > 10:
        anomalies.append("модель не нашла ничего в непустом документе")
    qt, qv = totals["quotes_total"], totals["quotes_verified"]
    if qt and (qt - qv) / qt > 0.2:
        anomalies.append(f"цитаты не подтверждены дословно: {qt - qv} из {qt} "
                         f"({round((qt - qv) * 100 / qt)}%) — проверить, галлюцинация это "
                         f"или расхождение формы")
    return anomalies


def selftest():
    # raw-строка обязательна: в обычной \n внутри пути превращается в перевод строки
    # и проверка missing_file получает не тот вход, что задумано
    test_md = r"""
## 1. Введение.
Текст введения.

## 2. Основная часть.
Подробности изложены в §99 — раздела с таким номером в документе нет.
См. ниже
`nonexistent-fixture-file.md`
C:\nonexistent\file.txt

## 3. Пустой раздел.
"""
    # НАЙДЕНО ВНЕШНИМ АУДИТОМ (#AUDIT-1, 2026-08-24): раньше здесь вызывалось
    # structural_checks(test_md) БЕЗ base_dir, а main() всегда зовёт с явным base_dir —
    # тест проверял НЕ ТУ ветку резолва путей, что реально используется в продакшене.
    # Даём тот же base_dir, что дал бы вызов из main() для файла в этом каталоге.
    _here = os.path.dirname(os.path.abspath(__file__))
    findings = structural_checks(test_md, base_dir=_here)
    # unresolved_relative_path проверяется отдельно от missing_file: без него ветка
    # относительных путей осталась бы непокрытой, а тест — зелёным (#SA-3)
    expected_kinds = {"broken_ref", "missing_file", "empty_section", "dangling_pointer",
                      "unresolved_relative_path"}
    found_kinds = {f["kind"] for f in findings}
    if not (expected_kinds <= found_kinds):
        print(f"SELFTEST FAILED: не найдены {expected_kinds - found_kinds}")
        sys.exit(1)
    
    # Проверка на отсутствие дефектов
    clean_md = r"""
## 1. Введение.
Первая содержательная строка введения.
Вторая содержательная строка — порог непустых строк пройден.

## 2. Основная часть.
Подробности см. в §1 — этот раздел существует.
C:\Windows\System32\cmd.exe
"""
    findings_clean = structural_checks(clean_md, base_dir=_here)
    if findings_clean:
        print(f"SELFTEST FAILED: найдены ложные положительные {findings_clean}")
        sys.exit(1)
    
    # --- валидатор цитат: случаи, включая те, на которых он раньше ошибался ---
    # (внешний аудит #AUDIT-1, 2026-08-24: em-dash/кавычки не нормализовались)
    doc_q = "Текст с **жирной разметкой** и `кодом` — вот так — внутри строки."
    probes = [
        {"quote": "Текст с жирной разметкой", "expect": True},   # разметка снята — обязан пройти
        {"quote": "**Текст с жирной разметкой**", "expect": True},  # разметка в цитате — тоже
        {"quote": "Такого предложения в документе нет", "expect": False},  # выдумка
        {"quote": "вот так - внутри строки", "expect": True},  # дефис вместо em-dash
    ]
    verify_quotes(probes, doc_q)
    for p in probes:
        if p["quote_verified"] != p["expect"]:
            print(f"SELFTEST FAILED: валидатор цитат ошибся на {p['quote'][:40]!r} "
                  f"(ожидалось {p['expect']}, получено {p['quote_verified']})")
            sys.exit(1)

    # Позитивный тест base_dir: файл, существующий ТОЛЬКО относительно base_dir (не через
    # CONTOUR_ROOTS) — этот скрипт сам себя. Без этого проверка выше доказывает лишь, что
    # ветка не падает, а не что она находит существующий файл.
    self_ref_md = "Смотри `audit_doctrine.py` рядом."
    findings_self = structural_checks(self_ref_md, base_dir=_here)
    if any(f["kind"] in ("missing_file", "unresolved_relative_path") for f in findings_self):
        print(f"SELFTEST FAILED: base_dir не разрешил существующий файл: {findings_self}")
        sys.exit(1)

    # --- compute_totals: упавшая линза не должна считаться находками (внешний аудит #AUDIT-1) ---
    fake_results = {
        "ok_lens": {"seconds": 10.0, "findings": [{"quote": "x"}, {"quote": "y"}]},
        "failed_lens": {"seconds": 1.0, "findings": {"kind": "lens_failed", "lens": "failed_lens", "detail": "boom"}},
    }
    t = compute_totals(fake_results, [])
    if t["model"] != 2:
        print(f"SELFTEST FAILED: compute_totals посчитал модельные находки как {t['model']}, "
              f"ожидалось 2 (упавшая линза не должна давать len(dict)=3)")
        sys.exit(1)
    if t["failed_lenses"] != 1:
        print(f"SELFTEST FAILED: failed_lenses = {t['failed_lenses']}, ожидалось 1")
        sys.exit(1)

    # --- compute_anomalies: контрпример внешнего аудита (#AUDIT-1) [20,90,22,21,23] ---
    # Прежняя (self-masking) медиана НЕ ловила 90 — leave-one-out обязана ловить.
    median_results = {}
    for _i, _s in enumerate([20, 90, 22, 21, 23]):
        median_results[f"lens{_i}"] = {"seconds": float(_s), "findings": [],
                                        "quotes_verified": 0, "quotes_total": 0, "retried": False}
    m_totals = compute_totals(median_results, [])
    m_anom = compute_anomalies(median_results, m_totals, sum(v["seconds"] for v in median_results.values()), 999)
    if not any("lens1" in a and "90" in a for a in m_anom):
        print(f"SELFTEST FAILED: leave-one-out медиана не поймала контрпример 90 из "
              f"[20,90,22,21,23]: {m_anom}")
        sys.exit(1)

    print("SELFTEST OK")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=False)
    parser.add_argument("--out", required=False)
    parser.add_argument("--model", default="qwen3-coder:30b")
    parser.add_argument("--lenses", default="all")
    parser.add_argument("--selftest", action="store_true")
    
    args = parser.parse_args()
    
    if args.selftest:
        selftest()
    
    if not args.doc or not args.out:
        print("Необходимо указать --doc и --out", file=sys.stderr)
        sys.exit(1)
    
    with open(args.doc, "r", encoding="utf-8") as f:
        doc_text = f.read()
    
    sha8 = hashlib.sha256(doc_text.encode()).hexdigest()[:8]
    line_count = len(doc_text.splitlines())
    
    # Структурный аудит
    structural_findings = structural_checks(doc_text, base_dir=os.path.dirname(os.path.abspath(args.doc)))
    
    # Линзы
    selected_lenses = args.lenses.split(",") if args.lenses != "all" else list(LENSES.keys())
    lens_results = {}
    total_seconds = 0.0
    retried = []   # линзы, перезапущенные из-за подозрительно быстрого пустого ответа
    
    for lens_name in selected_lenses:
        if lens_name not in LENSES:
            print(f"Неизвестная линза: {lens_name}", file=sys.stderr)
            continue
        title, instruction = LENSES[lens_name]
        start_time = time.time()
        findings = run_lens(args.model, doc_text, lens_name, title, instruction)
        end_time = time.time()
        seconds = round(end_time - start_time, 2)
        # Пустой результат при аномально быстром ответе — тихий отказ модели, а не «находок нет».
        # Установлено фактом: прогон дал 0 находок за 2.2 с, повтор того же входа при
        # temperature=0 дал 8 за 15.5 с. Один повтор (§4: ≤2), затем принимаем как есть
        if isinstance(findings, list) and not findings and seconds < SUSPICIOUS_FAST_S:
            print(f"[{lens_name}] пусто за {seconds}с — похоже на тихий отказ, повтор",
                  file=sys.stderr)
            retry_start = time.time()
            findings = run_lens(args.model, doc_text, lens_name, title, instruction)
            seconds = round(seconds + time.time() - retry_start, 2)
            retried.append(lens_name)
        total_seconds += seconds
        n_ver = verify_quotes(findings, doc_text) if isinstance(findings, list) else 0
        n_all = len(findings) if isinstance(findings, list) else 0
        lens_results[lens_name] = {"seconds": seconds, "findings": findings,
                                   "quotes_verified": n_ver, "quotes_total": n_all,
                                   "retried": lens_name in retried}
    
    # Сводка
    totals = compute_totals(lens_results, structural_findings)
    
    result = {
        "doc": args.doc,
        "sha8": sha8,
        "lines": line_count,
        "model": args.model,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "structural": structural_findings,
        "lenses": lens_results,
        "totals": totals
    }
    
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    # Вывод сводки в stderr
    for name, data in lens_results.items():
        _n = len(data["findings"]) if isinstance(data["findings"], list) else "FAILED"
        print(f"{name}: {_n} находок за {data['seconds']} секунд", file=sys.stderr)
    print(f"Всего: {totals['structural']} структурных + {totals['model']} модельных находок ({totals['failed_lenses']} проваленных линз)", file=sys.stderr)
    
    # Требует толкования — считает compute_anomalies() (та же функция, что в selftest)
    anomalies = compute_anomalies(lens_results, totals, total_seconds, line_count)
    if anomalies:
        print(f"ТРЕБУЕТ ТОЛКОВАНИЯ: {', '.join(anomalies)}", file=sys.stderr)
    else:
        print("ТРЕБУЕТ ТОЛКОВАНИЯ: пусто", file=sys.stderr)

if __name__ == "__main__":
    main()
