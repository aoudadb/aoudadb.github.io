---
title: "Guides"
nav_order: 2
has_children: true
---

# Aouda Functionality Overview and Documentation Program

This document is the control plane for Aouda functionality documentation after completion of phases `P0` through `P16` (MVP).

Program status (2026-04-08): all phases through P16 are complete. P14 (Production Readiness) closed all high-severity correctness, durability, and security gaps. P15 delivered the full join engine. P16 delivered cloud/Hub infrastructure, Studio management console, Kubernetes support, managed cloud foundation, and TypeScript client SDK feature parity. Aouda MVP is now complete.

Completion report: `docs/tasks/P16/P16-Completion-Report.md`.
Execution strategy reference: `docs/dev/Production-Readiness-And-Agent-Autonomy-Plan.md`.

Its purpose is to ensure every capability is documented from two angles:

- **Engineering truth**: what was implemented, what is incomplete, and what gaps exist.
- **User truth**: what the feature is, how it works, defaults, config, API usage, code examples, and operations guidance.

This document does not replace dedicated functionality docs. It governs how those docs are produced and validated.

---

## 1) Documentation Outcomes We Need

For each functionality area, documentation must answer all of the following:

1. What exists today in the shipped implementation.
2. What is still planned/deferred and why.
3. How the feature actually works internally (conceptual + implementation model).
4. How to use it in practice from both `.NET` and TypeScript paths where applicable.
5. What defaults are active if users do nothing.
6. What Aouda differentiators are visible in this area.
7. What common mistakes occur and how to fix them quickly.

If one of these answers is missing, the functionality doc is not complete.

---

## 2) Source-of-Truth Hierarchy (Do Not Skip)

Functionality docs must be written from evidence in this order:

1. **Code + tests** in `src/` and `tests/` (current behavior authority).
2. **Phase task reports** in `docs/tasks/P*/` (`*-Report.md`).
3. **Phase task specs** in `docs/tasks/P*/`.
4. **ADRs** in `docs/decisions/`.
5. **Roadmap and backlog** (`docs/ROADMAP.md`, `docs/BACKLOG.md`) for unresolved work.

Rules:

- ADRs define intent; they are not automatic proof of shipped behavior.
- If docs and code disagree, code/tests win and docs must call out drift.
- If gap findings have no backlog entry, add one.

---

## 3) Phase-to-Functionality Mapping Program

Because delivery happened phase-by-phase, each functionality document must include explicit phase mapping.

At minimum, each doc must contain a "Phase Coverage Matrix" with:

- phase (`P0`..`P14`),
- relevant tasks and reports,
- delivered functionality,
- deferred or partial items,
- linked backlog IDs for remaining work.

Use this mapping as the baseline when planning doc updates:

| Functionality Domain | Primary Delivery Phases | Current Doc |
|---|---|---|
| Engine architecture, storage model, write path durability | P0, P1 | `docs/dev/Functionality-Write-Path-Durability.md`, `docs/dev/Functionality-Storage-And-Persistence.md` |
| Query execution, indexing, joins, aggregates | P2, P3, P14, P15 | `docs/dev/Functionality-Query-Execution.md` |
| Hot/cold behavior and memory control | P3, P7 | `docs/dev/Functionality-HotCold-And-Memory.md` |
| Integration/distribution, backup, replication, partitioning, clustering, materialized queries | P4 (+ sub-epics) | `docs/dev/Functionality-Distribution-And-Licensing.md`, `docs/dev/Functionality-Backup-And-Restore.md`, `docs/dev/Functionality-Replication-And-Clustering.md`, `docs/dev/Functionality-Partitioning-And-Multitenancy.md`, `docs/dev/Functionality-TimeSeries-And-Clustering.md`, `docs/dev/Functionality-Materialized-Queries.md` |
| Real-time streaming | P10 | `docs/dev/Functionality-RealTime-Streaming.md` |
| Embedded/document-model and related DX | P11 | `docs/dev/Functionality-AI-Native-Usage.md` |
| Auth foundation and two-layer auth | P12, P14 | `docs/dev/Functionality-Auth-And-Authorization.md` |
| Testing package and developer testing workflows | P13 | `docs/dev/Functionality-Testing-And-DX.md` |
| ADRA/RLS/PLS and auth deepening | P14 | `docs/dev/Functionality-Auth-And-Authorization.md`, `docs/dev/Functionality-AI-Native-Usage.md` |
| Schema lifecycle and evolution patterns | Cross-phase (notably P3/P4/P7/P12/P14) | `docs/dev/Functionality-Schema-Lifecycle.md` |
| Server CLI, Docker, Kubernetes, cloud, Hub | P16 | `docs/dev/Functionality-Cloud-And-Hub.md` |
| **Server configuration** (precedence, install bootstrap, restart) | P34 / P4 | `guides/server-configuration.md` |
| **Named queries, data-plane listener, transforms, access-surface diff** | P37 | `guides/named-queries.md`, `guides/direct-client-access.md`, `guides/division-of-responsibility.md`, `guides/insert-transforms.md`, `guides/access-surface.md`, `guides/browser-tier-read-limits.md` — **user guides**; they follow §1 and §4 below, not the engine `Functionality-Document-Template` 2.1–2.18 skeleton |
| **Freshness and replica consistency** | P38 | `guides/freshness.md` — token, `AtLeast`, alias `freshness`, caveats; wire in `reference/http-api.md` § Consistency tokens. Same user-guide rules as the P37 cluster |
| **How to build an application on Aouda** (the flagship entry point) | Cross-phase (P37, P40) | `guides/build-apps.md` — canonical build path for new applications; `guides/adoption.md` is its existing-application branch. Same user-guide rules as the P37 cluster |
| Studio management console | P5, P6, P9, P12, P16 | `docs/dev/Functionality-Studio.md` |
| TypeScript client SDK (`@aouda/client`) | P5, P10, P12, P14, P15, P16 | `docs/dev/Functionality-TypeScript-Client.md` |

Notes:

- Some early and transition tasks are stored in legacy root paths while newer work is under `docs/tasks/P*/`.
- During phase audit, normalize references to phase folders so doc evidence is easier to maintain.
- P14 (Production Readiness) closed correctness, durability, and security gaps; see `docs/dev/Production-Readiness-And-Agent-Autonomy-Plan.md`.
- P15 (Full Join Support) delivered complete join engine; see `docs/tasks/P15/P15-Full-Join-Support-Tasks.md`.
- P16 (Cloud and Hub) delivered all 8 epics (75 tasks); see `docs/tasks/P16/P16-Completion-Report.md`.

---

## 4) Quality Bar for All Functionality Docs

Every functionality doc must pass these checks:

1. **Defaults-first**: explicit default behavior and default values table.
2. **Availability-first**: "Available now" vs "Planned" vs "Reserved".
3. **Phase evidence**: statements mapped to tasks/reports and code/tests.
4. **Differentiators-first**: explicit "why Aouda is different" section.
5. **Usage depth**: practical, copy-paste examples for real scenarios.
6. **API depth**: relevant command/API coverage for `.NET`, TypeScript, and HTTP when applicable.
7. **Operations depth**: restart/recovery behavior, observability signals, tuning surface.
8. **Troubleshooting depth**: symptom -> likely cause -> action matrix.
9. **Honesty**: no implied completeness when implementation is partial.
10. **Gap tracking**: explicit unresolved items with backlog links.

---

## 5) Mandatory Authoring Template (Moved Out)

The template for writing functionality docs is now maintained separately:

- `docs/dev/Functionality-Document-Template.md`

That template is intentionally extensive and is **required for engine-repo `docs/dev/Functionality-*` rewrites** (implementer-facing). It is **not** required for aouda-docs user guides — including the P37 pages (`named-queries`, `direct-client-access`, `division-of-responsibility`, `insert-transforms`, `access-surface`). Those follow §1 and §4 of this file (defaults, availability, honesty, troubleshooting) without the 2.1–2.18 audit skeleton.

It includes:

- research workflow,
- evidence capture rules,
- phase coverage matrix format,
- implementation and API documentation requirements,
- differentiator framing requirements,
- completion checklist for publish readiness.

Do not draft new **engine** functionality docs directly from this overview without using the template. User-facing aouda-docs pages do not copy that template.

Additionally, every functionality document must act as an explicit **entry point**:

- include "Start Here" navigation for common questions,
- include complete configuration and API coverage tables,
- include explicit missing-API and missing-capability matrices.

---

## 6) Documentation Workflow (Gap Audit -> Backlog + Delivery)

Now that the domain docs are approved, use this repeatable workflow for each domain:

1. **Inventory phase evidence**
   - Read all relevant task specs + reports in `docs/tasks/P*/`.
   - Build implemented/deferred list.
2. **Verify against code/API/tests**
   - Confirm behavior and defaults in actual implementation.
3. **Reconcile with existing docs**
   - Mark stale claims and update or remove.
4. **Extract concrete gaps**
   - Convert every unresolved/missing item into backlog candidates (with scope, impact, and evidence).
5. **Backlog reconcile**
   - Match candidates against `docs/BACKLOG.md`, avoid duplicates, and add missing entries.
6. **Prioritize for production readiness**
   - Classify as correctness, durability, security, performance, operability, DX, or ecosystem.
7. **Update this overview**
   - Keep status as approved unless a doc falls out-of-date; track audit date and major gap deltas.

---

## 7) Functionality Documentation Index and Status

This section tracks the per-domain documents and maturity level.

| Domain | Target Doc | Status |
|---|---|---|
| Schema lifecycle and evolution | `docs/dev/Functionality-Schema-Lifecycle.md` | Approved baseline — updated P14 (Extend inference mode) |
| Hot/cold and memory behavior | `docs/dev/Functionality-HotCold-And-Memory.md` | Approved baseline |
| Real-time streaming | `docs/dev/Functionality-RealTime-Streaming.md` | Approved baseline — updated P14 (WebSocket CORS) |
| Auth and authorization | `docs/dev/Functionality-Auth-And-Authorization.md` | Approved baseline — updated P14 (audit, server admin keys), P16 (Hub auth, server admin key API) |
| Storage and persistence | `docs/dev/Functionality-Storage-And-Persistence.md` | Approved baseline — updated P14 (embedded persistence fix) |
| Write path durability | `docs/dev/Functionality-Write-Path-Durability.md` | Approved baseline — updated P14 (graceful shutdown, count endpoint) |
| Query execution and optimization | `docs/dev/Functionality-Query-Execution.md` | Approved baseline — updated P14 (correctness fixes), P15 (full join engine, all join types, post-join ops) |
| Partitioning and multi-tenancy | `docs/dev/Functionality-Partitioning-And-Multitenancy.md` | Approved baseline |
| Time-series and clustering | `docs/dev/Functionality-TimeSeries-And-Clustering.md` | Approved baseline |
| Materialized queries | `docs/dev/Functionality-Materialized-Queries.md` | Approved baseline — updated P16 (client API, Studio browser) |
| Replication and cluster behavior | `docs/dev/Functionality-Replication-And-Clustering.md` | Approved baseline — updated P16 (cluster lifecycle APIs, witness role) |
| Backup and restore | `docs/dev/Functionality-Backup-And-Restore.md` | Approved baseline — updated P16 (backup REST APIs, scheduling, Studio UI) |
| AI-native usage model | `docs/dev/Functionality-AI-Native-Usage.md` | Approved baseline — updated P14 (Extend mode, WhereClause groups), P16 (MCP cluster tools) |
| Testing and developer experience | `docs/dev/Functionality-Testing-And-DX.md` | Approved baseline |
| Distribution and licensing | `docs/dev/Functionality-Distribution-And-Licensing.md` | Approved baseline — updated P16 (CLI, Docker, Helm, K8s operator) |
| **Server configuration** (precedence, install, persistence) | `guides/server-configuration.md` | **Published** — canonical operator reference |
| Cloud, Hub, and deployment | `docs/dev/Functionality-Cloud-And-Hub.md` | **New** — P16 (Hub backend, cloud control plane, K8s operator, Docker) |
| Studio management console | `docs/dev/Functionality-Studio.md` | **New** — P5/P6/P9/P12/P16 (data explorer, cluster ops, Hub integration) |
| TypeScript client SDK | `docs/dev/Functionality-TypeScript-Client.md` | **New** — P5/P10/P12/P15/P16 (query builder, joins, aggregates, admin APIs, MCP tools) |
| Market data / stock quotes (use case) | `guides/market-data.md` | **Rewritten P40 S09** — browser-tier first; `whenParamPresent`, `orderByChoices`, computed MQ ranking, `collapse_inserts`. Fixture: `examples/p40-browser-tier/` |
| **Building applications on Aouda** (flagship entry point) | `guides/build-apps.md` | **Published** — BL-183; canonical build path, capability map, agent contract. Adoption is its existing-app branch |

---

## 8) Relationship to Getting Started Docs

Keep these boundaries strict:

- `Getting-Started*.md` -> fastest first-run success.
- `Functionality-*.md` -> deep behavior, defaults, architecture, operations, and advanced usage.

Getting-started guides should link to functionality docs for depth, not duplicate them.

---

## 9) Maintenance Rules

- Update this file when a functionality doc is created, substantially revised, or marked complete.
- Any "planned" claim in a functionality doc must have either:
  - an ADR reference, and
  - an active task/backlog reference.
- If a doc section grows into implementation detail, split detail into dedicated functionality/reference docs and keep this overview concise.

