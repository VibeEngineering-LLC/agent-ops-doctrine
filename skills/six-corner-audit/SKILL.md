---
name: six-corner-audit
description: "Независимый аудит ОДНОГО финализированного артефакта ПО ФАКТУ перед пушем/мерджем: 6 углов + отдельный скептик, actor≠verifier, находки с file:line/SHA, GATED-вердикт — необратимое за оператором. Триггеры: «6-corner», «шесть углов», «скептик», «audit this PR/diff», «проверь/sanity-check чужую работу»."
---

# 6-Corner + Skeptic: Independent Audit by Fact

A methodology for auditing ONE finalized artifact and returning an evidence-cited,
gated verdict. The auditor judges and recommends; the operator decides the
irreversible action. Use it for code PRs/diffs, docs, research claims, and
data-extraction output — any artifact someone wants vetted before they trust or
ship it.

## Three principles (read these first — they govern everything below)

1. **actor ≠ verifier.** The auditor must be independent of whoever produced the
   artifact. *Why:* a producer is blind to their own assumptions — they verify the
   thing they meant to build, not the thing they built. If THIS session wrote the
   artifact, you are not a valid auditor of it: delegate the audit to a fresh agent,
   or at minimum run the skeptic pass (Phase 3) as a separate independent verifier.
   On material / irreversible / security-relevant work this separation is mandatory,
   not optional.

2. **Anti-hallucination — every finding cites concrete evidence.** A verdict is only
   as good as the evidence under it: `file:line`, a commit SHA, a URL, a log offset,
   or a quoted source line. *Why:* "usually X" and "probably Y" are how a confident
   wrong audit launders a hallucination into an approval. If a fact cannot be located
   in the source, the honest verdict is **"не нашёл / not found in source"** — that is
   a finding, not a gap to paper over.

3. **Gate the ACTION.** Automate the *verdict*; gate the *action*. *Why:* merge, push
   to main, release, deploy, and delete are irreversible and belong to the operator's
   risk budget, not the auditor's. The auditor's job ends at a crisp recommendation.

## The loop

### Phase 0 — Pre-register the charter (BEFORE seeing results)

State the 6 corners and the skeptic's target claims up front, adapted to this
artifact type. *Why:* pre-registering your pass/fail criteria before you inspect the
result is the cheapest defense against confirmation bias — once you've seen a clean-
looking diff, you will unconsciously soften the bar. Write the charter, then look.

For per-type corner mappings (code PR, prose/docs, research/claims, data extraction),
see `references/corner-mappings.md`. Load it when the artifact type is non-obvious or
you want the tailored checklist; the generic six below are enough for the common case.

### Phase 1 — Acquire the finalized artifact (read-only)

Never audit a moving target. *Why:* if the artifact is still changing, every finding
has a shelf-life of seconds and you'll re-audit churn. For code that means the
**committed diff / pushed branch / open PR** — not an uncommitted working tree.

- If it is not finalized yet, **say so and wait** — do not audit a draft as if it were
  done.
- Gather everything read-only. Do **not** mutate the artifact while auditing (no
  reformatting, no "while I'm here" fixes) — that destroys your own independence and
  contaminates the thing you're judging.

### Phase 2 — The 6 corners

Run all six directly (you're independent of the actor, so you may inspect freely).
Each corner returns **PASS / FAIL / FAIL-with-fix**, backed by cited evidence.

1. **Factual fidelity / anti-hallucination** — every claim, number, quote, and
   citation in the artifact traces to a real, exact source. Open the source and check
   the number; don't trust the artifact's own restatement of it.
2. **Technical / logical correctness** — the mechanisms, math, and reasoning actually
   hold. Recompute the arithmetic. Confirm a cited API behaves as described. Walk the
   causal chain link by link and find the one that doesn't connect.
3. **Scope / blast-radius** — the change touches only what it should. No stray files,
   no logic change smuggled inside a "docs-only" diff, additions proportionate to the
   stated intent, nothing reaching outside the intended boundary.
4. **Process & hygiene** — the *way* it was produced is clean and reversible until the
   operator approves. Code: right base branch, no contamination of protected branches,
   correct commit footers, no stray tag/merge, diff actually shown. Docs/research:
   provenance, sourcing discipline, reproducibility.
5. **Completeness / internal consistency** — all intended surfaces are covered;
   cross-references resolve; no version/number/date drift across files; the summary
   matches what the change actually does.
6. **Style / integration / conventions** — fits surrounding conventions and tone;
   nothing broken (markdown, links, formatting); it's a focused change, not an
   unrequested rewrite.

### Phase 3 — Skeptic refute pass (run as a SEPARATE independent verifier)

Run the skeptic as a distinct verifier — **ideally a background agent**, for double
independence from both the actor and the 6-corner pass. *Why a separate skeptic:* the
6-corner pass is **constructive** ("does this hold up?"); the skeptic is **destructive**
("can I break this?"). They catch different failure classes. Redundancy ≠ diversity —
so the skeptic must attack from angles the corners don't, not re-run them.

The skeptic is adversarial: it tries to **falsify the artifact's central claims**,
defaulting every claim to *refuted / unsound* unless the evidence forces a concession.
Per-claim verdict:

- `REFUTED` — found counter-evidence; claim is wrong.
- `CONCEDED-SOUND` — the evidence forced a concession; claim holds.
- `OVERSTATED-BUT-DEFENSIBLE` — the core is true but the claim over-reaches (e.g. an
  over-broad causal exclusion, an unacknowledged caveat or latent mitigation).

Each verdict carries quoted evidence, same anti-hallucination bar as Phase 2.

**Границы видимости проверяющего (добавлено 2026-08-16, находка контура «Программист»).**
Проверка отвечает ровно на заданный ей вопрос — и только внутри того, что проверяющий реально
видел. Поэтому:

1. **Фиксируй у каждого проверяющего границу видимости** («читал клиента, прошивку не читал»,
   «смотрел диff, историю не смотрел») и сверяй, лежит ли его утверждение ВНУТРИ этой границы.
2. **Отрицательные утверждения требуют этого особо.** «Восстановление невозможно», «нигде не
   используется», «такого случая нет» истинны только при полноте обзора, а не при корректности
   рассуждения. Цена ошибки на практике: вывод «данные не спасти» был вынесен за границу
   видимости прохода, а данные лежали в кольцевом буфере платы — до 256 строк подлежали спасению.
3. **Спрашивай не только «верно ли это само по себе», но и «что это меняет для соседей».** Два
   стерильных прохода проверяли семафор на корректность захвата и ответили верно; эффект на
   соседние эндпоинты не нашёл никто, потому что такого вопроса им не задавали.
4. **Вес находки — отдельное суждение, и ошибается чаще именно он.** Факт находится инструментом,
   тяжесть факта — только суждением. Пример: дефект «данные пишутся с чужой калибровкой» автор
   поставил четвёртым из четырёх; он первый — потерянные данные видны как отсутствие, а данные с
   чужой калибровкой выглядят валидными и дают неверную идентификацию нуклида.
5. **Независимость от автора ≠ независимость от его источников.** Если в бриф проверяющему попали
   утверждения, полученные от ТРЕТЬЕЙ стороны (соседний контур, чужой отчёт, документация), их
   надо перечислить отдельным списком и потребовать проверить у первоисточника. Иначе стерильный
   проход честно проверит вывод и унаследует чужую ошибку целиком: он не видел моей работы, но
   принял на веру то, что принял на веру я.
6. **Деструктивная находка дороже конструктивной — подавать её надо так, чтобы нельзя было
   выполнить не проверив.** «Это мёртвый код», «файл не используется», «репозиторий лишний»
   исполняются одним движением и необратимы, тогда как ошибочное «здесь есть дефект» стоит лишь
   времени на разбор. Поэтому у каждой находки класса «удалить/снести/отключить» обязательны:
   границы обзора, на котором она сделана, и явная проверка перед исполнением. Практика того же
   дня: стерильный проход выдал «7 скиллов без резервной копии» — проверка показала, что бэкап
   есть у всех семи; будь находка про удаление, исполнение вслепую стоило бы данных.

### Phase 4 — Synthesis & gated verdict

Combine both lines of inquiry:

- Classify each finding **blocker** (must fix before the action is safe) vs
  **non-blocker** (optional refinement / honesty improvement).
- Give an overall verdict, e.g. *"5/6 corners PASS, 1 FAIL-with-fix; 3 claims
  conceded-sound, 2 overstated-but-defensible."*
- Recommend the next step.
- **Then STOP at the gate.** Do not merge / push / release. Present the operator a
  crisp choice: **(a)** apply refinements first, **(b)** ship as-is, **(c)** hold.
- **Audit your own brief.** If a skeptic "finding" turns out to be an artifact of how
  *you* phrased the question rather than a real flaw in the artifact, say so out loud
  and retract it. Intellectual honesty applies to the auditor too — an audit that
  can't catch its own framing errors isn't independent of itself.

## Output template (copy-paste, fill in)

```
ARTIFACT: <what was audited> @ <SHA / URL / path>
CHARTER (pre-registered): <6 corners + skeptic target claims for this artifact type>

— 6 CORNERS —
| # | Corner                         | Verdict          | Cited evidence            |
|---|--------------------------------|------------------|---------------------------|
| 1 | Factual fidelity               | PASS/FAIL/FIX    | file:line / SHA / URL     |
| 2 | Technical correctness          | ...              | ...                       |
| 3 | Scope / blast-radius           | ...              | ...                       |
| 4 | Process & hygiene              | ...              | ...                       |
| 5 | Completeness / consistency     | ...              | ...                       |
| 6 | Style / integration            | ...              | ...                       |

— SKEPTIC REFUTE PASS (separate verifier) —
| Claim                | Verdict                          | Quoted evidence    |
|----------------------|----------------------------------|--------------------|
| <central claim 1>    | REFUTED / CONCEDED / OVERSTATED  | "<quote>" (src)    |

— SYNTHESIS —
Blockers:      <list, or "none">
Non-blockers:  <optional refinements>
Verdict:       <N/6 corners PASS, K refuted, M overstated-but-defensible>
Self-check:    <any skeptic finding that was a framing artifact, retracted>

— GATED RECOMMENDATION (operator decides the irreversible action) —
(a) apply refinements first   (b) ship as-is   (c) hold
Recommended: <a/b/c> — <one-line why>
```

## Worked example (ONE instance — your artifact will differ)

Auditing a **docs-only PR** (PR #5, commit `d7f2a71`) that documented a GPU-VRAM-
starvation failure mode:

- **6 corners: all PASS.** Corner 1 verified the figure by hand:
  `4294967296 == 4*1024**3 == 4 GiB`. Corner 3 confirmed the one `.py` edit lived
  *inside a docstring* via `git show d7f2a71:path/to/file.py` — no executable logic
  changed in a "docs" PR. Corner 4 confirmed `origin/main`'s SHA was unmoved, so no
  protected-branch contamination.
- **Skeptic:** conceded 3 claims as sound; flagged 2 as **overstated-but-defensible** —
  an over-claimed causal exclusion ("X was the *only* cause") and an unacknowledged
  latent mitigation the doc didn't credit.
- **Result:** *approved-by-fact* with two optional honesty refinements; **merge gated to
  the operator** (the auditor did not merge).

This is just one shape. The same loop drives a research-claim audit, a data-extraction
QA, or a 2000-line feature diff — only the corner mappings (`references/`) change.
