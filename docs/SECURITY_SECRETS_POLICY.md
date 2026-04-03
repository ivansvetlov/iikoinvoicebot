# Security Secrets Policy

_Updated: 2026-03-16_

## Scope
This policy defines how secrets are stored, used, logged, and rotated in this repository and in related Termux/agent tooling.

## Secret classes
1. `Production secrets`:
   - Real iiko credentials, API keys, webhook secrets, infrastructure tokens.
2. `Demo/Test secrets`:
   - Credentials for sandbox/demo stands with no production access.
3. `Local developer secrets`:
   - Personal temporary credentials used only on one workstation/phone.

## Storage rules
1. Never store production secrets in tracked files.
2. Store runtime secrets in environment (`.env`) and keep `.env` out of git.
3. `config/.env.example` must contain placeholders only.
4. `data/users.json` must not be used as long-term secret storage for production.
5. Demo credentials may be documented only in dedicated demo profile docs under `docs/exp/` and must be clearly marked as non-production.

## Logging and output rules
1. Do not print full credentials/tokens in logs, debug output, or chat dumps.
2. Redact secrets in screenshots, shared terminal snippets, and runbooks.
3. Script reports may include endpoint/status, but not raw passwords/tokens.

## Agent/automation rules
1. Commands executed by agent wrappers must not echo secrets to terminal unless explicitly required for one-time local setup.
2. `wmailbox`, `wphone`, and related helpers should transport task text only; no credentials inside task content.
3. For scripted integrations, prefer token/session derived at runtime over hardcoded credentials.

## Rotation and incident response
1. Rotate demo credentials after broad sharing or if leaked externally.
2. Immediately rotate production secrets on suspected leak.
3. Record incident summary and remediation steps in `docs/DEBUG.md` and internal ops notes.

## Current repo action items
1. Migrate persistent iiko credentials away from `data/users.json` to protected storage flow.
2. Add pre-commit/CI scan for obvious secret patterns in tracked files.
3. Keep demo profile docs up to date with explicit "demo only" warning.

