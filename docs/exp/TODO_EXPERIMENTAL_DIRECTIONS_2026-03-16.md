# TODO: Experimental Directions from Downloads Review (2026-03-16)

This list is separate from product roadmap TODO because it tracks experimental ideas from external documents.

## D1 - MCP Gateway (`exp/topic-mcp-iiko-gateway`)
- [ ] Define minimal MCP tool contract for current backend (`health`, `metrics`, `task_status`, `diagnose_request`).
- [ ] Add auth model for MCP access (token-based + scoped tool permissions).
- [ ] Implement read-only MCP adapter over existing API endpoints.
- [ ] Add audit logging for all MCP tool calls.
- [ ] Add failure policy and timeouts per tool.

## D2 - Orchestration Layer (`exp/topic-agent-orchestration-layer`)
- [ ] Design optional supervisor service contract (no direct replacement of worker/backend).
- [ ] Add explicit "human approval required" step before irreversible actions.
- [ ] Define guardrails for chat-intent invoice automation (confidence threshold + deny rules).
- [ ] Add safe dry-run mode for orchestration scenarios.

## D3 - Telegram Channel Strategy (`exp/topic-telegram-channel-strategy`)
- [ ] Document transport matrix: Bot API vs Business API vs MTProto/MCP (capabilities/limits/risks).
- [ ] Keep current production path on Bot API; describe fallback and migration criteria.
- [ ] Define compliance checklist for user-like messaging modes (if ever enabled).

## D4 - Agent DevOps Automation (`exp/topic-agent-devops-automation`)
- [x] Build SSH alias convention and documented host profiles.
- [x] Add scripted health bundle (`service status + health endpoint + metrics snapshot`).
- [ ] Pilot DNS automation playbook (Cloudflare API) in non-production environment.
- [ ] Define secrets policy for automation scripts and agent-executed commands.
- [x] Add mailbox duplex loop (`wplan/codexclip/pull/watch`) with Android clipboard support.
- [x] Add local phone terminal control (`wphone`) and practical tutorials (`wtutor`).

## D5 - Quality Gates for AI Development (`exp/topic-quality-gates-ai-dev`)
- [ ] Add baseline static checks (formatter/linter/type checks where feasible).
- [ ] Add anti-pattern test review checklist (avoid vacuous assertions).
- [ ] Add CI job template for pre-merge quality gates.
- [ ] Add coding-task template requiring verification commands before completion.

## D6 - Repository Benchmark Radar (`exp/topic-repo-benchmark-radar`)
- [ ] Create shortlist of reference repos with decision notes (what to adopt / reject and why).
- [ ] Add periodic review cadence for external patterns (monthly or per milestone).
- [ ] Keep comparison notes linked to architecture decisions to avoid random adoption.
