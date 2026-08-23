# hard-locks.md — enforcement detail for HL-1 / HL-3 / HL-5

Reference for the `new-contour` skill. Core `SKILL.md` states each hard-lock as an
**imperative + pointer**; the verbose enforcement mechanics, code blocks,
operator-provenance quotes, and observed failure modes live here — load on demand when
wiring or debugging a contour. HL-2 / HL-4 are short enough to stay wholly in core;
HL-6's full body is in `context-layering.md`.

---

## HL-1 — Delegate by default (detail)

**The role in three verbs — read / manage / delegate.** Sharpened 2026-06-06 by the
operator (verbatim: «сам ничего не делай, только читай и управляй — делегируй задачи»,
«зафиксируй навсегда … для всех субагентов»). An orchestrating contour does exactly
three things and nothing else:

- **Reads** (read-only): bus envelopes, `registry/<role>.json`, contour status, *one*
  file / *one* field to cite in a verdict. A single lookup is reading.
- **Manages**: verdicts, synthesis, adjudication, operator dialogue, irreversible-gating,
  writing briefs, and edits to its **own control-space** (TaskList, this/its skill
  doctrine, audit log). Meta-management of its own role is NOT delegated.
- **Delegates** all executor work: bulk/template/parse → Ollama `guarded_generate`;
  multi-step file work **and investigation** → background subagent; work *inside another
  contour* (code edits, builds, tests, that contour's git) → that contour over the bus.

**The border that bites — "reading a fact" vs "investigating by hand".** A single read
for a citation is fine. The moment you need a *series* of commands (`gh run view`,
`git log`, repeated `grep`, ad-hoc `python`) to *find something out* or *assemble
evidence*, that is **investigation** — delegate it to a background subagent (its template
part → Ollama) and take back only the digest plus the thing to judge. Self-correction
(2026-06-06, censor contour): a CI-RED root-cause run by hand through `gh run list` /
`gh run view --log-failed` / `gh api contents` is the anti-pattern; the same diagnosis
belongs in a subagent that returns a JSON/markdown summary. Even read-only command
*series* count as investigation.

**Recursive — the "для всех субагентов" lock.** Every brief a contour writes to a
subagent MUST embed this same contract verbatim: the subagent's own Claude tokens go to
synthesis / decisions / git / anti-hallucination only; its template/bulk part goes to
Ollama `guarded_generate`; its multi-step or investigative part may fan out to its own
background subagents; and if that subagent itself orchestrates, it inherits read / manage
/ delegate in turn. A brief that does not name the Ollama delegation for its template part
is itself a process bug the Censor flags on sight.

**Provenance the Censor will demand.** A step that did multi-step work without a subagent
task-id (or a bulk step without an Ollama helper) is reported as solo work, and the Censor
withholds ACCEPT on process-hygiene grounds.

---

## HL-3 — Run a Censor-watcher (detail)

**Start it from the contour's own main loop via the `Monitor` tool**, NEVER as a
`&`/`nohup`/`disown` background process spawned by a subagent (those become zombies on
session reload). Replace `tester` with the role:

```
Monitor tool, persistent, command:
  while true; do PYTHONUTF8=1 python C:/Users/<you>/.claude/skills/new-contour/scripts/watch.py tester; sleep 15; done
description: "📬 TESTER BUS-MAIL WATCHER (role=tester, cc-interchat-bus) — persistent inbox monitor, sentinel-aware, 15s tick"
```

**The `while true; … sleep 15` wrapper is mandatory, not optional (verified 2026-06-21).**
The Monitor tool **ends the watch when its command exits** — a bare `watch.py` call is
single-shot, so it fires once and the watcher dies immediately (caught live: a no-wrapper
Monitor task "stream ended" on the first empty scan). The loop is exactly the unbounded
command the Monitor tool's own docs prescribe for "one notification per occurrence,
indefinitely". Each tick exits+flushes, so a `NEW MAIL` line surfaces on the next scan;
empty scans print nothing → no spurious notification.

**Visible-naming requirement (HL-3 invariant, added v1.1.1).** The `Monitor` task
`description` MUST start with a high-visibility marker (`📬` or equivalent unicode glyph
the operator can spot at a glance), include the **role name in CAPS**, and cue the protocol
(`cc-interchat-bus`). Generic descriptions like `"watcher"` or `"inbox monitor"` are
forbidden — the operator's UI surfaces background tasks by description text, and if your
watcher is indistinguishable from any other Monitor task, the operator cannot verify by
glance that "mail" is actually running. This is an **operator-discoverability**
requirement, not cosmetics: a watcher that runs silently and unnamed is functionally
equivalent to a missing one when the operator needs to confirm liveness without a forensic
dig. The 📬 prefix + role-in-CAPS template is the minimum; teams may add more (heartbeat
tick, role-coloured emoji) but never less. Real failure mode observed 2026-06-06: operator
reported "не вижу в фоне процесса почты" about an alive watcher with a generic description;
the watcher was healthy but invisible. Forward fix: this requirement.

`watch.py` is a single-shot scan (prints 0..N lines, exits 0) the `Monitor` tool runs
**inside the `while true; … sleep 15` wrapper above** (the Monitor tool ends the watch on
command exit, so the loop is what keeps it live); it emits one task-notification line per
NEW Censor→contour envelope, refreshes the registry heartbeat, and tracks seen ids in
`_state/<role>_watcher_seen.txt`. On every `<task-notification>` the contour: drains its
inbox, reads the Censor envelope in full, re-anchors its role, acts.

**Machine-global watchdog (`scripts/watchdog.py` → `bus/wake/`, added v1.4.0).** The
per-contour watcher is the fast path; this is the backstop that catches a watcher that has
*died* (its own `Monitor` loop can no longer flag itself). `watchdog.py` is a single-shot
health scan — run it from ANY live chat, or on a Task Scheduler cadence so it survives every
chat being down. It does **not** run `watch.py` for other roles (that would corrupt their
heartbeat/seen and hide the stall); it only reads each role's registry + inbox and flags a
role **STALLED** when `heartbeat age > --stale-seconds` (default 180) **AND** it has ≥1 real
pending envelope. For each stalled role it writes a `bus/wake/<role>.STALLED` marker (cleared
automatically when the role goes healthy again), prints a health table, and appends a JSONL
line to `bus/wake/watchdog.log`.

```bash
PYTHONUTF8=1 python C:/Users/<you>/.claude/skills/new-contour/scripts/watchdog.py
# optional: --stale-seconds 120   (tighten the staleness window)
```

Reading the output: a row `raspi5 age 1642s pending 1 → STALLED` means raspi5's watcher is
dead while mail waits — go to that chat and run the pre-start dedup invariant to revive it
(its `_state/<role>_watcher_seen.txt` does NOT yet contain the pending id, so the revived
watcher re-emits the missed `NEW MAIL` immediately — nothing is lost).

**Truly machine-global (survives ALL chats being down) — Windows Task Scheduler:**

```powershell
$action  = New-ScheduledTaskAction -Execute "python" `
  -Argument "C:/Users/<you>/.claude/skills/new-contour/scripts/watchdog.py"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5)
$env_settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "cc-bus-watchdog" -Action $action `
  -Trigger $trigger -Settings $env_settings -Description "cc-interchat-bus stall backstop"
```

Do not disable either layer.

**Pre-start dedup invariant (MANDATORY, runs every time before you spawn a Monitor watcher
task — session start, post-compaction revival, operator-flagged restart):**

1. `TaskList` → find every running task whose command line matches `inbox/<role>` /
   `watch.py <role>`. Read the list, don't trust memory.
2. **If 0 matches** → spawn normally (`Monitor`, persistent, `watch.py <role>`).
3. **If ≥1 match** → for each, sentinel-probe: drop
   `inbox/<role>/.heartbeat-probe-<ts>.json` (minimal valid JSON, e.g. `{}`). On its next
   tick `watch.py` emits a `PROBE-ALIVE inbox/<role>: <probe-fname>` task-notification **and
   self-deletes the probe** (so it never re-fires) — you do not delete it yourself. If that
   `PROBE-ALIVE` line naming your probe arrives → that watcher is **alive**; **REUSE it, do
   not spawn another.** If 120s passes with no `PROBE-ALIVE` → that watcher is **dead**;
   `TaskStop` it (your own task id, never a peer PID — §HL-2 hard rule), then spawn the
   replacement. (Added v1.4.0: the `.heartbeat-probe-` branch in `watch.py` — older copies
   silently dropped these files because they lack the `__id` separator, so the probe never
   produced a signal.) NEVER run two watcher tasks for the same inbox: each one fires
   `INBOX-NEW` on every envelope, so two watchers double your token burn for zero detection
   benefit. This is a real failure mode observed 2026-06-06 in two contours (51m + 25m on
   atomfast, 72m + 1m19s on gamma).

The Monitor tool itself restarts the script cleanly across a single chat reload; the problem
this invariant fixes is **session-compaction revival** — a fresh `revival #N+1` Monitor task
spawned while `revival #N` is still alive from before the compaction.

---

## HL-5 — Source git is read-only: a tester works only in a clone (detail)

Standing operator rule (the operator, 2026-06-06, verbatim: «Запрети тестеру изменять что-то в
исходном гите проекта. Работа только в клоне!!!»). A tester/verifier contour **NEVER**
mutates the canonical (source-of-truth) git of the project under test. All build / deploy /
test / fix-experiment work happens in a **clone**; the canonical repo is a **read-only
reference** (`git show` / read files — yes; write — no).

- **Zero mutation to canonical**: no `commit`, `push`, `tag`, `branch`, or any working-tree
  edit that reaches the canonical origin. Even an operator-approved code fix is applied and
  tested **in the clone**, not in the source.
- A fix the tester validates (in the clone, by post-deploy fact) lands in the canonical
  source **ONLY by the owner/operator's hand under operator-gate (HL-2)** — never by the
  tester directly. The tester's deliverable ends at "fix works in the clone, here are the
  terminal artifacts"; the canonical landing is a separate, owner-gated step.
- Composes with HL-1 (the Censor's own review subagents already clone read-only) and HL-4
  (the clone topology is reported as provenance, so the Censor can confirm the canonical
  stayed pristine).
- **Why**: the source-of-truth must stay pristine and reproducible. A tester that edits it
  conflates "testing a change" with "committing a change", and an unreviewed tester-mutation
  in canonical history is exactly the irreversible blast-radius HL-2 exists to prevent. Real
  trigger 2026-06-06: a tester applied an operator-approved code fix directly to the project
  source working tree; the operator drew the hard line — test in a clone, never the source.
