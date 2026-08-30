# SKILL reference — orchestration: scalable role multiplicity

> Reference material split out of `SKILL.md` (T-16). Loaded on demand when
> the orchestrator needs to scale a role horizontally (N parallel workers of
> the same type) under the fan-out/fan-in canon.

## Scalable role multiplicity

> `roles:` in `workflow.yaml` defines role _types_, not a hard cap on the
> number of running agents. The Strategist sizes the fleet to the shape of
> the backlog, spawning N parallel instances of the same role when ≥2
> independent same-typed tasks sit in the queue.

### Principle

`workflow.yaml` `roles:` are role _types_. The Strategist (D) sizes the
running fleet to the shape of the queue, not the YAML's role count. Adding
a second Math instance does not change the workflow definition — it's a
runtime decision by D when two or more same-typed tasks are independent.
Math (A) is the canonical example: with two non-overlapping math bugs in
the backlog, two Math agents (A and A2) run in parallel.

### When to scale a role horizontally

The orchestrator spawns N parallel instances of role R only when all of:

- The backlog contains ≥2 items whose decision profile maps to R
- The items' file scopes (or other resource scopes) are disjoint
- A merge order is obvious (which N's work is foundational, which sits on top)
- Wall-clock pressure justifies the coordination overhead (single-instance
  serial would meaningfully delay the next milestone)

If any of these fail → keep R at multiplicity 1 and serialize.

### Naming convention

First instance carries the role letter alone: **A**. Subsequent instances
use the letter + ordinal: **A2**, **A3**, ... Same for B/C. Logs, outbox
subdirs, branch names follow the same pattern (e.g.
`_state/agent_a/outbox/BUG21_*`, `_state/agent_a/outbox/MULTIPLET_V2_*` —
same `agent_a/` dir is fine when filename prefixes disambiguate). For git,
parallel instances each commit on their own branch (e.g.
`agent-a2-issue37-multiplet-v2`).

### Race protection (mandatory)

For every N+1th instance of a role, one of the following protections MUST
be in place:

| Protection | When to use | Cost |
|---|---|---|
| `isolation: "worktree"` (Agent tool) | Default for Math/Reports/Docs N+1 | ~200-500 ms setup + disk per agent |
| Manual `git worktree add` + path injection into the agent brief | When the project lives outside the orchestrator's repo (Agent tool's `isolation: "worktree"` operates on the current repo) | Same disk cost + 1 extra orchestrator step |
| Explicit hands-off list in the brief | When file scopes are obviously disjoint AND a worktree is unwarranted (e.g. doc-only edits) | Cheapest, weakest — needs orchestrator vigilance |

The orchestrator chooses the appropriate protection per launch. A
multi-instance launch without a chosen protection is a process bug.

### Merge order

The Strategist defines the merge order BEFORE launching N+1, not after.
Foundational changes land first; dependent changes rebase on top. The
brief for each N+1th instance includes:

- a "hands-off list" (territory of the lower-index instance)
- the rebase expectation ("D may ask you to rebase your branch after
  instance N lands")

**Cross-territory escalation**: if N+1 genuinely needs to touch the
hands-off list, it STOPS and writes
`_state/agent_<role>/outbox/<task>_CROSS_TERRITORY.md`. The orchestrator
coordinates — never the parallel instance directly.

### Roles that cannot scale

Some roles are singletons by design:

- **Strategist (D)**: there is exactly one conversation with the user.
  Spawning a parallel D produces inconsistent state.
- **Planner (E)** within a single planning cycle: one PLAN draft per
  cycle. Multiple Es in the same cycle produce contradictory drafts. (E
  can run on different cycles in parallel if scopes are clearly different
  — but treat that as the exception.)

Scalable roles: **A** (Math/Numerical), **B** (Reports/Render), **C**
(Docs/Validator-hat). They scale up when the backlog warrants it and back
down to 1 when serial work suffices.

### Not to be confused with Workflow tool fan-out

`Workflow(...)` script's `parallel()` and `pipeline()` fan out **within a
single workflow run** — multiple short-lived subagents doing pieces of one
larger task, all under one orchestrator script.

Scalable role multiplicity is **across independent `Agent(...)` calls** —
multiple long-lived parallel role instances, each addressing its own item
in the backlog, coordinated by the main-loop Strategist directly.

The two patterns compose: a Workflow run can itself spawn multiple
"A-shaped" sub-tasks via `parallel()`, and orthogonally the orchestrator
can have a separate Agent A2 long-running on a different backlog item at
the same time.

### Example (worked, brief)

Backlog state:

| ID | Scope | File(s) | Decision profile |
|---|---|---|---|
| BUG-X | Peak detection regression | `src/peaks.py` | Math (A) |
| #Y | Multiplet clustering rewrite | `src/multiplet.py` | Math (A) |

Both are math-shaped; file scopes disjoint → scale Math to 2 instances.

```
A   on master           working BUG-X         branch: agent-a-bug-x
A2  in wt-issue-Y       working #Y            branch: agent-a2-issue-Y
                                              isolation: worktree
```

Merge order pre-committed by D:

1. A lands first (foundational — touches the peak-detection primitive
   that #Y's clustering may rely on)
2. A2 rebases on the new master if needed
3. D merges A2
4. Validator C runs once over both fixes before the release cut

If A2 discovers it needs to edit `src/peaks.py` mid-task, it writes
`_state/agent_a/outbox/ISSUE_Y_CROSS_TERRITORY.md` and stops. D arbitrates.

---

### FILL THE FLEET (HARD-LOCK 2026-06-04)

> User instruction (recorded 2026-06-04):
> «исправь что нужно. чтобы больше не было затыков и простоев».
>
> Context: during the session, the orchestrator was making pauses (waiting
> for one subagent to finish before launching the next, asking "where to
> go next", releasing "I won't trigger anything in parallel"). This is a
> direct violation of Phase 1 MAXIMUM mandate. We are establishing a
> procedural rule to ensure such bottlenecks do not occur again, either in
> this session or future ones.

Source: SpectraVibe `CLAUDE.md` §"Throughput rule — FILL THE FLEET (HARD-LOCK 2026-06-04)" lines 196-261.

**Applicability**: Phase 1 + Phase 2. In Phase 3/4 — review-gated, rule does not apply.

**Hard requirements for orchestrator main loop** (HARD-LOCK):

1. **After EVERY `<task-notification>`** (any Agent finishes):
   - Re-scan task list (TaskList) for pending tasks without blockedBy.
   - Re-scan running agents — which scopes are occupied.
   - Form a **maximum disjoint batch** of pending tasks → launch
     **ALL** in one message (multi-tool-use Agent calls in one
     response) with `run_in_background: true`.
   - Do not launch one by one. Do not "let this finish, then the next".
     This is an anti-pattern.

2. **Before commit / tag / release**:
   - If there are pending tasks, **race-safe** relative to fixed
     changes → launch them **before** commit, so they run while
     orchestrator is building manifest.
   - Sequential «commit → wait → dispatch» — forbidden.

3. **Main loop NEVER idle** when subagents are running:
   - Permissible idle activities: preparing release notes templates,
     cleaning up task list, reading old outboxes for next wave prep,
     marking chapters, updating CLAUDE.md / AGENTS.md, lightweight
     housekeeping.
   - Forbidden: «waiting for notification», «let it run», «won't trigger
     anything in parallel» — if there are race-safe pending tasks or
     housekeeping.

4. **No confirmation-seeking when race-safe pending tasks exist**:
   - Marker phrases like «where to go next — X is running, wait, or
     another priority?», «give it 5 minutes to work?», «continue?» —
     forbidden if there's a non-empty pending backlog and slots are free.
   - Bias always: launch first, ask later (if something goes wrong,
     user will say — they clearly gave mandate).

5. **Race protection during scale-out**:
   - Before each multi-dispatch — formal hands-off list per agent,
     including directories of active parallel agents.
   - When worktree isolation is not possible (Windows path-limit) —
     hands-off list becomes the only protection; make it stricter.
   - If ≥ 2 pending tasks physically compete for one file
     (e.g. both edit `scripts/build.py`) — pick one, queue the other.
     Do not run both in parallel.

**Anti-patterns** (recording today's experience to avoid repetition):
- ❌ Notification A → launch only B → wait for notification B
- ❌ A2 finished → wait before launching A3 → wait before launching C
- ❌ «Make commit, then think about next wave»
- ❌ «Launching one subagent. Waiting for notification.» as a normal step
- ✅ Notification → re-scan → batch-launch ALL race-allowed →
  do housekeeping (commit, RAG updates, chapter mark, CLAUDE.md edits,
  etc.) in parallel

**Override**: user can explicitly say «stop», «pause», «don't launch anymore» —
then orchestrator stops. Without explicit command — fleet is always full.

### Two-tier release publishing (HARD-LOCK 2026-06-04)

> User instruction (recorded 2026-06-04):
> «настрой автовыгрузку на гит при значительных изменениях. мелкие релизы
>  архивируй локально».

Source: SpectraVibe `CLAUDE.md` §"Release publishing strategy — two-tier auto-push (HARD-LOCK 2026-06-04)" lines 141-194.

**Tier 1 — Significant changes → auto-push to GitHub**:
- **Minor bumps** (`vX.Y.0`): `v1.22.0`, `v1.23.0`, `v2.0.0`, … — closing
  entire waveset / feature group / cross-cutting fix.
- **Major bumps** (`vX.0.0`): `v2.0.0` GA, `v3.0.0` redesign — phase
  transitions always go to GitHub.
- **Phase transitions** (1→2 RC, 2→3 GA, any limit-critical change):
  always push regardless of version-bump tier.

  **Action chain** for significant release:
  1. **Subagent** (C / A / B): zip + commit + local tag (as usual).
     **STOP HERE**. Subagent does NOT do `git push` / `gh release create`.
  2. **Orchestrator (Claude main)** locally via Bash:
     - `git push origin master --tags`
     - `gh release create <tag> --title "<title>" --notes-file <release_notes_path> "<zip_path>"`

  **Rationale split** (HARD-LOCK 2026-06-04):
  > «Agents work locally». Subagents do not spend Claude tokens on
  > push/release ops — these are network-bound operations, cheap for main loop
  > (Bash call), no need to spawn subagent. Subagent briefs explicitly say
  > `DO NOT push/tag/release — orchestrator handles publish`.

**Tier 2 — Small patches → local archive only**:
- **Patch bumps** (`vX.Y.Z`, Z ≥ 1): `v1.22.1`, `v1.22.2`, … —
  hot-fixes, single-bug fixes, doc-only updates.
- Do NOT push to `origin/master`, do NOT create GH release.
- `1_Version/vX.Y.Z/SpectraVibe_vX.Y.Z.zip` stays local.
- Local git commit + local tag — yes (for history / git revert).

**Rationale**: Phase 1 + Phase 2 — high frequency patches (several per day
in active wave). Each patch in GitHub release creates noise for consumers
and operators. Minor bumps close "meaningful units of work" — that's what's
worth publishing. Patch bumps — internal surgical adjustments between minors.

**Override**: user can explicitly say «push patch X.Y.Z» — then single push
without upgrade tier policy. Auto-policy does not block explicit commands.

**Initial repo setup** (one-time, done at first publication):
```bash
gh repo create <owner>/<repo> --private \
    --description "<project description>"
git remote add origin git@github.com:<owner>/<repo>.git
git push origin master --tags  # retroactively pushes all local commits + tags
```

After initial setup — subsequent significant releases follow
**Tier 1 action chain** automatically.
