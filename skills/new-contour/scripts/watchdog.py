# -*- coding: utf-8 -*-
"""Machine-global bus watchdog - SINGLE-SHOT health scan for cc-interchat-bus.

Зачем: per-contour watcher (watch.py) живёт в Monitor-таске СВОЕГО чата и умирает,
когда чат перезагружается/компактится. После смерти watcher а новые envelope ы
ложатся в inbox/<role>/, но строка NEW MAIL не печатается - контур "глохнет".
Этот watchdog - backstop: single-shot скан, который любой долгоживущий хост
(Windows Task Scheduler, ad-hoc shell, команда оператора) перезапускает по cadence.

Он НЕ запускает watch.py за другие роли (это затёрло бы их heartbeat/seen и
спрятало бы тот самый сбой) - он только ДЕТЕКТИРУЕТ и РАПОРТУЕТ застой.

Контур STALLED, когда ОБА условия:
  - его registry heartbeat старше STALE_S секунд, И
  - в его inbox лежит >=1 настоящий (не probe) недренированный envelope.

На каждом прогоне:
  1. Печатает health-таблицу (строка на каждую зарегистрированную роль).
  2. Дописывает одну JSONL-запись в wake/watchdog.log.
  3. Кладёт маркер wake/<role>.STALLED для застрявших, снимает для здоровых.
  4. Exit 0 (дружелюбно к Monitor). Действие - по таблице/маркерам.

Истинное авто-воскрешение watcher а может сделать только главный цикл ВЛАДЕЮЩЕГО
чата (re-spawn Monitor watch.py). Маркер здесь - это сигнал так сделать. Для
backstop а, переживающего падение ВСЕХ чатов, планируй ЭТОТ скрипт на уровне ОС
(см. SKILL.md, раздел "wake/ watchdog").

Usage:
  python watchdog.py [--stale-seconds N]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bus_lib import BUS, inbox, read_registry, now_iso


def _age_s(hb_ts):
    if not hb_ts:
        return None
    try:
        t = datetime.fromisoformat(hb_ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
    return datetime.now(timezone.utc).timestamp() - t


def _pending(role):
    ib = inbox(role)
    n = 0
    if ib.exists():
        for fp in ib.iterdir():
            if not fp.name.endswith(".json"):
                continue
            if fp.name.startswith(".heartbeat-probe-"):
                continue
            if "__" not in fp.name[:-5]:
                continue
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stale-seconds", type=int, default=180,
                    help="heartbeat age over which a role with pending mail is STALLED")
    args = ap.parse_args()

    reg_dir = BUS / "registry"
    wake = BUS / "wake"
    wake.mkdir(parents=True, exist_ok=True)
    roles = sorted(p.stem for p in reg_dir.glob("*.json")) if reg_dir.exists() else []

    rows = []
    stalled = []
    for role in roles:
        reg = read_registry(role)
        age = _age_s(reg.get("last_heartbeat_ts"))
        pend = _pending(role)
        is_stalled = (age is not None and age > args.stale_seconds and pend > 0)
        rows.append((role, age, pend, reg.get("status", "?"), is_stalled))
        marker = wake / (role + ".STALLED")
        if is_stalled:
            stalled.append(role)
            marker.write_text(
                json.dumps({"role": role, "age_s": round(age, 1), "pending": pend,
                            "flagged_ts": now_iso()}, ensure_ascii=False),
                encoding="utf-8")
        else:
            try:
                marker.unlink(missing_ok=True)
            except OSError:
                pass

    print("=== bus watchdog @ " + now_iso() + "  (stale>" + str(args.stale_seconds) + "s) ===")
    print("{:<12} {:>9} {:>7} {:<9} flag".format("role", "hb_age_s", "pending", "status"))
    for role, age, pend, status, is_stalled in rows:
        age_str = "n/a" if age is None else "{:.0f}".format(age)
        flag = "STALLED <-- restart its watcher" if is_stalled else "ok"
        print("{:<12} {:>9} {:>7} {:<9} {}".format(role, age_str, pend, status, flag))
    if not rows:
        print("(no registered roles)")

    logf = wake / "watchdog.log"
    with logf.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "ts": now_iso(),
            "stale_seconds": args.stale_seconds,
            "roles": {r: {"age_s": (None if a is None else round(a, 1)),
                          "pending": p, "stalled": st}
                      for r, a, p, _s, st in rows},
            "stalled": stalled,
        }, ensure_ascii=False) + "\n")

    if stalled:
        print("")
        print("STALLED roles: " + ", ".join(stalled) + " - markers in wake/<role>.STALLED")


if __name__ == "__main__":
    main()