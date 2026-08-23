---
name: workflow
description: "Bootstrap и управление multi-agent workflow конфигами across projects — render project AGENTS.md из декларативных YAML-шаблонов (roles, model assignments, Ollama delegation, concurrency). Триггеры: «set up agents in this project», «create AGENTS.md», «bootstrap workflow», «show available workflows», «validate AGENTS consistency». Не в чат-субагенты — управляет конфигом источника правды."
---

# Workflow skill — multi-agent architecture bootstrap

This skill manages **workflow templates** — declarative YAML configs that describe agent roles, model assignments, Ollama delegation rules, concurrency policies, and messaging conventions. It renders project-specific `AGENTS.md` files from a single source of truth so settings stay synchronized across many projects.

Source repository: https://github.com/Verter73/claude-workflow-skill
Local clone: `~/claude-workflow-skill/`

**Reference files (load on demand — this core stays ≤200 lines):**
- `SKILL_OLLAMA.md` — Ollama-first delegation detail: pre-flight checklist, hard rules, calling convention, UTF-8 helper rules, budget signals.
- `SKILL_VRAM_GUARD.md` — two-layer VRAM guard, three-tier GPU/queue/CPU fallback, per-role `num_ctx`, drop-out triggers.
- `SKILL_IRON_MODE.md` — dispatch-only execution lock (verbatim), enforcement hooks, `gen_code.py` codegen harness.
- `SKILL_ORCHESTRATION.md` — scalable role multiplicity, FILL THE FLEET, two-tier release publishing.

## Scope & host assumptions

**Personal toolkit**, tuned to one operator/workstation — not a general-purpose shareable skill. The environmental coupling is an **accepted contract, not a defect** (audit F-3, resolved "keep as personal toolkit" 2026-06-05). Revisit ALL of it before using on another machine:

- **Single Windows host.** Ollama at `127.0.0.1:11434`; `qwen3-coder:30b` (~18 GB) + `bge-m3`. Paths under `~/claude-workflow-skill/` and `%LOCALAPPDATA%/`.
- **RTX 4090, 24 GB VRAM.** `SYSTEM_RESERVE_MB`, per-role `num_ctx`, and the single-model policy are calibrated to exactly this ceiling; a bigger model would force CPU fallback (~10×) or OOM — that is why `qwen3-coder:30b` is the locked generative default.
- **Imported HARD-LOCK rules** (FILL THE FLEET, two-tier publishing, …) are imported verbatim from SpectraVibe + global `~/.claude/CLAUDE.md` — this operator's decisions, not universal best practice.

On different hardware/models/OS revisit the VRAM constants (`SKILL_VRAM_GUARD.md`), the model policy (below), and the cross-chat queue paths first.

## Available workflows

| Workflow | Roles | Purpose |
|---|---|---|
| `multi-agent-strategist` | 5 (A/B/C/D/E) | Math + Reports + Docs + Strategist + Planner. Tier-1 methodological work with RAG. |
| `solo-research` | 1 (R) | Single researcher in the main loop. Bibliographies, methodology extraction, citation-grounded RAG. No subagents, no mailboxes. |
| `pair-review` | 2 (I/R) | Implementor + Adversarial Reviewer. High-risk fixes that must survive a "fix is wrong until proven otherwise" pass before shipping. |
| `migration-sweep` | 3 (M/W/V) + N parallel W | One strategist, N parallel workers in isolated git worktrees, one verifier per batch. Codebase-wide mechanical refactors. |

## Available subcommands

| Command | Effect |
|---|---|
| `/workflow list` | List all workflow templates under `~/claude-workflow-skill/workflows/` |
| `/workflow show <name>` | Print roles, models, policies, Ollama config for a workflow |
| `/workflow bootstrap <name>` | Initialize current project: render AGENTS.md, create `_state/agent_*/inbox` mailboxes, optionally seed `audit/_rag/` skeletons, write `.workflow.lock.yaml` |
| `/workflow sync` | Re-render this project's AGENTS.md from upstream workflow.yaml (preserves tier from lock) |
| `/workflow validate` | Check this project's AGENTS.md matches its `.workflow.lock.yaml` |
| `/workflow dispatch <role> "<task>"` | Print a dispatch sheet (subagent_type, model, run_in_background, inherited policies) for an `Agent(...)` call — does NOT spawn anything |
| `/workflow install` | Copy all `~/claude-workflow-skill/skill/*.md` (SKILL.md + references) into `~/.claude/skills/workflow/` |

## How to invoke

User intent maps to a subcommand + workflow:

- *"set up 5-agent workflow here"* → `bootstrap multi-agent-strategist`
- *"literature-review project, one researcher"* → `bootstrap solo-research`
- *"adversarial review" / "second pair of eyes on fixes"* → `bootstrap pair-review`
- *"sweep this rename across the codebase" / "parallel migration"* → `bootstrap migration-sweep`
- *"what workflows do we have?"* → `list` ; *"refresh AGENTS.md"* → `sync` ; *"still in sync?"* → `validate`

For `bootstrap` always ask/infer the **cost tier** (`ECONOMY` / `BALANCED` / `MAX_QUALITY`) unless specified. BALANCED is the safe default.

## Ollama-first delegation (MANDATORY, model policy TRIAL SINGLE-DEFAULT 2026-08-23)

Every workflow ships an `ollama:` block that is standing policy, not advisory (global `~/.claude/CLAUDE.md` §8). Claude tokens are reserved for synthesis, decisions, tool calls; routine extraction / classification / templated generation goes to local Ollama.

**Model policy (revised 2026-08-23 evening, operator decision — replaces the same-day per-task
split; no auto-select branching by task type for the duration of this trial)** — observing
`qwen3.6:27b` as the sole delegation default across a real workload before deciding permanently.
Benchmark background (Codeaudit contour, `BENCH-V2-2026-08-23.md`, 4-seed paired bootstrap,
p<0.001): `qwen3.6:27b` beats the rest of the fleet on quality but costs 2-40× more wall-clock
per call than `qwen3-coder:30b` — that trade-off is exactly what this trial is measuring.
- `qwen3.6:27b` — TEMPORARY single default for ALL generative delegation (extraction,
  classification, summarization, code, RU prose). **Thinking model** — `guarded_generate()`
  auto-guards `think=false` whenever `format="json"` and the caller doesn't pass `think`
  explicitly (v1.9.0, see `SKILL_VRAM_GUARD.md`), so the silent-empty-response failure mode is
  covered by default; no manual per-call handling needed.
- `qwen3-coder:30b` — NOT default for now. Stays installed; use only on explicit request (e.g.
  a workload where `qwen3.6:27b`'s wall-clock cost proves too high).
- `bge-m3:latest` — embeddings only.
- **Disabled**: `qwen3:4b` (failed 10/10 RAG-classify batches, 2026-06-04), `qwen3.6:latest`
  (superseded by `qwen3.6:27b`), `nemotron-cascade-2:30b` (7/26 calls failed incl. schema field
  corruption), `glm-4.7-flash:latest` (reproducible infinite generation on code review) —
  do not use.
- Aliases in rendered `AGENTS.md`: `coder`/`fast`/`reasoner` all → `qwen3.6:27b` for the
  duration of this trial (was `qwen3-coder:30b` before this revision).
- Per-domain knowledge gaps → `<project>/scripts/ollama/_context/<domain>_<date>.md`, spliced into prompts.

**Operational detail** (pre-flight checklist, hard rules 1-5, calling convention, UTF-8 helper rules, budget signals) → **`SKILL_OLLAMA.md`**. VRAM guard / three-tier fallback / `num_ctx` / `think` handling → **`SKILL_VRAM_GUARD.md`**.

### HARD RULE — `guarded_generate()` for ALL Ollama helpers (LOCKED 2026-06-04)

> **Rationale (empirical crash 2026-06-04)**: Tasks #67/#86/#87 dispatched in parallel on the same
> host, each calling Ollama via raw `requests.post('/api/generate')`. The cross-chat queue stayed
> empty — Tier 2 never activated; requests serialised at Ollama's internal NUM_PARALLEL=2. The parent
> Claude Code process crashed mid-task at VRAM 21.8 / 23.0 GB; all three background agents were killed
> with partial work. Without `guarded_generate()` the machine-global queue does not engage and OOM
> races cannot be prevented.

All Ollama-helper scripts MUST import `guarded_generate` from `_vram_guard.py` (copied per project as `scripts/ollama/_vram_guard.py` or `audit/_drafts/_ollama_helpers/_vram_guard.py`).

```python
from _vram_guard import guarded_generate
response = guarded_generate(
    model='qwen3-coder:30b', prompt='...', want_gpu=True,
    priority=50,        # orchestrator=100, subagent=50, batch=10
    max_wait_s=600,
    options={'temperature': 0, 'num_ctx': 32768, 'format': 'json'},
)
```

Raw `requests.post(...)` is FORBIDDEN except: (a) single-shot diagnostic snippets in Bash (≤30 lines), documented "queue bypass acceptable, no concurrent caller"; (b) the `_vram_guard.py` implementation itself. Every subagent brief mentioning Ollama MUST contain the literal phrase `from _vram_guard import guarded_generate` — absent → the orchestrator rewrites the brief before dispatch. Reference implementation: `~/claude-workflow-skill/scripts/vram_guard_reference.py` (896 lines).

### IRON MODE — dispatch-only execution lock

In this skill Claude is a **dispatcher/architect, not a coder**: implementation (code, diffs, patches, tests) is delegated to Ollama via the `gen_code.py` harness — Claude authors the spec, Ollama writes the code. Enforced at the platform layer by two fail-open hooks (`delegation_guard.py` PreToolUse blocks code-file Write/Edit ≥25 lines; `stop_iron_mode.py` flags code fences). Full verbatim lock, hook wiring, and the `gen_code.py` harness → **`SKILL_IRON_MODE.md`**.

### Bootstrapped projects

After `/workflow bootstrap`, rendered `AGENTS.md` §5 carries the per-workflow Ollama config (endpoint, models, delegation rules, pre-flight, hard rules, forbidden list). After a workflow.yaml upgrade — re-render with `/workflow sync` to refresh all consuming projects.

## Execution model

The skill is a **thin dispatcher** over Python scripts in `~/claude-workflow-skill/scripts/`. Always run the script via the Bash tool — do NOT inline Python interpretation; the scripts handle Jinja2 rendering, scaffolding, and lock management deterministically.

```bash
# bootstrap (renders AGENTS.md + .claude/agents/agent-{a,b,c,e}-*.md — D is a main-loop role)
python ~/claude-workflow-skill/scripts/bootstrap.py --workflow multi-agent-strategist --tier BALANCED --project-name "$(basename "$PWD")"
python ~/claude-workflow-skill/scripts/bootstrap.py --update            # sync: re-render from existing lock
python ~/claude-workflow-skill/scripts/validate.py                      # validate against lock
python ~/claude-workflow-skill/scripts/dispatch.py A "Fix BUG-21"       # print dispatch sheet (no spawn)
ls   ~/claude-workflow-skill/workflows/                                 # list workflows
cat  ~/claude-workflow-skill/workflows/multi-agent-strategist/workflow.yaml   # show workflow YAML
```

## Workflow structure

`~/claude-workflow-skill/` layout: `workflows/<name>/` holds the SSOT `workflow.yaml` (roles, models, Ollama, policies, RAG), `templates/` (`AGENTS.md.j2`, `inbox-README.md`, `RAG_INDEX.skeleton.json`, and `agents/` subagent defs including the shared `_agent_body.j2` partial — no `agent-d`, D is a main-loop role), and `README.md`. `skill/` holds this `SKILL.md` + the reference `.md` files. `scripts/` holds `bootstrap.py`, `dispatch.py`, `validate.py`, `install_skill.py`.

## Cost tiers

Each role has a `model_alias`. Tiers map aliases to concrete models:

- **ECONOMY**: all roles → workhorse (Sonnet). Cheapest. Escalate manually if numerical/reasoning quality drops.
- **BALANCED** (default): A=numerical, B=workhorse, C=workhorse, D=flagship (1M ctx), E=workhorse. Production strategist work.
- **MAX_QUALITY**: A/B=numerical, C/D/E=flagship (1M ctx). For multi-tier-1 cycles with adversarial risk analysis.

Concrete models resolve from each `workflow.yaml` `models:` block (see Model revision policy) — not hard-coded here. Pass `--tier ECONOMY|BALANCED|MAX_QUALITY` to bootstrap; the chosen tier is recorded in `.workflow.lock.yaml`.

## Project artifacts after bootstrap

`<project>/` gets: `AGENTS.md` (rendered); `.workflow.lock.yaml` (authoritative project-side state — records workflow name/version/tier/metadata; keep under version control); `.claude/agents/agent-{a,b,c,e}-*.md` (one per spawnable role — frontmatter selects model+tools, body becomes the subagent system prompt; D is the main loop, no file); `_state/agent_{a..e}/{inbox/{,processed/},outbox/}` mailboxes; and — if `rag.enabled` — `audit/_rag/{RAG_INDEX.json,DOC_CORPUS_INDEX.json}` skeletons. Use `/workflow dispatch <role> "<task>"` to print the exact `Agent(...)` parameters.

## Non-blocking orchestrator pattern

All `Agent(...)` calls run with `run_in_background: true` (foreground only if the user explicitly asked for synchronous). The orchestrator's chat stays free for live dialogue at all times — background agents return a task-id instantly, `<task-notification>` arrives on completion. Full rule → global `~/.claude/CLAUDE.md` §7 "Agent Dispatch — always background". Anti-patterns: `run_in_background:false` for routine delegation; sleeping/polling instead of waiting for the notification; "wait while I check on agent X" (use `TaskGet`/`TaskOutput` inline).

## Scalable role multiplicity

Role _types_ in `workflow.yaml` are not a hard cap — the orchestrator sizes the fleet to the work. Full reference (scaling principle, when to scale, naming, race protection, merge order, non-scalable roles, worked example, FILL THE FLEET HARD-LOCK, two-tier release publishing): **`SKILL_ORCHESTRATION.md`**.

## Session hygiene

Every rendered `AGENTS.md` carries a "Session hygiene" section; the orchestrator and every subagent self-monitor context fill and rotate before quality degrades — monitor, `/compact` at 60-65%, `/clear` + re-prime at 75%+. Two-correction rule: if the same issue is explained twice, the context is poisoned — `/clear`, don't push through. Poison signals: same correction twice, contradicting a fact established 20+ turns earlier, generic/evasive/hedge-heavy output, re-asking for provided info, sudden quality drop without scope change. If `claude-mem` is installed, past-session context auto-injects on session-2+. Full rule → global `~/.claude/CLAUDE.md` §6 "Context Hygiene".

## CI & validation

`python scripts/ci_smoke.py` runs bootstrap × validate per workflow × tier (4×3 = **12 combos**, baseline 12/12 PASS); `python scripts/lint_templates.py` Jinja-parse-checks all templates (baseline **8/8 OK** since T-05 removed `agent-d-strategist.md.j2`). GitHub Actions `.github/workflows/validate.yml` runs both on every push/PR to `main` — keep green before pushing.

## Model revision policy

Model aliases (`flagship`/`workhorse`/`scout`/`numerical`) live only in each `workflow.yaml` `models:` block — **review on every major Claude release** (models can deprecate silently). `multi-agent-strategist` workflow.yaml carries a `# Models last verified: <date>` comment; refresh it on re-verify, then run `python scripts/ci_smoke.py`.

## Updating & creating

- **Update across projects**: edit `workflows/<name>/workflow.yaml` → commit+push → in each consuming project `git pull` (workflow repo) then `bootstrap.py --update` → diff the regenerated AGENTS.md → commit.
- **New workflow**: `cp -r workflows/multi-agent-strategist workflows/my-new-workflow`, edit its `workflow.yaml`, adjust `templates/` if structure changes, add `README.md`. Auto-detected — no registration needed.

## Anti-patterns to avoid

- Do NOT hand-edit `AGENTS.md` after bootstrap — `sync` overwrites it. Edit `workflow.yaml` and re-render.
- Do NOT skip `--update` for routine refreshes — `--force` overwrites without preserving project knobs.
- Do NOT bootstrap into a project with a hand-written AGENTS.md without backing it up first.
