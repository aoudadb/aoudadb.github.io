---
title: "Reference"
nav_order: 7
has_children: true
---

# Reference

Low-level reference material for the Aouda wire protocol, type system, and error contracts.

| Document | Contents |
|---|---|
| [HTTP API](http-api/) | Full wire protocol — every REST endpoint, request/response shapes, error codes |
| [Timestamp Type](timestamp.md) | Timestamp semantics, storage format, query and comparison behavior |
| [Declaration Finding Codes](plan-codes.md) | Every code a refused start reports for its configuration: severity, stage, exit status, what to do (**BL-1463, next train**) |

Browser-tier closed list (guide, not wire): [What a browser-tier read cannot do](../guides/browser-tier-read-limits.md).

For auth-specific error codes and endpoint reference, see [Auth Reference](../auth/reference.md).
