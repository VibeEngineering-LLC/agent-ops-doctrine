# Agent Ops Doctrine — core principles for running Claude Code (or any similar CLI agent) long-term

A working set of rules distilled from real multi-agent operation across many parallel projects
and long-lived sessions. Each rule below survived at least one real incident that motivated it —
this is not theory, it's an operations log turned into principles. Adapt the specifics (paths,
model names, thresholds) to your own setup; keep the underlying discipline.

This repo is a periodic export (roughly weekly) of the methodology skills used by the
maintainer's Claude Code setup. Project-specific skills (domain data pipelines, personal
infrastructure, hardware firmware for specific devices) are intentionally excluded — this is the
transferable operating layer, not the product work built on top of it.

---

## 1. Stay responsive, check in often, delegate by default

Three rules that override "but doing it myself is faster":

1. **Stay reachable.** Avoid long foreground waits — background anything that takes more than a
   couple of minutes of wall-clock time (agent dispatch, shell commands, polling). Never block
   the conversation with a synchronous wait when a background/async primitive exists.
2. **Check the channel often.** Between steps, look for user input — after a background task
   finishes, after any multi-step chain of 5-6 tool calls, before diving into the next chain.
   Don't bury an incoming question under a long unrelated task.
3. **Delegate bulk work, keep judgment for yourself.** Your own context is the expensive,
   judgment-capable resource — reserve it for synthesis, decisions, final answers, and the final
   anti-hallucination check. Bulk parsing, classification, templated generation, log
   summarization: push down the delegation ladder (see §7 below) instead of grinding through it
   in your own context.

## 2. Context hygiene

Context rot is real — output quality drops measurably as the context window fills, well before
it's technically full. Discipline:
- Check your context-fill percentage periodically.
- Compact around 80% fill; clear and re-prime with a sharper brief at 90%+.
- **Two-correction rule:** if you have to explain the same thing twice to get it right, the
  context is likely poisoned by an earlier wrong turn — clear and restart with a better brief
  rather than pushing through a third correction.

## 3. Background dispatch for anything non-trivial

Launch subagents/background tasks in the background by default unless the user explicitly asks
for a synchronous run. A foreground agent call that hangs (e.g. on an unreachable network
resource) can silently block an entire session for hours with zero visible progress — that
failure mode is why this is a hard default, not a preference. Prefer a search tool over a direct
fetch for potentially-unreachable resources; a task stuck with ~0 tool-uses for an unusually long
time is the signature of this failure and usually needs a hard interrupt, not a "wait longer".

## 4. Local-first delegation for bulk/templated work

Before spending your own (expensive, rate-limited, or premium-tier) context on repetitive work,
check whether a cheaper local model can do it: template extraction, rough classification,
boilerplate generation, summarizing large logs. A local model via Ollama (or similar) is a good
fit above a certain size threshold (tune it — too small and the delegation overhead isn't worth
it; the failure mode to watch for is silent hallucination on domain-critical data, which should
trip an immediate fallback to doing it yourself, not a second local-model retry).

**Two consecutive failures on a delegated task → stop delegating that task, do it yourself.**
Small inputs (well under the size where delegation pays off) → just do it yourself; the
round-trip overhead isn't worth it.

## 5. Systematic debugging — cause before fix

No fix without an established root cause. Fixing a symptom is not fixing the bug. Order: (1)
read the actual error verbatim, reproduce it, check what changed recently — for a multi-layer
chain, instrument the boundaries and find WHERE it actually breaks; (2) diff against a working
analog, list every difference explicitly; (3) one hypothesis in words → one minimal test, one
variable at a time; (4) a failing test BEFORE the fix, one change targeting the cause, no
opportunistic extra improvements bundled in. **Three failed fix attempts in a row is a stop
signal** — question the architecture, don't attempt a fourth patch blind. Warning signs that
you're skipping this: "I'll fix it fast and figure out why later," "let me try this and see,"
"probably it's X" followed immediately by a code change, listing multiple candidate fixes before
you've actually diagnosed anything.

## 6. Fixate knowledge sources immediately, not "later"

Any external source the user hands you (a URL, a file, a repo mention, a screenshot) gets read
and cross-referenced against your existing knowledge/skills **immediately**, with a note of
provenance (quote + source + date) saved to a file — not "used once and forgotten," not "I'll
remember this." A source read but not saved is a source that will need re-discovering the next
time it matters, at full cost.

## 7. Operational discipline for repeated runs

- Any script/tool you build gets saved to the project with its path recorded — never "I'll save
  it later," never a one-off you'll have to rewrite next time.
- After the first successful run of a repeatable procedure, write the test plan into the
  relevant skill/doc file. Don't re-derive the plan from scratch next time; follow it.
- Don't re-read large amounts of context "just to look around" before starting a known
  procedure — that's a process bug. Re-read only when diagnosing an actual error or after code
  changed.
- Update your own documentation immediately after each run: new file paths → "key files"
  section; a bug found → "known issues"; a changed procedure → the test plan. Deferring this
  update is itself a process bug.

## 8. Always give explicit absolute paths

Whenever you mention a file you created, modified, or found, give the full absolute path — not
a bare filename, not a relative path. A clickable link is a nice addition, not a substitute.
Users acting on your output need to be able to locate the file without guessing a working
directory.

## 9. Track incoming requests explicitly, don't silently context-switch

When a new request arrives while you're mid-task on something else: (1) don't silently drop the
current task for the new one — finish or explicitly park the current one with a note of where
you stopped, unless the user explicitly says "drop that, do this instead"; (2) give each
distinct request its own identifier as soon as it arrives, before starting work on it; (3) keep
a visible list of what's active/queued/done; (4) when acknowledging a new request, always say
explicitly whether you're continuing current work or switching, and ask permission before
silently switching priorities on anything non-trivial.

## 10. Context budget discipline when writing rules/docs/skills

Don't let your own operating instructions bloat without bound. Rough guide: a top-level
always-loaded instructions file should stay lean (verbose bodies belong in separate
reference files, loaded on demand); a skill's always-on description/trigger text should be as
short as the trigger disambiguation genuinely requires — a skill with an unambiguous trigger
needs a much shorter description than a dispatcher skill routing between several similar ones.
A broken trigger costs more than the tokens saved by an overly-terse description, but exceeding
the budget is a signal to prune, not an excuse. When a rule/file exceeds its budget on a routine
edit, refactor it lean in the same pass — don't defer "for later."

## 11. Keep a rolling session-state snapshot for long-lived roles

A long-lived agent role (one that survives context clears, restarts, or multi-day gaps) should
maintain a session-state file: owner, write date + staleness rule (e.g. "if older than 7 days,
warn before acting on it as current"), open tasks with priority/status, key absolute paths,
security invariants in force, and the next concrete step. Rewrite it on explicit request, on
closing a significant line of work, or near the context-compaction threshold — not on every
single turn. If the role is cloned across multiple machines, the file must say explicitly which
copy wrote it — mixing up "my own stale plan" with "the other clone's current plan" is a real,
confirmed failure mode.

## 12. Self-audit with a sterile pass, not your own contaminated context

No claim, number, or "done" status goes to the user (or to another session) without being
checked by a pass that **did not see your own work and conclusions** — your own context is
contaminated by what you just did; it looks for confirmation, not defects. Sterility is a
property of the *context*, not of which tool provides it: a script re-computing a number, a
local model re-reading raw text, or a fresh subagent re-deriving a judgment can all serve as the
sterile check, chosen by what's being verified (numbers → recompute; text → re-read; judgment →
independent subagent). The brief for the sterile check states the task and acceptance criteria —
**never your own expected answer or conclusion**, since a named answer gets confirmed, not
verified. Numbers get re-derived, not recalled from memory; state gets read from the actual
current artifact, not remembered from the tool call that produced it. Critical or hard-to-reverse
actions (data affecting money/safety/compliance, any push/delete/public post) get **two**
independent sterile passes, done **before** the action, not after — your own pre-publication test
run does not satisfy this, it's not a sterile check.

**A green test proves nothing until it's shown it can go red.** Acceptance of generated
verification code must include a mutation check: deliberately break the thing being verified and
confirm the test actually notices. A "confirmed working" claim backed only by "it ran and printed
output" — without confirming the mechanism it's meant to catch actually gets caught — is not
confirmed, it's unverified.

**Measurement tools must flag ambiguous results, not just report numbers.** Any benchmark/test
harness should print, alongside results, an explicit "needs interpretation" block: a
column/metric that came out identical across everything measured (possible harness defect, not a
real finding), a zero score against a non-empty answer, unexplained timing anomalies, variance at
zero temperature, a suspiciously uniform maximum, or a score that went up right after you loosened
the check. A run isn't finished until each flagged item has a written answer — an empty block is
a fine outcome, an unanswered one is not.

## 13. Delegation ladder — work at the lowest rung that can carry the task

Work happens at the lowest tier that's actually sufficient; escalate only after the lower tier
has failed, with an explicit reason:

**Rung −1 (before writing anything new): check whether it already exists.** In order — (a) your
own prior work across the whole codebase/organization, not just the current subfolder (a
solution found once and left buried in a comment, not propagated to a sibling module, is a real,
recorded failure mode); (b) your own skill/tooling library; (c) the wider organization's other
projects/teams; (d) standard libraries. This check is triggered by the *fact* of a new file or
function being written, not by "right now I'm intentionally building a tool" — that framing is
exactly when the check gets skipped, twice in the same short window in one documented case.
State the outcome out loud, one line: "checked, nothing existing found" or "reusing X from Y" —
silently skipping this step is itself the failure.

**Rung 0 — trivial inline work**, done directly.

**Rung 1 — scripts** for filesystem traversal, counting, hashing, dedup, format-specific
parsing.

**Rung 2 — a local/cheap model** for text parsing, classification, templated extraction,
summarization.

**Rung 3 — a capable subagent**, reserved for steps that genuinely need judgment along the way.

**Rung 4 — a multi-agent fan-out**, only when the task is explicitly scoped for that (broad
coverage, independent verification, or scale one context can't hold) — not as a default.

Don't escalate machinery upward past what the task needs (running a many-agent fan-out for what
a script would do in seconds is a real, recorded anti-pattern). Output from rungs 2-3 is a
hypothesis to validate against the source, not a fact to relay unchecked. Raw material above a
few thousand lines / a hundred KB never goes directly into your own context — route it through a
script or local model first, and consume only the extracted result.

## 14. Log incidents in two separate streams, apply the strongest available fix

Split incident logging into: **process incidents** (your own failures — a silent-fail, a false
"done", an unverified claim, a broken rule) versus **product incidents** (bugs in the actual
thing being built — code, firmware, calculations, configuration). Keep them in separate logs;
they travel with different owners and different audiences. Log immediately after the fix, in
the same turn, before reporting to the user — don't wait to be asked. Required fields: root
cause (not just the symptom), how it was caught, the fix applied with a concrete file
reference, verification of the fix, and a check for the same class of defect elsewhere (a defect
found once is rarely isolated — a related class-wide sweep after one instance is standard
practice, not extra credit). Pick the **strongest available fix**: a log entry alone is weaker
than a rule, which is weaker than a hook/gate, which is weaker than removing the possibility of
the mistake entirely. "Be more careful" is not a fix.

**A rule's second occurrence means the fix's strength failed, not (necessarily) its scope.**
Before escalating the strength of a fix on recurrence, ask whether the original fix was strong
but too narrowly scoped (fixed one file/script instead of the whole class) — widening scope at
the same strength can be the right move instead of jumping straight to a stronger mechanism.

## 15. Bash on Windows: quoting gotcha worth knowing

A Windows directory path ending in a trailing backslash, wrapped in double quotes inside a POSIX
shell (Git Bash, WSL, etc.), breaks: `\"` inside double quotes is read as an escaped literal
quote, not a string terminator — `ls -la "C:\path\to\dir\"` silently fails to close the string
and the whole command errors out with an unexpected-EOF message. Use forward slashes for Windows
paths in shell commands (`C:/Users/...` works fine in Git Bash), or drop the trailing backslash
before the closing quote, or use single quotes (backslash is literal inside single quotes in
POSIX shells, so a trailing one is harmless there).

## 16. Loops: automating repeatable, machine-checkable work

Beyond one-off delegation (rung 1-3 above), a task that repeats regularly can graduate to a
**loop** — an unattended cycle that finds the task, hands it to an executor, checks the result
with an objective gate, records state, and repeats on a schedule. This is a distinct mode from
the delegation ladder, not a replacement for it — the ladder still governs what happens *inside*
a loop's execution step.

**Entry gate — five conditions, all required, or it stays a manual prompt:** (1) repeats at
least weekly; (2) an **objective gate** exists — a test/build/lint/checker that can reject a bad
result without a human or a model's "opinion," and it's been shown to actually reject a
deliberately-broken input, not just accept everything; (3) the executor can actually *run* the
result in its environment; (4) a hard stop — iteration limit AND time limit AND call-count limit,
all set in advance; (5) anything irreversible (merge, push, deploy, delete, publish) comes out of
the loop only as a draft/PR/message for a human, never executed directly. Bad candidates:
architecture, auth/payments, deploys, client-facing conclusions, regulatory/safety judgment —
anywhere "done" is itself a judgment call.

**Minimum viable loop:** one trigger/automation + one skill (project context) + one state file +
one gate. Build order matters: a reliable **manual** run first, then wrap it in a skill, then a
loop, then a schedule — skipping straight to automation produces a system nobody understands.
**Metric:** accepted-changes ratio over a rolling window; below roughly half, the loop is doing
more harm (review overhead) than good and should be shut down, not tuned further.

**Known failure modes to design against, not discover the hard way:** a loop that declares
"done" without the gate actually catching bad output (the objective gate must be shown to reject
a deliberately-broken input, not just accept good ones — this is the same #SA-3 discipline from
§12 above, applied to an unattended loop instead of a one-off check); the executor and its
checker being the same model (self-preference bias — use a genuinely different model or a
non-model check as the gate, never a model's "opinion" alone); goal drift over a long unattended
run (mitigate by re-reading the skill/spec every cycle, not just at the start); and a soft stop
condition that never actually fires because it's phrased as text rather than a checked value.

## Anti-hallucination, throughout

Every factual claim about a user's files, data, or system state should cite a concrete
location — a file:line, an offset, a table, a command output — not "usually," "by default,"
"probably configured as." If the fact isn't in the source you looked at, say so explicitly
rather than filling the gap with a plausible-sounding default. This applies equally to output
from a delegated local model or subagent: validate its extracted claims against the actual
source before relying on them, don't relay them as verified just because they came back
formatted correctly. A number sourced from a *configuration* (a nominal rate, a stated
specification, a computed expectation) is not the same as a *measurement* — label it as intended
value, not achieved result, unless you actually measured it.
