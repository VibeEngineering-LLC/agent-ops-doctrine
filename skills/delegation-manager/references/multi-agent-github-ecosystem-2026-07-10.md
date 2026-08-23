# Ландшафт multi-agent / delegation экосистемы (снимок 2026-07-10)

Провенанс: WebSearch (2 запроса), рабочая сессия 2026-07-10, контекст — составление
промпта bootstrap-агента для iOS-репо с несколькими ИИ-коллаборантами.

## Вывод (главное)

Ниша **«несколько независимых ИИ-коллаборантов на разных машинах/аккаунтах,
координация через GitHub Issues/PR»** готовым официальным продуктом НЕ закрыта.
Существующие решения делятся на два кластера:

1. **Одномашинные оркестраторы** (Agent Teams, workflow-orchestration, agent-team) —
   несколько сессий Claude Code на ОДНОМ аккаунте/машине, координация напрямую между
   агентами (не через GitHub state). Не подходит для сторонних коллаборантов со своими
   аккаунтами.
2. **Вендорские GitHub-native агенты** (Copilot Coding Agent + Claude/Codex как
   исполнители) — назначил Issue агенту, он сам открывает PR. Близко к нашей схеме,
   но привязано к GitHub Copilot подписке/инфраструктуре.

Наш подход (`delegation-manager` skill: source-of-truth = GitHub Issues/PR/labels,
координатор = обычная сессия Claude Code с `gh` CLI, БЕЗ вендор-лока) закрывает нишу,
которую готовые продукты не закрывают: гетерогенные исполнители (разные люди, разные
ИИ-инструменты, разные машины), ноль зависимости от конкретного оркестратора.

## Источники (verbatim цитаты + URL)

### Официальное

- **Agent Teams (Anthropic, research preview)** — "Agent teams enable multiple Claude
  instances to work in parallel on different subtasks while coordinating through a
  git-based system... one session acting as the team lead... teammates work
  independently in their own context windows and communicate directly with each other."
  https://code.claude.com/docs/en/agent-teams
  → Ограничение: одна машина/аккаунт, агенты общаются НАПРЯМУЮ (не через persistent
  GitHub state) — контекст теряется при перезапуске сессии лида.

- **GitHub Copilot Coding Agent + сторонние агенты (Claude, Codex)** — "Digital workers
  can act autonomously on behalf of developers, taking assigned issues, understanding
  existing code bases, planning an implementation strategy, executing said
  implementation, scanning for security issues, producing documentation, and ultimately
  submitting a pull request for human review."
  https://smartscope.blog/en/generative-ai/github-copilot/github-copilot-claude-code-multi-agent-2025/
  → "As of February 2026, AI coding tools have entered the production phase of
  multi-agent collaboration, with GitHub Copilot now integrating Copilot Coding Agent
  alongside third-party agents (Claude by Anthropic, OpenAI Codex), while Claude Code
  introduces Agent Teams in research preview."

### Сообщество (одномашинные оркестраторы — для справки, не для нашей схемы)

- barkain/claude-code-workflow-orchestration — декомпозиция + параллельные агенты +
  делегация специализированным агентам, native plan mode.
  https://github.com/barkain/claude-code-workflow-orchestration
- aws-samples/sample-claude-code-agent-team — spec-driven: Full Stack Developer
  parent-оркестратор + динамические пулы Coding/DevOps/Review/Solutions Architect.
  https://github.com/aws-samples/sample-claude-code-agent-team
- EPAM guide — multi-agent команда через tmux + Telegram-уведомления (ближе всего к
  распределённой схеме среди community-примеров, но самодельная инфраструктура, не skill).
  https://www.epam.com/insights/ai/blogs/step-by-step-guide-to-building-a-multi-agent-claude-code-ai-development-team

### Каталоги skills (искать готовое под конкретную задачу — iOS CI, ревью-агенты и т.п.)

- VoltAgent/awesome-agent-skills — крупнейший, 1000+ skills, кросс-инструментный
  (Claude Code, Codex, Gemini CLI, Cursor). https://github.com/VoltAgent/awesome-agent-skills
- ComposioHQ/awesome-claude-skills — 1000+ production-ready.
  https://github.com/ComposioHQ/awesome-claude-skills
- travisvn/awesome-claude-skills. https://github.com/travisvn/awesome-claude-skills
- rohitg00/awesome-claude-code-toolkit — 135 агентов, 35 skills, 176+ плагинов, 20 hooks.
  https://github.com/rohitg00/awesome-claude-code-toolkit
- ithiria894/awesome-claude-code-workflows — рецепты hooks+MCP+skills+CLAUDE.md.
  https://github.com/ithiria894/awesome-claude-code-workflows

## Применение к этому скиллу

Текущая методология `delegation-manager` (SKILL.md) остаётся основным подходом для
гетерогенных ИИ-коллаборантов. При следующей ревизии скилла — сверить машину состояний
`status:*` против GitHub Copilot Coding Agent conventions (могут появиться нативные
`assigned`-триггеры, которые упростят «Коллаборант узнаёт о задаче»-петлю (см.
локальный промпт bootstrap-агента для iOS-репо, составлен в этой же сессии).

Не тянуть Agent Teams как замену — другой use-case (одна команда, один аккаунт).