# Codex Instruction

## Communication

- Use Traditional Chinese for all user-facing responses by default.
- English is allowed and preferred for:
  - Technical terms
  - Code
  - Tool usage, such as search queries and commands
- Keep explanations simple, concrete, and easy to follow, as the user has a limited programming background.
- When explaining code or technical decisions, always include:
  - What this approach is
  - Why this approach is used
  - What impact and trade-offs it introduces
- Keep `README.md` up to date in Traditional Chinese. It should tell users how to install, build, and use this program.

## Workflow

- First, clarify the actual requirement.
- Then, propose a Minimum Viable Solution (MVS).
- Only after that, consider adding complexity if needed.
- Clearly state:
  - Known constraints
  - Current assumptions
  - Unverified or unclear parts
- If critical requirements or assumptions are unclear, ask for clarification instead of making decisions.
- Avoid adding features, abstractions, or flexibility that were not explicitly requested.
- If modifying existing code, make the smallest possible change that solves the problem.

## Problem-Solving

Before implementing or making decisions, check:

- What is the actual goal?
- What is the simplest solution that works?
- Am I making any unstated assumptions?
- Is this adding unnecessary complexity?
- Is there a simpler or more maintainable alternative?

## Python Development

- Prefer using `uv` for Python projects to manage dependencies, virtual environments, lockfiles, and command execution.
- Prefer `NiceGUI` apps styled with TailwindCSS and Quasar-style UI.

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for `LesterCtw/Atlas`. See `docs/agents/issue-tracker.md`.

### Triage labels

This repo uses the default five triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain docs layout. See `docs/agents/domain.md`.
