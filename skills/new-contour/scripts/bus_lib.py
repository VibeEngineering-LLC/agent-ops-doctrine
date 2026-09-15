# -*- coding: utf-8 -*-
"""Shared UTF-8-safe primitives for the cc-interchat-bus.

Schemas mirror the LIVE bus (verified 2026-06-06 against existing censor/gamma
envelopes and registry files):

  registry/<role>.json : {role, session_id, status, last_heartbeat_ts, pid}
  envelope             : {id, ts, from, to, type, subject, body, refs[],
                          action_class, requires_operator, in_reply_to}
  audit/log.jsonl line : {event_ts, event, id, from, to, type, subject,
                          action_class, requires_operator, in_reply_to, filename}
  inbox filename       : <YYYY-MM-DDTHH-MM-SS-ffffff Z>__<id>.json

Atomicity: write to bus/tmp/*.tmp then os.replace into the target dir (atomic on
NTFS/POSIX). No fcntl/msvcrt locks needed. Never mutate another role's registry.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

BUS = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\<you>\AppData\Local")) / "cc-interchat-bus"


# ---- timestamps -------------------------------------------------------------
def now_iso():
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond:06d}Z"


def fname_ts():
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H-%M-%S-") + f"{n.microsecond:06d}Z"


# ---- paths ------------------------------------------------------------------
def inbox(role):
    return BUS / "inbox" / role


def processed(role):
    return BUS / "processed" / role


def registry_file(role):
    return BUS / "registry" / f"{role}.json"


def seen_file(role):
    return BUS / "_state" / f"{role}_watcher_seen.txt"


def _atomic_write(dst: Path, text: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = BUS / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / (dst.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dst)


# ---- audit ------------------------------------------------------------------
def audit_append(rec: dict):
    f = BUS / "audit" / "log.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---- registry ---------------------------------------------------------------
def read_registry(role):
    f = registry_file(role)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_registry(role, session_id=None, status="working", pid=None):
    """Create/refresh a role's registry entry. Preserves session_id if not given."""
    cur = read_registry(role)
    rec = {
        "role": role,
        "session_id": session_id or cur.get("session_id") or uuid.uuid4().hex,
        "status": status,
        "last_heartbeat_ts": now_iso(),
        "pid": pid if pid is not None else cur.get("pid"),
    }
    _atomic_write(registry_file(role), json.dumps(rec, ensure_ascii=False, indent=2))
    return rec


def heartbeat(role):
    """Refresh only the heartbeat timestamp; leave the rest intact."""
    cur = read_registry(role)
    if not cur:
        return None
    cur["last_heartbeat_ts"] = now_iso()
    _atomic_write(registry_file(role), json.dumps(cur, ensure_ascii=False, indent=2))
    return cur


def is_live(role, stale_s=900):
    """True if the role has a heartbeat younger than stale_s seconds."""
    cur = read_registry(role)
    hb = cur.get("last_heartbeat_ts")
    if not hb:
        return False
    try:
        t = datetime.fromisoformat(hb.replace("Z", "+00:00")).timestamp()
    except Exception:
        return False
    return (datetime.now(timezone.utc).timestamp() - t) < stale_s


# ---- envelopes --------------------------------------------------------------
def send(frm, to, etype, subject, body, refs=None, action_class="read-only",
         in_reply_to=None):
    """Place an envelope atomically in inbox/<to>/ and log a 'send' audit line.
    Returns (msg_id, filename)."""
    msg_id = uuid.uuid4().hex
    ts = now_iso()
    fname = f"{fname_ts()}__{msg_id}.json"
    requires_operator = (action_class == "irreversible")
    env = {
        "id": msg_id, "ts": ts, "from": frm, "to": to, "type": etype,
        "subject": subject, "body": body, "refs": refs or [],
        "action_class": action_class, "requires_operator": requires_operator,
        "in_reply_to": in_reply_to,
    }
    _atomic_write(inbox(to) / fname, json.dumps(env, ensure_ascii=False, indent=1))
    audit_append({
        "event_ts": ts, "event": "send", "id": msg_id, "from": frm, "to": to,
        "type": etype, "subject": subject, "action_class": action_class,
        "requires_operator": requires_operator, "in_reply_to": in_reply_to,
        "filename": fname,
    })
    return msg_id, fname
