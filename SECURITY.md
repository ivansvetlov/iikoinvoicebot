# Security Policy

## Scope

This policy applies to this repository and all runtime components:
- Telegram bot
- FastAPI backend
- worker/queue pipeline
- integrations with external providers (LLM, iiko API, Redis, DB)

## Reporting a Vulnerability

Please do not open public GitHub issues for security vulnerabilities.

Report privately by email:
- `security@iikoinvoicebot.local` (replace with real mailbox)

Required report fields:
- short summary
- affected component and file/path
- reproduction steps (minimal)
- impact assessment
- suggested fix (optional)

## Response SLA

- Initial acknowledgment: up to 2 business days
- Triage decision: up to 5 business days
- Mitigation or patch plan: up to 10 business days for high/critical issues

## Severity Guidance

- Critical: secret leakage, auth bypass, remote code execution
- High: privilege escalation, unsafe data exposure, destructive action without confirmation
- Medium: denial of service, weak validation, misconfiguration with constrained impact
- Low: informational weaknesses with no direct exploit path

## Disclosure Process

1. Report is received privately.
2. Maintainers validate and assign severity.
3. Fix is prepared in a private branch or restricted PR.
4. Release notes are published after patch deployment.
5. Coordinated public disclosure may follow.

## Hard Rules

- Never commit secrets (`.env`, private keys, tokens, passwords).
- Never store long-lived private keys in project root.
- Use least-privilege credentials for integrations.
- Rotate leaked credentials immediately.
