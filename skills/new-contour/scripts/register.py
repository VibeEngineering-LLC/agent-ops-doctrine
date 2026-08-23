# -*- coding: utf-8 -*-
"""Phase-1 registration for a new bus contour.

Creates the role's registry entry, inbox/processed dirs, seeds the watcher-seen
file, and writes a 'register' audit event. Refuses to clobber a live role
(heartbeat <15 min) unless --force, to prevent two chats answering as one role.

Usage:
  python register.py --role tester --project "C:\\path\\to\\project" [--force]
"""
import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bus_lib import (BUS, inbox, processed, registry_file, seen_file,
                     read_registry, write_registry, is_live, audit_append, now_iso)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, help="Bus role name, e.g. 'tester'")
    ap.add_argument("--project", required=True, help="Absolute project root for this contour")
    ap.add_argument("--force", action="store_true",
                    help="Allow clobber of an existing live role (DANGEROUS — only if you are sure "
                         "the other session is dead).")
    args = ap.parse_args()

    role = args.role.strip()
    if not role or "/" in role or "\\" in role:
        print(f"ERROR: invalid role name: {role!r}", file=sys.stderr)
        sys.exit(2)

    project = Path(args.project)
    if not project.is_absolute():
        print(f"ERROR: --project must be absolute, got: {project}", file=sys.stderr)
        sys.exit(2)

    # Live-role guard
    existing = read_registry(role)
    if existing and is_live(role, stale_s=900) and not args.force:
        print(f"ERROR: role '{role}' is already LIVE (last_heartbeat_ts="
              f"{existing.get('last_heartbeat_ts')}, session_id={existing.get('session_id')}). "
              f"Refusing to clobber. Use --force only if you are certain that session is dead.",
              file=sys.stderr)
        sys.exit(3)

    # Create dirs
    inbox(role).mkdir(parents=True, exist_ok=True)
    processed(role).mkdir(parents=True, exist_ok=True)
    (BUS / "_state").mkdir(parents=True, exist_ok=True)

    # Seed seen-file empty (so first watcher pass surfaces nothing pre-existing — clean slate)
    sf = seen_file(role)
    if not sf.exists():
        sf.write_text("", encoding="utf-8")

    # Fresh registry entry: new session_id, new pid
    new_session_id = uuid.uuid4().hex
    rec = write_registry(role, session_id=new_session_id, status="working", pid=os.getpid())

    # Audit
    audit_append({
        "event_ts": now_iso(),
        "event": "register",
        "role": role,
        "project": str(project),
        "session_id": new_session_id,
        "pid": os.getpid(),
        "forced": bool(args.force),
    })

    print(f"REGISTERED role={role} session_id={new_session_id} pid={os.getpid()}")
    print(f"  inbox     : {inbox(role)}")
    print(f"  processed : {processed(role)}")
    print(f"  registry  : {registry_file(role)}")
    print(f"  seen-file : {sf}")
    print(f"  project   : {project}")


if __name__ == "__main__":
    main()
