# -*- coding: utf-8 -*-
"""Phase-2 Censor-watcher — SINGLE-SHOT scan, looped by the Monitor tool.

Design constraint (lesson from MAILBOX_PROTOCOL.md zombie note): the long-lived
loop is provided by Claude's Monitor tool running a shell wrapper
`while true; do watch.py <role>; sleep 15; done` from the contour's OWN main loop.
The Monitor tool ENDS the watch when its command exits, so a bare single-shot
invocation fires once and stops (verified 2026-06-21) — the wrapper is what keeps
it live. This script itself MUST stay single-shot and exit each run. DO NOT spawn a
`while True` watcher in a `&`/`nohup`/`disown` subprocess — those zombie on
session reload and you lose the link to the Censor.

What it does on each invocation:
  1. Refreshes the role's registry heartbeat (so peers see this contour as live).
  2. Scans inbox/<role>/ for envelopes not yet in _state/<role>_watcher_seen.txt.
  3. Prints ONE LINE PER NEW envelope to stdout — each line becomes a
     <task-notification> in the Monitor tool's surfacing to the main loop.
  4. Appends new envelope ids to the seen-file (atomic via tmp+replace).
  5. Exits 0.

Usage:
  python watch.py <role>

In SKILL.md, the Monitor tool runs (looped):
  while true; do PYTHONUTF8=1 python <path>/scripts/watch.py tester; sleep 15; done
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bus_lib import BUS, inbox, seen_file, heartbeat, read_registry


def main():
    if len(sys.argv) < 2:
        print("usage: watch.py <role>", file=sys.stderr)
        sys.exit(2)
    role = sys.argv[1].strip()

    # Registry must exist — refuse to silently create one for an unknown role
    if not read_registry(role):
        print(f"ERROR: no registry for role '{role}'. Run register.py first.", file=sys.stderr)
        sys.exit(3)

    # 1. Heartbeat
    heartbeat(role)

    # 2. Load seen ids
    sf = seen_file(role)
    sf.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if sf.exists():
        for line in sf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                seen.add(line)

    # 3. Scan inbox
    ib = inbox(role)
    new_ids = []
    if ib.exists():
        # Filenames are <fname_ts>__<id>.json — sortable by name == sortable by time
        for fp in sorted(ib.iterdir()):
            if not fp.name.endswith(".json"):
                continue
            # Sentinel-probe liveness file (doctrine: inbox/<role>/.heartbeat-probe-<ts>.json).
            # Emit ONE PROBE-ALIVE line proving this watcher tick actually ran, then
            # self-delete so it never re-fires on the next tick (ephemeral, NOT tracked
            # in seen). This is what makes the global "sentinel-probe FIRST" liveness
            # check work against new-contour — the older watch.py skipped these files.
            if fp.name.startswith(".heartbeat-probe-"):
                print(f"PROBE-ALIVE inbox/{role}: {fp.name}")
                try:
                    fp.unlink()
                except OSError:
                    pass
                continue
            stem = fp.name[:-5]  # strip .json
            if "__" not in stem:
                continue
            msg_id = stem.split("__", 1)[1]
            if msg_id in seen:
                continue
            # Print as Monitor-tool-friendly single-line event:
            print(f"NEW MAIL inbox/{role}: {fp.name}")
            new_ids.append(msg_id)

    # 4. Persist seen
    if new_ids:
        tmp = BUS / "tmp" / (sf.name + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        text = sf.read_text(encoding="utf-8") if sf.exists() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n".join(new_ids) + "\n"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, sf)

    # 5. Exit 0


if __name__ == "__main__":
    main()
