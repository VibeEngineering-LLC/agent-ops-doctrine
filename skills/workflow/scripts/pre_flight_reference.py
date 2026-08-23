# Reference implementation of Ollama pre-flight check.
# Consuming projects MAY copy verbatim to <project>/scripts/ollama/_lib/pre_flight.py
# or <project>/audit/_drafts/_ollama_helpers/_lib/pre_flight.py
#
# Source: gamma-spectrum-analysis audit/_drafts/_ollama_helpers/_lib/pre_flight.py
# Shipped in workflow-skill v1.5.0 for discoverability.
"""Pre-flight check for Ollama availability (HTTP + VRAM).

Lightweight, non-blocking. Returns context dict; caller decides whether
to STOP / fallback / continue with warning. Used by heavy helpers
(math/archive 128k profiles) and batch loops.

Usage example::

    from pre_flight_reference import ollama_pre_flight

    pre = ollama_pre_flight('qwen3-coder:30b', min_vram_gb=14.0)
    if not pre['ok']:
        import sys, json
        print(json.dumps({'_error': f'pre_flight_failed: {pre["reason"]}',
                          '_pre_flight': pre}), file=sys.stderr)
        sys.exit(1)
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict

import requests


# Per-profile minimum free VRAM (GB) required if model is NOT already loaded.
# math/archive 128k -> ~24 GB total allocated; leaving ~14 GB headroom for
# other system use keeps us VRAM-only (no CPU offload on RTX 4090).
# guard/forge-large 64k -> ~22 GB total; 10 GB headroom threshold is conservative.
# forge 32k -> overhead is acceptable without a VRAM gate (0 = skip check).
PROFILE_MIN_VRAM_GB: Dict[str, float] = {
    "forge":       0.0,
    "forge-large": 10.0,
    "guard":       10.0,
    "math":        14.0,
    "archive":     14.0,
}


def ollama_pre_flight(
    model: str,
    min_vram_gb: float,
    endpoint: str = "http://127.0.0.1:11434",
    timeout_s: int = 3,
) -> Dict[str, Any]:
    """Check Ollama server health and free VRAM before a heavy generate call.

    Args:
        model: model name to check (e.g. 'qwen3-coder:30b').
        min_vram_gb: minimum free VRAM required if model NOT already loaded.
                     Suggested: math/archive 128k -> 14.0; guard/forge-large 64k -> 10.0.
                     Use 0.0 to skip the VRAM check (forge 32k).
        endpoint: Ollama base URL.
        timeout_s: HTTP timeout for /api/ps probe.

    Returns:
        {
          'ok': bool,
          'reason': str,                  # 'ready' | 'ollama_down: ...' | 'low_vram: ...'
          'vram_free_gb': float | None,   # None if nvidia-smi unavailable
          'loaded': list[str],            # names of currently loaded models
          'model_already_loaded': bool,   # if True, low_vram check is skipped
        }
    """
    # 1. HTTP /api/ps -- is Ollama up?
    try:
        ps_resp = requests.get(f"{endpoint}/api/ps", timeout=timeout_s)
        ps_resp.raise_for_status()
        ps = ps_resp.json()
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "reason": f"ollama_down: {type(e).__name__}: {e}",
            "vram_free_gb": None,
            "loaded": [],
            "model_already_loaded": False,
        }

    loaded = [m.get("name", "") for m in ps.get("models", [])]
    model_already_loaded = any(model in name for name in loaded)

    # 2. nvidia-smi -- free VRAM (skip check if model already in VRAM or min == 0)
    vram_free_gb: float | None = None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            timeout=2,
            text=True,
        ).strip()
        # nvidia-smi may report several GPUs; we use the first (RTX 4090 on this host)
        first_line = out.splitlines()[0].strip()
        vram_free_gb = float(first_line) / 1024.0
    except Exception:  # noqa: BLE001
        # nvidia-smi unavailable -- do NOT block, just report None
        vram_free_gb = None

    if (
        vram_free_gb is not None
        and min_vram_gb > 0.0
        and not model_already_loaded
        and vram_free_gb < min_vram_gb
    ):
        return {
            "ok": False,
            "reason": f"low_vram: {vram_free_gb:.1f}GB free < required {min_vram_gb}GB",
            "vram_free_gb": vram_free_gb,
            "loaded": loaded,
            "model_already_loaded": False,
        }

    return {
        "ok": True,
        "reason": "ready",
        "vram_free_gb": vram_free_gb,
        "loaded": loaded,
        "model_already_loaded": model_already_loaded,
    }
