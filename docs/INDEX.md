# Documentation Index

This directory contains the working documentation for `ollama-control-plane`.

The docs are currently kept in a flat `docs/` structure.
That is intentional for the current stage of the project.
If the project grows, the docs can later be split into subdirectories, but for now the single-level layout keeps navigation simple.

---

## Reading order

If you are new to the project, read documents in this order:

1. `product-requirements.md`
2. `architecture.md`
3. `security.md`
4. `agent-lifecycle.md`
5. `api-spec.md`
6. `mvp-scope.md`
7. `implementation-guide.md`

If you only need a quick implementation start:
1. `product-requirements.md`
2. `architecture.md`
3. `api-spec.md`
4. `mvp-scope.md`

---

## Document guide

### `product-requirements.md`
Defines what the system is, why it exists, and what it must do.

Use this file for:
- product goals
- scope
- use cases
- functional requirements
- non-functional requirements
- success criteria

This file should answer:
- what problem the system solves
- who uses it
- what capabilities are required
- what is out of scope

---

### `architecture.md`
Defines how the system is structured.

Use this file for:
- major components
- controller / agent-host / gateway boundaries
- data flow
- polling design
- model routing concepts
- deployment topology
- storage and queueing direction

This file should answer:
- how the system works internally
- which component owns which responsibility
- which assumptions are architectural rather than temporary

---

### `security.md`
Defines security assumptions and rules.

Use this file for:
- registration flow
- invitation/bootstrap tokens
- listener tokens
- refresh tokens
- API key handling
- trust boundaries
- audit expectations
- secret handling
- future hardening items such as mTLS and RBAC

This file should answer:
- who can register an agent
- how agents authenticate
- how clients authenticate
- what is considered sensitive
- what must be logged or never logged

---

### `agent-lifecycle.md`
Defines the runtime lifecycle of an agent host.

Use this file for:
- agent states
- registration lifecycle
- polling loop
- refresh behavior
- job execution flow
- retry behavior
- failure and offline handling

This file should answer:
- what an agent does from startup to shutdown
- how polling behaves
- what happens when auth expires
- what happens on failure or disconnect

---

### `api-spec.md`
Defines external and internal API behavior.

Use this file for:
- endpoint definitions
- request and response shapes
- OpenAI-compatible API behavior
- future Anthropic-compatible behavior
- error response format
- streaming behavior when introduced

This file should answer:
- what each endpoint accepts
- what each endpoint returns
- how compatibility behavior is represented
- what clients can rely on

---

### `mvp-scope.md`
Defines phase boundaries and delivery scope.

Use this file for:
- MVP definition
- phase goals
- in-scope vs out-of-scope by phase
- implementation ordering
- milestone boundaries

This file should answer:
- what belongs in Phase 1
- what is deferred to later phases
- what “done” means for each phase

---

### `implementation-guide.md`
Defines how to drive implementation sessions with Claude Code.

Use this file for:
- phased execution guidance
- prompt templates
- implementation checklists
- recommended task ordering
- completion gates

This file should answer:
- how to prompt Claude Code effectively
- how to break work into phases
- how to verify progress before moving on

---

## Document responsibilities

To avoid confusion, use the following separation:

- `product-requirements.md` = what must be true
- `architecture.md` = how the system is organized
- `security.md` = security and trust rules
- `agent-lifecycle.md` = runtime behavior of agents
- `api-spec.md` = interface contracts
- `mvp-scope.md` = what gets built in each phase
- `implementation-guide.md` = how to execute work with Claude Code

Do not mix all concerns into one file unless there is a strong reason.

---

## Update rules

When making changes, ask:

### If product behavior changes
Update:
- `product-requirements.md`
- possibly `mvp-scope.md`

### If architecture changes
Update:
- `architecture.md`
- possibly `agent-lifecycle.md`
- possibly `security.md`

### If authentication or trust boundaries change
Update:
- `security.md`
- `agent-lifecycle.md`
- `api-spec.md` if request/response behavior changes

### If endpoint behavior changes
Update:
- `api-spec.md`

### If phase boundaries change
Update:
- `mvp-scope.md`
- `implementation-guide.md`

### If Claude Code workflow changes
Update:
- `implementation-guide.md`
- `CLAUDE.md` if persistent rules changed

---

## Recommended workflow

Use this order for non-trivial work:

1. Read `CLAUDE.md`
2. Read this file (`INDEX.md`)
3. Read the relevant source docs
4. Update docs if needed
5. Implement a small task
6. Add or update tests
7. Reconcile docs and code
8. Summarize what changed and what remains

---

## Current priority sequence

The current recommended delivery path is:

1. single Controller
2. single Agent Host
3. polling-based execution
4. local Ollama integration
5. OpenAI-compatible chat completions
6. token-based auth and basic auditability
7. multi-agent and scheduling
8. Claude Code integration
9. production hardening

---

## If the docs conflict

If two docs conflict:
1. do not guess
2. identify the conflict explicitly
3. propose the correct resolution
4. update the files so one clear source of truth remains

---

## Future refactor note

The current flat `docs/` structure is acceptable for early development.
If the project grows, it can later be split into subdirectories such as:
- `docs/product/`
- `docs/architecture/`
- `docs/api/`
- `docs/security/`
- `docs/specs/`

Until then, keep filenames stable and responsibilities clear.