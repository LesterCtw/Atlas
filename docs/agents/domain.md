# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

This repo uses a single-context domain docs layout.

Expected locations:

- `CONTEXT.md` at the repo root for domain language, project goals, constraints, and glossary.
- `docs/adr/` for architectural decision records.

## Before exploring, read these

- `CONTEXT.md` at the repo root, if it exists.
- Relevant ADRs under `docs/adr/`, if they exist.

If these files do not exist, proceed silently. Do not flag their absence or create them unless the current task needs them.

## Current domain summary

Atlas wraps the company's internal web-based LLM, `tgenie`, behind a programmable API and agent harness. The goal is to let an LLM that normally runs through a web UI participate in agent workflows.

The project should reference only the necessary harness behavior from opencode. Avoid copying unrelated architecture until the project has a concrete need for it.

## Use the glossary's vocabulary

When output names a domain concept, use the term as defined in `CONTEXT.md`.

If the concept is not in the glossary yet, either use the clearest existing project term or note the gap for a future domain-doc update.

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly instead of silently overriding it.
