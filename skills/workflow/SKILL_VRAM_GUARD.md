# SKILL reference — VRAM guard & three-tier Ollama fallback

> Reference material split out of `SKILL.md` (T-16) to keep the skill
> dispatcher thin. Loaded on demand when a helper needs the full VRAM-guard
> / queue / CPU-fallback details. The canonical implementation lives in
> `scripts/vram_guard_reference.py`.

### Pre-flight check — two-layer VRAM guard

Before invoking Ollama, helper scripts should verify resource availability to fail-fast
rather than silently OOM or fall back to CPU with a 10× slowdown.

Two complementary layers, used together:

#### Layer 1 — coarse profile guard (`_lib/pre_flight.py`)

Per-profile minimum-free-VRAM threshold. Cheap, sufficient when the script already knows
its profile (forge/guard/math/archive).

**Pattern** (reference implementation: gamma-spectrum-analysis `audit/_drafts/_ollama_helpers/_lib/pre_flight.py`):

1. HTTP `GET /api/ps` → list models currently loaded in VRAM.
2. `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` → free VRAM in MB.
3. If `model_already_loaded` → skip VRAM check (will reuse).
4. Else require `vram_free_gb >= PROFILE_MIN_VRAM_GB[profile]`:
   - `forge` (32k): 0 GB (CPU fallback acceptable)
   - `forge-large` / `guard` (64k): 10 GB
   - `math` / `archive` (128k): 14 GB
5. Return `{ok: bool, reason: str, vram_free_gb: float, loaded: bool, model_already_loaded: bool}`.

**When to use Layer 1**:
- MANDATORY for math/archive 128k profile invocations.
- RECOMMENDED for batch loops (>5 sequential Ollama calls).
- SKIP for routine forge (32k) single-shot calls.

#### Layer 2 — fine per-model guard (`_vram_guard.py`)

Per-model VRAM estimate + **system reserve** subtracted from free VRAM, with **neighbour-process
diagnosis** (distinguishes "another Ollama model holds VRAM" from "non-Ollama GPU process holds VRAM"
from "absolute shortage"). Added 2026-06-04 after a verified field incident: a neighbour session's
`qwen2.5vl:7b` + `qwen3-coder:30b` together exceeded 24 GB RTX 4090, causing three dispatched
subagents to return 0-byte outputs (silent OOM during `/api/generate`).

**Pattern** (reference implementation: gamma-spectrum-analysis `audit/_drafts/_ollama_helpers/_vram_guard.py`):

1. Probe free/used/total VRAM via `nvidia-smi --query-gpu=memory.{total,used,free}`.
2. Probe currently-loaded Ollama models via `GET /api/ps`.
3. Probe non-Ollama GPU processes via `nvidia-smi --query-compute-apps=pid,process_name,used_memory`.
4. Look up `MODEL_VRAM_ESTIMATE_MB[model]` (defaults calibrated for **forge profile 32k**;
   pass `estimate_override_MB=` for larger contexts).
5. Decide: `headroom_MB = free_MB - SYSTEM_RESERVE_MB`; need `headroom_MB >= need_MB`.
6. Return `VramVerdict` with `ok`, `reason` (one of `already_loaded` / `sufficient_headroom` /
   `insufficient_vram_competing_ollama` / `insufficient_vram_other_processes` /
   `insufficient_vram_absolute`), `recommendation` (actionable next step), plus the raw probe data.

**Defaults** (RTX 4090, 24 GB VRAM, Windows host with DWM + browser + Python):

| Constant | Value | Rationale |
|---|---:|---|
| `SYSTEM_RESERVE_MB` | 3 000 | OS compositor (~1-1.5 GB) + browser GPU (~0.5-1 GB) + ~1 GB generative slack (KV growth mid-call, allocator fragmentation) |
| `MODEL_VRAM_ESTIMATE_MB["qwen3-coder:30b"]` | 17 500 | 30.5B Q4_K_M (~17.9 GB weights) + small MoE KV at 32k ≈ 17.5 GB resident. Override to ~22 500 for math 128k q8_0. |
| `MODEL_VRAM_ESTIMATE_MB["qwen3.6:27b"]` | 17 800 | 27.8B Q4_K_M dense; measured resident 2026-08-22/23 (LLM contour + Codeaudit bench, both @ 32k). |
| `MODEL_VRAM_ESTIMATE_MB["qwen2.5vl:7b"]` | 7 000 | Vision-language; measured |
| `MODEL_VRAM_ESTIMATE_MB["bge-m3:latest"]` | 1 500 | Embedding |

**API**:
- `check_can_load(model) -> VramVerdict` — one-shot decision.
- `guarded_generate(model, prompt, **kwargs)` — drop-in for `requests.post('/api/generate')`
  that raises `VramGuardFailure` on FAIL (caller can `except VramGuardFailure` and fall back to Claude / a smaller model).
- `wait_until_can_load(model, max_wait_s=120, poll_s=5)` — poll-and-retry variant for batch loops.
- CLI: `python _vram_guard.py --check <model>` (exit 1 on FAIL, structured JSON to stdout),
  `--watch` (continuous monitor), `--wait <sec>` (poll-and-emit).

### Thinking models — `think` parameter (added v1.9.0, 2026-08-23)

**Incident**: thinking-capable models (`qwen3.6:27b`, formerly also `qwen3.6:latest`) put their
answer in Ollama's `thinking` response field, not `response`, whenever reasoning triggers —
`format="json"` triggers it every time. A caller reading only `response` gets `""` back with
`done=true` — a **silent failure**, no exception, no non-zero exit. Found independently by the
Цензор contour (`_interchat` letter 2026-08-23) and reproduced by the LLM contour.

**Second failure mode, found 2026-08-23 evening (LLM contour P-002 / W-004)**: on long codegen
(`fmt=None`) reasoning eats the `num_predict` budget and the output is cut off mid-function with
`done_reason="length"` — again with no exception. Measured, same prompt and budget on
`qwen3.6:27b`: think on → 19 347 chars of thinking, 3 891 chars of code, TRUNCATED; think off →
0 thinking, 10 236 chars of code, `done_reason="stop"`. The v1.9.0 fix below did **not** cover
this because it was scoped to `fmt=="json"`, the form the bug was first seen in.

**Fix**: `guarded_generate()` accepts `think: bool | None = None`. When the caller leaves it
unset AND `model` is in `THINKING_CAPABLE_MODELS`, the guard auto-sets `think=False` before
building the payload — **on every call, regardless of `fmt`** (widened in v1.9.1; it was
`fmt=="json"` only in v1.9.0). Rationale: `guarded_generate()` exists to delegate mechanical
work; reasoning is not what it is for, and callers who genuinely want it say so explicitly.
This is the exact recipe independently verified by
the Codeaudit contour (`hard_bench_text.py`, 26 calls, 0 load failures) and by a direct repro on
clean VRAM (LLM contour, 2026-08-23, `qwen3.6:27b`, 10.5 s, correct JSON). An earlier claim that
`think=False` breaks model loading (`CUDA_Host buffer allocation failed`) did **not** reproduce on
retest — recorded as LLM contour `work-incidents.md` W-002, do not resurrect that workaround.

Callers may still pass `think=True`/`False` explicitly to override the auto-guard (e.g. force it
on for a call where reasoning quality matters more than the ~10-40× time cost and the truncation
risk — if you do, raise `num_predict` accordingly).

### Truncation warning (v1.9.1, 2026-08-23)

Ollama reports `done_reason` on every `/api/generate` response; anything other than `"stop"`
means the output was **cut off**, not finished. Both call paths (`_gpu_call` and `try_cpu`) now
run `_warn_if_truncated()`, which prints a stderr warning naming the model and reason. Callers
that write the result somewhere should check `done_reason` themselves and refuse to save a
truncated body — `gen_code.py` v1.1 does exactly this (`exit 2`, writes nothing). Silently
saving a half-file is the "output exists, therefore it worked" trap (§31.A #SA-3).

**When to use Layer 2** (in addition to Layer 1, or instead):
- MANDATORY in shared-GPU environments (multiple Claude sessions / IDE plugins / vision OCR tools running on the same box).
- MANDATORY for any script that loads >10 GB models (the silent-OOM failure mode is worst there).
- RECOMMENDED for new helpers — fail-fast with structured `recommendation` text simplifies subagent fallback logic.
- SKIP for embeddings on dedicated GPU (Layer 1 already sufficient).

**Failure modes prevented**:
- Layer 1 alone: model load attempt with insufficient VRAM falls back to CPU silently → 10× timeout blowout.
- Layer 2 adds: silent OOM crash when total VRAM demand from THIS process + neighbour processes > GPU capacity, even though Layer 1 saw "enough free VRAM" before the neighbour spiked. Layer 2's system reserve absorbs the spike; the neighbour-process diagnosis produces an actionable recommendation in the verdict (`"Wait for Ollama models [X, Y] to unload"` vs `"Non-Ollama processes hold N MB VRAM"` vs `"Fall back to Claude"`).

#### Out of scope — co-resident desktop GPU starvation (host env mitigation)

The two-layer guard and the three-tier fallback below cover **Ollama-side** OOM /
HTTP 500 caused by VRAM contention *between Ollama jobs* (this job vs neighbour
Ollama / OCR / vision models). They do **not** cover starvation of a *co-resident
interactive desktop GPU process* — an Electron app (Claude Code itself, browsers)
or the OS compositor — sharing the GPU with Ollama on a workstation.

**Verified incident (2026-06-05, RTX 4090 24 GB workstation)**: `qwen3-coder:30b`
stayed resident at ~20.8 / 23 GB VRAM through a long idle background watch
(`OLLAMA_KEEP_ALIVE` was 30m). That left < 2 GB for the desktop compositor + the
Claude Electron GPU/renderer process. The Chromium GPU process crashed
(`'GPU' process exited with 'crashed', exitCode 34, fatal`), tearing down the
session. **Ollama's own log was clean — no OOM, no HTTP 500**, and no OS-level TDR
was involved (no `Kernel-Power 41` / `4101` / BugCheck logged, ruling out a driver
reset). A healthy Ollama simply pinned VRAM long enough to starve a co-resident GPU
consumer. The guard never fired because there was no Ollama-side fault to detect —
note that the old CPU tier (removed 2026-08-28, see below) would have been a *latent*
mitigation here — it never triggered, because nothing signals a fallback while Ollama
is healthy. Since CPU is now gone entirely, the env vars below are the only
mitigation for this scenario.

**Mitigation — set these on the Ollama host** (service/daemon environment, then
restart the daemon). These live *outside* the guard:

| Env var | Value | Effect |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `5m` | Short idle TTL — the big model unloads during idle windows instead of pinning VRAM for 30m. |
| `OLLAMA_GPU_OVERHEAD` | `4294967296` (4 GiB) | Ollama reserves desktop headroom and offloads partially to CPU before it can starve the GPU process. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Concurrent loads can't spike VRAM. |

This is **complementary to, not a replacement for, the guard** — there is no
conflict: the guard reads *real free VRAM* from `nvidia-smi` at decision time, and
these env vars simply leave more of it free, so the guard's verdicts stay correct
and just see more headroom.

### Per-role `num_ctx` profiles (LOCKED 2026-06-04)

Universal `num_ctx: 32768` was replaced by per-role profiles in every shipped `workflow.yaml` (`ollama.num_ctx_profiles` + `ollama.role_profile_defaults`). KV-cache scales ~linearly with `num_ctx`; bigger context = bigger RAM/VRAM footprint, so each role gets the minimum window that does not starve its task. Helper scripts under `<project>/audit/_drafts/_ollama_helpers/` (or `scripts/ollama/`) MUST accept `--profile <name>` and apply the matching `num_ctx` / `num_predict`. Default profile when no flag is passed: `forge` (32k).

| Profile | `num_ctx` | `num_predict` | Typical role |
|---|---:|---:|---|
| `forge` | 32 768 (32k) | 8 192 | Reports / B / E — templated codegen, JSON emit, plan-markdown drafts. Default. |
| `forge-large` | 65 536 (64k) | 16 384 | Mid-batch multi-file extraction or summarization. |
| `guard` | 65 536 (64k) | 16 384 | Validator review (D in `multi-agent-strategist`, R in `pair-review`, M+V in `migration-sweep`) — holds spec + code + tests + diff together. |
| `math` | 131 072 (128k) | 32 768 | A in `multi-agent-strategist` — multi-paper derivation, full PDF formula validation. |
| `archive` | 131 072 (128k) | 32 768 | R in `solo-research` — whole-standard reads (>50-page PDFs), multi-page RAG-entry builds. |

**MANDATORY env on 24 GB VRAM hosts**: `OLLAMA_KV_CACHE_TYPE=q8_0` (set once in the Ollama service environment, then restart the daemon). Halves KV-cache memory; quality loss ≤1% on extraction/derivation tasks. Without it, `math`/`archive` 128k profiles spill to CPU offload (TTFT ~10-30 s vs ~1-2 s). Even on hosts with more VRAM, `q8_0` is the recommended default — the throughput win is large and the quality cost stays inside per-task noise.

The rendered `AGENTS.md` §5.1 in every bootstrapped project contains the full profile table + the per-role default mapping for that workflow. The per-agent `.claude/agents/agent-*.md` files (in `multi-agent-strategist`) also state each role's default profile + suggested override conditions in their Ollama section.

## GPU-only Ollama fallback (v1.8.0+, CPU tier REMOVED v1.9.2 2026-08-28)

Added in v1.8.0 (SpectraVibe Task 75D). Extended in v1.9.0 with FILL THE FLEET policy, two-tier publish strategy, and HARD RULE for guarded_generate(). **v1.9.2 (2026-08-28, operator instruction "проц запрещён" / "оллама только гпу"): the CPU tier is REMOVED from the automatic path.** `guarded_generate()` now raises `VramGuardFailure` whenever GPU is unavailable after the queue tier — it never silently falls to CPU. `try_cpu()` still exists in the module for explicit manual use; nothing in this skill calls it automatically anymore.

### The pattern (current)

```
Tier 1 — GPU direct:    check_can_load → VRAM OK  → run on GPU
Tier 2 — Queue:         VRAM busy      → enter machine-global queue
                        First-in-line + VRAM free → run on GPU
                        Drop-out / queue timeout    → raise VramGuardFailure
Tier 3 — Claude (caller): catch VramGuardFailure → retry, raise priority,
                        or fall back to Anthropic API. No CPU tier.
```

**API entry point**: `guarded_generate(model, prompt, *, want_gpu=True, priority=50, max_wait_s=600, return_mode=False, ...)` — backward-compatible drop-in for `requests.post('/api/generate', ...)`. `return_mode=True` still returns `(response_dict, Literal['gpu', 'cpu'])` for signature compatibility, but the `'cpu'` branch is now unreachable via the automatic path — a failed GPU attempt raises instead of returning `'cpu'`.

**Historical note (pre-2026-08-28 behaviour, kept for context):** the old Tier 3 CPU fallback (`num_gpu=0` + RAM check + 5× timeout) silently pinned a model to CPU whenever GPU headroom was tight — worse, `check_can_load()`'s `already_loaded` check didn't look at `size_vram`, so a model that fell to CPU once stayed "already loaded" forever, even after VRAM freed up (Программист W-019, `references/error-classes.md` C-003). Both defects are fixed together in v1.9.2: CPU is gone from the automatic path, and `already_loaded` now requires `size_vram > 0`.

Reference implementation: `scripts/vram_guard_reference.py` (copy to any project's `scripts/ollama/_vram_guard.py` or `audit/_drafts/_ollama_helpers/_vram_guard.py`).

### Cross-chat machine-global queue

The VRAM queue is **machine-global**, not project-local. All Claude Code sessions,
subagents, and ad-hoc Python scripts on the same host share one queue so no two
processes independently think they are first-in-line.

**Storage location**:
- Windows: `%LOCALAPPDATA%/ollama-vram-queue/` (fallback: `%TEMP%/`)
- POSIX: `$XDG_CACHE_HOME/ollama-vram-queue/` (fallback: `~/.cache/`)

**Atomicity**: ticket files written via `tmp → os.replace` (atomic on NTFS and POSIX);
heartbeat files via `Path.touch()` (atomic create-or-update). No fcntl/msvcrt locks needed.

**Ticket filename format**: `{inv_priority:03d}_{utc_iso}_{uuid8}.json`
where `inv_priority = 999 - priority`. Pure lexicographic ASC sort of filenames
gives priority DESC + timestamp ASC without parsing.

### Drop-out triggers

A waiter drops out of the queue and falls back to CPU when any of:

| Trigger | Default | kwarg to override |
|---|---|---|
| Queue position > N | N = 2 | `drop_out_position=` |
| Elapsed time > T | T = 120 s | `drop_out_after_s=` |
| Hard timeout | `max_wait_s` = 600 s | `max_wait_s=` |

Return value on drop-out: `VramVerdict(ok=False, reason='queue_drop_out_cpu_recommended')`.

### CPU mode RAM requirements

`try_cpu(model, prompt, ...)` runs `num_gpu=0` with a 5× timeout (default 5 × 300 s = 1500 s).
Before calling, it checks available system RAM:

| Constant | Value |
|---|---|
| `MODEL_RAM_ESTIMATE_GB["qwen3-coder:30b"]` | 18 GB |
| `MODEL_RAM_ESTIMATE_GB["qwen3.6:27b"]` | 19 GB |
| `CPU_OS_RESERVE_GB` | 4 GB |
| Minimum free RAM required | model_GB + 4 GB |

If available RAM < minimum, `VramGuardFailure` is raised. If RAM is undetectable
(`-1.0` from the probe chain), the mode is accepted permissively (trust the caller).

RAM probe chain (zero new dependencies): `psutil` → `ctypes.GlobalMemoryStatusEx` (Windows) → `/proc/meminfo MemAvailable` (POSIX) → `-1.0` (permissive).

### Priority classes

| Class | `priority=` | Who uses it |
|---|---:|---|
| `orchestrator` | 100 | Main Claude loop (blocks user dialog) |
| `subagent` | 50 | Default — background workers |
| `batch` | 10 | Low-priority sweeps, RAG-build jobs |

Pass `priority=` as a kwarg to `guarded_generate()` or `wait_in_queue()`. Downstream
projects MAY override at call site — no changes to workflow YAMLs required.

### Anti-pattern guards

These are **enforced by code path** (not just documented):

1. **NEVER kill a foreign PID.** `_scan_live_tickets()` deletes stale ticket *files*
   only — it never reads the `pid` field from the ticket body to send a signal.
   Killing a neighbour process would break the user's other Claude sessions or scripts.

2. **NEVER delete a ticket with a fresh heartbeat.** A ticket is TTL-expired only
   when its heartbeat file is missing OR its mtime > 60 s. Tickets whose heartbeat
   is < 60 s old are left untouched by the stale-cleanup pass — a neighbour waiter
   may be 1 second from passing.

3. **`try/finally` guarantees own-ticket cleanup.** The waiter loop is wrapped in
   `try/finally`; even on exception, the caller's own ticket + heartbeat are deleted.

4. **`nvidia-smi [Insufficient Permissions]` rows ignored, not flagged.** `query_gpu_processes()`
   sets `mem_MB=0` for these rows and continues; it does not treat them as errors.

### NEVER via Ollama

- Direct project-file edits (Claude / Edit only)
- "Do or don't" decisions
- Final commits, releases
- User-facing dialog
- Final anti-hallucination check (every claim ↔ offset/line/table in source)
