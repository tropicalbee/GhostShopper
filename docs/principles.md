# Principles

Copied from CLAUDE.md. If they ever differ, CLAUDE.md wins.

## Rules

- The shopper agent is a real tool-calling loop, not a fixed script.
- The readiness score is deterministic, never computed by the LLM. The LLM only navigates and explains fixes.
- No secrets in git.
- Never silently fall back to sample data.
- Small commits.

## Scope lock

One store, one product flow, one score. No accounts, no multi-store.
