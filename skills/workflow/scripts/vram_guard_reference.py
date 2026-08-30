# Reference implementation of Ollama Layer 2 VRAM guard — v1.9.2 (2026-08-28).
# CANONICAL SOURCE: C:\Users\<you>\.claude\skills\workflow\scripts\vram_guard_reference.py
#
# Consuming projects MAY copy verbatim to <project>/scripts/ollama/_vram_guard.py.
# IF YOU COPY THIS FILE: check GUARD_VERSION below against the canonical source
# before trusting it. On 2026-08-28 eighteen copies existed across the tree, eight
# of them missing the thinking-model guard, and ALL of them still claimed "v1.8.0"
# in this header because the header was never updated with the body — two contours
# diagnosed the version from this line that day and both got a false answer.
# Prefer importing over copying (doctrine §33); if you must copy, re-check on every
# guard change. `python vram_guard_reference.py --version` prints GUARD_VERSION.
#
# Pairs with pre_flight_reference.py (Layer 1 — coarse profile guard).
# See skill/SKILL.md "Pre-flight check — two-layer VRAM guard" for the rationale.
# See skill/SKILL_VRAM_GUARD.md "GPU-only Ollama fallback" for the queue API.
"""
VRAM pre-flight guard for Ollama helpers.

Why
---
Local-First Ollama policy (CLAUDE.md, LOCKED 2026-06-04) routes routine
extraction / classification / templated generation to the local Ollama
endpoint. The host (RTX 4090, 24 GB VRAM) is shared with other agents /
sessions / GUI processes. When a neighbour process inflates VRAM use
(e.g. double-OCR with qwen2.5vl:7b + qwen3-coder:30b > 24 GB), the next
Ollama `/api/generate` call OOMs catastrophically: the model fails to
load, the HTTP request hangs or returns garbage, and the subagent
producing the call returns 0-byte output (silent crash visible only in
`tasks/<id>.output`).

This module turns "silent OOM" into "explicit fail-fast with structured
error" so the caller can:
  - wait + retry (poll loop)
  - enter the cross-chat machine-global queue (v1.8.0)
  - fall back to CPU mode (v1.8.0)
  - escalate to Claude / a larger model
  - report to the orchestrator and abort cleanly

What it does (v1.8.0)
---------------------
  check_can_load(model_name) -> VramVerdict
      structured verdict {ok, reason, free_MB, need_MB, headroom_MB,
                          currently_loaded, other_processes, recommendation}

  wait_until_can_load(model_name, max_wait_s=120, poll_s=5) -> VramVerdict
      poll loop, returns the first successful verdict or a timeout verdict

  wait_in_queue(model, *, priority, max_wait_s, ...) -> VramVerdict    [v1.8.0]
      enter the cross-chat machine-global VRAM queue; wait until
      first-in-line + VRAM OK, then return ok=True; or drop-out to CPU.

  try_cpu(model, prompt, ...) -> dict                                   [v1.8.0]
      run /api/generate in CPU mode (num_gpu=0) + RAM check.

  guarded_generate(model, prompt, **kwargs) -> dict                     [v1.8.0]
      three-tier drop-in replacement for requests.post('/api/generate'):
        Tier 1: GPU direct (check_can_load → if OK, call on GPU)
        Tier 2: cross-chat queue (if GPU busy AND want_gpu=True)
        Tier 3: CPU fallback (num_gpu=0 + RAM check + 5x timeout)
        Tier 4: raise VramGuardFailure → caller falls back to Claude

Out of scope
------------
This guard protects Ollama jobs from each other (Ollama-side OOM /
contention between Ollama models). It does NOT reserve VRAM for a
co-resident interactive desktop GPU process (an Electron app like Claude
Code, or a browser) sharing the GPU with Ollama on a workstation — a
healthy Ollama pinning VRAM through a long idle window can starve that
process and crash it, with no Ollama-side fault to detect. For that, set
OLLAMA_GPU_OVERHEAD (plus a short OLLAMA_KEEP_ALIVE and
OLLAMA_MAX_LOADED_MODELS=1) on the host. See skill/SKILL_VRAM_GUARD.md
"Out of scope — co-resident desktop GPU starvation".

CLI
---
  python vram_guard_reference.py                     # one-shot status
  python vram_guard_reference.py --check qwen3-coder:30b
  python vram_guard_reference.py --watch              # polling status every 5 s
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Per-model VRAM estimates (MB). Sourced from `ollama show <model>` +
# observed `nvidia-smi` deltas on RTX 4090 with KV cache.
#
# Defaults are calibrated for the **forge profile (num_ctx=32_768)** — the
# routine generation case. Source: `ollama show qwen3-coder:30b` reports
# 30.5B params Q4_K_M (~17.9 GB weights), MoE architecture → small KV per
# token. Observed nvidia-smi load: ~17.5 GB resident at 32k context.
#
# For larger contexts (math 128k / archive 128k with KV cache q8_0) pass
# `estimate_override_MB=` explicitly:
#   - qwen3-coder:30b @ 128k q8_0  → ~22_500 MB
#   - qwen3-coder:30b @ 64k        → ~19_500 MB
#   - qwen3-coder:30b @ 32k (forge)→ ~17_500 MB (default below)
# ---------------------------------------------------------------------------
MODEL_VRAM_ESTIMATE_MB: dict[str, int] = {
    "qwen3-coder:30b": 17_500,
    "qwen3.6:27b":     17_800,  # measured 2026-08-22/23, LLM contour + Codeaudit bench, both @ 32k
    "qwen2.5vl:7b":     7_000,
    "qwen3.6:latest":   8_500,  # NOTE: stale/wrong estimate for the 36B model this tag now is —
                                # kept only because the tag is Disabled by policy (superseded by
                                # qwen3.6:27b); do not trust this number if the tag is reused.
    "qwen3:4b":         4_500,
    "bge-m3:latest":    1_500,
}

# Thinking-capable models. Two measured failure modes, BOTH fixed by think=False:
#   1. fmt="json": the answer lands in the hidden `thinking` field, `response` comes
#      back empty with done=true and no exception (2026-08-23, v1.9.0).
#   2. long codegen (fmt=None): reasoning eats the num_predict budget, output is cut
#      mid-function with done_reason="length". Measured on qwen3.6:27b, same prompt,
#      num_predict=6000: think on -> 19347 chars of thinking, 3891 chars of code,
#      TRUNCATED; think off -> 0 thinking, 10236 chars of code, done_reason="stop"
#      (LLM contour P-002, 2026-08-23 evening).
# Hence v1.9.1: guarded_generate() auto-sets think=False for these models on EVERY
# call, regardless of fmt. guarded_generate() delegates mechanical work — reasoning
# is not what it is for. Callers who genuinely want it pass think=True explicitly.
# See SKILL_VRAM_GUARD.md "Thinking models".
THINKING_CAPABLE_MODELS: set[str] = {
    "qwen3.6:27b",
    "qwen3.6:latest",
    "qwen3:4b",
}

# Default num_predict cap for models with reproducible runaway generation.
# Empty by default — populate a model here if it shows the failure pattern
# (Codeaudit 2026-08-23: glm-4.7-flash:latest ran 357s / 105KB on one call
# before being removed from the fleet). guarded_generate()'s explicit
# num_predict= kwarg always overrides this.
MODEL_NUM_PREDICT_CAP: dict[str, int] = {}

# Hard trial block: check_can_load() and try_cpu() refuse ANY model listed here
# unconditionally, before the VRAM probe. Populate ONLY on explicit operator
# instruction, and clear it the same way — never on your own judgment.
#
# History: qwen3-coder:30b was blocked 2026-08-23 evening while observing
# qwen3.6:27b as sole delegation default (24 GB card, both models ~17-18 GB,
# so one call to the other model evicts the resident one). LIFTED the same
# night on operator instruction, after the block's first practical cost showed
# up: the GEANT4 contour hit a codegen failure on qwen3.6:27b (LLM contour
# P-002) and qwen3-coder is ~6x cheaper per correct answer on code by the
# Codeaudit 2026-08-23 benchmark (2.8 vs 16.8, median time / class score).
# qwen3.6:27b REMAINS the delegation default — see SKILL.md; qwen3-coder:30b
# is simply reachable again on explicit request.
TRIAL_BLOCKED_MODELS: set[str] = set()

# ---------------------------------------------------------------------------
# Per-model RAM estimates (GB) for CPU fallback mode (num_gpu=0).
#
# CPU inference puts the full Q4_K_M weights + KV cache in system RAM. For
# qwen3-coder:30b (Q4_K_M, ~17.9 GB weights + KV @ 32k ~= 0.5 GB) the typical
# resident-set is ~18 GB; we add a +4 GB OS reserve before accepting CPU mode.
# ---------------------------------------------------------------------------
MODEL_RAM_ESTIMATE_GB: dict[str, int] = {
    "qwen3-coder:30b": 18,
    "qwen3.6:27b":     19,
    "qwen3.6:latest":  22,
    "qwen2.5vl:7b":     8,
    "qwen3:4b":         5,
    "bge-m3:latest":    2,
}
CPU_OS_RESERVE_GB: int = 4

# Buffer kept for the OS / desktop compositor / other CUDA-aware apps,
# plus headroom for Ollama's actual VRAM use overshooting the estimate
# (KV cache growth during long generations, internal allocator slack).
#
# 3 GB on RTX 4090 covers: Windows DWM + browser GPU compositing
# (~1-1.5 GB) + small Python procs (~0.5 GB) + ~1 GB generative slack
# (KV cache expansion mid-generation, allocator fragmentation).
# Bump on EVERY behaviour change, together with the header line. Machine-readable
# so copies can be diffed against the canonical source without reading comments —
# the 2026-08-28 drift (8 stale copies, all claiming v1.8.0) was invisible precisely
# because the only version marker was a comment nobody updated.
GUARD_VERSION: str = "1.9.2"

SYSTEM_RESERVE_MB: int = 3_000

OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class VramVerdict:
    ok: bool
    reason: str
    model_name: str
    free_MB: int
    used_MB: int
    total_MB: int
    need_MB: int
    reserve_MB: int
    headroom_MB: int
    already_loaded: bool
    currently_loaded: list[dict[str, Any]] = field(default_factory=list)
    other_processes: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str = ""


class VramGuardFailure(RuntimeError):
    """Raised when guarded_generate cannot proceed due to insufficient VRAM."""

    def __init__(self, verdict: VramVerdict) -> None:
        super().__init__(f"VRAM guard FAIL: {verdict.reason} (free={verdict.free_MB} MB, "
                         f"need={verdict.need_MB} MB, headroom={verdict.headroom_MB} MB)")
        self.verdict = verdict


# ---------------------------------------------------------------------------
# GPU + Ollama probes
# ---------------------------------------------------------------------------
def _run_nvidia_smi(args: list[str]) -> str | None:
    """Run nvidia-smi with utf-8 decode + replace; return stdout str or None on failure.

    Decoded with `errors='replace'` because Windows process names may contain
    non-UTF-8 bytes (CP1251-encoded paths) — `text=True` would crash.
    """
    try:
        r = subprocess.run(
            ["nvidia-smi", *args],
            capture_output=True, timeout=5, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    raw: bytes = r.stdout or b""
    return raw.decode("utf-8", errors="replace")


def query_vram_state() -> dict[str, int]:
    """nvidia-smi --query-gpu memory totals."""
    out = _run_nvidia_smi([
        "--query-gpu=memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    ])
    if out is None:
        # No NVIDIA driver / non-CUDA host: treat as "infinite VRAM" sentinel
        # so guard becomes a no-op rather than blocking everything.
        return {"total_MB": 0, "used_MB": 0, "free_MB": 999_999,
                "_probe_error": "nvidia-smi unavailable"}  # type: ignore[dict-item]
    try:
        total, used, free = (int(x.strip()) for x in out.strip().split(","))
    except (ValueError, AttributeError):
        return {"total_MB": 0, "used_MB": 0, "free_MB": 999_999,
                "_probe_error": f"unparsable nvidia-smi output: {out!r}"}  # type: ignore[dict-item]
    return {"total_MB": total, "used_MB": used, "free_MB": free}


def query_ollama_loaded() -> list[dict[str, Any]]:
    """/api/ps — currently resident models in Ollama."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=3)
        r.raise_for_status()
        return r.json().get("models", [])
    except Exception:  # noqa: BLE001 — broad: probe must never raise
        return []


def unload(model: str, timeout: float = 60) -> None:
    """Explicitly evict `model` from Ollama (keep_alive=0). Best-effort — never raises.

    Use before switching models on a single-model-at-a-time GPU (Codeaudit
    recipe, 2026-08-23: without this, the next model can fail to load on a
    24 GB card while the previous one is still resident on its keep_alive
    timeout). Do NOT call this in a shared-GPU environment against a model
    you didn't load yourself — it can evict a neighbour session's work.
    """
    try:
        import requests
        requests.post(f"{OLLAMA_BASE_URL}/api/generate",
                      json={"model": model, "keep_alive": 0}, timeout=timeout)
    except Exception:  # noqa: BLE001 — best-effort, caller doesn't need this to succeed
        pass


def query_gpu_processes() -> list[dict[str, Any]]:
    """nvidia-smi process listing (PID + name + VRAM used).

    Note: rows with '[Insufficient Permissions]' in the memory field are
    included with mem_MB=0 — they are NOT flagged as errors. This is normal
    when system processes appear in the list without VRAM detail.
    """
    out = _run_nvidia_smi([
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader,nounits",
    ])
    if out is None:
        return []
    procs: list[dict[str, Any]] = []
    for raw in out.strip().splitlines():
        if not raw.strip():
            continue
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            continue
        pid_s, name, mem_s = parts[0], parts[1], parts[2]
        try:
            pid = int(pid_s)
        except ValueError:
            pid = -1
        mem_MB = 0
        if mem_s not in ("[N/A]", "[Insufficient Permissions]", ""):
            try:
                mem_MB = int(mem_s)
            except ValueError:
                mem_MB = 0
        procs.append({"pid": pid, "name": name, "mem_MB": mem_MB})
    return procs


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------
def check_can_load(
    model_name: str,
    *,
    reserve_MB: int = SYSTEM_RESERVE_MB,
    estimate_override_MB: int | None = None,
) -> VramVerdict:
    """Decide if `model_name` can be loaded right now without OOM risk."""
    if model_name in TRIAL_BLOCKED_MODELS:
        return VramVerdict(
            ok=False, reason="blocked_by_trial_policy", model_name=model_name,
            free_MB=0, used_MB=0, total_MB=0, need_MB=0,
            reserve_MB=reserve_MB, headroom_MB=0, already_loaded=False,
            recommendation=(
                f"{model_name} is hard-blocked while the qwen3.6:27b trial is "
                "active (operator decision 2026-08-23) — loading it would evict "
                "the resident trial model. Use qwen3.6:27b, or ask the operator "
                "to lift TRIAL_BLOCKED_MODELS."),
        )
    vram = query_vram_state()
    loaded = query_ollama_loaded()
    procs = query_gpu_processes()

    free_MB = vram["free_MB"]
    used_MB = vram["used_MB"]
    total_MB = vram["total_MB"]

    need_MB = (
        estimate_override_MB
        if estimate_override_MB is not None
        else MODEL_VRAM_ESTIMATE_MB.get(model_name, 10_000)
    )

    # v1.9.2 (2026-08-28, Программист W-019, C-003): size_vram distinguishes
    # "resident on GPU" from "resident on CPU" (size_vram==0). A model that
    # fell to CPU once must NOT be treated as already_loaded forever — that
    # silently pinned it to CPU even after VRAM freed up. CPU-resident falls
    # through to the ordinary headroom check below, same as not-loaded.
    already_loaded_gpu = any(
        m.get("name") == model_name and m.get("size_vram", 0) > 0
        for m in loaded
    )
    headroom_MB = free_MB - reserve_MB

    if already_loaded_gpu:
        return VramVerdict(
            ok=True, reason="already_loaded", model_name=model_name,
            free_MB=free_MB, used_MB=used_MB, total_MB=total_MB,
            need_MB=0, reserve_MB=reserve_MB, headroom_MB=headroom_MB,
            already_loaded=True, currently_loaded=loaded, other_processes=procs,
            recommendation="proceed",
        )

    if headroom_MB >= need_MB:
        return VramVerdict(
            ok=True, reason="sufficient_headroom", model_name=model_name,
            free_MB=free_MB, used_MB=used_MB, total_MB=total_MB,
            need_MB=need_MB, reserve_MB=reserve_MB, headroom_MB=headroom_MB,
            already_loaded=False, currently_loaded=loaded, other_processes=procs,
            recommendation="proceed",
        )

    # FAIL — diagnose why and recommend an action.
    others_MB = sum(p["mem_MB"] for p in procs)
    competing_ollama = [m for m in loaded if m.get("name") != model_name]
    if competing_ollama:
        rec = (f"Wait for Ollama models {[m['name'] for m in competing_ollama]} "
               f"to unload (keep_alive timeout) OR `curl -X POST {OLLAMA_BASE_URL}/api/generate "
               f"-d '{{\"model\":\"<name>\",\"keep_alive\":0}}'` to force unload.")
    elif others_MB > need_MB:
        rec = (f"Non-Ollama processes hold {others_MB} MB VRAM "
               f"(top: {sorted(procs, key=lambda p: -p['mem_MB'])[:3]}). "
               "Wait or kill conflicting process.")
    else:
        rec = (f"Insufficient VRAM ({free_MB} MB free, {need_MB} MB needed, "
               f"{reserve_MB} MB reserved for system). Consider a smaller model "
               "or fall back to Claude for this task.")

    reason = (
        "insufficient_vram_competing_ollama" if competing_ollama
        else "insufficient_vram_other_processes" if others_MB > need_MB
        else "insufficient_vram_absolute"
    )
    return VramVerdict(
        ok=False, reason=reason, model_name=model_name,
        free_MB=free_MB, used_MB=used_MB, total_MB=total_MB,
        need_MB=need_MB, reserve_MB=reserve_MB, headroom_MB=headroom_MB,
        already_loaded=False, currently_loaded=loaded, other_processes=procs,
        recommendation=rec,
    )


def wait_until_can_load(
    model_name: str,
    *,
    max_wait_s: float = 120.0,
    poll_s: float = 5.0,
    reserve_MB: int = SYSTEM_RESERVE_MB,
) -> VramVerdict:
    """Poll check_can_load until OK or timeout."""
    waited = 0.0
    last: VramVerdict | None = None
    while waited <= max_wait_s:
        v = check_can_load(model_name, reserve_MB=reserve_MB)
        if v.ok:
            return v
        last = v
        time.sleep(poll_s)
        waited += poll_s
    # Timed out — return the last seen verdict marked with timeout reason.
    if last is None:
        last = check_can_load(model_name, reserve_MB=reserve_MB)
    last.reason = f"timeout_after_{int(max_wait_s)}s_with_{last.reason}"
    last.recommendation = (f"Waited {int(max_wait_s)}s, VRAM did not free up. "
                           + last.recommendation)
    return last


# ---------------------------------------------------------------------------
# Cross-chat VRAM queue (machine-global, NOT project-local)         [v1.8.0]
#
# Rationale: Ollama at 127.0.0.1:11434 is a shared host resource across all
# Claude Code sessions, project subagents, and ad-hoc Python scripts. A
# project-local queue would not see neighbour-chat tickets and could let
# two waiters both think they are first-in-line.
#
# Storage: %LOCALAPPDATA%/ollama-vram-queue/ (Windows) or
#          $XDG_CACHE_HOME/ollama-vram-queue/ (POSIX, falls back to ~/.cache).
#
# Atomicity model
# ---------------
#   * Ticket creation: write tmp file, os.replace → atomic on NTFS & POSIX.
#   * Heartbeat touch: pathlib.Path.touch() (atomic O_CREAT|O_WRONLY).
#   * Scan: read-only glob, no locking.
#   * Stale cleanup: try/except FileNotFoundError, race-tolerant.
# No fcntl/msvcrt advisory locks needed — each waiter owns its own files.
#
# Anti-patterns (FORBIDDEN — documented to keep them out of refactors)
# -------------------------------------------------------------------
#   * NEVER kill a foreign ticket whose heartbeat is fresh (< 60 s old) — a
#     neighbour-chat waiter may be 1 second from passing.
#   * NEVER terminate a foreign PID. We do not own neighbour processes;
#     killing them breaks the user's other Claude sessions / scripts.
#   * Only TTL-expired tickets (heartbeat missing OR mtime > 60 s) are
#     deleted, and only as best-effort cleanup.
#
# Priority classes (recommended by role)
# --------------------------------------
#   orchestrator  = 100   (main Claude loop; blocks user dialog)
#   subagent      =  50   (default; background worker)
#   batch         =  10   (background sweep; lowest priority)
# ---------------------------------------------------------------------------
_QUEUE_HEARTBEAT_TTL_S: int = 60
_QUEUE_POLL_S: float = 5.0
_QUEUE_DROP_OUT_AFTER_S: float = 120.0
_QUEUE_DROP_OUT_POSITION: int = 2  # if my_pos > 2, fall back to CPU


def _queue_dir() -> pathlib.Path:
    """Locate (and create) the machine-global queue directory."""
    if os.name == "nt":
        base = pathlib.Path(os.environ.get("LOCALAPPDATA")
                            or os.environ.get("TEMP")
                            or os.path.expanduser("~"))
    else:
        base = pathlib.Path(os.environ.get("XDG_CACHE_HOME")
                            or os.path.expanduser("~/.cache"))
    d = base / "ollama-vram-queue"
    (d / "tickets").mkdir(parents=True, exist_ok=True)
    (d / "heartbeats").mkdir(parents=True, exist_ok=True)
    return d


def _utc_iso_compact() -> str:
    """ISO-8601 UTC timestamp safe for filenames: 2026-06-04T12-24-18Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _ticket_filename(created_at: str, priority: int, ticket_id: str) -> str:
    # Inverted priority key so lexicographic ASC sort = priority DESC, time ASC.
    # e.g. priority=100 → 899, priority=50 → 949, priority=10 → 989.
    inv = 999 - max(0, min(999, int(priority)))
    return f"{inv:03d}_{created_at}_{ticket_id}.json"


def _parse_ticket_filename(name: str) -> dict[str, Any] | None:
    """Return {inv_prio, created_at, id} or None if unparsable."""
    if not name.endswith(".json"):
        return None
    stem = name[:-5]
    parts = stem.split("_", 2)
    if len(parts) != 3:
        return None
    try:
        inv = int(parts[0])
    except ValueError:
        return None
    return {"inv_prio": inv, "created_at": parts[1], "id": parts[2],
            "priority": 999 - inv}


def _create_ticket(model: str, priority: int, estimated_mb: int,
                   max_wait_s: int, project: str, agent: str) -> dict[str, Any]:
    """Write a ticket file atomically and return its metadata."""
    qdir = _queue_dir()
    ticket_id = uuid.uuid4().hex[:8]
    created_at = _utc_iso_compact()
    body = {
        "id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "priority": priority,
        "model": model,
        "estimated_mb": estimated_mb,
        "project": project,
        "agent": agent,
        "pid": os.getpid(),
        "max_wait_s": max_wait_s,
    }
    fname = _ticket_filename(created_at, priority, ticket_id)
    tickets_dir = qdir / "tickets"
    tmp = tickets_dir / f".{fname}.tmp"
    final = tickets_dir / fname
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, final)
    _touch_heartbeat(ticket_id)
    return {"id": ticket_id, "filename": fname, "path": final, "body": body}


def _touch_heartbeat(ticket_id: str) -> None:
    """Update the heartbeat mtime for `ticket_id` (creates file if missing)."""
    hb = _queue_dir() / "heartbeats" / f"{ticket_id}.ts"
    try:
        hb.touch(exist_ok=True)
    except OSError:
        pass


def _heartbeat_age_s(ticket_id: str) -> float | None:
    """Return age in seconds, or None if the heartbeat file is missing."""
    hb = _queue_dir() / "heartbeats" / f"{ticket_id}.ts"
    try:
        mtime = hb.stat().st_mtime
    except FileNotFoundError:
        return None
    return max(0.0, time.time() - mtime)


def _delete_ticket(ticket_id: str, filename: str | None = None) -> None:
    """Best-effort delete of ticket + heartbeat files (race-tolerant)."""
    qdir = _queue_dir()
    if filename is None:
        # Scan tickets/ for matching id (slow path; only for legacy callers).
        for p in (qdir / "tickets").glob(f"*_{ticket_id}.json"):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    else:
        try:
            (qdir / "tickets" / filename).unlink()
        except FileNotFoundError:
            pass
    try:
        (qdir / "heartbeats" / f"{ticket_id}.ts").unlink()
    except FileNotFoundError:
        pass


def _scan_live_tickets() -> list[dict[str, Any]]:
    """
    Return all queue tickets sorted by (priority DESC, created_at ASC),
    filtering out tickets whose heartbeat is missing OR > TTL old.

    Side-effect: best-effort cleanup of TTL-expired tickets (NEVER touches
    tickets with a fresh heartbeat — those belong to other chats / processes).

    Anti-pattern guard: stale cleanup ONLY deletes the file; it NEVER
    terminates the foreign PID stored in the ticket body.
    """
    qdir = _queue_dir()
    rows: list[dict[str, Any]] = []
    for p in (qdir / "tickets").glob("*.json"):
        meta = _parse_ticket_filename(p.name)
        if meta is None:
            continue
        age = _heartbeat_age_s(meta["id"])
        if age is None or age > _QUEUE_HEARTBEAT_TTL_S:
            # TTL-expired — safe to clean. We do NOT kill the foreign PID,
            # we only remove the stale ticket file (best-effort).
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            try:
                (qdir / "heartbeats" / f"{meta['id']}.ts").unlink()
            except FileNotFoundError:
                pass
            continue
        meta["filename"] = p.name
        meta["path"] = str(p)
        rows.append(meta)
    # Filenames already encode (inv_prio, created_at) — a lexicographic sort
    # of `filename` is equivalent to (priority DESC, created_at ASC).
    rows.sort(key=lambda r: r["filename"])
    return rows


def wait_in_queue(
    model: str,
    *,
    priority: int = 50,
    max_wait_s: int = 600,
    reserve_MB: int = SYSTEM_RESERVE_MB,
    estimate_override_MB: int | None = None,
    project: str = "unknown",
    agent: str = "subagent",
    poll_s: float = _QUEUE_POLL_S,
    drop_out_after_s: float = _QUEUE_DROP_OUT_AFTER_S,
    drop_out_position: int = _QUEUE_DROP_OUT_POSITION,
) -> VramVerdict:
    """
    Enter the cross-chat VRAM queue and wait until first-in-line + VRAM-OK.

    Priority classes (recommended):
      orchestrator = 100  (main loop; blocks user dialog)
      subagent     =  50  (default; background worker)
      batch        =  10  (low-priority sweep)

    Returns:
      VramVerdict(ok=True,  reason='queue_passed_first_in_line')    → run GPU
      VramVerdict(ok=False, reason='queue_drop_out_cpu_recommended') → try CPU
      VramVerdict(ok=False, reason='queue_timeout_cpu_recommended')  → try CPU

    Drop-out triggers:
      - queue position > drop_out_position (default 2)
      - elapsed > drop_out_after_s (default 120 s)
      - elapsed > max_wait_s (hard timeout)

    Anti-pattern guards (enforced by this function's code path):
      - NEVER kill foreign PIDs: _scan_live_tickets() only deletes stale files.
      - NEVER delete a ticket with a fresh heartbeat (< TTL_S = 60 s).
    """
    need_MB = (estimate_override_MB
               if estimate_override_MB is not None
               else MODEL_VRAM_ESTIMATE_MB.get(model, 10_000))
    ticket = _create_ticket(model, priority, need_MB, max_wait_s, project, agent)
    ticket_id = ticket["id"]
    ticket_fname = ticket["filename"]
    start = time.monotonic()
    try:
        while True:
            elapsed = time.monotonic() - start
            # Heartbeat must be touched every poll cycle to signal liveness.
            _touch_heartbeat(ticket_id)
            live = _scan_live_tickets()
            my_pos = next((i for i, r in enumerate(live) if r["id"] == ticket_id), None)
            if my_pos is None:
                # Our heartbeat lapsed or another process garbage-collected us.
                # Re-create silently and continue.
                ticket = _create_ticket(model, priority, need_MB, max_wait_s,
                                        project, agent)
                ticket_id = ticket["id"]
                ticket_fname = ticket["filename"]
                continue

            verdict = check_can_load(model, reserve_MB=reserve_MB,
                                     estimate_override_MB=estimate_override_MB)

            # First-in-line + VRAM available → pass.
            if my_pos == 0 and verdict.ok:
                verdict.reason = "queue_passed_first_in_line"
                verdict.recommendation = (
                    f"Queue position 0/{len(live)} after {elapsed:.0f}s; proceed on GPU.")
                return verdict

            # Drop-out triggers — fall back to CPU at caller.
            if my_pos > drop_out_position:
                verdict.ok = False
                verdict.reason = "queue_drop_out_cpu_recommended"
                verdict.recommendation = (
                    f"Queue position {my_pos}/{len(live)} > {drop_out_position} "
                    f"after {elapsed:.0f}s; recommend CPU fallback.")
                return verdict
            if elapsed > drop_out_after_s:
                verdict.ok = False
                verdict.reason = "queue_drop_out_cpu_recommended"
                verdict.recommendation = (
                    f"Waited {elapsed:.0f}s > {drop_out_after_s:.0f}s threshold "
                    f"at position {my_pos}/{len(live)}; recommend CPU fallback.")
                return verdict
            if elapsed > max_wait_s:
                verdict.ok = False
                verdict.reason = "queue_timeout_cpu_recommended"
                verdict.recommendation = (
                    f"Exhausted max_wait_s={max_wait_s}s at position "
                    f"{my_pos}/{len(live)}; recommend CPU fallback.")
                return verdict

            time.sleep(poll_s)
    finally:
        # Ticket is always cleaned up on exit, including on exception.
        _delete_ticket(ticket_id, ticket_fname)


# ---------------------------------------------------------------------------
# CPU fallback (num_gpu=0)                                           [v1.8.0]
# ---------------------------------------------------------------------------
def _available_ram_gb() -> float:
    """
    Return system RAM available in GB. Uses psutil if installed; otherwise
    falls back to ctypes (GlobalMemoryStatusEx on Windows) or /proc/meminfo
    on Linux. Returns -1.0 if undetectable (caller treats as 'unknown OK').
    """
    try:
        import psutil  # type: ignore
        return psutil.virtual_memory().available / (1024 ** 3)
    except ImportError:
        pass
    if os.name == "nt":
        try:
            import ctypes
            class _MEMSTATEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = _MEMSTATEX()
            stat.dwLength = ctypes.sizeof(_MEMSTATEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullAvailPhys / (1024 ** 3)
        except Exception:  # noqa: BLE001 — best effort
            return -1.0
    # POSIX best-effort
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / (1024 ** 2)
    except OSError:
        pass
    return -1.0


def _warn_if_truncated(result: dict[str, Any], model: str) -> None:
    """v1.9.1 (2026-08-23, P-002): surface Ollama's own truncation signal.
    done_reason != "stop" means the response was cut off (num_ctx/num_predict
    limit), not the model choosing to stop — otherwise invisible to the caller.
    """
    reason = result.get("done_reason")
    if reason and reason != "stop":
        print(f"[vram_guard] WARNING: {model} generation truncated, "
              f"done_reason={reason!r} (likely num_ctx/num_predict limit) — "
              f"response is probably incomplete", file=sys.stderr)


def try_cpu(
    model: str,
    prompt: str,
    *,
    fmt: str | None = "json",
    temperature: float = 0.0,
    num_ctx: int = 32_768,
    gpu_timeout_s: int = 300,
    cpu_timeout_multiplier: int = 5,
    extra_options: dict[str, Any] | None = None,
    think: bool | None = None,
    keep_alive: int | str | None = None,
    num_predict: int | None = None,
) -> dict[str, Any]:
    """
    Run an Ollama /api/generate call in CPU mode (num_gpu=0).

    RAM check: if available system RAM < MODEL_RAM_ESTIMATE_GB[model] +
    CPU_OS_RESERVE_GB, raises VramGuardFailure — caller should fall back
    to Claude. If RAM is undetectable (avail_gb = -1.0), mode is accepted
    permissively (trust the caller).

    Timeout: cpu_timeout_multiplier * gpu_timeout_s (default 5x = 1500 s)
    because CPU inference is ~5-10x slower than GPU.
    """
    if model in TRIAL_BLOCKED_MODELS:
        verdict = VramVerdict(
            ok=False, reason="blocked_by_trial_policy", model_name=model,
            free_MB=0, used_MB=0, total_MB=0, need_MB=0, reserve_MB=0,
            headroom_MB=0, already_loaded=False,
            recommendation=f"{model} is hard-blocked during the qwen3.6:27b trial (2026-08-23).")
        raise VramGuardFailure(verdict)
    avail_gb = _available_ram_gb()
    need_gb = MODEL_RAM_ESTIMATE_GB.get(model, 18)
    reserve_gb = CPU_OS_RESERVE_GB

    if avail_gb >= 0 and avail_gb < (need_gb + reserve_gb):
        verdict = VramVerdict(
            ok=False, reason="insufficient_ram_for_cpu",
            model_name=model, free_MB=0, used_MB=0, total_MB=0,
            need_MB=(need_gb + reserve_gb) * 1024,
            reserve_MB=reserve_gb * 1024,
            headroom_MB=int(avail_gb * 1024),
            already_loaded=False,
            recommendation=(
                f"avail={avail_gb:.1f} GB RAM, need={need_gb}+{reserve_gb} GB. "
                "Fall back to Claude."),
        )
        raise VramGuardFailure(verdict)

    import requests  # lazy
    options: dict[str, Any] = {
        "temperature": temperature,
        "num_ctx": num_ctx,
        "num_gpu": 0,  # force pure-CPU inference — anti-pattern: do NOT remove this
    }
    if extra_options:
        # Caller options win EXCEPT num_gpu which we hard-pin to 0.
        merged = {**extra_options, **options}
        options = merged
    effective_num_predict = num_predict if num_predict is not None else MODEL_NUM_PREDICT_CAP.get(model)
    if effective_num_predict is not None:
        options["num_predict"] = effective_num_predict
    payload: dict[str, Any] = {
        "model": model, "prompt": prompt, "stream": False, "options": options,
    }
    if fmt:
        payload["format"] = fmt
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    # v1.9.1: auto-guard thinking models on EVERY call (not just fmt=="json") —
    # see THINKING_CAPABLE_MODELS for the two measured failure modes.
    # Caller-supplied `think` always wins.
    effective_think = think
    if effective_think is None and model in THINKING_CAPABLE_MODELS:
        effective_think = False
    if effective_think is not None:
        payload["think"] = effective_think
    cpu_timeout = gpu_timeout_s * cpu_timeout_multiplier
    r = requests.post(f"{OLLAMA_BASE_URL}/api/generate",
                      json=payload, timeout=cpu_timeout)
    r.raise_for_status()
    result = r.json()
    _warn_if_truncated(result, model)
    return result


# ---------------------------------------------------------------------------
# Guarded generate — three-tier (GPU direct → queue → CPU)          [v1.8.0]
# ---------------------------------------------------------------------------
def guarded_generate(
    model: str,
    prompt: str,
    *,
    # Three-tier kwargs (v1.8.0)
    want_gpu: bool = True,
    priority: int = 50,
    max_wait_s: int = 600,
    gpu_timeout_s: int | None = None,
    cpu_timeout_multiplier: int = 5,
    project: str = "unknown",
    agent: str = "subagent",
    # Backward-compat kwargs (pre-v1.8.0 API)
    fmt: str | None = "json",
    temperature: float = 0.0,
    num_ctx: int = 32_768,
    timeout_s: int = 600,
    wait_max_s: float | None = None,
    reserve_MB: int = SYSTEM_RESERVE_MB,
    extra_options: dict[str, Any] | None = None,
    estimate_override_MB: int | None = None,
    return_mode: bool = False,
    # v1.9.0: thinking-model support (2026-08-23)
    think: bool | None = None,
    keep_alive: int | str | None = None,
    num_predict: int | None = None,
) -> "dict[str, Any] | tuple[dict[str, Any], Literal['gpu', 'cpu']]":
    """
    Two-tier fallback for `requests.post('/api/generate', ...)` (CPU tier
    REMOVED 2026-08-28, operator instruction "проц запрещён" / "оллама
    только гпу" — see try_cpu() below, kept for explicit manual use only):

      Tier 1 (GPU direct): check_can_load → if OK, call /api/generate on GPU.
      Tier 2 (queue):      if GPU busy AND want_gpu=True, enter cross-chat queue.
                           First-in-line + VRAM free → GPU.
      Tier 3 (Claude):     not handled here — raises VramGuardFailure when
                           GPU is unavailable after tiers 1-2; caller falls
                           back to Claude / retries / raises priority.

    Priority classes:
      orchestrator = 100  (main loop; blocks user dialog)
      subagent     =  50  (default)
      batch        =  10  (low-priority sweep)

    Backward compatibility
    ----------------------
    * Old signature (`wait_max_s=...`, `timeout_s=...`) still works.
    * Default `return_mode=False` returns the raw response dict (old behaviour).
    * `return_mode=True` returns `(response, mode)` where mode in {'gpu','cpu'}.
    * `want_gpu=False` skips Tier 1/2 entirely (straight to CPU).

    Raises
    ------
    VramGuardFailure when CPU RAM is also insufficient.
    """
    # Reconcile legacy `wait_max_s` (float) vs new `max_wait_s` (int).
    if wait_max_s is not None:
        max_wait_s = int(wait_max_s)
    if gpu_timeout_s is None:
        gpu_timeout_s = timeout_s

    import requests  # lazy

    def _gpu_call() -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": temperature, "num_ctx": num_ctx}
        if extra_options:
            options.update(extra_options)
        effective_num_predict = num_predict if num_predict is not None else MODEL_NUM_PREDICT_CAP.get(model)
        if effective_num_predict is not None:
            options["num_predict"] = effective_num_predict
        payload: dict[str, Any] = {
            "model": model, "prompt": prompt, "stream": False, "options": options,
        }
        if fmt:
            payload["format"] = fmt
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        # v1.9.1 thinking-model auto-guard — see try_cpu() above / SKILL_VRAM_GUARD.md
        effective_think = think
        if effective_think is None and model in THINKING_CAPABLE_MODELS:
            effective_think = False
        if effective_think is not None:
            payload["think"] = effective_think
        r = requests.post(f"{OLLAMA_BASE_URL}/api/generate",
                          json=payload, timeout=gpu_timeout_s)
        r.raise_for_status()
        result = r.json()
        _warn_if_truncated(result, model)
        return result

    mode: Literal["gpu", "cpu"] = "gpu"

    if want_gpu:
        # Tier 1: GPU direct.
        verdict = check_can_load(model, reserve_MB=reserve_MB,
                                 estimate_override_MB=estimate_override_MB)
        if verdict.ok:
            resp = _gpu_call()
            return (resp, "gpu") if return_mode else resp

        # Tier 2: cross-chat queue (only if any wait budget exists).
        if max_wait_s > 0:
            q = wait_in_queue(
                model, priority=priority, max_wait_s=max_wait_s,
                reserve_MB=reserve_MB, estimate_override_MB=estimate_override_MB,
                project=project, agent=agent,
            )
            if q.ok:
                resp = _gpu_call()
                return (resp, "gpu") if return_mode else resp
            # Queue gave up waiting for GPU headroom.
            verdict = q
    else:
        verdict = check_can_load(model, reserve_MB=reserve_MB,
                                 estimate_override_MB=estimate_override_MB)

    # CPU inference is DISABLED per operator instruction 2026-08-28
    # ("проц запрещён" / "оллама только гпу"). try_cpu() is kept below for
    # explicit manual use only — guarded_generate() never falls back to it
    # on its own. Caller must handle VramGuardFailure (retry, raise queue
    # priority, or escalate to Claude).
    raise VramGuardFailure(verdict)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _emit(verdict: VramVerdict) -> None:
    print(json.dumps(asdict(verdict), ensure_ascii=False, indent=2))


def _watch(model: str | None, poll_s: float, reserve_MB: int) -> None:
    target = model or "qwen3-coder:30b"
    try:
        while True:
            v = check_can_load(target, reserve_MB=reserve_MB)
            status = "OK " if v.ok else "FAIL"
            print(f"[{time.strftime('%H:%M:%S')}] {status}  "
                  f"free={v.free_MB:>5} MB  used={v.used_MB:>5} MB  "
                  f"need={v.need_MB:>5} MB  headroom={v.headroom_MB:>5} MB  "
                  f"loaded={[m.get('name') for m in v.currently_loaded]}  "
                  f"reason={v.reason}", flush=True)
            time.sleep(poll_s)
    except KeyboardInterrupt:
        sys.stderr.write("\n[stopped]\n")


def main() -> int:
    p = argparse.ArgumentParser(description=f"Ollama VRAM pre-flight guard (v{GUARD_VERSION})")
    p.add_argument("--version", action="store_true",
                   help="print GUARD_VERSION and exit (use to diff copies against canonical)")
    p.add_argument("--check", metavar="MODEL", help="check a specific model")
    p.add_argument("--wait", type=float, default=0.0,
                   help="poll up to N seconds for free VRAM (default: 0 = fail-fast)")
    p.add_argument("--watch", action="store_true", help="continuous status monitor")
    p.add_argument("--poll-s", type=float, default=5.0, help="polling interval for --watch / --wait")
    p.add_argument("--reserve-MB", type=int, default=SYSTEM_RESERVE_MB,
                   help=f"system reserve in MB (default {SYSTEM_RESERVE_MB})")
    args = p.parse_args()

    if args.version:
        print(GUARD_VERSION)
        return 0

    if args.watch:
        _watch(args.check, args.poll_s, args.reserve_MB)
        return 0

    target = args.check or "qwen3-coder:30b"
    if args.wait > 0:
        verdict = wait_until_can_load(target, max_wait_s=args.wait,
                                      poll_s=args.poll_s, reserve_MB=args.reserve_MB)
    else:
        verdict = check_can_load(target, reserve_MB=args.reserve_MB)
    _emit(verdict)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
