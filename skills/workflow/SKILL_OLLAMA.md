# SKILL_OLLAMA.md — Ollama-first delegation detail

Reference for the `workflow` skill. Core `SKILL.md` keeps only the LOCKED model policy, the
`guarded_generate()` crash HARD RULE, and pointers; the operational detail lives here — load
on demand.

Related references: `SKILL_VRAM_GUARD.md` (two-layer VRAM guard, three-tier GPU/queue/CPU
fallback, per-role `num_ctx`), `SKILL_IRON_MODE.md` (dispatch-only lock + codegen harness).
Global policy: `~/.claude/CLAUDE.md` §8 "Local-First (Ollama) — MAXIMUM delegation" and §2
"Windows stdout — UTF-8".

## Pre-flight checklist (run BEFORE every Agent/Workflow dispatch or large Read)

Ask yourself these four questions. If ANY answer is yes, delegate to Ollama before consuming
Claude tokens. Single trial default `qwen3.6:27b` for all four (operator decision 2026-08-23,
observation period — no per-task branching, see core `SKILL.md`); `guarded_generate()`
auto-guards `think=false` on `format="json"` calls, no manual handling needed:

1. **Templated extraction?** (TSCF from PDF, fields from logs, metrics from CSV, tables from dumps) → `qwen3.6:27b` with `format='json'` ONLY if extracting a SINGLE record; multi-record extraction (table rows, N log entries) → no `format`, see caveat below.
2. **Templated generation?** (pytest scaffolds for N items, boilerplate classes, release-notes from prior template, RU prose summaries) → `qwen3.6:27b`.
3. **Bulk classification?** (tier docs, validity yes/no, dedup by heuristic) → `qwen3.6:27b`, **NO `format='json'`** — see caveat below.
4. **Long summarization >5000 lines / >100 KB?** (raw dumps, PDF conversion, multi-page logs) → `qwen3.6:27b`, output markdown ≤200 lines.

If all four are NO, the task belongs to Claude / a Claude subagent.

**`format='json'` batch caveat (Codeaudit finding, 2026-08-23):** Ollama's grammar-constrained
JSON mode stops generation after the FIRST object on multi-item output — confirmed 0.00 score
across all 5 fleet models on a 200-item batch (13 tokens produced vs 2893 needed), correct only
without `format`. Use `format='json'` ONLY for a single-object response; for any list/array of
N≥2 records, omit `format`, prompt for a bare JSON array or newline-delimited JSON, and parse it
yourself. Getting this wrong is a silent quality failure, not a crash — the call succeeds,
`done=true`, just truncated.

## Hard rules (no exceptions)

1. **Never read large files into Claude context directly.** >5000 lines or >100 KB → ALWAYS first through Ollama; Claude receives the digest (JSON or ≤200-line markdown), not the source.
2. **Bulk operations always on Ollama.** Parsing hundreds of records, classification, pattern search, rough summarization, translation, field extraction, dedup. Claude receives aggregates.
3. **Before spawning a subagent — check what fraction of its work is templated.** If ≥30% of the subagent's work is extraction/classification/generation by template → run Ollama first, pass the ready JSON to the subagent, which only validates + writes to the project.
4. **Subagent briefs MUST contain an Ollama mandate block.** Every dispatch brief explicitly says: "For the templated portion of this task, use local Ollama (see `audit/_drafts/_ollama_helpers/` or equivalent in the project). Claude tokens are spent ONLY on synthesis / decisions / git / anti-hallucination verification."
5. **Helper scripts live in the project.** Idiomatic location: `<project>/audit/_drafts/_ollama_helpers/` or `<project>/scripts/ollama/`. Each script is idempotent, emits JSON to stdout, exits 0 on success / stderr+1 on error, with field-level provenance in `_extraction_log` / `_gaps`.

## Calling convention (use `requests`, NOT CLI `ollama run`)

Diagnostic snippet only — production helpers MUST call `guarded_generate()` (see the crash
HARD RULE in core `SKILL.md` and `SKILL_VRAM_GUARD.md`), never raw `requests.post`.

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

## Windows stdout — UTF-8 для Ollama-хелперов (HARD, 2026-06-10)

Машина оператора — Windows + русская локаль (cp1251 codepage по умолчанию). Глобальное
правило в `~/.claude/CLAUDE.md` §2 «Windows stdout — UTF-8 для русского и Unicode». Для
каждого Ollama-хелпер-скрипта в `scripts/ollama/` (или `audit/_drafts/_ollama_helpers/`):

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

Subagent-брифы для bulk-обработки русских данных ОБЯЗАНЫ цитировать этот пункт в начале
брифа (см. также «Брифы субагентов» в глобальной policy).

## Budget signals + enforcement via brief structure (v1.3.0, 2026-06-04)

Every rendered `AGENTS.md` carries a `§5.2 Mandatory Ollama-first execution` section (and every
`multi-agent-strategist` per-agent `.claude/agents/agent-*.md` opens with an `Ollama-first execution
checklist`). Together they convert the standing policy from advisory text into a structural
enforcement loop:

| Wave `subagent_tokens` | Interpretation | Strategist action |
|---|---|---|
| `< 30k` | On policy | None |
| `30k–60k` | Warn | Review brief for missed delegation opportunities |
| `> 60k` | Process bug | Re-prompt next cycle with explicit helper-first instruction |

**Tier-1 exception**: math derivation, F-rule conflict resolution, ISO 11929 interpretation
legitimately burn 100k+ tokens. Wave brief tagged `[TIER-1-REASONING]` suppresses the budget warning.

The `multi-agent-strategist` §5.2 also carries a worked anti-pattern (real 2026-06-04 session
telemetry: 120k-token docs sync) vs corrected pattern (~25k via Ollama helper) so subagents see a
concrete delta, not just a rule.
