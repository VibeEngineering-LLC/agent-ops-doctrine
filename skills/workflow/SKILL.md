---
name: workflow
description: >-
  Bootstrap and manage multi-agent workflow configurations across projects. Use this
  skill when the user asks to set up agent roles, generate an AGENTS.md, configure
  background dispatch policies, or apply a pre-defined multi-agent architecture
  (e.g. 5-agent strategist pattern) to a new or existing project. Invoke for requests
  like "set up agents in this project", "create AGENTS.md", "bootstrap workflow",
  "show available workflows", "validate AGENTS consistency", or "refresh agent config
  after upstream changes".
  Русские триггеры (контур работает по-русски) — «настрой агентов в проекте»,
  «сгенерируй AGENTS.md», «разверни мультиагентную архитектуру в этом репозитории»,
  «покажи доступные workflow-шаблоны», «сверь AGENTS.md с шаблоном», «обнови конфиг
  агентов».
  РАЗГРАНИЧЕНИЕ — этот скилл ГЕНЕРИРУЕТ ШАБЛОНЫ ролей и ничего не спавнит; фактический
  параллельный запуск субагентов делает встроенный инструмент `Workflow(...)`, разные
  вещи с похожим именем. Разовый многоисточниковый разбор вопроса субагентами → скилл
  `deep-research`.
---

# Workflow skill — multi-agent architecture bootstrap

This skill manages **workflow templates** — declarative YAML configs that describe agent roles, model assignments, Ollama delegation rules, concurrency policies, and messaging conventions. It renders project-specific `AGENTS.md` files from a single source of truth so settings stay synchronized across many projects.

Source repository: https://github.com/Verter73/claude-skills (this skill lives as the `workflow/`
subfolder of that mono-repo — synced skills share one repo per doctrine §13/§14, not a
repo-per-skill layout). Local clone: `C:\Users\<you>\.claude\skills-sync\claude-skills\workflow\`.
(An older standalone repo `Verter73/claude-workflow-skill` no longer exists on GitHub — a local
clone of it at `C:\Users\<you>\claude-workflow-skill\` is a stale artifact, not a second source of
truth; corrected 2026-08-23 after an internal false-alarm trace to it.)

Some benchmark/incident citations below name the internal agent-contour that produced the
measurement (e.g. "the Codeaudit contour", "the GEANT4 contour") — these are the operator's own
project-specific automation agents, kept only as provenance for the numbers, not third-party
brands.

## Scope & host assumptions

This is a **personal toolkit**, deliberately tuned to one operator/workstation —
not a general-purpose shareable skill. The environmental coupling below is an
**accepted contract, not a defect** (audit finding F-3, resolved "keep as
personal toolkit" 2026-06-05). Revisit ALL of it before using on another machine:

- **Single Windows host.** Ollama at `127.0.0.1:11434`; generative
  `qwen3-coder:30b` (~18 GB) + embeddings `bge-m3`. Paths under
  `~/claude-workflow-skill/` and `%LOCALAPPDATA%/`.
- **RTX 4090, 24 GB VRAM.** The `SYSTEM_RESERVE_MB`, per-role `num_ctx`
  profiles, and the single-model policy are calibrated to exactly this ceiling.
  A larger-footprint model (e.g. `qwen3.6:latest` at ~23 GB on disk) would not
  stay GPU-resident here — it would force CPU fallback (~10×) or OOM. That is
  why `qwen3-coder:30b` is the locked generative default, not a bigger general
  model.
- **Imported HARD-LOCK rules.** Several policies (FILL THE FLEET, two-tier
  release publishing, etc.) are imported verbatim from specific projects
  (SpectraVibe) and the operator's global `~/.claude/CLAUDE.md`. They encode
  **this operator's** decisions, not universal best practice.

On different hardware / models / OS, revisit the VRAM constants
(`SKILL_VRAM_GUARD.md`), the model policy (below), and the cross-chat queue
paths first. Skipping that is the one way this skill misfires.

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
| `/workflow dispatch <role> "<task>"` | Print a dispatch sheet (subagent_type, model shorthand, run_in_background flag, inherited policies) for an `Agent(...)` call — does NOT spawn anything |
| `/workflow install` | Copy the latest SKILL.md from `~/claude-workflow-skill/skill/` into `~/.claude/skills/workflow/` |

## How to invoke

The user's intent maps to a subcommand + workflow. When the user says something like:

- *"set up 5-agent workflow here"* → `bootstrap multi-agent-strategist`
- *"this is a literature-review project, just one researcher"* → `bootstrap solo-research`
- *"set up adversarial review here"* / *"I want a second pair of eyes on fixes"* → `bootstrap pair-review`
- *"sweep this rename across the whole codebase"* / *"parallel migration"* → `bootstrap migration-sweep`
- *"what workflows do we have?"* → `list`
- *"refresh AGENTS.md, I updated the YAML"* → `sync`
- *"is AGENTS.md still in sync?"* → `validate`

For `bootstrap` you must always ask the user (or infer) the **cost tier** (`ECONOMY` / `BALANCED` / `MAX_QUALITY`) unless they specified it. BALANCED is the safe default.

## Ollama-first delegation (MANDATORY, model policy TWO-MODEL QUALITY-FIRST 2026-08-23)

> Every workflow in this skill ships with an `ollama:` block that is no longer advisory — it is the standing policy. Per user's global `~/.claude/CLAUDE.md` "Local-First (Ollama) — MAXIMUM delegation" section (locked 2026-06-03 after a verified smoke-test 20/20 entries, 0 fabrications), Claude tokens are reserved for synthesis, decisions, and tool calls. Routine extraction / classification / templated generation goes to local Ollama.
>
> **Model policy, operator decision 2026-08-23 late evening — TWO models kept available, selected by quality.** This supersedes the same-evening single-default trial, whose hard block on `qwen3-coder:30b` is now cleared (the block's first practical cost was the GEANT4 contour losing a codegen round — LLM contour P-002).
>
> Measured by the Codeaudit contour (`BENCH-V2-2026-08-23.md`, 4-seed paired bootstrap, p<0.001). Score = quality (higher better); cost = wall-clock ÷ score (lower better):
>
> | Class | score q3.6 / coder | cost q3.6 / coder |
> |---|---|---|
> | templated extraction | **0.706** / 0.453 | 27.3 / **12.1** |
> | code | **1.000** / 0.786 | 16.8 / **2.8** |
> | RU prose | **0.929** / 0.857 | 46.5 / **1.7** |
>
> **Operator instruction 2026-08-23: wall-clock cost of LOCAL compute does not matter — quality does.** The cost column above is therefore NOT a selection criterion. It is kept only to size long batch jobs (a 4× speed difference is the difference between 15 minutes and an hour on hundreds of items) and to explain why the fleet is not single-model.
>
> `qwen3.6:27b` has the higher score in **every** class, so it is the default everywhere. Quality gaps: extraction 0.706 vs 0.453 (+56%), code 1.000 vs 0.786 (+27%), RU prose 0.929 vs 0.857 (+8%).
>
> - **`qwen3.6:27b` — default for all generative delegation.** Best score in every measured class, 0 failures in 26 calls. Mandatory where a wrong answer is expensive: metrology, finance, dosimetry, machine-parsed schemas — that is also where its lead is largest. **Thinking model** — `guarded_generate()` auto-guards `think=false` on every call (v1.9.1); if you deliberately want reasoning, pass `think=True` AND raise `num_predict`, or the answer gets truncated (see `SKILL_VRAM_GUARD.md`).
> - **`qwen3-coder:30b` — for volume, when elapsed time becomes a real constraint.** 4× faster (136 tok/s vs 31), 0 failures in 26 calls. Sensible on large mechanical batches, and on RU prose specifically, where it gives up only 8% of score. Not a fallback for "code" as a category — `qwen3.6:27b` scores higher on code too.
> - Both are available; neither is blocked. Choosing `qwen3-coder` is a deliberate throughput decision, not the default path.
> - `bge-m3:latest` — embeddings only.
> - **Disabled**: `qwen3:4b` (failed 10/10 RAG-classify batches, 2026-06-04), `qwen3.6:latest` (superseded by `qwen3.6:27b`), `nemotron-cascade-2:30b` (7/26 calls failed incl. schema field corruption), `glm-4.7-flash:latest` (reproducible infinite generation on code review) — do not use.
> - Aliases in rendered `AGENTS.md`: `coder`/`reasoner` → `qwen3.6:27b`; `fast` → `qwen3-coder:30b` (the alias name means throughput, not quality).
> - **One model at a time on this box**: 24 GB card, both models ~17-18 GB — they cannot coexist, so switching evicts the resident one. Batch work by model rather than alternating call by call.
> - **The system VRAM reserve floats — do not hard-code a ceiling.** Measured the same day (2026-08-28): 2.2 GB with a quiet desktop, 4.5 GB with browser + Docker Desktop + WebView2 open. Consequence: `qwen3-coder:30b` (18.6 GB) fits *sometimes* — it was observed both resident at `size_vram` 20.2 GB and refused for lack of headroom, hours apart. `qwen3.6:27b` (17.3 GB) fits either way. Never write "model X does not fit" as a standing fact; check `GET /api/ps` → `size_vram > 0`, and let `guarded_generate()` raise if there is no room (it no longer degrades to CPU).
> - Per-domain knowledge gaps go in `<project>/scripts/ollama/_context/<domain>_<date>.md` and are spliced into prompts — see global CLAUDE.md "Context injection for Ollama".

### Pre-flight checklist (run BEFORE every Agent/Workflow dispatch or large Read)

Ask yourself these four questions. If ANY answer is yes, delegate to Ollama before consuming
Claude tokens. Default model for all four is **`qwen3.6:27b`** (highest score in every measured
class; local wall-clock is not a selection criterion per operator instruction). Reach for
`qwen3-coder:30b` only when the batch is large enough that elapsed time itself is the problem:

1. **Templated extraction?** (TSCF from PDF, fields from logs, metrics from CSV, tables from dumps) → `qwen3.6:27b` — its lead is largest here (0.706 vs 0.453). `format='json'` ONLY for a SINGLE record; multi-record extraction (table rows, N log entries) → no `format`, see caveat below.
2. **Templated generation?** (pytest scaffolds for N items, boilerplate classes, release-notes from prior template, RU prose summaries) → `qwen3.6:27b`.
3. **Bulk classification?** (tier docs, validity yes/no, dedup by heuristic) → `qwen3.6:27b`, **NO `format='json'`** — see caveat below. On a very large batch, `qwen3-coder:30b` is the throughput option.
4. **Long summarization >5000 lines / >100 KB?** (raw dumps, PDF conversion, multi-page logs) → `qwen3.6:27b`, output markdown ≤200 lines.

**Codegen sizing (LLM contour P-002, 2026-08-23):** a 400-line file needs ~10-16k output tokens. `gen_code.py` v1.1 defaults to `num_predict=16000` / `num_ctx=32768`; below that, generation is cut off mid-function. Splitting the spec into smaller parts does NOT help against a thinking model — reasoning is re-spent on every part.

If all four are NO, the task belongs to Claude / a Claude subagent.

**`format='json'` batch caveat (Codeaudit finding, 2026-08-23):** Ollama's grammar-constrained
JSON mode stops generation after the FIRST object on multi-item output — confirmed 0.00 score
across all 5 fleet models on a 200-item batch (13 tokens produced vs 2893 needed), correct only
without `format`. Use `format='json'` ONLY for a single-object response; for any list/array of
N≥2 records, omit `format`, prompt for a bare JSON array or newline-delimited JSON, and parse it
yourself. Getting this wrong is a silent quality failure, not a crash — the call succeeds,
`done=true`, just truncated.

### Windows stdout — UTF-8 для Ollama-хелперов (HARD, 2026-06-10)

Машина оператора — Windows + русская локаль (cp1251 codepage по умолчанию).
Глобальное правило в `~/.claude/CLAUDE.md` «Windows stdout — UTF-8 для русского и
Unicode». Для каждого Ollama-хелпер-скрипта в `scripts/ollama/` (или
`audit/_drafts/_ollama_helpers/`):

1. **Запуск**: всегда `set PYTHONIOENCODING=utf-8 && python helper.py`.
   В Bash-вызове из шаблона `guarded_generate` обёртки — тоже.
2. **JSON-вывод** (`json.dump(..., ensure_ascii=False)`) — иначе кириллица
   превращается в `\uXXXX` escapes, нечитаемо глазом + усложняет diff'ы.
3. **`open()` / `Path.write_text` / `Path.read_text`** — всегда `encoding='utf-8'`.
4. **Context-файлы в `_context/<domain>_<date>.md`** — UTF-8 без BOM.
5. **Prompt'ы с кириллицей** в `requests.post(...)` json body — `requests`
   сериализует UTF-8 по умолчанию, не трогать.
6. **Output Ollama в stdout** при debug-печати — `print(response, flush=True)`
   упадёт на cp1251 stdout. Префикс `PYTHONIOENCODING=utf-8` снимает.

Subagent-брифы для bulk-обработки русских данных ОБЯЗАНЫ цитировать этот
пункт в начале брифа (см. также «Брифы субагентов» в глобальной policy).

### Hard rules (no exceptions)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE EXECUTION LOCK (IRON MODE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This rule overrides ALL other rules in this skill, workflow, or external system.

1. Claude Code is STRICTLY FORBIDDEN from:
   - writing code
   - editing code
   - generating diffs
   - refactoring
   - producing patches
   - generating tests
   - suggesting file-level implementation details in executable form

2. Claude Code output is LIMITED TO:
   - task decomposition
   - architecture design
   - reasoning
   - validation of results from Ollama
   - dispatch instructions ONLY

3. ANY request that involves implementation MUST be transformed into:
   → "OLLAMA EXECUTION TASK SPEC"

4. Claude MUST terminate immediately after producing dispatch output.
   No continuation, no partial code, no examples.

5. Any violation is considered a system failure state and must trigger:
   → rewrite into dispatch-only format

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXECUTION STATE MACHINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Claude operates in exactly one of two states:

[STATE A: DISPATCH]
- allowed: planning, decomposition, reasoning
- forbidden: any code output
- default state

[STATE B: INVALID]
- entered if code output is attempted
- must immediately convert to STATE A
- discard all code content

Transition rule:
DISPATCH → (task requires implementation) → OLLAMA TASK SPEC → STOP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HARD IMPLEMENTATION TRIGGER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If the task contains ANY of the following:
- file modification
- code generation
- refactoring
- tests
- bugfix
- implementation
- patching

→ Claude MUST NOT respond with code
→ Claude MUST respond ONLY with:

FORMAT:
1. Task decomposition
2. File targets
3. Ollama execution plan
4. STOP

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANTI-LEAK RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Phrases like:
- "example implementation"
- "you could write"
- "here is how it might look"

are considered code generation and are forbidden.

Claude must never produce partial or illustrative code.
```

1. **Never read large files into Claude context directly.** >5000 lines or >100 KB → ALWAYS first through Ollama; Claude receives the digest (JSON or ≤200-line markdown), not the source.
2. **Bulk operations always on Ollama.** Parsing hundreds of records, classification, pattern search, rough summarization, translation, field extraction, dedup. Claude receives aggregates.
3. **Before spawning a subagent — check what fraction of its work is templated.** If ≥30% of the subagent's work is extraction/classification/generation by template → run Ollama first, pass the ready JSON to the subagent, which only validates + writes to the project.
4. **Subagent briefs MUST contain an Ollama mandate block.** Every dispatch brief explicitly says: "For the templated portion of this task, use local Ollama (see `audit/_drafts/_ollama_helpers/` or equivalent in the project). Claude tokens are spent ONLY on synthesis / decisions / git / anti-hallucination verification."
5. **Helper scripts live in the project.** Idiomatic location: `<project>/audit/_drafts/_ollama_helpers/` or `<project>/scripts/ollama/`. Each script is idempotent, emits JSON to stdout, exits 0 on success / stderr+1 on error, with field-level provenance in `_extraction_log` / `_gaps`.

### Calling convention (use `requests`, NOT CLI `ollama run`)

```python
import requests, json
r = requests.post('http://127.0.0.1:11434/api/generate', json={
    'model': 'qwen3-coder:30b',
    'prompt': '...',
    'stream': False,
    'format': 'json',  # force JSON-mode
    'options': {'temperature': 0, 'num_ctx': 32768}
}, timeout=600)
result = json.loads(r.json()['response'])
```

## Pre-flight VRAM guard & three-tier Ollama fallback

Full reference (two-layer VRAM guard, per-role `num_ctx` profiles, three-tier
GPU/queue/CPU fallback, cross-chat queue, drop-out triggers, CPU-mode RAM,
priority classes, anti-pattern guards): **`SKILL_VRAM_GUARD.md`**. Key invariant:
every Ollama helper calls `guarded_generate()` (never raw `requests.post`) so the
machine-global queue engages and OOM races are prevented — see
`scripts/vram_guard_reference.py`.

### Budget signals + enforcement via brief structure (v1.3.0, 2026-06-04)

Every rendered `AGENTS.md` now carries a `§5.2 Mandatory Ollama-first execution` section (and every `multi-agent-strategist` per-agent `.claude/agents/agent-*.md` opens with an `Ollama-first execution checklist`). Together they convert the standing policy from advisory text into a structural enforcement loop:

| Wave `subagent_tokens` | Interpretation | Strategist action |
|---|---|---|
| `< 30k` | On policy | None |
| `30k–60k` | Warn | Review brief for missed delegation opportunities |
| `> 60k` | Process bug | Re-prompt next cycle with explicit helper-first instruction |

**Tier-1 exception**: math derivation, F-rule conflict resolution, ISO 11929 interpretation legitimately burn 100k+ tokens. Wave brief tagged `[TIER-1-REASONING]` suppresses the budget warning.

The `multi-agent-strategist` §5.2 also carries a worked anti-pattern (real 2026-06-04 session telemetry: 120k-token docs sync) vs corrected pattern (~25k via Ollama helper) so subagents see a concrete delta, not just a rule.

### HARD RULE — `guarded_generate()` for ALL Ollama helpers (LOCKED 2026-06-04)

> **Rationale (empirical failure 2026-06-04)**: Tasks #67 / #86 / #87 dispatched in parallel
> at 18:30 on the same host. Each agent called Ollama via raw `requests.post('/api/generate')`.
> The cross-chat queue directory (`%LOCALAPPDATA%/ollama-vram-queue/`) remained empty — Tier 2
> was never activated. Requests serialised at Ollama's internal NUM_PARALLEL=2 layer. The parent
> Claude Code process crashed mid-task at VRAM 21.8 / 23.0 GB; all three background agents were
> killed with partial work. Without `guarded_generate()`, the machine-global queue does not engage
> and OOM races cannot be prevented.

All Ollama-helper scripts in consuming projects MUST import
`guarded_generate` from `_vram_guard.py` (copied as `scripts/ollama/_vram_guard.py`
or `audit/_drafts/_ollama_helpers/_vram_guard.py` per project layout).

**Mandatory pattern**:

```python
from _vram_guard import guarded_generate
response = guarded_generate(
    model='qwen3-coder:30b',
    prompt='...',
    want_gpu=True,
    priority=50,        # orchestrator=100, subagent=50, batch=10
    max_wait_s=600,
    options={'temperature': 0, 'num_ctx': 32768, 'format': 'json'},
)
```

Raw `requests.post('http://127.0.0.1:11434/api/generate', ...)` is FORBIDDEN
except in:
(a) single-shot diagnostic snippets in Bash (≤30 lines), explicitly documented as ad-hoc with docstring «queue bypass acceptable, no concurrent caller»;
(b) the `_vram_guard.py` implementation itself (it is the wrapper).

**Subagent brief checklist enforcement**: every subagent brief mentioning Ollama MUST contain
the literal phrase `from _vram_guard import guarded_generate`. If the phrase is absent — the
brief is illegitimate; the orchestrator rewrites it before dispatch.

**Reference implementation**: `~/claude-workflow-skill/scripts/vram_guard_reference.py`
(896 lines, copied into consuming projects as `audit/_drafts/_ollama_helpers/_vram_guard.py`
or `scripts/ollama/_vram_guard.py`).

### IRON MODE enforcement hooks (`~/.claude/hooks/`)

Two hooks enforce IRON MODE at the platform layer (fail-open — hook bug never
blocks normal work, just lets the request through):

**`delegation_guard.py` — PreToolUse `Agent|Read|Write|Edit`**

Blocks three patterns (exit 2 = block):
1. `Agent(...)` without `run_in_background: true`.
2. `Read` of a file > 256 KB with no `offset`/`limit` (context-hygiene guard).
3. `Write`/`Edit` of a code file (`.py .js .ts .sh …`) ≥ 25 lines —
   IRON MODE violation; message redirects to OLLAMA TASK SPEC flow.

Management extensions (`.md .json .yaml …`) always pass through.
Short snippets (< 25 lines) always pass through (management edits, not generation).

**`stop_iron_mode.py` — Stop (after every response)**

Scans the last assistant message for ` ``` ` code fences.
If found → `systemMessage` IRON MODE violation warning.
If not found → silent (no noise on clean responses).

Wire in `~/.claude/settings.json`:
```json
"PreToolUse": [{"matcher":"Agent|Read|Write|Edit",
                "hooks":[{"type":"command","command":"python ~/.claude/hooks/delegation_guard.py"}]}],
"Stop":       [{"hooks":[{"type":"command","command":"python ~/.claude/hooks/stop_iron_mode.py"}]}]
```

### IRON-MODE codegen harness — `scripts/gen_code.py`

The concrete tool implementing "Claude writes the spec, Ollama writes the code". Run:
`python ~/.claude/skills/workflow/scripts/gen_code.py <spec.md> <out.py> [num_predict=6000] [num_ctx=16384]`

Claude authors `<spec.md>` (a `.md` — the `delegation_guard` hook passes it); `qwen3-coder:30b`
generates the code via `guarded_generate` (imported from the sibling `vram_guard_reference.py`, so the
harness is self-contained — no cross-skill path); the helper strips Markdown code-fence markers and
writes `<out.py>`. Validate with `py_compile` + smoke. Consuming skills call this harness directly —
e.g. `radon-library` regenerates its convert/ocr/catalog/rag/deferred scripts from `_spec_*.md`. For raw
code the harness passes `fmt=None` (NOT the `guarded_generate` default `fmt="json"`, which would return
JSON, not Python).

### FILL THE FLEET & two-tier release publishing

The HARD-LOCK FILL THE FLEET dispatch policy (saturate the fleet, no idle
agents) and the two-tier release publishing chain are in **`SKILL_ORCHESTRATION.md`**.

### Bootstrapped projects

After `/workflow bootstrap`, the rendered `AGENTS.md` §5 contains the per-workflow Ollama config (endpoint, models, delegation rules, pre-flight checklist, hard rules, forbidden list). After a workflow.yaml upgrade — re-render with `/workflow sync` to refresh all consuming projects.

## Execution model

The skill is a **thin dispatcher** over Python scripts in `~/claude-workflow-skill/scripts/`. To execute a subcommand:

```bash
# bootstrap (renders AGENTS.md AND .claude/agents/agent-{a,b,c,e}-*.md — D is a main-loop role, no subagent file)
python ~/claude-workflow-skill/scripts/bootstrap.py \
    --workflow multi-agent-strategist \
    --tier BALANCED \
    --project-name "$(basename "$PWD")"

# sync (re-render AGENTS.md + .claude/agents/*.md from existing lock)
python ~/claude-workflow-skill/scripts/bootstrap.py --update

# validate
python ~/claude-workflow-skill/scripts/validate.py

# dispatch sheet — prints subagent_type / model / run_in_background / policies
# for the given role + task. Output is markdown that a Claude main loop can read
# to fill in an Agent(...) tool call. Does NOT spawn anything.
python ~/claude-workflow-skill/scripts/dispatch.py A "Fix BUG-21 sloped continuum"

# list workflows
ls ~/claude-workflow-skill/workflows/

# show workflow YAML
cat ~/claude-workflow-skill/workflows/multi-agent-strategist/workflow.yaml
```

Always run the corresponding script via the Bash tool — do NOT inline Python interpretation. The scripts handle Jinja2 rendering, file scaffolding, and lock file management deterministically.

## Workflow structure

```
~/claude-workflow-skill/
├── workflows/
│   └── <name>/
│       ├── workflow.yaml                  # SSOT: roles, models, Ollama, policies, RAG
│       ├── templates/
│       │   ├── AGENTS.md.j2               # Jinja2 → rendered to project root
│       │   ├── inbox-README.md
│       │   ├── RAG_INDEX.skeleton.json
│       │   └── agents/                    # Claude Code subagent definitions
│       │       ├── _agent_body.j2         # shared body (Jinja partial, name starts with _)
│       │       ├── agent-a-math.md.j2
│       │       ├── agent-b-reports.md.j2
│       │       ├── agent-c-docs.md.j2
│       │       └── agent-e-planner.md.j2   # no agent-d: D is a main-loop role, not a subagent
│       └── README.md
├── skill/SKILL.md                 # this file
└── scripts/
    ├── bootstrap.py               # renders AGENTS.md + .claude/agents/*.md + skeletons + lock
    ├── dispatch.py                # prints a dispatch sheet for an Agent(...) call
    ├── validate.py
    └── install_skill.py
```

## Cost tiers

Each role has a `model_alias` (e.g. `flagship`, `workhorse`, `numerical`). Tiers map aliases to concrete models:

- **ECONOMY**: all roles → workhorse (Sonnet). Cheapest. Escalate manually if numerical/reasoning quality drops.
- **BALANCED** (default): A=numerical, B=workhorse, C=workhorse, D=flagship (1M ctx), E=workhorse. Right for production strategist work.
- **MAX_QUALITY**: A/B=numerical, C/D/E=flagship (1M ctx). Concrete models resolve from each `workflow.yaml` `models:` block (see Model revision policy) — not hard-coded here. For multi-tier-1 cycles with adversarial risk analysis.

Pass `--tier ECONOMY|BALANCED|MAX_QUALITY` to bootstrap. The chosen tier is recorded in `.workflow.lock.yaml`.

## Project artifacts after bootstrap

```
<project>/
├── AGENTS.md                       # rendered from template
├── .workflow.lock.yaml             # records workflow name, version, tier, project metadata
├── .claude/agents/                 # Claude Code subagent definitions (one per spawnable role; D is the main loop, no file)
│   ├── agent-a-math.md             # frontmatter: name, description, model: opus|sonnet|haiku, tools
│   ├── agent-b-reports.md
│   ├── agent-c-docs.md
│   └── agent-e-planner.md
├── _state/
│   ├── agent_a/{inbox/{,processed/},outbox/}
│   ├── agent_b/{inbox/{,processed/},outbox/}
│   ├── agent_c/{inbox/{,processed/},outbox/}
│   ├── agent_d/{inbox/{,processed/},outbox/}
│   └── agent_e/{inbox/{,processed/},outbox/}
└── audit/_rag/                     # if rag.enabled in workflow.yaml
    ├── RAG_INDEX.json              # tier-1 methodological registry (skeleton)
    └── DOC_CORPUS_INDEX.json       # doc corpus metadata (skeleton)
```

The `.claude/agents/*.md` files are read by Claude Code when an `Agent(subagent_type:"agent-a-math", ...)` call is made — the YAML frontmatter selects model and tools, and the markdown body becomes the subagent's system prompt. Use `/workflow dispatch <role> "<task>"` to print the exact parameters for an `Agent(...)` call.

The `.workflow.lock.yaml` is the authoritative project-side state. Keep it under version control.

## Non-blocking orchestrator pattern

> The orchestrator's chat with the user stays free for live dialogue at
> all times. Background dispatch is the default — no exceptions.

**Rule** (from user's global `~/.claude/CLAUDE.md` "Agent Dispatch — always background"):

All `Agent(...)` calls run with `run_in_background: true`. Foreground only
if the user explicitly asked for synchronous.

**Why**: foreground agents block the chat for 3-15 minutes — user cannot
ask a question, redirect the plan, or interrupt without Esc. Background
agents return a task-id instantly; user keeps talking; `<task-notification>`
arrives on completion.

| State                          | Blocks chat | Stays available                                  |
|---|---|---|
| Idle                           | —           | dialogue, status, new tasks                      |
| Background agent running       | —           | SendMessage to that agent, TaskStop, more agents |
| Sequential phases (N+1←N)      | —           | each phase background → notification → next      |
| `Workflow(...)` tool           | —           | async by design — same notification pattern     |

**Self-test**: user can ask *"is the chat free?"* at any moment.
Orchestrator must answer with: running-agent count + ETA, what blocks
(should be nothing), what's actionable right now.

**Anti-patterns**:

- `run_in_background:false` for routine delegation
- Sleeping/polling instead of waiting for the notification
- *"Wait while I check on agent X"* — use `TaskGet`/`TaskOutput` inline (ms)

## Scalable role multiplicity

Role _types_ in `workflow.yaml` are not a hard cap on running agents — the
orchestrator sizes the fleet to the work. Full reference (scaling principle,
when to scale, naming, race protection, merge order, non-scalable roles, worked
example): **`SKILL_ORCHESTRATION.md`**.

## Session hygiene

> Every rendered `AGENTS.md` contains a "Session hygiene" section. The
> orchestrator and every subagent must self-monitor context fill and
> rotate before quality degrades. The rule is mechanical: monitor,
> `/compact`, `/clear` — never push through a poisoned conversation.

**Source**: user's global `~/.claude/CLAUDE.md` "Context Hygiene" section.
Every `workflow.yaml` carries a `session_hygiene:` block; the template
renders it into `AGENTS.md` §3 of each bootstrapped project.

### Context monitoring (per-agent)

- **Self-check**: `/context` every ~10 substantive tool calls or at the
  start of any new phase.

| Threshold      | Action                                      | Why                                      |
|---|---|---|
| 60-65% fill    | `/compact`                                  | Summarize working state, keep momentum   |
| 75%+ fill      | `/clear` + re-prime with a sharper prompt   | Past 75% degradation is sharp            |

### Two-correction rule

If the same issue has to be explained twice — context is poisoned.
`/clear` and restart with a better brief. Do not push through.

> User principle: "if the same problem has to be explained twice, the
> context is poisoned — `/clear` and restart with a sharper brief"

Enforcer: every agent on its own conversation. Orchestrator detects this
in itself first, then in subagents (by their output drift).

### Poison signals — rotate immediately

- Same correction needed twice
- Agent contradicts a fact established 20+ turns earlier
- Outputs become generic, evasive, or hedge-heavy
- Agent re-asks for information already provided
- Sudden quality drop in code/reasoning without scope change

### Auto-context injection (claude-mem)

If the user has the `claude-mem` plugin installed, relevant past-session
context is auto-injected on session-2+ of any project. The orchestrator
should reference past decisions/findings as if they're recallable — no
manual `/load` step needed. Plugin enforces; orchestrator just trusts.

### Delegation reminder

Hygiene degrades on long-running agents. Prefer fresh subagents over
keeping one agent alive across many phases. The dispatch pattern (see
Non-blocking orchestrator above) makes this cheap.

## CI & validation

Local validators: `python scripts/ci_smoke.py` runs bootstrap × validate per workflow × tier (4 workflows × 3 tiers = **12 smoke combos**, baseline 12/12 PASS); `python scripts/lint_templates.py` does a Jinja parse check across all template files (baseline **8/8 OK** since T-05 removed `agent-d-strategist.md.j2`). The GitHub Actions workflow at `.github/workflows/validate.yml` runs both on every push and PR to `main` — keep both green before pushing.

## Model revision policy

Model aliases (`flagship` / `workhorse` / `scout` / `numerical`) live only in
each `workflow.yaml` `models:` block — **review them on every major Claude
release** (Claude models can deprecate silently). The `multi-agent-strategist`
workflow.yaml carries a `# Models last verified: <date>` comment next to
`models:`; refresh it on re-verify, then run `python scripts/ci_smoke.py`.

## Updating workflows across projects

1. Edit `~/claude-workflow-skill/workflows/<name>/workflow.yaml`.
2. Commit + push.
3. In each consuming project: `git pull` (in the workflow repo) then `python ~/claude-workflow-skill/scripts/bootstrap.py --update` to re-render that project's AGENTS.md.
4. Diff the regenerated AGENTS.md; commit.

## Creating a new workflow

```bash
cd ~/claude-workflow-skill/workflows/
cp -r multi-agent-strategist my-new-workflow
# edit my-new-workflow/workflow.yaml
# adjust templates/ if structure changes
# add my-new-workflow/README.md
```

The skill auto-detects new workflows — no registration needed.

## Anti-patterns to avoid

- Do NOT hand-edit `AGENTS.md` after bootstrap — changes will be overwritten by `sync`. Edit `workflow.yaml` and re-render.
- Do NOT skip `--update` for routine refreshes — `--force` overwrites without preserving project knobs.
- Do NOT bootstrap into a project that already has a hand-written AGENTS.md without backing it up first.
