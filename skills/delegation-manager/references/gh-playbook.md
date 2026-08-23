# gh-playbook.md — команды, шаблоны, разовая настройка

Reference для скилла `delegation-manager`. Ядро `SKILL.md` держит принципы, роли,
машину состояний и анти-паттерны; здесь — verbatim `gh`-команды, шаблон Issue и
one-time настройка репо. Открывай, когда реально выполняешь процедуру.

---

## Шаблон Issue (единица делегирования)

Каждая задача/этап = один GitHub Issue. Файл в репо: `.github/ISSUE_TEMPLATE/deleg.md`.
Три поля обязательны (что / где / когда готово) — ниже этого минимума задача НЕ
делегируется: без явных **Границ** и **Definition of Done** исполнитель угадывает
scope → scope-creep → неревьюибельный PR.

```markdown
---
name: Delegated task
about: Задача для коллаборанта
title: "[DELEG] <краткое имя>"
labels: ["delegated", "status:ready"]
---

## Задача
<одно предложение — что нужно сделать>

## Границы (scope)
- Трогать только: <файлы / модули>
- НЕ трогать: <что за пределами задачи>

## Definition of Done
- [ ] <критерий 1 — проверяемый>
- [ ] <критерий 2>
- [ ] тесты зелёные: `<команда прогона тестов>`

## Контекст
- Зависит от: #<issue-номер> (если есть)
- Базовая ветка: <main / develop>
- Файлы-якоря: `path/to/file.ext:строка`
```

---

## Процедуры координатора

### Завести задачу
```bash
gh issue create \
  --title "[DELEG] <имя>" \
  --label "delegated,status:ready" \
  --assignee "<github-логин-исполнителя>" \
  --body-file <заполненный-шаблон.md>
```
После создания — назвать владельцу номер Issue.

### Сводка по проекту (вся картина)
```bash
# Все делегированные задачи с их статусом
gh issue list --label delegated --state open \
  --json number,title,labels,assignees

# PR по делегированным задачам — какие в review, какие draft
gh pr list --search "label:delegated" \
  --json number,title,isDraft,reviewDecision,headRefName
```
Синтез для владельца одной строкой:
`Ready(N) | In-progress(N) | Review(N) | Blocked(N) | Done(N)` + что требует решения.

### Проверить заблокированные (что требует владельца)
```bash
gh issue list --label "status:blocked" --json number,title
# по каждому — прочитать последний коммент «почему заблокировано»
gh issue view <N> --comments
```

### Проверить готовые к мержу
```bash
gh pr list --search "label:delegated draft:false" \
  --json number,title,reviewDecision,mergeable
```
Доложить: «#N, #M готовы — можно мержить». **Сам не мержишь.**

### Двигать статус
```bash
gh issue edit <N> --remove-label "status:ready" --add-label "status:in-progress"
```

---

## Протокол доклада (апдейты — в PR-коммент, не в личку)

```
progress: DoD 2/3, тесты зелёные локально.
Остался критерий <X> — нужно решение владельца по <Y> → ставлю status:blocked.
```
Владелец подписан на PR → уведомление само. Никаких «статус-пингов» в чат.

---

## Разовая настройка репо (владелец делает один раз)

1. Дать исполнителю `write`-доступ (Issues + ветки `deleg/*`).
2. **Branch protection** на `main`/`develop`: мерж только через approve владельца.
3. Создать 6 меток: `delegated` + пять `status:*`:
   ```bash
   gh label create "delegated" --color "5319e7"
   gh label create "status:ready" --color "0e8a16"
   gh label create "status:in-progress" --color "fbca04"
   gh label create "status:review" --color "1d76db"
   gh label create "status:blocked" --color "d93f0b"
   gh label create "status:done" --color "c5def5"
   ```
4. Положить `.github/ISSUE_TEMPLATE/deleg.md` (шаблон выше).
5. Завести Project-board с колонками по статусам.
6. В `CLAUDE.md` репо записать: команду тестов, базовую ветку, конвенцию веток
   `deleg/*` — чтобы Claude исполнителя читал их каждую сессию.
