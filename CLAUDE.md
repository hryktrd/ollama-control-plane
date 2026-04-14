# CLAUDE.md

## Project

`ollama-control-plane` is a control plane for using locally running Ollama model hosts across multiple PCs.

The system should support:
- remote use of local Ollama-backed models
- polling-based agent execution from user PCs
- model-agnostic routing across Qwen, Gemma, and future Ollama-compatible models
- OpenAI-compatible API access
- Claude Code-friendly integration paths
- secure agent registration, authentication, and auditability

This repository is not model-specific.
Do not design the system around Qwen only unless a task explicitly requires model-specific behavior.

---

## Read first

Before making non-trivial changes, read these in order:

1. `README.md`
2. `docs/INDEX.md`
3. `docs/product-requirements.md`
4. `docs/architecture.md`

If the task involves authentication, registration, trust boundaries, or audit behavior, also read:

- `docs/security.md`
- `docs/agent-lifecycle.md`

If the task involves API behavior or SDK compatibility, also read:

- `docs/api-spec.md`

If the task is implementation work, also read:

- `docs/mvp-scope.md`
- `docs/implementation-guide.md`

---

## Current repository structure

Top-level:
- `CLAUDE.md` — persistent project instructions for Claude Code
- `README.md` — human-readable project overview and setup
- `docs/` — working project documentation

Current docs:
- `docs/INDEX.md` — document index and reading order
- `docs/product-requirements.md` — product and system requirements
- `docs/architecture.md` — architecture and component design
- `docs/api-spec.md` — API contracts and compatibility behavior
- `docs/security.md` — auth, token, trust boundary, and security requirements
- `docs/agent-lifecycle.md` — agent states, polling loop, and lifecycle flows
- `docs/mvp-scope.md` — scoped implementation plan for MVP and phases
- `docs/implementation-guide.md` — Claude Code execution playbook and prompt templates

---

## Core architecture assumptions

Unless a task explicitly changes them, assume:

- Agent Hosts run on user-controlled PCs and connect to local Ollama.
- Agent Hosts poll the Controller rather than receiving inbound commands directly.
- The Controller is the central trust and coordination boundary.
- Ollama should not be directly exposed to the public internet.
- Registration credentials and normal polling credentials must be separated.
- Short-lived operational credentials are preferred over long-lived static secrets.
- The architecture must stay compatible with multiple model families.

---

## Working rules

### Docs-first
Update docs before or alongside code when behavior, requirements, or architecture changes.

### Specs before implementation
Do not implement major behavior until the relevant details are reflected in the docs.
If the behavior is not described clearly enough in the current docs, update the relevant document first.

### No hidden assumptions
If requirements are ambiguous, do not silently invent behavior.
State the ambiguity, propose concrete options, and ask for a decision when needed.

### Small, reviewable changes
Prefer small, bounded tasks over large all-at-once implementations.

### Preserve model-agnostic design
Keep the system generic across Qwen, Gemma, and future Ollama-served models.

### Keep documentation aligned
Do not let code drift away from `product-requirements.md`, `architecture.md`, `api-spec.md`, `security.md`, or `agent-lifecycle.md`.

---

## Implementation workflow

For non-trivial work, follow this order:

1. Read `docs/INDEX.md`
2. Read the most relevant source docs
3. Check whether the current docs are sufficient
4. Update docs first if needed
5. Implement the smallest useful slice
6. Add or update tests
7. Update docs again if behavior changed
8. Summarize changed files, decisions, and unresolved risks

For phase-based work, use:
- `docs/mvp-scope.md`
- `docs/implementation-guide.md`

---

## Source of truth by topic

Use these files as the current source of truth:

- Product and scope: `docs/product-requirements.md`
- Architecture and component boundaries: `docs/architecture.md`
- API behavior and payloads: `docs/api-spec.md`
- Auth and security rules: `docs/security.md`
- Agent states and polling flow: `docs/agent-lifecycle.md`
- Phase boundaries and delivery scope: `docs/mvp-scope.md`
- Execution prompts and phased implementation guidance: `docs/implementation-guide.md`

If these files conflict, prefer resolving the conflict explicitly instead of guessing.

---

## Coding expectations

- Keep Controller, Gateway, and Agent Host responsibilities separated.
- Prefer explicit types and clear interfaces.
- Design for retries, offline agents, cancellation, and partial failure.
- Keep state transitions explicit and auditable.
- Avoid tight coupling between external API payloads and internal persistence models.
- Do not hardcode model-specific logic unless required.
- Do not log secrets, raw tokens, or sensitive values.

---

## Security expectations

- Treat the Controller as an internet-facing boundary.
- Keep Ollama local to the Agent Host.
- Use bootstrap registration credentials only for enrollment.
- Use short-lived listener or session tokens for normal agent operation.
- Support revocation and rotation where possible.
- Keep auditability for registration, auth events, job dispatch, and admin actions.
- Any security tradeoff made for convenience must be documented in `docs/security.md`.

---

## Testing expectations

When implementing behavior:
- add tests with the implementation
- prefer meaningful unit tests plus integration coverage for critical flows
- preserve previously validated behavior
- verify auth failures, polling behavior, job execution flow, and retry-sensitive paths

Critical flows that should remain testable:
- agent registration
- token issuance and refresh
- polling
- job dispatch
- job result submission
- OpenAI-compatible request/response flow
- model routing behavior if introduced

---

## Definition of done

A task is not complete unless:
- code is implemented
- relevant tests are added or updated
- affected docs are updated
- behavior remains aligned with the current docs
- the final summary lists changed files and any remaining risks or follow-up work

---

## When unsure

If you are unsure:
- identify the ambiguity clearly
- propose 1 to 3 concrete options
- recommend one option with reasoning
- wait for confirmation if the choice affects architecture, security, compatibility, or migration