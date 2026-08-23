# agent-ops-doctrine

A working set of operating rules for running Claude Code (or a similar CLI coding agent)
across long-lived, multi-project setups: delegation discipline, context hygiene, self-audit,
incident logging, and a library of reusable skills covering review, research, documentation,
and session handoff.

This is not a framework or a tool — it's a distillation of rules that survived real incidents
across months of daily multi-agent operation. Adapt the specifics to your own setup; the
underlying discipline is what's meant to transfer.

## Contents

- [`DOCTRINE-CORE.md`](DOCTRINE-CORE.md) — the core operating principles (delegation ladder,
  context budget, self-audit discipline, incident logging, systematic debugging).
- `skills/` — a set of Claude Code skills (`SKILL.md` + `references/`) implementing parts of
  the doctrine: independent audit/review (`censor`, `six-corner-audit`, `fact-audit`),
  multi-agent workflow bootstrap (`workflow`), a self-improvement loop (`self-learning`),
  incident logging (`incident-log`), session handoff (`session-handoff`), and several others
  covering documentation, research, and delegation patterns.

## What's intentionally NOT here

Project-specific and domain-specific skills (hardware firmware, personal data pipelines,
finance calculators, infrastructure tied to one person's machine) are excluded — this repo is
the transferable operating layer, not the product work built on top of it.

## Update cadence

This is a periodic export (roughly weekly) from a working private setup, not a continuously
synced mirror. Expect occasional drift between what's documented here and the latest internal
iteration.

## License

MIT — see [`LICENSE`](LICENSE).
