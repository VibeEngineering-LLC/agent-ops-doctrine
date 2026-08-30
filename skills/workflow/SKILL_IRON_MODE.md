# SKILL_IRON_MODE.md — IRON MODE (dispatch-only execution lock) + enforcement hooks

Reference for the `workflow` skill. Loaded on demand when the orchestrator needs the full
IRON MODE lock text, the enforcement-hook wiring, or the codegen harness. Core `SKILL.md`
carries only a 4-line summary + a pointer here.

**What IRON MODE is.** In this skill's execution model Claude is a *dispatcher / architect*,
not a coder. Implementation (writing/editing code, diffs, patches, tests) is delegated to
Ollama `qwen3-coder:30b` via the `gen_code.py` harness: Claude authors the spec, Ollama
writes the code. The lock below is the verbatim behavioural contract; the hooks enforce it
at the platform layer (fail-open — a hook bug never blocks normal work, it just lets the
request through). This is the skill's defining discipline, imported into every rendered
`AGENTS.md`.

## ABSOLUTE EXECUTION LOCK (verbatim)

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

## IRON MODE enforcement hooks (`~/.claude/hooks/`)

Two hooks enforce IRON MODE at the platform layer (fail-open — hook bug never blocks normal
work, just lets the request through):

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

Install `delegation_guard.py` once per workstation from the reference script:
`cp ~/claude-workflow-skill/scripts/delegation_guard_reference.py ~/.claude/hooks/delegation_guard.py`.

Wire in `~/.claude/settings.json`:
```json
"PreToolUse": [{"matcher":"Agent|Read|Write|Edit",
                "hooks":[{"type":"command","command":"python ~/.claude/hooks/delegation_guard.py"}]}],
"Stop":       [{"hooks":[{"type":"command","command":"python ~/.claude/hooks/stop_iron_mode.py"}]}]
```

## IRON-MODE codegen harness — `scripts/gen_code.py`

The concrete tool implementing "Claude writes the spec, Ollama writes the code". Run:
`python ~/.claude/skills/workflow/scripts/gen_code.py <spec.md> <out.py> [num_predict=6000] [num_ctx=16384]`

Claude authors `<spec.md>` (a `.md` — the `delegation_guard` hook passes it); `qwen3-coder:30b`
generates the code via `guarded_generate` (imported from the sibling `vram_guard_reference.py`, so the
harness is self-contained — no cross-skill path); the helper strips Markdown code-fence markers and
writes `<out.py>`. Validate with `py_compile` + smoke. Consuming skills call this harness directly —
e.g. `radon-library` regenerates its convert/ocr/catalog/rag/deferred scripts from `_spec_*.md`. For raw
code the harness passes `fmt=None` (NOT the `guarded_generate` default `fmt="json"`, which would return
JSON, not Python).
