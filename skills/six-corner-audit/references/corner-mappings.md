# Per-artifact-type corner mappings

The six corners are constant in *intent*; what changes per artifact type is *what you
actually open and check*. Use the row for your artifact when pre-registering the
charter (Phase 0). The skeptic's job (Phase 3) is always the same: try to falsify the
artifact's central claim — the column below only tells you where that claim lives.

---

## Code PR / diff / commit

| Corner | What to verify (open these) |
|--------|------------------------------|
| 1 Factual fidelity | Comments, docstrings, and the PR description match the actual code. Any number/constant cited (`4 GiB`, a timeout, a port) recomputed by hand. |
| 2 Technical correctness | The logic does what it claims: trace the changed branch, recompute math, confirm any cited API/library behaves as used. Run the test if cheap. |
| 3 Scope / blast-radius | `git diff --stat`: only intended files touched. No logic change hiding in a "docs"/"rename" diff. No stray vendored files, no debug prints, no commented-out blocks left behind. |
| 4 Process & hygiene | Branched off the right base; `origin/main` (or protected branch) SHA unmoved; correct commit footers/trailers; no unwanted tag or merge commit; diff was actually shown, not summarized. |
| 5 Completeness / consistency | Tests/docs/changelog updated to match; version/date bumps consistent across all files; the PR summary matches the real diff. |
| 6 Style / integration | Matches surrounding style (linter clean); imports/links resolve; a focused change, not an unrequested refactor riding along. |

Central claim the skeptic attacks: *"this diff does X and only X, correctly and safely."*

---

## Prose / documentation

| Corner | What to verify |
|--------|----------------|
| 1 Factual fidelity | Every factual assertion traces to a real source; quotes are exact; figures match the cited origin. |
| 2 Technical correctness | The reasoning/instructions actually work if followed; examples run; commands are correct. |
| 3 Scope / blast-radius | Edits stay within the stated section; no silent rewrite of unrelated passages; tone/meaning of untouched parts preserved. |
| 4 Process & hygiene | Provenance/sourcing discipline: where did each claim come from? Reproducible (a reader can re-derive it). |
| 5 Completeness / consistency | All intended sections covered; cross-references and links resolve; no terminology/version/date drift across the doc set. |
| 6 Style / integration | Fits house voice and formatting; markdown renders; headings/anchors intact. |

Central claim the skeptic attacks: *"this document is accurate, complete, and the
reader can trust and act on it."*

---

## Research / claims

| Corner | What to verify |
|--------|----------------|
| 1 Factual fidelity | Each cited study/stat/quote is real and says what's claimed (open the source, don't trust the paraphrase). |
| 2 Technical correctness | Methodology is sound; the inference from evidence to conclusion holds; no statistical sleight-of-hand. |
| 3 Scope / blast-radius | Conclusions stay within what the evidence supports; no over-generalization beyond the sampled domain. |
| 4 Process & hygiene | Sources are primary where it matters; reproducible search/method; conflicts of interest or gaps disclosed. |
| 5 Completeness / consistency | Counter-evidence acknowledged; internal numbers reconcile; no contradiction between abstract and body. |
| 6 Style / integration | Citations formatted/resolvable; claims calibrated to confidence (no "proves" where "suggests" is warranted). |

Central claim the skeptic attacks: *"the central thesis is established by the evidence
presented."* (Default: unproven until the evidence forces a concession.)

---

## Data-extraction output (JSON/CSV/table from a source dump)

| Corner | What to verify |
|--------|----------------|
| 1 Factual fidelity | Spot-check extracted values against the source by offset/line/cell — every field provenance-checked, no invented values. |
| 2 Technical correctness | Types/units/formats correct; derived/computed fields recomputed from the raw source. |
| 3 Scope / blast-radius | Only the requested fields/records extracted; no schema creep, no extra inferred columns. |
| 4 Process & hygiene | `_extraction_log` / provenance present and points at real offsets; re-running the extractor is idempotent. |
| 5 Completeness / consistency | All expected records present (count matches source); no silent drops; `_gaps` honestly lists what couldn't be found. |
| 6 Style / integration | Output matches the agreed schema/format; encoding clean; consumable downstream without reshaping. |

Central claim the skeptic attacks: *"every row faithfully and completely reflects the
source, with nothing invented and nothing dropped."*

---

## Reminder

Whatever the type: a finding without `file:line` / SHA / URL / offset / quoted line is
not a finding — it's an opinion. If you can't locate the fact, the verdict is
**"not found in source,"** and the action stays gated to the operator regardless of how
clean the artifact looks.
