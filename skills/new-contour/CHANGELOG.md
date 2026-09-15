# new-contour — CHANGELOG

All notable changes to this skill follow SemVer (`vMAJOR.MINOR.PATCH`).
Auto-push policy: every SemVer bump is pushed via `scripts/bump_and_push.py`.

## v1.5.0 — 2026-06-16 — HL-6: context-layering strategy + Phase 4 bootstrap setup

Trigger: после lossless lean-рефакторинга 2026-06-15/16 (`~/.claude/CLAUDE.md`
93→27 КБ, `надзорный/CLAUDE.md` 21→12 КБ; always-on пол 114.8→38.8 КБ, −66%) разведка
скиллов и папок агентов показала, что та же логика применима шире: SKILL.md приватного
проектного скилла спектрометрии 90 КБ, `esp32-dev/SKILL.md` 76 КБ, SKILL.md скилла сетевого контура 26 КБ — все с явным
смешением слоёв (правила + narrative + инциденты-с-датами в одном теле). Каждый
триггер скилла грузил весь архив. Operator-запрос 2026-06-16: «создай стратегию
снижения размера контекста путём дробления файлов на части (известные проблемы,
инциденты и т.д.). Стратегию необходимо зафиксировать в скилл по созданию новых
агентов».

What this adds:
- **HL-6 hard-lock** — load-frequency ladder (L1 always-on ≤ 14 КБ, L2 trigger-on
  ≤ 8 КБ, L3 on-demand `references/*`, L4 never-auto `audit/`+history) + 3-слойный
  разрез каждого артефакта знания (A императив inline, B методика → `references/`,
  C история/инцидент → `audit/`+history-файл). Lossless-протокол: verbatim backup
  ПЕРВЫМ шагом, index-таблица в шапке lean-файла, sanity-grep safety-локов и
  реестров на verbatim-присутствие.
- **Phase 4 bootstrap (NEW)** — onboarding нового контура теперь обязательно создаёт
  каркас `<project>/references/` + `<project>/audit/` и проектирует первый
  CLAUDE.md/SKILL.md контура lean по 3-слойному правилу с нуля. Жёсткое правило на
  всю жизнь контура: дата инцидента в теле правила = одновременная запись в
  `audit/incidents-<month>.md`, не «потом отрефакторим». Старые Phase 4 (staff fleet)
  и Phase 5 (work loop) перенумерованы в Phase 5 и Phase 6 соответственно.
- **`references/context-layering.md`** — полное тело правила: load-frequency table,
  маркеры выноса, файловая раскладка 13 типов контента, шаблон index-таблицы, brief
  для subagent при делегировании рефакторинга, метрики успеха, carve-outs,
  anti-patterns с наблюдёнными примерами (смешения в проектном скилле спектрометрии и esp32-dev).

Changes:
- `SKILL.md` — добавлен HL-6 после HL-5, врезана Phase 4 (context-layering setup),
  старые Phase 4/5 перенумерованы.
- `SKILL.md` frontmatter — version 1.4.0 → 1.5.0.
- `references/context-layering.md` — new file (~9.7 КБ).

Scripts unchanged.

NOT pushed (new-contour public-repo push remains operator-gated; Censor control-space
stays private per 2026-06-14).

## v1.4.0 — 2026-06-15 — sentinel-probe in watch.py + machine-global stall watchdog

Trigger: the bus between two contours (both onboarded via this skill) showed
"notifications aren't arriving" — one contour's `Monitor` watcher had died (heartbeat frozen
~27 min) while envelope #8 from the other contour sat undrained in its
inbox. Two gaps surfaced: (1) the global doctrine's sentinel-probe liveness technique
(`.heartbeat-probe-<ts>.json`) was silently ignored by `watch.py` (it skips files with
no `__id` separator), so a probe produced no signal and could never confirm liveness;
(2) there was no backstop for a watcher that is *dead* — a dead watcher cannot flag
itself, and `bus/wake/` was referenced in SKILL.md but had no script behind it.

What this adds:
- **`watch.py` sentinel-probe branch** — on encountering `inbox/<role>/.heartbeat-probe-*.json`
  the watcher emits one `PROBE-ALIVE inbox/<role>: <fname>` task-notification (proving
  this tick actually ran) and **self-deletes** the probe (ephemeral, never tracked in
  seen, never re-fires). This is what makes the HL-3 pre-start dedup invariant's
  sentinel-probe actually work against new-contour watchers.
- **`scripts/watchdog.py`** — single-shot machine-global health scan. Flags a role
  STALLED when `heartbeat age > --stale-seconds` (default 180) AND ≥1 real pending
  envelope; writes `bus/wake/<role>.STALLED` markers (auto-cleared when healthy), prints
  a health table, appends JSONL to `bus/wake/watchdog.log`. Does NOT run `watch.py` for
  other roles (would corrupt their heartbeat/seen and mask the stall). Run from any live
  chat or via Windows Task Scheduler (recipe in SKILL.md HL-3) for true survives-all-
  chats-down coverage.
- **`scripts/_smoke_probe.py`** — self-cleaning regression test for the probe branch
  (throwaway role, asserts PROBE-ALIVE emitted + probe auto-deleted). PASS verified
  2026-06-15.

Changes:
- `scripts/watch.py` — added the `.heartbeat-probe-` branch inside the inbox scan loop.
- `scripts/watchdog.py` — new file.
- `scripts/_smoke_probe.py` — new file.
- `SKILL.md` HL-3 — corrected the dedup invariant's liveness signal from the wrong
  `INBOX-NEW` term to the actual `PROBE-ALIVE` line + self-delete semantics; expanded
  the 3-line watchdog mention into a full subsection (run command, output reading,
  Task Scheduler recipe).
- `SKILL.md` "Files in this skill" — added watchdog.py + _smoke_probe.py, noted the
  watch.py probe behavior.
- `SKILL.md` frontmatter — version 1.3.0 → 1.4.0.

Both changes smoke-tested against the LIVE bus 2026-06-15 (watchdog correctly flagged
the stalled role STALLED with the right marker + log line; probe test PASS).

NOT pushed (new-contour public-repo push remains operator-gated; Censor control-space
stays private per 2026-06-14).

## v1.3.0 — 2026-06-06 — HL-5: source git read-only, a tester works only in a clone

Standing operator rule (оператор, 2026-06-06, verbatim: «Запрети тестеру изменять
что-то в исходном гите проекта. Работа только в клоне!!!»). Real trigger: a tester
contour (atomfast) applied an operator-approved code fix (Option A,
`OrchestratorService.java:182`) directly to the project's canonical source working
tree. The operator drew a hard line — a tester never mutates the source-of-truth git.

What this adds:
- **HL-5 hard rule** — a tester/verifier contour NEVER mutates the canonical
  (source-of-truth) git of the project under test. All build / deploy / test /
  fix-experiment work happens in a **clone**; canonical is a **read-only reference**.
- **Zero mutation to canonical** — no commit, push, tag, branch, or working-tree
  edit that reaches origin.
- **Landing a validated fix** — a fix the tester validates in the clone lands in
  canonical ONLY by the owner/operator's hand under HL-2 (operator-gate), NEVER by
  the tester. The tester's role ends at a verdict + terminal artifacts.
- **Composes with HL-1 and HL-4** — clone-only is the *location* constraint on the
  executor work HL-1 already delegates; every step still reported per HL-4.

Changes:
- `SKILL.md` — inserted HL-5 after HL-4, before the "---" preceding the Onboarding
  workflow.
- `SKILL.md` frontmatter — version 1.2.0 → 1.3.0.

Scripts unchanged.

NOT pushed (claude-skills first-push remains operator-gated per task #5).

## v1.2.0 — 2026-06-06 — read/manage/delegate role border + recursive subagent contract (HL-1)

Operator sharpened HL-1 to an absolute and ordered it locked permanently for
**all subagents** and in this (the chat-creation) skill: «сам ничего не делай,
только читай и управляй — делегируй задачи» → «зафиксируй навсегда … для всех
субагентов и в скилле по созданию чатов».

What this adds on top of the existing HL-1 delegate-by-default:
- **Role in three verbs** — an orchestrating contour only Reads (read-only),
  Manages (verdicts/synthesis/adjudication/operator-gate/briefs/own control-space),
  and Delegates all executor work. Nothing done by hand beyond a single read.
- **The border that bites** — "reading a fact" (single lookup, OK by hand) vs
  "investigating by hand" (a *series* of `gh`/`git`/`grep`/`python` commands to
  find out or assemble evidence → must delegate to a background subagent, its
  template part to Ollama). Even read-only command series count as investigation.
- **Recursive "для всех субагентов" clause** — every brief a contour writes to a
  subagent MUST embed the same contract verbatim (Claude tokens only for
  synthesis/decisions/git/anti-hallucination; template/bulk → Ollama; investigative
  part may fan out further; a sub-orchestrator inherits read/manage/delegate). A
  brief that omits the Ollama delegation for its template part is a process bug.

Real self-correction that motivated the lock (censor contour, 2026-06-06): a CI-RED
root-cause for a supervised repo was run by hand through `gh run list` /
`gh run view --log-failed` / `gh api contents` instead of being delegated to a
subagent returning a digest. Recorded in SKILL.md HL-1 as the reference anti-pattern.

Changes:
- `SKILL.md` HL-1 — inserted "The role in three verbs", "The border that bites",
  and the recursive subagent-contract block, after the pre-flight bullet and before
  the provenance paragraph.
- `SKILL.md` frontmatter — version 1.1.0 → 1.2.0.

Scripts unchanged.

NOT pushed (claude-skills first-push remains operator-gated per task #5).

## v1.1.1 — 2026-06-06 — watcher visible-naming requirement (HL-3)

New contract requirement (HL-3): the `Monitor` task `description` for the
inbox watcher MUST start with a high-visibility marker (`📬` or equivalent),
include the **role name in CAPS**, and cue the protocol (`cc-interchat-bus`).
Generic descriptions like `"watcher"` or `"inbox monitor"` are forbidden —
operator UI surfaces background tasks by description, and a generically-named
watcher is indistinguishable from any other Monitor task, so the operator
cannot verify-by-glance that "mail" is running.

Real failure mode observed 2026-06-06 in the **censor** contour itself:
operator reported "у тебя не вижу в фоне процесса почты" about a healthy
watcher with a generic description. Watcher was alive (sentinel-probe
confirmed prior restart) but operator-invisible. Forward fix: this
requirement, applied retroactively to all contours (advisory broadcast
gamma + atomfast same day).

Changes:
- `SKILL.md` HL-3 — added "Visible-naming requirement" subsection right
  after the `Monitor` command block, with the 📬 + role-CAPS + protocol-cue
  template and operator-discoverability rationale.
- `SKILL.md` HL-3 Monitor example — added `description: "📬 TESTER BUS-MAIL
  WATCHER ..."` line so the template is copy-pasteable.

Scripts unchanged.

NOT pushed (claude-skills first-push remains operator-gated per task #5).

## v1.1.0 — 2026-06-06 — pre-start watcher dedup invariant

New contract requirement (HL-3): before spawning any watcher Monitor task,
execute the pre-start dedup check. Closes a real failure mode observed
2026-06-06 in two contours on the same machine — atomfast had a 51m pre-
compaction watcher running alongside a 25m post-compaction one; gamma had
72m + 1m19s. The bus stayed safe (atomic `os.replace` move), but each chat
doubled its INBOX-NEW notification token cost for zero detection benefit.

Changes:
- `SKILL.md` HL-3 — added "Pre-start dedup invariant" subsection (TaskList
  scan → sentinel-probe verify → REUSE if alive OR TaskStop+replace if
  silent; NEVER spawn parallel).
- `SKILL.md` Anti-patterns — added "Do NOT spawn a second watcher Monitor
  task" bullet.
- `references/bus-protocol.md` §4.1 — new section with full restart-vs-
  revival rationale, sentinel-probe procedure, and 2026-06-06 incident
  citation.
- `references/bus-protocol.md` §6 anti-patterns — added §3a parallel-watcher
  bullet cross-referencing §4.1.

Scripts unchanged: `watch.py` is already single-shot main-loop correct
(§4); the parallel-watcher bug lives at the orchestration layer where a
contour decides whether to spawn a fresh Monitor task at all, not inside
the watcher script itself.

NOT pushed (claude-skills first-push is operator-gated per task #5).

## v1.0.0 — 2026-06-06 — initial sync

Initial publish of the working copy that bootstrapped the **atomfast** contour
2026-06-06 (POCO F5 rig, supervised by censor). Sanity-tested round-trip
(register → empty scan → send → watch surfaces NEW MAIL → step_report → dedup scan)
before declaring stable.

Contents at this version:
- `SKILL.md` — four hard-locks (HL-1 delegate / HL-2 stay in contact /
  HL-3 watcher / HL-4 step reports) + bootstrap workflow + composition with
  `/workflow` and bus protocol.
- `references/bus-protocol.md` — `cc-interchat-bus` schemas, lifecycle,
  watcher main-loop rationale, push/publish non-transitivity (Rule #7),
  hard anti-patterns.
- `references/rig-atomfast.md` — adb / BLE safety map for PC ↔ phone ↔
  AtomFast dosimeter rigs (used by the first executor contour).
- `scripts/register.py` — Phase-1 registration with live-role guard.
- `scripts/watch.py` — Phase-2 single-shot watcher (run via Monitor tool).
- `scripts/step_report.py` — HL-4 step reporting wrapper.
- `scripts/bus_lib.py` — atomic envelope/registry/audit primitives.
- `scripts/bump_and_push.py` — this version-bump + push automation.
