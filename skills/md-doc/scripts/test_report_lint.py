#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мутационная приёмка линтера report_lint.py.

Для каждого кода правила есть образец, нарушающий РОВНО это правило,
и проверяется и срабатывание, и отсутствие посторонних срабатываний.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import io

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "report_lint.py")
STYLE_DICT_LINES = [
    '{"bad": "кейс", "good": "случай", "domain": "", "status": "canon", "note": "", "source": "", "added": "2026-09-12"}',
    '{"bad": "юзер", "good": "пользователь", "domain": "", "status": "canon", "note": "", "source": "", "added": "2026-09-12"}',
    '{"bad": "воркфлоу", "good": "порядок работы", "domain": "", "status": "candidate", "note": "", "source": "", "added": "2026-09-12"}',
]

_DICT_PATH = None


def write_dict():
    global _DICT_PATH
    if _DICT_PATH is not None:
        return _DICT_PATH

    fd, path = tempfile.mkstemp(suffix=".jsonl")
    try:
        with io.open(fd, "w", encoding="utf-8") as f:
            for line in STYLE_DICT_LINES:
                f.write(line + "\n")
        _DICT_PATH = path
        return path
    except Exception:
        os.close(fd)
        raise


def doc(*blocks):
    result = ["# Проверочный образец", ""]
    result.extend(blocks)
    result.append("")
    result.extend(["## Источники", "", "Справочник по стилю, раздел 6", ""])
    return "\n".join(result)


def run_lint(text, extra_args=None, dicts=None):
    tmpdir = tempfile.mkdtemp()
    sample_path = os.path.join(tmpdir, "sample.md")
    with io.open(sample_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    cmd = [sys.executable, LINT, sample_path, "--json"]
    if dicts is not None:
        for d in dicts:
            cmd.extend(["--dict", d])
    elif dicts is None:
        cmd.extend(["--dict", write_dict()])
    if extra_args:
        cmd.extend(extra_args)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env
    )

    try:
        violations = json.loads(result.stdout)
    except Exception as e:
        raise AssertionError("Ошибка разбора JSON: %s\nstdout: %s\nstderr: %s" %
                             (e, result.stdout, result.stderr))

    return (violations, result.returncode)


def codes(violations):
    return {v["code"] for v in violations}


CASES = [
    ("Ш-1", ["Очень длинная строка без чисел и латиницы " * 3], None),
    ("Ш-2", ["| Колонка А | Колонка Б |",
             "|---|---|",
             "| Первая колонка с достаточно длинным описанием предмета "
             "| Вторая колонка с не менее длинным описанием предмета |"],
     ["--width", "400"]),
    ("Ш-3", ["| А | Б | В | Г | Д |", "|---|---|---|---|---|", "| 1 | 2 | 3 | 4 | 5 |"], None),
    ("Ш-4", ["| Колонка | Описание |", "|---|---|",
             "| Значение | Описание предмета длиной больше тридцати |"],
     ["--cell", "30"]),
    ("Ч-1", ["\n".join(["Текст абзаца набран русскими словами без сокращений и без чисел"] * 15)], None),
    ("Ч-2", ["Первое предложение. Второе предложение. Третье предложение. Четвёртое предложение.",
             "Пятое предложение. Шестое предложение. Седьмое предложение. Восьмое предложение."], None),
    ("Ч-3", ["- Первый уровень", "  - Второй уровень", "    - Третий уровень"], None),
    ("С-1", ["Разбор опубликован по адресу https://example.org/report в открытом доступе"], None),
    ("С-2", ["Разбор приведён в справке [здесь](https://example.org/report) без пояснений"], None),
    ("С-3", ["Материал лежит в файле D:\\Отчёты\\проба.md рядом с исходником"], None),
    ("Я-1", ["Этот кейс разобран отдельно"], None),
    ("Я-2", ["Отдельно рассмотрен benchmark по методике"], None),
    ("Т-1", ["Погрешность составила 7.5 единицы"], None),
    ("Т-2", ['Величина названа "опорной" в источнике'], None),
    ("Т-3", ["Диапазон от пяти до семи - это предел"], None),
    ("Т-4", ["Доля составила 7,5% от общего числа"], None),
    ("Т-5", ["Переход к выводу \u2192 результат получен"], None),
    ("Т-6", ["## Подраздел с точкой.", "", "Текст подраздела"], None),
    ("К-1", ["# Второй заголовок первого уровня", "", "Текст раздела"], None),
    ("К-2", ["## Раздел второго уровня", "", "#### Подраздел четвёртого уровня", "",
             "Текст подраздела"], None),
]

CLEAN = """# Отчёт о проверке методики

## Краткий ответ

Методика применима в заданных пределах, расхождение не превышает допустимого.

## Обоснование

| Величина | Значение | Единица |
|---|---|---|
| Разрешение | 7,5 | процент |
| Энергия | 662 | килоэлектронвольт |

Расхождение между расчётом и измерением составило 6 % — это в пределах допуска.

## Ограничения

- Проверка охватывает только рабочий диапазон
  - Вне диапазона поведение не изучалось

## Источники

Ильин, Кириллов, «Радиационная гигиена», с. 38
"""


class TestReportLint(unittest.TestCase):
    def assert_only(self, text, code, extra_args=None):
        violations, _ = run_lint(text, extra_args)
        got = codes(violations)
        self.assertIn(code, got, "образец обязан нарушать %s; линтер увидел: %s" % (code, sorted(got)))
        self.assertEqual(got, {code},
                         "образец обязан нарушать ТОЛЬКО %s; лишние срабатывания: %s" % (code, sorted(got - {code})))

    def test_mutacionnye_obraztsy(self):
        """Каждый образец краснит ровно своё правило."""
        for code, body, extra in CASES:
            with self.subTest(код=code):
                self.assert_only(doc("\n".join(body)), code, extra)

    def test_k3_net_razdela_istochniki(self):
        """К-3: нет раздела источников."""
        text = "# Заголовок отчёта\n\nТекст без раздела источников\n"
        self.assert_only(text, "К-3")

    def test_godnyy_obrazets_chist(self):
        """Годной образец не даёт нарушений."""
        violations, rc = run_lint(CLEAN)
        self.assertEqual(violations, [], "на годном образце сработало: " + json.dumps(violations,
                                                                                       ensure_ascii=False,
                                                                                       indent=2))
        self.assertEqual(rc, 0)

    def test_uroven_canon_oshibka(self):
        """Я-1: канонический уровень — ошибка."""
        violations, rc = run_lint(doc("Этот кейс разобран отдельно"))
        v = [v for v in violations if v["code"] == "Я-1"][0]
        self.assertEqual(v["level"], "ОШИБКА")
        self.assertIn("случай", v["message"])
        self.assertEqual(rc, 1)

    def test_uroven_candidate_predupr(self):
        """Я-1: кандидатский уровень — предупреждение."""
        violations, rc = run_lint(doc("Предложенный воркфлоу описан в приложении"))
        v = [v for v in violations if v["code"] == "Я-1"][0]
        self.assertEqual(v["level"], "ПРЕДУПРЕЖДЕНИЕ")
        self.assertEqual(rc, 0)

    def test_predupr_ne_menyaet_kod(self):
        """Предупреждение не меняет код возврата."""
        violations, rc = run_lint(doc("- Первый уровень\n  - Второй уровень\n    - Третий уровень"))
        self.assertEqual(rc, 0)

    def test_oshibka_daet_kod_1(self):
        """Ошибка даёт код возврата 1."""
        violations, rc = run_lint(doc("Погрешность составила 7.5 единицы"))
        self.assertEqual(rc, 1)

    def test_blok_koda_ne_proveryaetsya(self):
        """Блок кода не проверяется."""
        text = doc("```python\nx = 7.5  # \"кавычки\" - дефис\n```")
        violations, _ = run_lint(text)
        self.assertEqual(violations, [])

    def test_dlinnaya_stroka_v_bloke_koda(self):
        """Длинная строка в блоке кода."""
        text = doc("```python\n# " + "длинный комментарий " * 6 + "\n```")
        violations, _ = run_lint(text)
        self.assertEqual(codes(violations), {"Ш-1"})

    def test_istochniki_razreshayut_adres(self):
        """Источники разрешают адрес."""
        text = "# Заголовок отчёта\n\nТекст без адресов\n\n## Источники\n\n" \
               "Отчёт: https://example.org/report, файл D:\\Отчёты\\проба.md\n"
        violations, _ = run_lint(text)
        c = codes(violations)
        self.assertNotIn("С-1", c)
        self.assertNotIn("С-3", c)

    def test_slovar_otsutstvuet_ne_padaet(self):
        """Отсутствующий словарь не приводит к падению."""
        violations, rc = run_lint(doc("Обычный текст без нарушений"),
                                  dicts=["C:\\nonexistent\\nope.jsonl"])
        self.assertNotEqual(rc, 2)

    def test_inline_kod_ne_tipografika(self):
        """Инлайн-код не считается типографикой."""
        text = doc("Значение задаётся строкой `x = 7.5` в примере")
        violations, _ = run_lint(text)
        self.assertNotIn("Т-1", codes(violations))

    def test_quiet_pechataet_svodku(self):
        """--quiet печатает сводку."""
        tmpdir = tempfile.mkdtemp()
        sample_path = os.path.join(tmpdir, "sample.md")
        with io.open(sample_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(CLEAN)

        cmd = [sys.executable, LINT, sample_path, "--quiet"]
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env
        )
        self.assertIn("Нарушений:", result.stdout)

    def test_s3_goloe_imya_ne_narushenie(self):
        """С-3: голое имя файла без каталога — не нарушение (решение оператора)."""
        v, _ = run_lint(doc("Сборка выполняется скриптом md2html.py по умолчанию"))
        self.assertEqual(codes(v), set(), json.dumps(v, ensure_ascii=False))

    def test_s3_put_rovno_odno(self):
        """С-3: путь с буквой диска — ровно одно срабатывание."""
        v, _ = run_lint(doc("Материал лежит в файле D:\\Library\\x.pdf рядом"))
        s3 = [x for x in v if x["code"] == "С-3"]
        self.assertEqual((len(s3), codes(v)), (1, {"С-3"}), json.dumps(v, ensure_ascii=False))

    def test_s3_put_s_probelami(self):
        """С-3: путь с пробелами — одно срабатывание, путь целиком, без хвостовой запятой."""
        v, _ = run_lint(doc("Исходник в файле D:\\Рабочие файлы\\отчёт по пробам.pdf, далее разбор"))
        s3 = [x["message"] for x in v if x["code"] == "С-3"]
        self.assertEqual((len(s3), codes(v)), (1, {"С-3"}), json.dumps(v, ensure_ascii=False))
        self.assertIn("D:\\Рабочие файлы\\отчёт по пробам.pdf —", s3[0])

    def test_s3_put_s_probelami_v_kavychkah(self):
        """С-3: путь с пробелами в обратных кавычках — одно срабатывание, путь целиком."""
        p = "D:\\Library\\books-library\\texts\\Нормы радиационной безопасности.pdf.md"
        v, _ = run_lint(doc("Исходник `%s` в библиотеке" % p), ["--width", "400"])
        s3 = [x["message"] for x in v if x["code"] == "С-3"]
        self.assertEqual((len(s3), codes(v)), (1, {"С-3"}), json.dumps(v, ensure_ascii=False))
        self.assertIn(p + " —", s3[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
