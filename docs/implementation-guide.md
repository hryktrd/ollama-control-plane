# Implementation Guide

This document is a phased implementation guide for building **Ollama Control Plane** with Claude Code.

It is intended to help drive development in small, reviewable increments while keeping requirements, architecture, API contracts, and security assumptions aligned.

This file is **not** the primary source of truth for system behavior.
The source of truth remains:

- `CLAUDE.md`
- `docs/requirements/`
- `docs/architecture/`
- `docs/api/`
- `docs/specs/`
- `docs/adr/`

Use this guide as the execution playbook for Claude Code sessions.

---

## How to use this guide

1. Start from the current phase only.
2. Before implementation, read the referenced docs for that phase.
3. Copy the relevant Claude Code prompt template into your session.
4. Ask Claude Code to implement only one small unit at a time.
5. Review the output, run tests, and update docs.
6. Move to the next task only after the current task is verified.

---

## Development principles

These rules apply to every phase.

### 1. Docs-first
Before implementing behavior changes, update the relevant spec or requirements document.

### 2. Small diffs
Do not ask Claude Code to build an entire phase in one shot.
Prefer one endpoint, one flow, or one subsystem at a time.

### 3. Test with implementation
Every meaningful implementation should include tests.

### 4. Backward compatibility
When moving to a later phase, avoid breaking validated earlier behavior unless explicitly planned and documented.

### 5. Explicit constraints
State stack, interfaces, auth assumptions, and out-of-scope items up front.
Claude performs better when constraints are concrete.

### 6. Keep the architecture model-agnostic
The system must not become Qwen-only.
Qwen, Gemma, and future Ollama-compatible models should remain possible.

---

## Current target architecture

The project is expected to evolve toward this structure:

- **Controller**: registration, auth, polling coordination, job dispatch, audit
- **Agent Host**: local runtime installed on user PCs, connected to local Ollama
- **Gateway/API**: OpenAI-compatible and Claude Code-friendly endpoints
- **Model routing layer**: logical model alias to real Ollama model and agent pool

Core architectural assumptions:

- Pull-based polling from Agent Host to Controller
- Short-lived polling credentials
- Bootstrap registration separate from normal operation credentials
- Ollama remains local to each Agent Host
- Controller acts as the public control plane

---

## Phase overview

| Phase | Goal | Expected outcome |
|---|---|---|
| Phase 1 | MVP foundation | Single Controller + single Agent Host + OpenAI-compatible basic API |
| Phase 2 | Scale-out runtime | Multiple agents, pools, scheduling, streaming, health tracking |
| Phase 3 | Integration layer | Claude Code integration, Anthropic-compatible API, admin UI, audit improvements |
| Phase 4 | Production hardening | mTLS, RBAC, advanced rate limiting, deployment automation, monitoring |

---

# Phase 1: MVP

## Goal

Build the smallest end-to-end working system with:

- one Controller
- one Agent Host
- local Ollama execution
- OpenAI-compatible chat endpoint
- polling-based job execution

## Expected duration

Approximately 4–6 weeks.

## Phase 1 success criteria

- Agent Host can connect to local Ollama.
- Controller supports agent registration and polling.
- OpenAI SDK works via `base_url` replacement.
- One Controller and one Agent Host can complete a job end-to-end.

## Required reference documents

Read these before starting Phase 1:

- `docs/product/vision.md`
- `docs/product/scope.md`
- `docs/requirements/functional-requirements.md`
- `docs/requirements/non-functional-requirements.md`
- `docs/requirements/security-requirements.md`
- `docs/architecture/overview.md`
- `docs/architecture/polling-lifecycle.md`
- `docs/architecture/auth-token-flow.md`
- `docs/api/openai-compatible.md`
- `docs/specs/spec-mvp-controller.md`

---

## Phase 1 implementation scope

### Controller
- FastAPI application bootstrap
- SQLite persistence for MVP
- Agent registration endpoint
- Agent polling endpoint
- Job result ingestion endpoint
- OpenAI-compatible chat completions endpoint
- Models listing endpoint
- JWT-based polling credentials
- Basic API key validation

### Agent Host
- Local runtime service
- Local Ollama connection
- Agent registration flow
- Polling loop
- Chat completion job execution
- Result submission
- Token refresh support
- Retry and basic failure handling

### Tests
- Controller unit tests
- Agent Host unit tests
- End-to-end integration test:
  registration -> polling -> job execution -> response return

---

## Phase 1 recommended implementation order

### Week 1–2: Foundation
- Controller project structure
- settings/config management
- database layer
- ORM models
- schema definitions
- bootstrap auth helpers
- JWT issue/verify helpers

### Week 2–3: Agent registration flow
- invitation token validation
- `/agents/register`
- listener token issuance
- refresh token issuance
- token refresh endpoint if included in MVP

### Week 3–4: Polling and job execution
- `/agents/poll`
- `/jobs/{job_id}/result`
- in-memory job queue
- agent state updates

### Week 4–5: OpenAI-compatible API
- `/v1/models`
- `/v1/chat/completions`
- job creation -> dispatch -> wait -> response mapping

### Week 5–6: Verification and cleanup
- pytest coverage improvements
- integration tests
- README setup instructions
- `.env.example`
- implementation notes

---

## Phase 1 Claude Code prompt template

Copy and paste this into Claude Code when starting a Phase 1 task.

```text
Project: Ollama Control Plane - Phase 1 MVP

Read first:
- docs/INDEX.md
- docs/product/vision.md
- docs/requirements/functional-requirements.md
- docs/requirements/non-functional-requirements.md
- docs/requirements/security-requirements.md
- docs/architecture/overview.md
- docs/architecture/polling-lifecycle.md
- docs/architecture/auth-token-flow.md
- docs/api/openai-compatible.md
- docs/specs/spec-mvp-controller.md

Task:
Implement the minimum viable Controller and Agent Host for Phase 1.

Tech stack:
- Python 3.10+
- FastAPI
- SQLite
- SQLAlchemy
- pytest

Controller scope:
1. FastAPI app bootstrap
2. settings.py for env-based config
3. database.py for SQLite
4. ORM models for agents, jobs, tokens, api_keys
5. POST /agents/register
6. POST /agents/poll
7. POST /jobs/{job_id}/result
8. GET /v1/models
9. POST /v1/chat/completions

Agent Host scope:
1. Local service package structure
2. Connect to local Ollama at http://127.0.0.1:11434
3. Register with invitation token
4. Keep listener token in memory
5. Poll Controller
6. Execute chat completion jobs via Ollama
7. Submit job results
8. Refresh token when needed
9. Retry on transient failures

Constraints:
- Phase 1 is single-agent only
- No multiple agent pools yet
- No streaming yet
- No Docker requirement yet
- JWT secret must come from env var
- Follow docs/api/openai-compatible.md for response shape
- Follow docs/requirements/security-requirements.md for auth assumptions
- Keep implementation small and reviewable

Deliverables:
- Complete implementation under apps/controller and apps/agent-host
- requirements.txt or pyproject.toml
- .env.example
- minimal README setup instructions
- pytest tests for key flows

Testing:
- Add unit tests and at least one end-to-end integration test
- Aim for >70% coverage
- Prefer focused tests over broad but shallow ones

Important:
Do not invent behavior not described in docs.
If anything is ambiguous, stop and propose concrete options before continuing.
```

---

## Phase 1 checklist

### Controller
- [ ] FastAPI app starts
- [ ] SQLite DB initializes
- [ ] `/agents/register` validates invitation token and registers agent
- [ ] `/agents/poll` validates listener token and returns job or 204
- [ ] `/jobs/{job_id}/result` accepts agent results
- [ ] `/v1/chat/completions` returns OpenAI-compatible response
- [ ] `/v1/models` returns available models
- [ ] JWT secret is env-driven
- [ ] Tests exist for key flows

### Agent Host
- [ ] Agent Host package exists
- [ ] Local Ollama connection works
- [ ] Agent can register
- [ ] Polling loop works
- [ ] Job execution works
- [ ] Results are sent back
- [ ] Token refresh works
- [ ] Retry logic exists
- [ ] Tests exist for key flows

### Integration
- [ ] Controller can start
- [ ] Agent Host can start
- [ ] OpenAI SDK can call the gateway/controller endpoint
- [ ] Agent receives the job
- [ ] Ollama executes the model call
- [ ] Response returns to the client correctly

---

## Phase 1 design notes

### Pull-based polling
Use pull-based polling from Agent Host to Controller.
This simplifies NAT traversal and avoids exposing local PCs publicly.

### Short-lived tokens
Use short-lived listener tokens.
Refresh tokens may exist for token renewal, but bootstrap credentials must remain separate.

### Expandable schema
Even in MVP, choose table names and relationships that can grow into multi-agent and pool-aware behavior later.

### Queue simplicity
Use in-memory queueing for MVP if needed.
Defer Redis/PostgreSQL queueing to later phases.

### Testing matters
Integration testing should begin in Phase 1 so later phases can preserve behavior with confidence.

---

# Phase 2: Multi-agent and scaling

## Goal

Expand the MVP to support multiple Agent Hosts, pool-based routing, scheduling, and streaming responses.

## Expected duration

Approximately 3–4 weeks after Phase 1.

## Phase 2 success criteria

- Multiple Agent Hosts can register and execute jobs.
- Agent Pools exist and are manageable.
- Scheduler can route jobs using pool and capability constraints.
- Streaming responses are supported.
- Offline agents are detected.

## Required reference documents

- `docs/requirements/functional-requirements.md`
- `docs/requirements/non-functional-requirements.md`
- `docs/architecture/agent-pool.md`
- `docs/architecture/deployment-topology.md`
- `docs/specs/spec-job-dispatch.md`
- `docs/specs/spec-model-routing.md`

---

## Phase 2 implementation scope

- `agent_pools` data model
- pool-aware agent registration
- scheduler
- resource-aware agent selection
- SSE or equivalent streaming
- health tracking and offline detection
- backward-compatible API evolution
- schema migration strategy

---

## Phase 2 Claude Code prompt template

```text
Project: Ollama Control Plane - Phase 2

Read first:
- docs/INDEX.md
- docs/requirements/functional-requirements.md
- docs/requirements/non-functional-requirements.md
- docs/architecture/agent-pool.md
- docs/architecture/deployment-topology.md
- docs/specs/spec-job-dispatch.md
- docs/specs/spec-model-routing.md

Task:
Extend the validated Phase 1 implementation to support multiple agents, pools, scheduler logic, and streaming.

Scope:
1. Add agent pool support
2. Add scheduler logic
3. Add health tracking
4. Add streaming responses
5. Preserve Phase 1 compatibility

Constraints:
- Do not break validated Phase 1 flows
- Add migrations or migration planning
- Keep scheduling logic explainable and testable
- Prefer minimal complexity before advanced optimization

Deliverables:
- updated models
- scheduler implementation
- pool-aware APIs if required by spec
- tests covering multi-agent dispatch
- streaming tests if implemented

Important:
Before implementing, identify all Phase 1 compatibility risks.
```

---

## Phase 2 checklist

- [ ] Multiple agents supported
- [ ] Agent pools supported
- [ ] Scheduler routes jobs correctly
- [ ] Resource/capability-aware matching exists
- [ ] Streaming works
- [ ] Offline agents are detected
- [ ] Phase 1 tests still pass

---

# Phase 3: Claude Code integration and advanced features

## Goal

Add developer-facing integrations and management functionality.

## Expected duration

Approximately 3–4 weeks after Phase 2.

## Phase 3 success criteria

- Claude Code can use routed local models through the control plane.
- Anthropic-compatible endpoint exists if still required by integration strategy.
- Logical model aliases map cleanly to physical models.
- Admin UI exists for operational visibility.
- Audit logging is significantly improved.

## Required reference documents

- `docs/api/anthropic-compatible.md`
- `docs/integrations/claude-code.md`
- `docs/specs/spec-claude-code-integration.md`
- `docs/specs/spec-model-routing.md`
- `docs/requirements/security-requirements.md`

---

## Phase 3 implementation scope

- Anthropic-compatible endpoint if required
- logical model alias routing
- Claude Code integration flow
- admin UI
- API key management
- improved audit logs

---

## Phase 3 Claude Code prompt template

```text
Project: Ollama Control Plane - Phase 3

Read first:
- docs/INDEX.md
- docs/api/anthropic-compatible.md
- docs/integrations/claude-code.md
- docs/specs/spec-claude-code-integration.md
- docs/specs/spec-model-routing.md
- docs/requirements/security-requirements.md

Task:
Implement Claude Code integration and the supporting compatibility/routing layers.

Scope:
1. Anthropic-compatible endpoint if required
2. Logical model alias mapping
3. Claude Code integration documentation and config support
4. Admin UI for agents, jobs, API keys, and audit logs
5. Improved audit logging

Constraints:
- Preserve OpenAI-compatible API behavior
- Keep model aliasing explicit and documented
- Protect admin features with appropriate auth
- Treat audit log as append-only where possible

Deliverables:
- endpoint and routing changes
- integration docs
- admin UI implementation
- audit log enhancements
- tests for compatibility behavior
```

---

## Phase 3 checklist

- [ ] Claude Code integration works
- [ ] Anthropic-compatible API exists if required
- [ ] Logical model aliases work
- [ ] Admin UI exists
- [ ] Audit logs improved
- [ ] OpenAI compatibility still works

---

# Phase 4: Production hardening

## Goal

Make the system safe and operable for real deployments.

## Expected duration

Approximately 2–3 weeks after Phase 3.

## Phase 4 success criteria

- mTLS is supported for Agent Host to Controller communication
- RBAC exists
- advanced rate limiting exists
- deployment automation exists
- monitoring and alerting exist

## Required reference documents

- `docs/requirements/security-requirements.md`
- `docs/architecture/deployment-topology.md`
- `docs/specs/` relevant deployment/security specs
- ADRs governing trust boundaries and security decisions

---

## Phase 4 implementation scope

- mTLS
- RBAC
- advanced rate limiting
- deployment automation
- monitoring and alerting
- secret handling improvements

---

## Phase 4 Claude Code prompt template

```text
Project: Ollama Control Plane - Phase 4

Read first:
- docs/INDEX.md
- docs/requirements/security-requirements.md
- docs/architecture/deployment-topology.md
- relevant docs/specs files
- relevant docs/adr records

Task:
Harden the system for production use.

Scope:
1. mTLS for agent-controller communication
2. RBAC
3. Advanced rate limiting
4. Deployment automation
5. Monitoring and alerting

Constraints:
- Preserve validated earlier behavior
- Security defaults must be safe
- Secrets must not be committed
- Monitoring must cover auth, job flow, and agent health

Deliverables:
- security implementation
- deployment manifests/templates
- monitoring config
- tests and operational docs
```

---

## Phase 4 checklist

- [ ] mTLS implemented
- [ ] RBAC implemented
- [ ] Rate limiting improved
- [ ] Deployment automation exists
- [ ] Monitoring exists
- [ ] Security defaults are safe

---

# General implementation guidelines

## Testing
- Write tests with implementation
- Prefer focused, meaningful tests
- Keep integration tests running early
- Coverage target should be meaningful, not cosmetic

## Error handling
- Use a consistent error format
- Return correct HTTP status codes
- Distinguish validation, auth, routing, and execution errors

## Secret handling
- Keep `.env`, `.env.local`, certs, and local secrets out of git
- Use `.env.example` for non-secret examples
- In production, prefer env injection or a secret manager

## Database evolution
- MVP may start with SQLite
- Use proper migration tooling before schema complexity grows
- Do not hide schema-breaking changes

## Documentation
- Update docs whenever behavior changes
- Keep API examples current
- Keep requirements and specs aligned with code

## Versioning
Tag major phase milestones if useful, for example:

```bash
git tag -a v0.1.0-phase1-mvp -m "Phase 1 MVP complete"
git push origin --tags
```

---

# Effective prompting patterns for Claude Code

## Good patterns

### Be explicit
Instead of:
```text
Make a nice endpoint
```

Use:
```text
Implement POST /agents/register according to docs/api/controller-api.md and docs/architecture/auth-token-flow.md
```

### Provide constraints
Instead of:
```text
Build Phase 1
```

Use:
```text
Implement only the Controller registration flow for Phase 1.
Do not add multiple agent support.
Add tests.
```

### Reference documents
Instead of:
```text
Use the architecture
```

Use:
```text
Follow docs/architecture/polling-lifecycle.md for polling semantics and docs/requirements/security-requirements.md for token handling assumptions.
```

### Require verification
Instead of:
```text
Implement it
```

Use:
```text
Implement it, add tests, and summarize any unresolved ambiguity.
```

---

## Avoid these patterns

### Vague requests
Do not ask for “something good” or “a full system” without boundaries.

### Overloading a single session
Do not ask Claude Code to build an entire phase in one prompt.

### Silent architecture changes
Do not let implementation drift beyond the spec or ADRs without updating docs.

---

# FAQ

## What if Claude Code output quality is low?
Check whether:
- the referenced docs are clear
- the task is too large
- the constraints are too vague
- the expected outputs are not explicit enough

## What if the logic is complex?
Ask Claude Code first to propose:
- a flow
- a data model
- edge cases
- a test plan

Then ask it to implement.

## What if security is important?
Quote the relevant sections from:
- `docs/requirements/security-requirements.md`
- `docs/architecture/auth-token-flow.md`
- related ADRs

## What if the existing code must not break?
Tell Claude Code explicitly:
- no breaking API changes
- preserve Phase 1 behavior
- update tests for backward compatibility

---

# Phase completion gates

## Phase 1 complete when
- [ ] Agent Host can connect to Ollama
- [ ] Controller starts successfully
- [ ] Agent registration works
- [ ] Polling works
- [ ] `/v1/chat/completions` works
- [ ] single-agent job loop works
- [ ] tests are passing
- [ ] setup docs exist

## Phase 2 complete when
- [ ] multiple agents work
- [ ] pools work
- [ ] scheduling works
- [ ] streaming works
- [ ] Phase 1 tests still pass

## Phase 3 complete when
- [ ] Claude Code integration works
- [ ] compatibility layer works as designed
- [ ] model alias routing works
- [ ] admin tooling exists
- [ ] auditability improves

## Phase 4 complete when
- [ ] transport security is hardened
- [ ] access control is hardened
- [ ] production deployment paths exist
- [ ] monitoring exists
- [ ] operational docs exist

---

# Final note

Use this guide to keep Claude Code sessions focused, small, and verifiable.

The most reliable workflow is:

1. update docs
2. implement one bounded task
3. run tests
4. review behavior
5. update docs again if needed

Do not optimize for speed at the cost of traceability.