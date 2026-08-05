# Domain Docs

How the engineering skills should consume this repo's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the repo root
- Relevant files in `docs/adr/`

If any of these files do not exist, proceed silently. The `/domain-modeling` skill creates them lazily when terms or decisions are resolved.

## File structure

This is a single-context repo:

```text
CONTEXT.md
docs/adr/
```

## Use the glossary's vocabulary

When an issue, ticket, refactor proposal, hypothesis, or test names a domain concept, use the term defined in `CONTEXT.md`. Do not drift to synonyms listed under `_Avoid_`.

## Flag ADR conflicts

If output contradicts an existing ADR, surface the conflict explicitly rather than silently overriding it.
