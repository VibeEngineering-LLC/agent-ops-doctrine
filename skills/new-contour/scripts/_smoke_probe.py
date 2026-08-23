# -*- coding: utf-8 -*-
"""Smoke-test: watch.py sentinel-probe support (PROBE-ALIVE emit + self-delete).

Creates a throwaway role, drops a .heartbeat-probe-*.json, runs watch.py once,
asserts the probe was announced and auto-deleted, then removes all scaffolding.

Usage: python _smoke_probe.py   (exit 0 = pass, 1 = fail)
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bus_lib import BUS, inbox, registry_file, seen_file, now_iso

ROLE = "ptest_smoke"
WATCH = str(Path(__file__).parent / "watch.py")


def cleanup():
    for p in [registry_file(ROLE), seen_file(ROLE)]:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    for d in [inbox(ROLE), BUS / "processed" / ROLE]:
        if d.exists():
            for f in d.iterdir():
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                d.rmdir()
            except OSError:
                pass


def main():
    cleanup()
    # minimal registry so watch.py does not refuse
    registry_file(ROLE).parent.mkdir(parents=True, exist_ok=True)
    registry_file(ROLE).write_text(json.dumps({
        "role": ROLE, "session_id": "smoke", "status": "working",
        "last_heartbeat_ts": now_iso(), "pid": 0}), encoding="utf-8")
    ib = inbox(ROLE)
    ib.mkdir(parents=True, exist_ok=True)
    probe = ib / ".heartbeat-probe-SMOKE.json"
    probe.write_text("{}", encoding="utf-8")

    out = subprocess.run([sys.executable, WATCH, ROLE],
                         capture_output=True, text=True, encoding="utf-8")
    stdout = out.stdout or ""
    ok_emit = "PROBE-ALIVE" in stdout and "SMOKE" in stdout
    ok_deleted = not probe.exists()

    print("stdout:", stdout.strip())
    print("PROBE-ALIVE emitted:", ok_emit)
    print("probe self-deleted :", ok_deleted)
    cleanup()

    if ok_emit and ok_deleted:
        print("RESULT: PASS")
        sys.exit(0)
    print("RESULT: FAIL")
    sys.exit(1)


if __name__ == "__main__":
    main()