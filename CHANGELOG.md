---
title: "Changelog"
nav_order: 9
---

# Aouda Changelog

Public, user-facing release notes. Engine phase status lives in the server
[CHANGELOG](https://github.com/aoudadb/aouda/blob/main/docs/CHANGELOG.md) and
[ROADMAP](https://github.com/aoudadb/aouda/blob/main/docs/ROADMAP.md) (P0–P46 complete).

---

## Unreleased

- **"Should this table have a partition key?" is now its own section, and the answer is often no.** The P45 rule — *partition a key only when each key value holds at least one full segment's worth of rows* — was previously stated only inside "Choosing `initialBucketCount` at scale", where a reader asking whether to partition at all would never find it, and it never named the number. It now leads [Partitioning](guides/partitioning.md#should-this-table-have-a-partition-key-p45), states the figure (**~1 000 000 rows**), and carries a worked example for a table *below* the line — where the right answer is no `partitionKey` and `clusterColumns` on the time column. Linked from the schema decision table in [Build apps](guides/build-apps.md), from [Bulk load](guides/bulk-load.md#choosing-partition-storage-mode), and from [Time-series](guides/time-series.md).
- **Grants do not require a partitioned table.** An `auth-db-rls` rule with `valueSource: "PartitionGrant"` injects the caller's grants as an ordinary `IN` predicate on a named column — it never consults the partition router, so it behaves identically on an unpartitioned table. A grant's `partitionKey` is a key *within the grant document*, not a claim about the table's physical layout. That is what lets a "user belongs to many rooms" application keep grant-based authorization while dropping a partition key its volume does not justify. New worked example: [the unpartitioned variant](auth/authorization.md#the-unpartitioned-variant--same-grants-no-partition-key) of the chat use case, with the same grant calls unchanged.
- **The chat and per-user-feed examples now check volume first.** Use Case 1 — Chat Application partitions `messages` by `room_id`, which is right only when each room holds ~1 M rows; a typical chat product is orders of magnitude below that. Both it and [live subscriptions](guides/partitioning.md#live-subscriptions-on-a-partitioned-table) now say so and point at the unpartitioned design. The live-subscriptions section gains **Option C** (drop the partition key, authorize with `auth-db-rls`) and two corrections: its schema snippet used `partitionBy`, which is not a field — the property is `partitionKey`, an array of `{ "column": … }` — and it omitted `authMode: "auth-db-pls"`, without which `permissionDimension` validates and then does nothing.
- **Layout and authorization mode are independent choices — and RLS is not the slower one.** The decision tables previously implied the auth mode followed from row count ("big tenants → `auth-db-pls`, small tenants → `auth-db-rls`"). It does not. Volume decides whether a table gets a `partitionKey`; the policy you need decides the mode. Both modes deposit an ordinary predicate into the same `Where` before translation — PLS into `Where.And`/`Where.Or`, RLS into `Where.Groups` — so on a partitioned table an `auth-db-rls` rule constraining the partition key with `Eq`/`In` satisfies the partition-filter guard **and** drives the same exact partition/bucket pruning PLS does. New section [Layout and authorization mode are independent choices](auth/authorization.md#layout-and-authorization-mode-are-independent-choices) with the real differences: PLS requires a partition key and can only constrain that column; RLS constrains anything but pre-reads matching rows on `UPDATE`/`DELETE` to evaluate its write check. Pinned in the engine repository by `RlsPartitionGuardAndPruningTests`, which asserts the pruning counters rather than only the row set.
- **Clustering is not partitioning.** [Time-series and clustering](guides/time-series.md) now opens by saying that `clusterColumns` prunes segments on partitioned and unpartitioned tables alike and carries no `RequirePartitionFilter` obligation — for a table below the partitioning line it is the whole layout decision.
- **Corrections.** [Bulk load](guides/bulk-load.md#choosing-partition-storage-mode) said `Auto` starts every key in one of **16** shared buckets; since P45 that is `16` only when every partition-key column carries a bounded time-truncation `partitionFunction`, and **128** otherwise. It also conflated the promotion thresholds (10 M rows / 1 GB) with the partition-or-not line; the two are now distinguished. [Time-series §2.5](guides/time-series.md) said schema apply sets no partition options — since P45 it sets `partitionStorage`, `initialBucketCount`, both promotion thresholds and `pkUniqueness` (late-arrival policy and migration options remain undeclarable).
- **Live subscriptions on a partitioned table are now documented.** The partition-filter rule applies to `subscribe` exactly as it does to reads — a `subscribe` runs its snapshot through the same enforcement — but the guide only ever described queries, so the commonest shape of all (a per-user live feed on a table partitioned by user id) had no coverage anywhere. The failure is late and misleading: the schema applies, the named query deploys, the catalog export lists it, and nothing complains until the first browser subscribes and gets `PARTITION_FILTER_REQUIRED` while a service key works fine. The new section covers the ways to supply the caller's partition value, which to pick, and why `.WithCrossPartitionAccess()` is not one of them on this path. [Partitioning — live subscriptions](guides/partitioning.md#live-subscriptions-on-a-partitioned-table).
- **Insert `autoIncrement`: `0` means generate; omit does not (BL-429).** Ordinary `POST …/tables/{t}/rows` and named-mutation insert require the autoIncrement column to be **present**; send `0` to auto-generate. Omitting it is `400 INVALID_REQUEST` (`Missing required column '…'`), not the previously documented “`0` / omitted” equivalence. [HTTP API insert](reference/http-api.md#post-apidatabasesdbtablesnamerows), [Named queries — batch insert](guides/named-queries.md#batch-insert-batchparam). Engine work to treat omit as `0` is BL-429 (not yet shipped).
- **Partition-grant `dimension` is case-sensitive (BL-430).** `POST …/partition-grants` `dimension` must match the table `permissionDimension` byte-for-byte (`"source"` ≠ `"Source"`). A casing mismatch still returns `201` and then every insert/query 403s. [Data Authorization §19.8](auth/authorization.md#198-admin-api-partition-grants). Engine work to case-fold or reject the mismatch is BL-430 (not yet shipped).

## 0.1.24 — 2026-09-11

**Opt-in case-insensitive strings, long-poll hardening, and a run of concurrency/auth correctness fixes.** Server **0.1.24**, `Aouda.Client` **0.1.24**, `@aouda/client` **0.1.22** (pin after npm — published line still **0.1.21**), Studio **0.0.25**. See [Compatibility](clients/compatibility.md).

- **Opt-in case-insensitive string comparison (BL-461).** `eq`, `ne`, `in`, `nin`, and `like` accept `"ignoreCase": true` on String columns; default `false`, so existing queries, payloads, and named-query hashes are unaffected. Primary-key/unique-column uniqueness stays always case-sensitive, and a case-insensitive predicate never satisfies the partition-filter rule or zone-map/bloom-filter pruning — same treatment `like` already gets. [HTTP API — query](reference/http-api.md#post-apidatabasesdbquery), "Case-insensitive comparison" under Where Clause.
- **Troubleshooting: a data-plane `404 NOT_FOUND` on an artifact that exists.** On the data-plane listener a permission denial is deliberately masked as "not found" so callers cannot enumerate named artifacts. The server now logs the real denial reason, code and subject for every masked 404 — read the server log rather than re-deploying the artifact, which cannot change the outcome. [Partitioning §2.14](guides/partitioning.md#214-troubleshooting-by-symptom).
- **Long-poll sessions on the data-plane listener now carry the caller's real trust level.** A data-plane long-poll session previously defaulted to Admin trust internally, so guards that should apply to it (subscribe-must-name-an-artifact, write-stream denial, table opt-in, identity quota) silently did not run. Also fixed: one caller could hold an unbounded number of concurrent long-polls on a single session; and a session's bearer-token expiry is now enforced on every send/poll, not only at connect (a long-poll session no longer outlives the JWT that created it).
- **Named-artifact execute (named mutations/queries) is now authorized against the tables it actually touches, not the whole database.** Previously only a database-wide grant satisfied it, so running a named mutation that writes one table required write access to every table in the database. A database-wide grant still works exactly as before.
- **Catalog reads (list/get databases) no longer 429 behind data-plane traffic.** These are in-memory lookups, not query work, and now run on their own control-plane lane alongside health probes — this specifically fixes a 429 that could follow immediately after a routine database migration step. A `429`/shed response now also names the lane and budget it exceeded in the server log.
- **A malformed primary-key literal on insert now returns a clean `400`** instead of an empty-body `500` (BL-468). **An RLS zero-grant deny rule on a non-string column now denies correctly** instead of `400`ing the whole query, including any sibling rule it was OR-combined with (BL-469).
- A run of internal concurrency/correctness fixes with no API surface change: a read racing a background segment merge could very rarely return fewer rows than exist (BL-441); the segment discovery cache could get stuck serving a stale pre-write view (BL-448); `ORDER BY` + `LIMIT` on a nullable sort column could 500 (BL-460); and a scan now holds the segment files it is reading against concurrent removal (BL-396).

## 0.1.23 — 2026-09-10

**WebSocket subscribe reliability and long-poll reachability.** Server **0.1.23**, `Aouda.Client` **0.1.23**, `@aouda/client` **0.1.21**, Studio **0.0.25**. See [Compatibility](clients/compatibility.md).

- **A WebSocket `subscribe` is no longer dropped by the server's own snapshot high-water mark.** A healthy client sending a first snapshot of a few thousand ordinary rows could trip `SLOW_CONSUMER` and get disconnected with no backlog at all; the high-water mark is now a real backpressure check rather than a message-size cap.
- **Long-poll streaming is reachable on the data-plane listener.** The documented client fallback previously 404'd there with no body.
- **`/ws` and long-poll no longer hold a general-concurrency permit for the life of the connection.** A batch of streaming clients could no longer starve ordinary request handling; streaming is now exempt from that lane.
- **Two stream-auth paths that could grant a full RLS/partition bypass now fail closed** instead of silently escalating a normal credential to service-key-level access over WebSocket/long-poll.

## 0.1.22 — 2026-09-10

**MQ correctness, P46 bulk-load materialization, bounded lifecycle.** Server **0.1.22**, `Aouda.Client` **0.1.22**, `@aouda/client` **0.1.21**, Studio **0.0.25**. See [Compatibility](clients/compatibility.md).

- **Bulk load materializes affected queries during the load (P46).** With `postLoadMqBehavior: "auto"` (the default), materialized queries of all four types accumulate in the load's own pass and are published at commit — a manual `:refresh` afterwards queues behind that work and re-scans the table. Wait on `mqRebuildStatus` / `MqRebuildCompleted` / `waitForMaterializedQueries()` instead. Reservation floor/ceiling: `Aouda:BulkLoad:MqIngestReservationFloorBytes` (default 1 MB) and `MqIngestReservationCeilingBytes` (default `0` = Transient governor is the bound). [Materialized queries](guides/materialized.md), [Bulk load](guides/bulk-load.md), [Defaults reference](guides/defaults-reference.md), [HTTP API — Bulk Load](reference/http-api.md#bulk-load-api).
- **MQ refresh await and client wait APIs (BL-419).** `:refresh?await=true` uses its own timeout policy; default `Aouda:MaterializedQueries:RefreshAwaitTimeout` is **120 s**. C# `RefreshAsync` / `RefreshAndWaitAsync` / `WaitForMaterializedQueriesAsync`; TS `refreshAndWait` / `waitForMaterializedQueries` (in the **0.1.21** npm cut). Bulk-load commit/status carry `mqRebuildStatus`.
- **`Aouda:MaxConnections` defaults to `0` (unlimited) (BL-419).** Stock deployments shed via the request limiter (`429`) instead of Kestrel silently closing excess connections. Pin a positive ceiling explicitly if you still want a hard cap.
- **MQ queue-drop staleness (BL-427).** Status gains optional `isStale` / `staleReason` (omitted when healthy). The `materializedQueries` health component reports **Degraded** after dropped updates (process-lifetime until restart). Mirrored on `Aouda.Client`; `@aouda/client` type parity is **BL-428**.
- **Derived-column predicate cold/hot scan gap (BL-432).** A `like` / `isNull` (or any predicate) over a column one segment does not carry no longer returns zero rows with an unfiltered `totalMatches`; hot fused aggregates no longer count a full segment when the predicate matched nothing.
- **Hot coalesce row tear (BL-424).** Queries racing background hot-segment coalesce no longer silently return a torn subset of durable rows.
- **Bounded startup/shutdown (BL-423).** `Aouda:ShutdownTimeout` defaults to **120 s**. Compose `stop_grace_period` / Kubernetes `terminationGracePeriodSeconds` must be that plus a margin (reference compose files use **130 s**); a shorter grace SIGKILLs before shutdown finishes. Slow opens stay unbounded (`Aouda:DatabaseOpenTimeout` remains disabled); a Warning fires at 30 s (`Aouda:DatabaseOpenSlowWarning`) — do not restart to unstick a slow open; three killed opens quarantine as `OpenKilled`, recovered with `aouda databases unquarantine --name <db>`. WAL redo horizon and shutdown checkpoint fixes. [Server configuration §8](guides/server-configuration.md#8-startup-shutdown-and-slow-opens), [Deployment](deployment/index.md).
- **WebSocket auth handshake harden.** A transport that dies while sending `auth_ok` / `auth_error` no longer leaves the browser with a bare close that forced long-poll fallback.

## 0.1.21 — 2026-09-08

**Named-mutation batch insert + bulk-load resilience.** Server **0.1.21**, `Aouda.Client` **0.1.21**, `@aouda/client` **0.1.20**, Studio **0.0.24**. See [Compatibility](clients/compatibility.md).

- **Named-mutation batch insert via `batchParam` (BL-416).** An `op: "insert"` named mutation can declare `batchParam`, the name of a parameter carrying an array of row objects, so one `execute` call inserts many rows through the data-plane listener — bounded by a required `maxItems` cap, bound all-or-nothing, with a bind failure naming the offending array index in `rowErrors`. See [HTTP API — Named mutations](reference/http-api.md#named-mutations) and [Named queries and mutations — Batch insert](guides/named-queries.md#batch-insert-batchparam).
- **Bulk load: transform intent, deadlines and the admission lane (BL-404/405/406).** A table with any write-time compute requires exactly one of `applyTransforms` or `preTransformed`. Streaming `:append`/`:commit` use a dedicated admission lane (`Aouda:BulkLoad:MaxConcurrentStreamingRequests` / `StreamingRequestQueueLimit`); `:append` is not idempotent and must not be retried. [HTTP API — Bulk Load](reference/http-api.md#bulk-load-api), [Bulk load](guides/bulk-load.md).

## 0.1.20 — 2026-09-07

**P45 spill/merge + OutOfTheBox ingest + column DDL.** Server **0.1.20**, `Aouda.Client` **0.1.20**, `@aouda/client` **0.1.19**, Studio **0.0.24** (pin after npm). See [Compatibility](clients/compatibility.md).

- **A destructive schema apply no longer leaves the table unwritable (BL-382).** After an apply with `allowDestructive: true` dropped a column from a table the server had already written to, every later insert into that table returned **HTTP 500** (`Pending column {name} (id=N) has 0 rows …`) until the server process was restarted. Queries were unaffected, and restarting the client application did not help. Fixed, together with the same class of failure when a schema apply runs concurrently with in-flight writes (`Collection was modified`, `Cannot add column while a transaction is active`, `Unknown column N`).
- **`GET …/tables/{table}/schema` reports each column's catalog `id`.** Engine diagnostics identify columns by id, and a column dropped and re-added under the same name gets a new one. See [HTTP API](reference/http-api.md).
- **Schema guide: a declarative apply drops by omission.** [Schema management](guides/schema.md) now spells out that any column in the catalog but not in your `aouda.schema.json` is planned as a `DropColumn` — including when an older copy of the file is applied — and how to avoid it.

- **Elastic memory shares and single-node bulk-load defaults.** A database at its fair share can borrow idle sibling headroom; fallback host-RAM detection uses a safer default fraction; single-node `LogShipSegments` can skip per-segment WAL frames. See [HTTP API](reference/http-api.md).

## 0.1.19 — 2026-09-04

**Memory governor, Timestamp MQ, table row counts, phone MFA.** Server **0.1.19**, `Aouda.Client` **0.1.19**, `@aouda/client` **0.1.18** (unchanged), Studio **0.0.23**. See [Compatibility](clients/compatibility.md).

- **Per-database memory accounting (BL-366).** PK-cache reservations no longer leak into the governed ceiling; `MEMORY_BUDGET_EXCEEDED` names the database and reservation categories; `GET /api/server/memory` gains `reservedBytes` / `governedCeilingBytes` / `reservedByCategory`.
- **Timestamp Materialized Query build (BL-373).** MQ build/rebuild over `Timestamp` columns no longer throws; `Date`/`Timestamp` key encoding is canonicalised.
- **Bulk-load table row counts (BL-374).** `GET …/tables` `rowCount` is catalog-backed (not residency-dependent); responses gain `rowCountIsExact`.
- **Phone MFA enroll is idempotent (BL-363).** A second phone enroll for the same user returns 409 `AUTH_MFA_FACTOR_ALREADY_ENROLLED` instead of creating a duplicate `_mfa_factors` row. Existing factor id in `detail`. Replace a number with `DELETE .../mfa/factors/{id}` then re-enroll.

## 0.1.18 — 2026-09-02

**BL-362 auth identity integrity.** Server **0.1.18**, `Aouda.Client` **0.1.18**, `@aouda/client` **0.1.18** (unchanged), Studio **0.0.23**. See [Compatibility](clients/compatibility.md).

- **Unique email + id-keyed admin mutations.** `_users.email` is unique on new auth databases (backfilled when duplicate-free). Admin password/disable/enable/PATCH update by user id; DELETE revokes JWTs then cascades by id. Duplicate-email sign-in verifies every matching hash. [Auth reference](auth/reference.md), [HTTP API](reference/http-api.md).

## 0.1.17 — 2026-09-02

**Keyless browser app-auth + auth hardening.** Server **0.1.17**, `Aouda.Client` **0.1.17**, `@aouda/client` **0.1.18**, Studio **0.0.23** (pin `@aouda/client` **0.1.18**). See [Compatibility](clients/compatibility.md).

- **Keyless browser login (BL-355, breaking).** Public app-auth POSTs (signup, signin, refresh, password-reset) no longer require `mk_anon_*`. Construct `@aouda/client` / `Aouda.Client` with the data-plane URL and database name only. Self-registration is **opt-in** (`AllowSelfSignup`, default off — BL-357) and grants `db_writer` unless `selfSignupRole` is set. CORS `*` on the data-plane lets any origin call those routes. `mk_pub_*` is still required for pre-auth named queries (BL-356). [Auth](getting-started/auth.md), [HTTP API](reference/http-api.md), [Direct client access](guides/direct-client-access.md).
- **Self-service signup switch (BL-357, breaking).** Signup is off until an operator enables it (`PUT …/auth/admin/signup-settings` or create-database `allowSelfSignup`). Disabled signup is **403** `AUTH_SIGNUP_DISABLED`. [Auth](getting-started/auth.md), [HTTP API](reference/http-api.md).
- **Trusted-proxy client IP (BL-359).** Per-IP rate limits, lockout attribution, and `_audit_log` client IPs are the proxy's address until you set `Aouda:ForwardedHeaders`. Off by default; enabling with no trust list is a startup error. [Behind a reverse proxy](deployment/reverse-proxy.md).
- **Failed-signin ceiling (BL-360).** Optional `Aouda:Auth:FailedSigninCeiling` (off by default) caps failed sign-ins per auth database — the credential-stuffing shape that per-IP limits and lockout cannot see. Per process; successful logins do not count until the ceiling trips, after which every sign-in on that database is 429 until the window drains. [Auth reference](auth/reference.md#rate-limiting).
- **Data-plane CORS startup warnings (BL-358).** Bound data-plane with `CorsOrigins` `*` or unset logs a warning; policy unchanged.

## 0.1.16 — 2026-09-02

**BL-186 complete — point-in-time recovery is shipped.** Server **0.1.16**, `Aouda.Client` **0.1.16**, `@aouda/client` **0.1.17**, Studio **0.0.22** (pin `@aouda/client` **0.1.17**). See [Compatibility](clients/compatibility.md).

- **PITR over HTTP and both SDKs.** `POST /admin/backup/restore` accepts `targetTime`; list responses gain `pitrEligible`; restore responses gain `targetTime` / `pitr`. Exact restore unchanged. Studio backup UI stays exact-restore-only. [Backup and restore](guides/backup.md), [HTTP API](reference/http-api.md), [TypeScript client](clients/typescript.md).
- **BL-343.** Unfiltered `POST /query` no longer 500s when the catalog is wider than a segment (derived / never-written columns synthesize defaults).

## 0.1.15 — 2026-09-01

**BL-319 Derive pilot gap close + BL-312 + BL-186 progress (mid-stream).** Server **0.1.15**, `Aouda.Client` **0.1.15**, `@aouda/client` **0.1.16** (unchanged), Studio **0.0.21**. See [Compatibility](clients/compatibility.md).

- **Derive pilot fixes (BL-319).** C# fluent `In`/`Nin`; omitted named-query `offsetParam` binds skip **0**; data-plane named-query / named-mutation execute returns `404` (not existence-leaking 401/403); App Auth GET user/roles no longer 500 on empty roles; CLI `start -h` does not boot; MQ `:refresh?await=true` can return 200; creator `db_admin` on new data DBs. [Named queries](guides/named-queries.md), [HTTP API](reference/http-api.md), [Direct client access](guides/direct-client-access.md).
- **Sealed-segment backups (BL-312).** Backups now capture `segment.manifest`; restored cold/sealed data returns rows again.
- **Backup / restore / archive (BL-186 partial).** Exact restore re-bases WAL + catalog; backup WAL position is per-database; archive positions are byte offsets and `WalArchiveWorker` runs when archive is configured; restore divergence handshake (v4). **PITR over HTTP/SDK is still not shipped** — no restore target-time API yet. [Backup and restore](guides/backup.md), [Storage](guides/storage.md).

## 0.1.14 — 2026-08-29

**P41 ingest remainder, P42 metadata at scale, P43 write-side authorization.** Server **0.1.14**, `@aouda/client` **0.1.16**, `Aouda.Client` **0.1.14**, Studio **0.0.21** (pin `@aouda/client` **0.1.16** after npm). See [Compatibility](clients/compatibility.md).

- **Catalog GET is metadata-only; linkage is no longer omitted.** `GET`/`list` `/api/databases` now document `auth.enabled` / `auth.database` (never `mk_*`). `authDatabaseKind: "none"` on a data DB does not mean unlinked. HTTP API v2.6. [HTTP API](reference/http-api.md#get-apidatabasesname).
- **Create role contract.** `POST …/auth/admin/roles` requires `name`; `permissions` is optional (empty grants nothing). `actions` is a string, not an array. 400 bodies include `error` / `suggestion`. [Auth reference](auth/reference.md), [Use cases](auth/use-cases.md).
- **Health vs ready.** Wait on `GET /ready` and `GET /api/databases/{name}` `state=Active` before schema apply; `/health` is liveness only. [`/ready` is unchanged](reference/http-api.md#get-health) for a `Dropping` sibling database.
- **P43 write-side authorization (docs).** Public pages now name the code's RLS value sources (`UserId`, `Literal`, `PartitionGrant`), admin-API resolver authoring, identity stamp (`"derived": { "identity": "subject" }`), `plsClaimBinding`, `writeCheckRules`, and per-user claims. Conformance fixture: [`examples/p43-write-side/`](examples/p43-write-side/).
- **P42 catalog directory (operators).** Live catalog is `catalog.root.json` plus per-table shards. Opening a pre-P42 database migrates forward; there is no downgrade. Lazy catalog residency is the shipped default. [Storage](guides/storage.md).

## 0.1.10 — 2026-08-23

**BL-188 complete — named-query name identity.** Server **0.1.10**, `@aouda/client` **0.1.15**, `Aouda.Client` **0.1.10**, Studio **0.0.20** (pin `@aouda/client` **0.1.15**). See [Compatibility](clients/compatibility.md).

- **Breaking — named-query name identity (BL-188).** The unique schema name is the only identity across HTTP, WebSocket, both SDKs, Studio, and these docs. Execute/batch/subscribe send the name; omitting a name deletes the definition; codegen is types-only (optional Args/Row). Alias surface and `NAMED_QUERY_ALIAS_MISMATCH` are retired. [Named queries](guides/named-queries.md), [HTTP API v2.5](reference/http-api.md).
- **`firstPerKey` / `topNPerGroup` materialized queries (BL-187).** Schema apply and HTTP create. `firstPerKey` is MIN of `orderBy`, not arrival order. `topNPerGroup` maintains at most N rows per group; working set is in-memory (use a compact per-key source). A Top-N whose `sourceTable` is another materialized query (for example `latestPerKey`) follows that source incrementally. Query the result table by name. [Schema management](guides/schema-management.md#materialized-queries-in-the-schema-file), [Materialized queries](guides/materialized.md).
- **P38 — Freshness and replica consistency.** New [Freshness](guides/freshness.md) guide: one 42-hex consistency token (`AtLeast`, not `AsOf`), `GET /api/databases/{db}/token`, named-query alias `freshness`, SDK store (`consistencyTokenStore` / `IConsistencyTokenStore`). HTTP API v2.4: `X-Aouda-Token` / `?at_least=` (query wins), `TOKEN_*` / `FRESHNESS_*` errors, stream `token` alongside `version`, bulk-load commit field `walPosition` → `token`. **Breaking:** `MaxLagSeconds` is measured staleness, not lag-bytes ÷ 1 MB/s. Caveats are first-class: scale-out in-memory store (gate 13), clock skew, `w:1` → `TOKEN_EPOCH_SUPERSEDED`, MQ watermark, token volume leak, blocking `waitMs` (default 250), Hub CP-B4 not shipped. Default read preference remains `Primary`.
- **Local CLI testing for agents.** New [Local CLI testing (agents)](ai/local-cli-testing.md): throwaway `aouda start` recipe (unused ports, temp `--data-dir`, pin CLI, stop with `-s`), plus engine/CLI traps — `aouda start -h` boots on `:5000` into `./data`; data-plane executes named-query **names** (not `POST /query`); `CorsOrigins` is one string; schema `partitionKey` / `where.and` / `offset` cap; columnar bodies; keys returned once. [Direct client access](guides/direct-client-access.md) CORS example corrected from a JSON array to a string. Linked from [llms.txt](llms.txt), [AI quick start](ai/quick-start.md), and [AI Agents](ai/index.md).

## 0.1.8 — 2026-08-19

**Three adoption gaps closed.** Server **0.1.8**, `@aouda/client` **0.1.12**, `Aouda.Client` **0.1.8**, Studio **0.0.17** (pin unchanged). See [Compatibility](clients/compatibility.md).

- **Typed subscribe-by-hash (BL-173).** `client.namedQueries.subscribe(hash, args, { conflate })` and `NamedQueries.SubscribeAsync(hash, args, options)` — the data-plane's only streaming path no longer requires hand-rolled WebSocket frames. Returns the same subscription object as table subscribe, so `gap` resume, reconnect, `re_auth`, and `SLOW_CONSUMER` recovery are unchanged. [Named queries](guides/named-queries.md#subscribe-by-name).
- **Materialized queries in `aouda.schema.json` (BL-174).** Top-level `materializedQueries` map (`latestPerKey`, `aggregate`, `filter`) managed by `schema diff` / `apply` / `export`. **A present map is desired state and drops anything not listed; omitting it leaves MQs unmanaged.** [Schema management](guides/schema-management.md#materialized-queries-in-the-schema-file).
- **String and rounding functions (BL-175).** `ScalarExprNode` gains `type: "call"` with a closed allowlist — `upper`, `lower`, `trim`, `concat`, `substring`, `round`, `roundTo`, `cast` — plus `$upper` … `$cast` operators in the TypeScript `.update()` builder. Normalization can now move out of an ingest service. [Insert-time transforms](guides/insert-transforms.md#call--string-and-rounding-functions), [Bulk mutations](guides/bulk-mutations.md#string-and-rounding-operators).

**New:** [Adopting Aouda in an existing application](guides/adoption.md) — the P37 target architecture for an app that already has a frontend, a gateway, and services: which hops stop earning their keep, an honest SDK coverage table, what direct access does to subscription and quota capacity, and the order to migrate in.

**Corrected:** [Auth architecture](auth/architecture.md) Pattern B described the pre-P37 model — a browser holding `mk_anon_*` and running ad-hoc `table().execute()`. Both are now refused. It documents `mk_pub_*`, the data-plane listener, and named queries.

**Added:** `policy inspect` in [Access-surface diff](guides/access-surface.md) ("what would this user see?"), with a corrected `aouda.identities.json` example — `identities` is an object keyed by name, and grants require `dimension` + `partitionKey` + `accessLevel`. [Insert-time transforms](guides/insert-transforms.md) gains failure semantics: a failed check or unmatched `route` fails **the whole batch**, `route` must be exhaustive, and quarantine is a table plus a catch-all route rather than a built-in dead-letter path. [Client integration](auth/client-integration.md) key tables now list `mk_pub_`.

## 0.1.7 — 2026-08-19

Public docs for **P37 Direct Client Access**: named queries (execute, batch, subscribe-by-hash, codegen), data-plane listener and `mk_pub_*`, insert-time transforms, access-surface diff (`aouda schema diff --access`), and the division-of-responsibility guide. HTTP API v2.3 documents `snapshot_complete`, `gap`, `re_auth`, `values_skipped`, and the credential/listener matrix. OAuth authorization-code + PKCE is **not** documented as available.

Guides: [Named queries](guides/named-queries.md), [Direct client access](guides/direct-client-access.md), [Division of responsibility](guides/division-of-responsibility.md), [Insert-time transforms](guides/insert-transforms.md), [Access-surface diff](guides/access-surface.md), [HTTP API](reference/http-api.md). Server **0.1.7**, `@aouda/client` **0.1.11**, Studio **0.0.17**. See [Compatibility](clients/compatibility.md).

---

## 0.1.6 — 2026-08-13

Server **0.1.6** treats `MaxTotalRamBytes` as a process RSS ceiling (default ~70% of detected RAM), keeps the write-ahead log bounded, and refuses over-budget ingest with HTTP 503 + `Retry-After`. Studio **0.0.16** shows RSS vs governed budget, reclaimable WAL, and quarantined databases. See [Sizing](guides/sizing.md), [Write durability](guides/write-durability.md), and [Compatibility](clients/compatibility.md).

---

## ✅ P0 — Core Bootstrap (Completed)

**Date:** 2025-Q1
**Scope:** Engine foundations, encoding, and columnar persistence.

### Highlights
- Introduced **typed identifiers**: `TableId`, `ColumnId`, `SegmentId`, `RowId`, `CommitId`.
- Implemented **encoder framework** (`IEncoder`, `IStringEncoder`) with versioning.
- Added numeric encoders:
  - `Int32DeltaBitpackEncoder`
  - `Int64DeltaBitpackEncoder`
  - `GorillaDoubleEncoder`
- Added `StringDictEncoder` with dictionary compression and varint encoding.
- Created **Page system** (`PageMeta`, `PageStats`, `PageAddress`) with CRC validation.
- Built **FilePageStore** with append-only persistence and page indexing.
- Implemented **QueryEngine v0** (projection, filter, aggregation primitives).
- Established **TableDef**, **ColumnDef**, and schema catalog foundations.

### Result
Aouda became capable of ingesting, encoding, and reading columnar pages fully in-memory and on-disk.

📄 *See also:* [P0-COMPLETION.md](./P0-COMPLETION.md)

---

## ✅ P1 — Durability & Recovery (Completed)

**Date:** 2025-Q3
**Scope:** Write-ahead logging, hybrid row buffering, compaction, and crash recovery.

### Highlights
- Added **Write-Ahead Log (WAL)** with frame-based append and CRC validation.
- Implemented **WalSegmentWriter** and **WalReplayer** for safe crash recovery.
- Introduced **Hybrid Row Area (HRA)** for in-memory, row-oriented buffering.
- Integrated **HRA snapshotting** into QueryEngine to unify query visibility across memory and disk.
- Added **CompactionWorker** and **RetentionManager** for background flushing and pruning.
- Introduced **Checkpoint system** ensuring consistency between WAL and column pages.
- All major recovery and durability tests now pass, including torn WAL detection.

### Result
Aouda now provides full **durable write semantics** — all data survives process restarts, and WAL replay guarantees correctness.

📄 *See also:* [P1-COMPLETION.md](./P1-COMPLETION.md)


---

## Historical notes

Versioned releases above are the public record. Engine phases P0–P37 are complete;
see the engine [ROADMAP](https://github.com/aoudadb/aouda/blob/main/docs/ROADMAP.md)
and [CHANGELOG](https://github.com/aoudadb/aouda/blob/main/docs/CHANGELOG.md).
The 2025 P0–P4 “in progress / planned” narrative that used to live here is not current.

