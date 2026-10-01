import os
import re
import sys
from datetime import datetime

HOOKS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "hooks")
SNAP_RE = re.compile(r"^snap_(\d{8}-\d{6})_([A-Za-z0-9-]{1,8})\.md$")
MAX_AGE_MIN = 30


def session_tag(session_id) -> str:
    return re.sub(r"[^A-Za-z0-9\-]", "", str(session_id or ""))[:8]


def snapshot_field(md_path, label) -> str:
    try:
        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                stripped = line.lstrip()
                prefix = "- **" + label + ":** "
                if stripped.startswith(prefix):
                    return stripped[len(prefix):].strip()
    except Exception:
        pass
    return ""


def own_snapshot(snap_dir, session_id, now=None, max_age_min=MAX_AGE_MIN) -> str:
    tag = session_tag(session_id)
    if not tag:
        return ""

    if now is None:
        now = datetime.now()

    try:
        entries = os.listdir(snap_dir)
    except Exception:
        return ""

    candidates = []
    for name in entries:
        m = SNAP_RE.match(name)
        if not m:
            continue
        if m.group(2) != tag:
            continue
        
        try:
            t = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
        except ValueError:
            continue

        d = (now - t).total_seconds()
        if not (-60 <= d <= max_age_min * 60):
            continue

        path = os.path.join(snap_dir, name)
        sess_field = snapshot_field(path, "Сессия")
        if sess_field != str(session_id):
            continue
        
        candidates.append((t, name, path))

    if not candidates:
        return ""

    # Наибольшее время, при равенстве — наибольшее имя
    best = max(candidates, key=lambda x: (x[0], x[1]))
    return best[2]


def contour_state_path(payload, fallback_cwd) -> str:
    try:
        if HOOKS_DIR not in sys.path:
            sys.path.insert(0, HOOKS_DIR)
        import contour_root
        r = contour_root.resolve(payload)
        if isinstance(r, dict):
            root = r.get("root")
            source = r.get("source")
            if root and source == "launch":
                return os.path.join(root, "SESSION-STATE.md")
    except BaseException:
        pass

    if fallback_cwd:
        return os.path.join(fallback_cwd, "SESSION-STATE.md")
    return ""


def state_dir(payload, fallback_cwd) -> str:
    p = contour_state_path(payload, fallback_cwd)
    if p:
        return os.path.dirname(p)
    return fallback_cwd or ""


def notice_inputs(payload, snap_dir, now=None) -> dict:
    try:
        if not isinstance(payload, dict):
            return {}

        md = own_snapshot(snap_dir, payload.get("session_id"), now)
        if not md:
            return {}

        snap_cwd = snapshot_field(md, "Рабочая папка")
        sp = contour_state_path(payload, snap_cwd)
        
        trigger_str = snapshot_field(md, "Триггер")
        words = trigger_str.split()
        trigger = words[0] if words else "?"

        cwd = os.path.dirname(sp) if sp else snap_cwd

        return {"path": md, "cwd": cwd, "trigger": trigger}
    except BaseException:
        return {}
