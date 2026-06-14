# Contributing Guide

## Branching

- Use feature branches from the active base branch.
- Recommended naming:
- `feature/<scope>-<short-topic>`
- `fix/<scope>-<short-topic>`
- `chore/<scope>-<short-topic>`

## Commit Quality

- Keep commits focused and logically scoped.
- Prefer small, reviewable commits.
- Commit message format:
- `<type>(<scope>): <summary>`
- Examples:
- `fix(bot): prevent duplicate pre-posting review message`
- `docs(audit): add post-audit remediation tracker`

## Pull Requests

- Use the PR template.
- Explain:
- what changed
- why this is needed
- risks and rollback plan
- Attach verification evidence:
- tests run
- manual scenario checks
- logs/screenshots when relevant

## Required Checks Before Merge

- Tests pass for changed area.
- No obvious regressions in core flow:
- document intake
- recognition
- sync/posting path
- Docs are updated when behavior/config changed.

## Code Standards

- Follow existing project structure and naming.
- Avoid monolithic handlers when adding new functionality.
- Add or update tests for non-trivial behavior changes.
- Keep external integrations behind clear service/client boundaries.

## Security and Secrets

- Do not commit `.env` or credentials.
- Do not keep private keys in repository root.
- If secret exposure is suspected, rotate immediately.
- Follow `SECURITY.md` for vulnerability handling.

## Documentation Standards

- `docs/TODO.md`: product roadmap and priorities.
- `docs/AUDIT_REMEDIATION_PLAN.md`: post-audit governance/security track.
- `docs/AGENT_HANDOFF.md`: historical handoff/change context.
