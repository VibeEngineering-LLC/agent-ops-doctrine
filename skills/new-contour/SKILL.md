---
name: new-contour
version: 2.0.0
description: >-
  Bootstrap нового контура/агента оператора: онбординг на актуальный межсессионный канал —
  файловый ящик `_interchat/inbox/` (#BUS-2). Задаёт шесть hard-locks для новой рабочей сессии:
  delegate-by-default, operator-gate на необратимом, ящик Цензора как канал ЭСКАЛАЦИИ (скорая
  помощь / доктринальные уроки — НЕ пошаговая отчётность; роль Цензора сужена оператором
  2026-08-30), read-only source git для тестера, context-layering, контур замыкает цикл
  разработка→проверка САМ (HL-6).
  Переписан 2026-08-23 взамен закрытой cc-interchat-bus (шина закрыта решением оператора
  16.08.2026 — watcher/register.py из версии 1.x больше не используются, см. историю в конце
  файла).
---

# new-contour — onboard a fresh chat as a self-closing contour

Turns the **current chat** into a first-class **contour** in the operator's registry (§11/§12
of the global `~/.claude/CLAUDE.md`). The contour closes its own development-verification
cycle itself (HL-6); the Censor is reachable over the file-mailbox channel for ESCALATION only
(#BUS-2). Hard-locks six non-negotiables: **delegate by default**, **stay in contact with the
operator**, **Censor mailbox = escalation only (no step-reporting)**, **read-only
source git for a tester**, **context-layering**, **the contour closes its own full cycle**.

**Index — rule → reference body → history:**

| Topic | Reference body | History |
|---|---|---|
| File-mailbox channel: schema, delivery proof, registry, gotchas | `~/.claude/references/interchat-channel.md` | `~/.claude/doctrine-history-2026-06-15.md` |
| Cross-contour zone boundaries, prompt format for the owner-agent | `~/.claude/references/cross-agent-routing.md` | — |
| HL-6 context-layering (full body) | `references/context-layering.md` | `~/.claude/doctrine-history-2026-06-15.md` |
| Rig / domain pack (AtomFast adb+BLE, reversible map) | `references/rig-atomfast.md` | — |
| Retired bus mechanism (v1.x, closed 2026-08-16) | `references/bus-protocol.md` (frozen, do not follow) | `CHANGELOG.md` |

## Three layers — do not confuse them

| Layer | Tool/skill | Scope |
|---|---|---|
| Cross-contour reporting | **this skill** (`new-contour`) | Registers THIS chat as a contour; wires the file-mailbox escalation channel + operator-gate. |
| In-project subagent fleet | `/workflow bootstrap …` | Renders `AGENTS.md` + `.claude/agents/*` INSIDE the contour's project. |
| Async process tree | `Workflow(...)` tool | The contour's own multi-agent fan-out (pipeline/parallel) for one task. |

A new contour uses all three: this skill → reporting channel; `/workflow` → internal fleet;
`Workflow(...)` / background `Agent(...)` → the work, verified by the contour itself (HL-6). The
file mailbox (`<WORKSPACE>\_interchat\inbox\`) is machine-global +
cross-session (contours survive each other's restarts — the file persists); a `/workflow` fleet
is intra-session (dies on reload — ephemeral). Don't confuse them.

---

## The six hard-locks (the whole point of this skill)

Imported from the operator's global `~/.claude/CLAUDE.md` and the `censor` skill —
**contract, not advice.** Every contour inherits them verbatim.

### HL-1 — Delegate by default

Contour Claude tokens are reserved for synthesis, decisions, dialogue, git, and
anti-hallucination checks. Everything else is delegated per the ladder in global §31.B:

- **Template / bulk / large-file** (extraction by template, classification, bulk parsing,
  summarization >5000 lines, logcat/CSV/spectrum dumps) → **local Ollama `qwen3-coder:30b`**
  via `guarded_generate()` (three-tier GPU/queue/CPU guard). NEVER raw `requests.post`,
  NEVER `ollama run`. Embeddings → `bge-m3:latest`.
- **Multi-step file work** (implement a fix, run a test matrix, diff analysis) **and
  investigation** (any *series* of commands to find something out) → **background subagent**
  (`Agent(..., run_in_background: true)`; ALWAYS background unless the operator says «синхронно»).
- **Multi-agent fan-out for one task** → the **`Workflow(...)` tool** (async by design).
- **Pre-flight** before any `Agent()` / big `Read`: if ≥30% of the work is
  template/extraction/classification → run Ollama first, hand the subagent ready JSON. The
  four-question checklist lives in `~/.claude/skills/workflow/SKILL.md`.

**The role in three verbs: read / manage / delegate.** Read-only lookups and own-control-space
edits (verdicts, briefs, own doctrine) are the contour's; ALL executor work is delegated; even
read-only command *series* are investigation → subagent. A brief without a named Ollama
delegation for its template part is a process bug the Censor flags.

### HL-2 — Stay in contact with the operator (operator-gate)

- `action_class ∈ {read-only, reversible}` → act **autonomously**. Do NOT ping the operator
  for reversible work.
- `action_class = irreversible` → **do NOT execute.** Park it, send a one-line decision-request
  to the operator **in the contour's own operator channel** (not via the Censor, not via the
  mailbox — authority is not transitive), wait for an explicit «да». The irreversible allow-list +
  per-rig destructive set live in the rig reference (`references/rig-atomfast.md`).
- Publish / push / release / send-to-device-that-changes-it is **never** authorized by a Censor
  ACCEPT or a mailbox relay. The Censor only JUDGES; irreversible execution needs the operator's
  own-channel permission.

### HL-3 — Censor mailbox is an ESCALATION channel, not step-reporting (rewritten 2026-08-30)

**Operator, 2026-08-30, verbatim:** «Цензор и Аудитор Кода не являются частью рабочего
процесса и не контролируют работу агентов. Задача Цензора и Аудитора Кода — проектирование
доктрины, новых контуров, глобальный аудит, аудит по заданию оператора и решение проблем,
когда локальные контура не справляются. Вы — интеллектуальная скорая помощь. Локальные агенты
должны закрывать весь цикл самостоятельно».

So: NO routine step-reports, NO ACKs, NO status pings to the Censor (they were already banned
by the Censor's own Д-1; now the whole step-reporting duty is retired). A contour writes to
the Censor's mailbox ONLY for:

- **(a) emergency call** — the contour is stuck after honestly exhausting tiers 0–1 (state
  what was tried and where it broke; «скорая помощь» needs the case history, not a symptom);
- **(b) doctrine-level lesson** — a §31.C-triaged lesson of the «доктринальный» bucket, or a
  class recurrence that needs global spread;
- **(c) response to an audit** the operator or the Censor explicitly requested;
- **(d) adjudication of the irreversible** when the operator routed that decision through the
  Censor (the operator-gate in HL-2 itself stays with the OPERATOR's own channel).

Receiving needs nothing: a global hook (`hooks/interchat_inbox.py`) injects unread mail into
the contour's first turn automatically.

**Delivery mechanics, when you DO send** (unchanged): the message is a **file**, written to:

```
<WORKSPACE>\_interchat\inbox\Цензор\
    YYYYMMDD-HHMMSS_from-<papka-этого-контура>_<slug>.md      (UTF-8)
```

The folder name in the path is the **working-folder basename of the sender**, not a session
title (registry: `~/.claude/_interchat`-adjacent `D:\…\_interchat\REGISTRY-adresatov.md`). The
first two lines of the body are mandatory so a lost file can still be routed:

```
**Адресат:** Цензор. **От:** <контур>-агент.
```

**HARD RULE — the file write is NEVER sufficient by itself.** `send_message`/`SendMessage` to
the Censor's session is a **MANDATORY duplicate**, not an optional nicety, whenever the Censor's
session is live (check `ListAgents` first). Reason, proven by fact (2026-08-16, eight sends
GEANT4→Censor): neither `sent` nor `queued` confirms delivery — a message into a sleeping
session is silently lost forever, and there is no other timely signal that it arrived. Skipping
the session-notify duplicate because "the file is already written" is the single most common way
a message goes unnoticed. Order of operations for every outgoing message:

1. Write the file to the recipient's inbox folder (durable — survives either side restarting).
2. Immediately call `SendMessage`/`send_message` to the same recipient's live session **if**
   `ListAgents` shows it running. If it isn't running, the file alone stands and mail delivery
   happens on the recipient's next natural turn — do not try to wake a sleeping session.
3. Neither `sent` nor `queued` status is proof of delivery. Proof is only a `*.read.md` marker
   appearing in your own sent file's place (the recipient's hook renames it on read) or an
   explicit reply. Do not claim "delivered to Censor" on tool-status alone.

An emergency call (case a) carries: what the task was, what tiers 0–1 already tried, where it
broke, and a fact trail (file:line / command output) — «скорая помощь» starts from the case
history, not from a bare symptom. Lessons (case b) follow the `self-learning` triage format.

**Incoming from the Censor: read and answer always** (#OPS-2, operator verbatim 2026-08-15:
«читай сообщения цензора и отвечай. Всегда!»). This is a floor, not a ceiling — the channel is
two-way; any contour may write to any other to request an audit or help, respecting zone
boundaries (§12: write a prompt, don't do the owner's work).

Full mechanics, gotchas (sleeping-session trap, sessionId rot, cross-machine caveats):
`~/.claude/references/interchat-channel.md`.

### HL-4 — Source git is read-only: a tester works only in a clone

Standing operator rule (2026-06-06). A tester/verifier contour **NEVER** mutates the canonical
(source-of-truth) git of the project under test: no `commit`/`push`/`tag`/`branch`/working-tree
edit reaching canonical origin. All build/deploy/test/fix-experiment work happens in a **clone**;
canonical is a read-only reference (`git show` / read — yes; write — no). A validated fix lands
in canonical **ONLY by the owner/operator under operator-gate (HL-2)** — never by the tester.

### HL-5 — Context layering: split docs by load-frequency

Standing rule (2026-06-16). Split every knowledge doc by **load-frequency**: L1 always-on
(CLAUDE.md global+project) — **Anthropic's own norm: «target under 200 lines per CLAUDE.md
file»** (docs.claude.com, best-practices). The limit is on ADHERENCE, not on context spend:
«Longer files consume more context and **reduce adherence**»; «Bloated CLAUDE.md files cause
Claude to **ignore your actual instructions**». Diagnostic from the same source: **if the agent
keeps breaking a rule it has written down, the file is too long and the rule is getting lost.**
Pruning test: «remove this line — would that cause a mistake? if not, cut it».
L2 trigger-on (SKILL.md core, HARD ≤8 КБ), L3 on-demand
(`references/*.md`), L4 never-auto (`audit/`, `*-history-*.md`, `CHANGELOG.md`). `/compact`/`/clear`
do NOT lower L1 — only editing content out to L3/L4 does. **3-layer cut:** A — imperative → inline
L1/L2; B — methodology / code ≥15 lines / anti-patterns-with-rationale → `references/`; C — history
/ dated incident / operator-verbatim >1 line → `<file>-history-<date>.md`. **NEVER move out of
L1/L2:** registries ($names/MAC/paths), safety/privacy-locks, cited absolute paths.

**Lossless refactor protocol (HARD):** (1) verbatim backup FIRST; (2) lean-rewrite after;
(3) index-table header; (4) sanity-grep every safety phrase + registry line verbatim-present in
lean; (5) backup byte-identical. **Bootstrap (Phase 4):** scaffold `<project>/references/` +
`audit/` on onboarding, design CLAUDE.md lean from scratch — not «later». Full body:
`references/context-layering.md`.

### HL-6 — The contour closes its OWN full cycle: development → verification (2026-08-30)

Operator's words, verbatim: «я вообще могу вас забыть подключить. и делаю это в глобальных
случаях. Локальные агенты должны уметь закрывать все циклы от разработки до проверки
субагентами». The Censor/Codeaudit tier is **an exception invoked by the operator, not a
pipeline stage** — work must be verified WITHOUT it. Concretely (global §31.D, #EVAL-1):

- **Tier 0, every LLM call:** result is NOT obtained until checked mechanically —
  `done_reason == "stop"`, non-empty `response`, format parsed (`json.loads`/`ast.parse`),
  any degradation (fallback/CPU/truncation) surfaced as an explicit field. Failure = loud
  error, never a silent return. Copy the reference snippet from `workflow\scripts\`
  (until it lands: `gen_code.py` v1.1 is the pattern) — do not re-invent it.
- **Tier 1, judgment checks:** ONE sterile background subagent-verifier per artifact. The
  brief follows global #SA-7: material presented as FOREIGN (no «my» label), no expected
  answer, no «is X correct?» questions, detection separated from fixing. The subagent brief
  states its verification BOUNDARY explicitly (#SA-8); a second verifier gets a DIFFERENT one.
- Waiting for the Censor, or shipping with «надзор потом проверит» — a process bug. The
  Censor/Codeaudit are NOT part of the workflow and do NOT control agents (operator,
  2026-08-30): their scope is doctrine design, new-contour design, global audit,
  operator-tasked audit, and emergency help when a local contour cannot cope.
- New automatic checks (hooks, gates, validators) created by the contour are registered in
  `~/.claude/references/evaluators-registry.md` (via a prompt to the Censor) with a mutation
  test — a check never shown to fail is not a check (#SA-3).

---

## Onboarding workflow (run in order, in the new chat)

- **Phase 0 — confirm intent.** Confirm with the operator: (a) contour name (= working-folder
  basename, e.g. `Цензор`, `GEANT4`, `0_Work`) — this is what mail addressing keys on; (b)
  **project root** this contour owns; (c) **rig**/domain (default AtomFast adb+BLE,
  `references/rig-atomfast.md`) if applicable; (d) operator's **own channel** for
  decision-requests. Don't guess (c)/(d).
- **Phase 1 — register in the operator's zone registry.** Not a script — a doctrine edit: add a
  row to `~/.claude/CLAUDE.md` §12 table (or ask the Censor/operator to add it) and, if the
  contour will send/receive mail, a row in `<WORKSPACE>\_interchat\
  REGISTRY-adresatov.md` mapping contour name → working-folder basename. There is no
  `register.py` step anymore — the file mailbox has no per-role registry file to seed.
- **Phase 2 — check the inbox once, then rely on the global hook.** Look at
  `<WORKSPACE>\_interchat\inbox\<this-contour-folder>\` for anything waiting;
  going forward the global `hooks/interchat_inbox.py` surfaces new mail automatically on each
  turn. Nothing to launch, no `Monitor` watcher — that mechanism is retired (v1.x).
- **Phase 3 — announce the new contour to the Censor** (HL-3, one-time registration — NOT a
  step-report; routine reporting is retired). File to
  `_interchat\inbox\Цензор\` **plus** a `SendMessage` duplicate if the Censor's session is live
  — role, project root, rig summary, operator channel, irreversible allow-list you gate on.
- **Phase 4 — context-layering setup (HL-5).** Scaffold `<project>/references/` + `<project>/audit/`
  before any task work; if the contour owns `<project>/CLAUDE.md`, design it lean from scratch
  (≤6 КБ core, index-table header). Dated incident in a rule = simultaneous `audit/incidents-<month>.md`
  entry, not «later».
- **Phase 5 — staff the internal fleet (optional).** If the work needs a fleet, `/workflow bootstrap
  <name> --tier BALANCED`. One-off fan-out → `Workflow(...)` directly. Both inherit HL-1.
- **Phase 6 — work the task loop.** plan → delegate (HL-1) → **verify it yourself: tier 0
  mechanics on every LLM call + a sterile subagent-verifier for judgment (HL-6)** → gate
  irreversible to the operator (HL-2) → escalate to the Censor ONLY on the four HL-3 cases
  (stuck / doctrine-level lesson / requested audit / routed adjudication) → keep the operator
  channel free (background dispatch, never foreground).

---

## Files in this skill

- `references/context-layering.md` — HL-5 full body.
- `references/rig-atomfast.md` — domain pack: adb + AtomFast BLE, reversible-vs-irreversible map, worked first task.
- `references/bus-protocol.md` — **frozen, historical only.** Describes the retired
  `cc-interchat-bus` (v1.x). Do not follow for new work — kept so incident history and script
  provenance aren't lost.
- `scripts/bus_lib.py`, `scripts/register.py`, `scripts/watch.py`, `scripts/watchdog.py`,
  `scripts/step_report.py`, `scripts/_smoke_probe.py` — **retired v1.x bus tooling, unused by
  this version.** Not deleted (history/rollback reference); do not invoke for new onboarding.

## Anti-patterns (do not)

- Template/bulk work in the contour's own context — Ollama's job; a >60k-token step with no delegation is a process bug (HL-1).
- Treating a Censor ACCEPT / mailbox message as permission to push/publish/flash — needs the operator's own-channel «да» (HL-2, non-transitive).
- **Writing a mailbox file and treating it as delivered** — the file alone is not proof of
  delivery and is not sufficient; the `SendMessage` duplicate to a live session is MANDATORY,
  and even then only a `*.read.md` marker or a reply is proof (HL-3).
- **Trying to wake a sleeping recipient session** — impossible and wastes the operator's tokens;
  the file waits for the recipient's next natural turn.
- Reviving the v1.x `Monitor`-based watcher — retired; the global inbox hook covers receiving.
- **Sending routine step-reports / ACKs / status pings to the Censor** — retired 2026-08-30;
  the Censor is not part of the workflow. Write only on the four HL-3 cases.
- **Shipping without closing tiers 0–1 yourself**, or waiting for the Censor to verify — the
  contour closes its own cycle (HL-6); «надзор потом проверит» is a process bug.

## История

- 2026-08-23 — переписан под #BUS-2 (файловый ящик) по прямому указанию оператора: «перепиши.
  и укажи обязательно уведомляй в сессию». Версия 1.x (watcher-based `cc-interchat-bus`) закрыта
  оператором 16.08.2026 («шина не нужна») и хранится только как история в
  `references/bus-protocol.md` + `scripts/`. HL-3/HL-4 версии 1.x слиты в один HL-3 (file +
  mandatory session-notify); HL-6 версии 1.x стал HL-5; нумерация остальных не менялась.
