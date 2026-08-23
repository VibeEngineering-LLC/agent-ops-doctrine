# cc-interchat-bus — the cross-contour protocol

This file documents the **bus** that the `new-contour` skill onboards a chat onto.
Read it before editing any script in this skill; the schemas here are the contract
every contour (censor, gamma, finance, secretary, webmaster, and now yours) speaks.

The bus is **not** the in-project subagent fleet. Subagents inside one chat use
project-local mailboxes (`<project>/_state/agent_*/inbox/`) and are wired by
the `/workflow` skill. The bus is **machine-global** — different Claude chats,
on different projects, surviving each other's restarts.

---

## 1. Where it lives

Root: `%LOCALAPPDATA%/cc-interchat-bus/` (Windows; on POSIX, the equivalent
under the user's data dir).

```
cc-interchat-bus/
├── registry/        <role>.json — one per active contour
├── inbox/<role>/    incoming envelopes (drained by the role's watcher)
├── processed/<role>/ where the role moves envelopes once acted-on
├── audit/log.jsonl  append-only event log (single file, shared)
├── wake/            machine-global watchdog (loop + .watchdog.loop.lock + watchdog.log)
├── _state/          <role>_watcher_seen.txt — per-role watcher dedup
├── tmp/             atomic-write staging area
└── parked/          envelopes held pending operator decision
```

All directories are auto-created by `bus_lib.py` on first use. The `tmp/`
directory is the staging area for atomic writes: write to `tmp/<name>.tmp`,
then `os.replace` into the target. Atomic on both NTFS and POSIX.

---

## 2. Schemas (canonical — match these exactly)

### 2.1 Envelope (inbox / processed)

Filename: `<fname_ts>__<id>.json` where `fname_ts` is `YYYY-MM-DDTHH-MM-SS-ffffff Z`
(colons replaced with hyphens — Windows filename rule) and `id` is `uuid4().hex`.

```json
{
  "id": "542d1473bffd49a8b3494a8edd283ed8",
  "ts": "2026-06-06T09:18:42.123456Z",
  "from": "censor",
  "to": "gamma",
  "type": "ack",
  "subject": "ACK CONDITIONAL GO TCS#47",
  "body": "...full UTF-8 body, may include markdown, may include code blocks...",
  "refs": ["fa597508976fc20041283ded839b7337", "agent-a-math:aae18fd5721f2a546"],
  "action_class": "read-only",
  "requires_operator": false,
  "in_reply_to": "fa597508976fc20041283ded839b7337"
}
```

Field rules:
- `id` — `uuid4().hex` (32 lowercase hex chars). Globally unique.
- `ts` — UTC, format `%Y-%m-%dT%H:%M:%S.%fZ` (microsecond precision).
- `from`/`to` — bus role names (`censor`, `gamma`, etc.).
- `type` — `ack`, `disclosure`, `step_report`, `decision-request`, `verdict`,
  `re-anchor`, `audit-request`, ... Free-form lowercase; receiver decides handling.
- `subject` — short one-line, MUST encode enough state for the recipient to
  triage without opening the body.
- `body` — UTF-8, no length cap. Use markdown.
- `refs` — ids of prior envelopes, SHAs, task-ids, URLs — anything the recipient
  may want to look up.
- `action_class` — one of `read-only` | `reversible` | `irreversible`. Drives
  the operator-gate (§5).
- `requires_operator` — derived: `action_class == "irreversible"`. Receivers
  MAY trust this flag (the sender library sets it).
- `in_reply_to` — id of the envelope this one responds to, or `null`.

JSON encoding: `ensure_ascii=False` (preserve Cyrillic etc.), `indent=1`
(human-readable in `cat`).

### 2.2 Registry (`registry/<role>.json`)

```json
{
  "role": "tester",
  "session_id": "8f3a9c2d1e4b4a5c8d9e0f1a2b3c4d5e",
  "status": "working",
  "last_heartbeat_ts": "2026-06-06T09:25:51.876543Z",
  "pid": 25400
}
```

- `role` — must match the filename stem.
- `session_id` — `uuid4().hex`, regenerated on each `register.py` call (so
  peers can detect a fresh session vs a heartbeat-restart).
- `status` — `working` | `idle` | `parked` (free-form lowercase).
- `last_heartbeat_ts` — refreshed by the role's watcher every cycle.
- `pid` — OS pid of the registering process (informational only — NEVER
  used to kill anyone; see §6 "Hard anti-patterns").

JSON encoding: `ensure_ascii=False`, `indent=2`.

### 2.3 Audit log (`audit/log.jsonl`)

One JSON object per line, append-only:

```json
{"event_ts":"...","event":"send","id":"...","from":"...","to":"...","type":"...","subject":"...","action_class":"...","requires_operator":false,"in_reply_to":null,"filename":"..."}
{"event_ts":"...","event":"register","role":"tester","session_id":"...","pid":25400,"forced":false}
{"event_ts":"...","event":"drain","id":"...","by":"tester"}
{"event_ts":"...","event":"park","id":"...","by":"tester","reason":"irreversible — operator decision pending"}
```

Required fields for `send`: `event_ts, event, id, from, to, type, subject,
action_class, requires_operator, in_reply_to, filename`. Other events (`register`,
`drain`, `park`, `decision`, etc.) define their own field sets.

---

## 3. Lifecycle of one envelope

```
sender                                receiver
  │                                      │
  │ 1. compose envelope dict             │
  │ 2. tmp/<name>.tmp ← json.dumps        │
  │ 3. os.replace → inbox/<to>/<name>     │
  │ 4. audit/log.jsonl ← "send" line      │
  │                                      │
  │       receiver's watcher fires       │
  │ ─────────────────────────────────→   │
  │                                      │ 5. read inbox/<to>/<name>
  │                                      │ 6. act on it (drain, ack, reply, park)
  │                                      │ 7. mv inbox/<to>/<name> → processed/<to>/
  │                                      │ 8. audit/log.jsonl ← "drain" / "park" line
```

If step 6 reads `action_class=irreversible` and the receiver is the executor,
it does NOT execute. It either parks the envelope to `parked/` and emits a
`decision-request` step-report (HL-4) to its operator's own channel, or it
treats the envelope as advisory only.

---

## 4. Watchers — why main-loop only

The watcher MUST run from the contour's main loop via the Claude **Monitor
tool**, as a `while true; do watch.py <role>; sleep 15; done` loop wrapping the
single-shot script. (The Monitor tool **ends the watch when its command exits**,
so a bare `watch.py` invocation fires exactly once and stops — verified
2026-06-21; the loop is the unbounded command Monitor's own docs prescribe for
"one notification per occurrence, indefinitely".) Why main-loop:

- A `&`/`nohup`/`disown` watcher spawned from a subagent process becomes a
  **zombie** the moment the chat session reloads or the subagent exits. You
  end up with a registered role whose heartbeat never refreshes and whose
  inbox never gets drained, while a new chat reuses the role name and now
  two "live" entries fight for the same envelopes. This is the literal lesson
  the gamma project's `MAILBOX_PROTOCOL.md` records.
- The Monitor tool is bound to the chat's main loop. When the chat reloads,
  the Monitor restarts cleanly with it. There is no zombie window.
- The single-shot script (`watch.py`) is cheap to run (one inbox scan plus a
  heartbeat write) — looping it on a ~15 s cadence wastes nothing, and each tick
  exits+flushes so a `NEW MAIL` line surfaces on the next scan.

There is ALSO a machine-global watchdog at `bus/wake/`. That is a backstop
that wakes a stale-but-undrained contour when ALL its watchers are down. It
is not a substitute for the per-contour watcher; it is the floor.

### 4.1 Pre-start dedup (MANDATORY — restart-revival zombie protection)

The Monitor-tool restart is clean across a single chat reload — the script
restarts with the chat, no zombie window. The failure mode this section
covers is different: **session-compaction revival**. When the chat compacts,
the SessionStart hook fires and the chat usually spawns a fresh watcher
("revival #N+1") — but the **previous** Monitor task ("revival #N") can still
be alive in the task table, untouched by the compaction. You end up with two
parallel watchers on one inbox, both reading every envelope, both firing
`INBOX-NEW` for every new file. The bus is safe (move via `os.replace` is
atomic on NTFS/POSIX — the second mover finds the file gone and skips), but
the chat's context burns double the notification tokens per envelope for
zero detection benefit.

Observed 2026-06-06 in two contours on this very machine: atomfast had a
51m pre-compaction watcher running alongside a 25m post-compaction one;
gamma had 72m + 1m19s. Both contours cleaned up after operator-flagged
sanity-check; both reported the same root cause — revival path skipped the
dedup check.

**Before spawning a watcher Monitor task — every time, including post-
compaction revival, including after operator-flagged restart — execute:**

1. `TaskList` to enumerate currently running tasks. Match by command line
   substring `inbox/<role>` or `watch.py <role>`. Do not rely on memory of
   "I spawned a watcher earlier" — memory does not survive compaction; the
   task table does.
2. **Zero matches** → safe to spawn. Proceed to the normal `Monitor`
   invocation in `SKILL.md` HL-3.
3. **One or more matches** → for each, run a sentinel-probe:
   - Drop `inbox/<role>/.heartbeat-probe-<ts>.json` with minimal valid JSON
     body (e.g. `{"sentinel": true, "ts": "<iso>"}`). The probe filename
     starting with `.heartbeat-probe-` signals drain scripts to ignore it
     as an envelope.
   - Wait up to 5 seconds for the candidate watcher to emit an `INBOX-NEW`
     event mentioning the probe filename.
   - Delete the probe file regardless of outcome (cleanup).
   - **Event fired** → that watcher is alive. **REUSE it.** Return early;
     do NOT spawn the new Monitor task.
   - **No event in 120s** (full §6.3 procedure timeout) → that watcher is
     dead/silent. `TaskStop` it (your own task id; never `taskkill` a peer
     PID — §6 anti-pattern #1), then spawn the replacement.

Skipping this invariant is how the parallel-watcher anti-pattern reproduces.
A fresh `register.py` run after compaction is not enough — `register.py`
guards the role registry, not the Monitor task table.

---

## 5. action_class and the operator-gate

The bus carries the gate, not the actor. Sender labels the envelope's class;
receiver enforces:

| `action_class`  | Receiver's autonomy                                         |
|-----------------|-------------------------------------------------------------|
| `read-only`     | Act autonomously. Examples: inspect, summarize, report.     |
| `reversible`    | Act autonomously. Examples: edit local file, install reversible test app, run benign adb command. |
| `irreversible`  | DO NOT EXECUTE. Park + decision-request to the operator in **the receiver's OWN channel**, NOT via this bus. Wait for the operator's explicit «да» in that channel. |

### 5.1 Push/publish non-transitivity (Rule #7)

An ACCEPT from the Censor over this bus does NOT authorize the executor to
push, publish, release, flash, or otherwise perform an irreversible step.
Censor only JUDGES; execution of an irreversible step needs the operator's
own-channel permission. Authority is not transitive through the bus.

This is the single most important property to internalize. The bus is
optimized for fast, low-friction information flow; the operator-gate stays
in the operator's own channel by design.

### 5.2 Irreversible allow-list (global default)

These action classes are ALWAYS irreversible regardless of context:

- `git push`, `git push --force`, any push to a remote.
- `gh release create`, GitHub release publication, tag push.
- Production deploys, prod database writes.
- Credential creation / rotation / write.
- Legal/regulatory publication, public-facing text post.
- `rm -rf`, mass delete, `git reset --hard origin/...` against published refs.
- For hardware-rig contours: any flash, factory reset, partition format,
  device unpair-and-erase, write to personal-user storage. The per-rig
  reference (`rig-*.md`) extends this list with rig-specific cases.

---

## 6. Hard anti-patterns

Each of these has burned a contour at least once. Treat them as code-enforced
rules in the helper scripts, not advisory.

1. **NEVER kill another process's PID.** The registry stores `pid` for
   informational purposes only. Sending SIGKILL/`taskkill` to a peer's pid
   may sever a session that is one second away from completing a drain.
   The operator stops a peer chat; you do not.

2. **NEVER clobber a live role.** `register.py` checks `is_live(role,
   stale_s=900)` and refuses unless `--force`. Two chats answering as the
   same role race on envelopes; only one drain wins, the other loses work.

3. **NEVER spawn the watcher as a backgrounded subprocess.** See §4. The
   Monitor tool runs `watch.py` wrapped in a `while true; … sleep 15` loop from
   the main loop.

3a. **NEVER spawn a second watcher Monitor task for an inbox you already
   watch.** Post-compaction revival is the high-risk site; run the §4.1
   pre-start dedup invariant before every Monitor task creation. Observed
   2026-06-06 in two contours (atomfast 51m+25m, gamma 72m+1m19s) — the
   bus stayed safe, but each chat doubled its notification token cost for
   no detection benefit. The Monitor task table outlives compaction in a
   way that operator memory does not; always check it.

4. **NEVER write directly into `inbox/<to>/` or `registry/<role>.json` from
   ad-hoc code.** Use `bus_lib.send()` and `bus_lib.write_registry()`. Direct
   writes skip the atomic tmp+replace and skip the audit-log entry; you lose
   the trail the Censor depends on.

5. **NEVER skip the audit-log entry.** It is append-only; never edit it,
   never rotate it without first archiving. The Censor's six-corner reads
   from it on demand.

6. **NEVER carry credentials in an envelope.** No tokens, no Basic-auth, no
   passwords, no personal financial data. The audit-log is plain JSON on
   disk; an envelope-borne credential is now a disk-borne credential.

---

## 7. Implementation reference

All of these are implemented in `scripts/bus_lib.py`:

| Function                       | Purpose                                        |
|--------------------------------|------------------------------------------------|
| `now_iso()` / `fname_ts()`     | UTC timestamps, microsecond precision          |
| `inbox(role)` / `processed(role)` / `registry_file(role)` / `seen_file(role)` | Path resolvers |
| `read_registry(role)`          | Read role's registry, returns `{}` if absent   |
| `write_registry(role, ...)`    | Atomic write of registry (preserves session_id) |
| `heartbeat(role)`              | Refresh just `last_heartbeat_ts`               |
| `is_live(role, stale_s=900)`   | True iff heartbeat younger than `stale_s` s    |
| `send(frm, to, ...)`           | Atomic envelope write + audit-log `send` line  |
| `audit_append(rec)`            | Append one JSON record to `audit/log.jsonl`    |

If you need a new envelope type, you do NOT need to extend `bus_lib.send()`
— just pass a new `etype` string. The schema is intentionally open.
