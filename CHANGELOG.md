---
title: "Changelog"
nav_order: 9
---

# Aouda Changelog

Public, user-facing release notes. Engine phase status lives in the server
[CHANGELOG](https://github.com/aoudadb/aouda/blob/main/docs/CHANGELOG.md) and
[ROADMAP](https://github.com/aoudadb/aouda/blob/main/docs/ROADMAP.md) (P0–P53 complete).

---

## Unreleased

## 0.1.36 — 2026-09-21

**A materialized-query build spills to one file.** Server **0.1.36**, `Aouda.Client` **0.1.36**, `@aouda/client` **0.1.23** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A materialized-query build no longer spends one file per partition eviction (BL-620).** A 15.3 M-row load left **173 434 files / 2 578 MB** under `materialized/` — 86 % of the database by size. A spill is now a byte range in one `<buildId>.mqspill` file, and pressure writes the whole working set in a single pass. How much is spilled is unchanged (BL-623). New counters: `MQ Spill Generations` and `MQ Spill Files Created`. A cancelled snapshot read reports cancellation rather than corruption.

## 0.1.35 — 2026-09-21

**NULL stays NULL on filtered and ordered reads; auth databases stay resident.** Server **0.1.35**, `Aouda.Client` **0.1.35**, `@aouda/client` **0.1.23** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A filtered read of a cold segment no longer turns a nullable `NULL` into the type's default (BL-613).** A `WHERE` against a demoted segment returned `Guid.Empty`, `0`, `false` or `0001-01-01` for every fixed-width type. The same rows without a filter were correct, and `String` was never affected. Nothing was lost on disk — re-read after upgrading returns `NULL`. This is what made Derive's lab return 401 on every service key after a reclaim: `_api_keys.user_id` is legitimately `NULL`, and a hash lookup read it as `Guid.Empty`.

- **`ORDER BY … LIMIT` no longer does the same thing (BL-615).** The ordered-with-limit fast path discarded validity even on a freshly flushed hot segment. Null sort order is unchanged (a null sort key still sorts as the CLR default).

- **Auth databases keep credential tables in memory (BL-614).** Nineteen of the twenty auth system tables had no residency policy, so an ordinary reclaim could demote `_users`, `_api_keys` and the rest. New auth databases pin them. `_audit_log` stays demotable. `Aouda:Memory:EnableEmergencyDemotion=true` no longer overrides those pins; a per-table `hotOnlyBackstop: DemoteAnyway` still does. **Databases created before this change are not migrated** — recreate them, or pin each table with `storageTemperature: HotOnly`. See [Sizing](guides/sizing.md).

## 0.1.34 — 2026-09-21

**Unused MQ build tables, log-level defaults that ship, no host-specific memory pin.** Server **0.1.34**, `Aouda.Client` **0.1.34**, `@aouda/client` **0.1.23** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A bulk load into a non-empty materialized-query result no longer creates a build table it will never write to (BL-609).** Maintenance applies through the ordinary write path. Measured: 2 064 create-and-drop pairs on one 15.3 M-row load became six.

- **Shipped binaries now run at `Warning` by default (BL-610).** `appsettings.json` never reached a Release publish, so every deployment sat at .NET's `Information` default — thousands of framework lines per second. An operator `Logging:LogLevel` still wins. `Aouda.Server.Startup` stays at `Information` (O(1) lifecycle / budget derivation).

- **No shipped configuration file pins an absolute memory budget (BL-612).** `MaxTotalRamBytes` is left unset so the host derives 70 % of a cgroup grant, or 40 % of total clamped by available memory.

## 0.1.33 — 2026-09-20

**P53 ingest admission, MQ-Amplification, crash reattach, and a large correctness train.** Server **0.1.33**, `Aouda.Client` **0.1.33**, `@aouda/client` **0.1.23** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A crash no longer rebuilds every materialized query (BL-311, BL-519, BL-495).** Restart reattaches to the result the log restored. A crash in the middle of ingest still rebuilds, deliberately. Databases written by earlier versions rebuild once, then attach on subsequent restarts.

- **Per-class memory admission is now enforced by default (BL-523).** A background rebuild can no longer consume an interactive query's share. Work that succeeds today can now be refused — a refusal names the class, what it holds, and its entitlement. `Aouda:Memory:PerClassAdmissionEnabled=false` restores process-ceiling-only admission. `Aouda:Memory:ClassBoundEnforced` is removed.

- **A `filter` materialized query over a source with no primary key now preserves duplicate rows (BL-515).** Two byte-identical source rows are two result rows. An update that moved a row out of the filter no longer leaves a phantom result row. Existing `_rowid` result tables migrate once at the next open.

- **A materialized query's result table is no longer pinned in RAM because of its query type (BL-586).** `aggregate`, `latestPerKey` and `firstPerKey` results were created `StorageTemperature = HotOnly` on the reasoning — written in the engine source — that they are *"small, frequent access"* and *"usually small"*. They are not bounded that way: an `aggregate` result holds one row per group and a `latestPerKey` one row per key, so both grow with the source's cardinality. A measured eight-query fan-out held **2 199 815 groups**, and per-minute candles over a few thousand instruments is an ordinary shape. **The default is now `Auto`**, the same default an ordinary table has.
  - ⚠️ **This was harmless until a pin became a charged reservation.** Since P53, a pinned table's bytes are subtracted from the ceiling the rest of the hot tier is admitted against, the table is skipped for demotion, and its cold segments are re-promoted. So an *undeclared* residency shrank the very tier ingest is paced against, on the tables producing the most hot bytes — and the drain-harder rung had nothing there it was allowed to reclaim.
  - **Residency is policy, not a property of the query type.** `storage.storageTemperature` on the query's schema entry (`Auto` | `HotOnly` | `ColdPreferred`) is how you choose — `ColdPreferred` for a result keyed by a time bucket, `HotOnly` plus a stated reservation for one keyed by identity, `Auto` plus `residency.memoryRowCap` for recent-hot-historical-cold.
  - 🔎 **The symptom an undeclared pin produced was a `503` on an unrelated write** — the candle result shrank the tier the tick ingest was admitted into. `pinnedHotBytes` on `GET /api/server/memory` is what your declared pins now cost. New guidance on which temperature to pick per query shape: [Materialized queries §2.3.1](guides/materialized.md#where-a-materialized-querys-result-lives), [Market data](guides/market-data.md#mq-residency), [Sizing](guides/sizing.md#mq-result-residency), [Hot/Cold](guides/hot-cold.md#mq-result-tables).

- **A time-bucketed `aggregate` result is now stored in time order, so a row cap bounds what you expect it to (BL-595, closing BL-596).** The result-table schema builder set a primary-key order on the group-by columns and a cluster order on **nothing**, so result rows sat in arrival order while the source table they aggregate was clustered by its timestamp. A derived time bucket (`TruncateToMinute` and friends) is now the result table's cluster column.
  - 🔎 **Why it matters is residency, not read speed.** The hot/cold sweep demotes the least-recently-accessed segment first, which on time-ordered data is a good proxy for *keep recent buckets resident, send historical ones to cold*. Without the ordering the proxy broke: **one still-updating current-bucket row kept its whole segment hot**, year-old buckets included.
  - ✅ **"Keep the last 24 hours hot" is answered by `residency.memoryRowCap`, not by a duration.** A duration cannot be honoured without knowing the arrival rate — at 1.25 MB/s, 24 h is 108 GB, which would have to be refused at declaration time. A count needs no such input and self-scales across a 1 ms feed and a 1-minute candle. Measured: 400 minute-buckets under a 50-row cap stay **queryable, complete and gap-free** while the resident footprint stays bounded.
  - **Only the leading time bucket clusters.** A plain group-by carries no temporal order, so clustering on it costs a sort on every seal and buys nothing. `filter`, `latestPerKey`, `firstPerKey` and `topNPerGroup` are untouched. [Time-series](guides/time-series.md#mq-result-clustering).

- **Every materialized query now reports what it costs, per query (`amplification`).** The engine could say precisely what a *bulk load* cost its materialized queries and nothing at all about what a stream of ordinary inserts cost them — which is the shape most deployments run in. `GET …/materialized-queries/{name}` (and the list route) now carries an `amplification` object: source rows ingested, keys planned, prior rows read, applies, result rows upserted and deleted, rebuild rows scanned and written, and the two ratios — **result rows written per source row ingested** and **source columns decoded per column the query declared it needs**.
  - **Per query, not per process.** An eight-query fan-out reports eight of these; a process total cannot be divided back out.
  - **The read-side ratio is new information.** A materialized query's source scan decodes every column of every row even for a query that declared three — on a twelve-column table feeding a three-column aggregate that is **4×**. Nothing counted it before, so it was an argument from source code rather than a number.
  - ⚠️ **Since process start, never persisted, and omitted entirely for a query that has done nothing** — treat an absent object as "no data yet", not as zero. Nothing about how a query is maintained changed. [Materialized queries §2.11d](guides/materialized.md#amplification), [HTTP API](reference/http-api.md).

- **P53's memory settings are reachable from configuration, and the server prints the ladder it is actually running (BL-594).** Nine settings each named a `Aouda:Memory:<Name>` key in their own documentation and **none of them bound** — a deployment ran the whole ingest-admission ladder at its compiled-in defaults permanently. Rung 1, the rate controller the phase is named for, was not merely off by default but *unsettable*. All nine now bind and reach the engine, and **no default changed**.
  - **One startup line reports the effective ladder**, not the configured one: `Memory ladder: admission=on, rung0=on (T42=60 %), rung1=off (T43=80 %, T44=00:01:00, T45=00:00:30), processHotCeiling=on, flushAlwaysHotFirst=off`. ⚠️ Every non-boolean **self-clamps** — `T43` against `T42`, both durations against their own floors — so a value you set can be silently replaced; printing the effective number is what stops that being invisible.
  - ⚠️ **Rung 1 (ingest pacing) still ships off, and that is now a decision rather than an absence (BL-591).** The safety case is made: it cannot engage below its water mark **by construction**, and a healthy server ingesting 300 000 rows in 1.4 s with the flag on took **0 delays and 0 refusals**. The sizing case is not: two of its three constants are Apache Kudu's rather than Aouda's, and nothing in the engine's suites derives them from a sustained production ingest. What changed is the cost of saying no — "keep it closed" used to mean "unavailable" and now means **opt-in**. Every key, with defaults: [Defaults Reference](guides/defaults-reference.md#hot-tier-and-ingest-admission).

- **A sustained heap-degradation signal, between "within budget" and "terminate" (BL-575).** Termination arms on six *consecutive* samples above 98 % of the heap limit; an observed incident oscillated 91.5 → 98.8 → 91.6 % as the collector worked, so the counter reset every time and the process sat alive-but-wedged for hours — refusing writes, collecting continuously, neither recovering nor dying. `GET /api/server/memory` now carries **`heapSustainedDegradation`**, **`heapDegradedSinceUtc`** and **`heapDegradedForSeconds`**, and the `memory` health component carries two of them in its details.
  - ⚠️ **A window majority rather than a consecutive run, deliberately** — oscillation is a *symptom* of the condition, not evidence against it, and a consecutive rule gets harder to trip the harder the GC is fighting.
  - ⚠️ **This reports and never acts.** Termination's own rule is untouched. 🔎 It is a field rather than only a log line because every other memory figure on that response is instantaneous, and an instantaneous reading cannot tell a spike from an hour. [Sizing](guides/sizing.md), [HTTP API](reference/http-api.md).

- **Documentation corrections.** [Sizing](guides/sizing.md) had four sections duplicated by a bad merge and now has one of each. [Materialized queries §2.3](guides/materialized.md) stated the old per-query-type residency defaults as current fact. The [market-data bulk-load example](guides/market-data.md#bulk-loading-historical-data) used `postLoadMqBehavior: auto` **and** called `:refresh`, which every other page correctly says not to do — with `auto` the refresh queues behind the load's own publication and then re-scans the whole source table. `PUT …/tables/{name}/policy` in the [HTTP API](reference/http-api.md) documented only `storageTemperature`, omitting the four residency fields and the sentinel convention that distinguishes *leave unchanged* from *clear*.

- **Nothing enters the hot tier without asking, and a flush writes exactly one representation (P53).** Five paths created resident in-RAM bytes and not one of them consulted the hot ceiling, while every mechanism that reclaimed them consulted three things — so a ceiling that looked like a bound was really a reporting category. All five now ask first, and each has a defined answer when the answer is no.
  - **A flush writes hot or cold, never both.** Which one is decided when the rows are flushed: hot when the tier can afford them, cold when it cannot, and **cold unconditionally for a `ColdPreferred` table** — that policy previously materialised an in-RAM copy anyway and waited for a sweep to undo it. Measured on 400 000 rows against a 2 MB hot ceiling: resident hot went from **23.6 MB to 0 B**, at a cost of one extra cold segment.
  - ⚠️ **Three named behaviour changes.** A `ColdPreferred` table's just-flushed rows read from disk. A bulk load into an **edge or vector** table writes cold by default (`Aouda:BulkLoad:Temperature: HotAndCold` restores it). Rows flushed cold under pressure read from disk rather than RAM. `Aouda:Memory:FlushAlwaysHotFirst=true` restores the previous flush for every table.
  - **The hot tier is bounded across databases, not only within one.** A per-database ceiling carries a 32 MB floor, so on a small host those floors could sum past what the process would ever commit — 416 MB of ceilings against a 208 MB heap limit at 256 MB with thirteen databases. The new aggregate bound is inert wherever the per-database ceilings already sum correctly and binds only where a floor has broken them. `Aouda:Memory:ProcessHotCeilingEnabled=false` turns it off.
  - **A residency pin is now a reservation with a price.** A `HotOnly` table's pinned bytes come off the ceiling the rest of the tier is admitted against, and such a table is refused on **its own** exhausted reservation rather than because an unrelated database filled the process. Pins that together exceed the process hot ceiling are refused **when they are declared**, naming both numbers.
  - **Backpressure answers in cost order.** Drain harder (I/O only, no writer delayed) → pace the writer against a measured admissible rate → refuse with a typed retryable `503` → and only then touch a declared pin. Draining harder is **on** by default and inert below 60 % hot occupancy. ⚠️ **Writer pacing ships off** (`Aouda:Memory:HotPacingEnabled`) — it is the first response that can slow a healthy workload if a constant is wrong. Enabling it also lets sustained heap pressure pace and drain for a bounded window before it refuses, except within 10 % of the heap hard limit where it refuses straight away.
  - **`GET /api/server/memory` gains the rates that made this diagnosable.** Per database: `hotArrivalBytesPerSecond`, `hotDrainBytesPerSecond`, `hotDrainLatencyP50Ms`, `hotDrainLatencyP90Ms`, `hotDrainAttempted`, `hotDrainSucceeded`, `hotDrainStalled`, `totalHotBytesAdmitted`, `totalHotBytesDrained`, `processHotCeilingShareBytes`, `pinnedHotBytes`. Per process: `hotArrivalBytesPerSecond`, `hotDrainBytesPerSecond`, `hotDrainStalled`, `processHotCeilingBytes`, `processHotResidentBytes`. All additive; no existing field changes meaning. ⚠️ **`hotDrainStalled` is not "drain is zero"** — zero drain is normal at rest; stalled means the drain tried and failed, which has the opposite remedy. See [Sizing](guides/sizing.md).

- **"Should this table have a partition key?" is now its own section, and the answer is often no.** The P45 rule — *partition a key only when each key value holds at least one full segment's worth of rows* — was previously stated only inside "Choosing `initialBucketCount` at scale", where a reader asking whether to partition at all would never find it, and it never named the number. It now leads [Partitioning](guides/partitioning.md#should-this-table-have-a-partition-key-p45), states the figure (**~1 000 000 rows**), and carries a worked example for a table *below* the line — where the right answer is no `partitionKey` and `clusterColumns` on the time column. Linked from the schema decision table in [Build apps](guides/build-apps.md), from [Bulk load](guides/bulk-load.md#choosing-partition-storage-mode), and from [Time-series](guides/time-series.md).
- **Grants do not require a partitioned table.** An `auth-db-rls` rule with `valueSource: "PartitionGrant"` injects the caller's grants as an ordinary `IN` predicate on a named column — it never consults the partition router, so it behaves identically on an unpartitioned table. A grant's `partitionKey` is a key *within the grant document*, not a claim about the table's physical layout. That is what lets a "user belongs to many rooms" application keep grant-based authorization while dropping a partition key its volume does not justify. New worked example: [the unpartitioned variant](auth/authorization.md#the-unpartitioned-variant--same-grants-no-partition-key) of the chat use case, with the same grant calls unchanged.
- **The chat and per-user-feed examples now check volume first.** Use Case 1 — Chat Application partitions `messages` by `room_id`, which is right only when each room holds ~1 M rows; a typical chat product is orders of magnitude below that. Both it and [live subscriptions](guides/partitioning.md#live-subscriptions-on-a-partitioned-table) now say so and point at the unpartitioned design. The live-subscriptions section gains **Option C** (drop the partition key, authorize with `auth-db-rls`) and two corrections: its schema snippet used `partitionBy`, which is not a field — the property is `partitionKey`, an array of `{ "column": … }` — and it omitted `authMode: "auth-db-pls"`, without which `permissionDimension` validates and then does nothing.
- **Layout and authorization mode are independent choices — and RLS is not the slower one.** The decision tables previously implied the auth mode followed from row count ("big tenants → `auth-db-pls`, small tenants → `auth-db-rls`"). It does not. Volume decides whether a table gets a `partitionKey`; the policy you need decides the mode. Both modes deposit an ordinary predicate into the same `Where` before translation — PLS into `Where.And`/`Where.Or`, RLS into `Where.Groups` — so on a partitioned table an `auth-db-rls` rule constraining the partition key with `Eq`/`In` satisfies the partition-filter guard **and** drives the same exact partition/bucket pruning PLS does. New section [Layout and authorization mode are independent choices](auth/authorization.md#layout-and-authorization-mode-are-independent-choices) with the real differences: PLS requires a partition key and can only constrain that column; RLS constrains anything but pre-reads matching rows on `UPDATE`/`DELETE` to evaluate its write check. Pinned in the engine repository by `RlsPartitionGuardAndPruningTests`, which asserts the pruning counters rather than only the row set.
- **Clustering is not partitioning.** [Time-series and clustering](guides/time-series.md) now opens by saying that `clusterColumns` prunes segments on partitioned and unpartitioned tables alike and carries no `RequirePartitionFilter` obligation — for a table below the partitioning line it is the whole layout decision.
- **Corrections.** [Bulk load](guides/bulk-load.md#choosing-partition-storage-mode) said `Auto` starts every key in one of **16** shared buckets; since P45 that is `16` only when every partition-key column carries a bounded time-truncation `partitionFunction`, and **128** otherwise. It also conflated the promotion thresholds (10 M rows / 1 GB) with the partition-or-not line; the two are now distinguished. [Time-series §2.5](guides/time-series.md) said schema apply sets no partition options — since P45 it sets `partitionStorage`, `initialBucketCount`, both promotion thresholds and `pkUniqueness` (late-arrival policy and migration options remain undeclarable).
- **Live subscriptions on a partitioned table are now documented.** The partition-filter rule applies to `subscribe` exactly as it does to reads — a `subscribe` runs its snapshot through the same enforcement — but the guide only ever described queries, so the commonest shape of all (a per-user live feed on a table partitioned by user id) had no coverage anywhere. The failure is late and misleading: the schema applies, the named query deploys, the catalog export lists it, and nothing complains until the first browser subscribes and gets `PARTITION_FILTER_REQUIRED` while a service key works fine. The new section covers the ways to supply the caller's partition value, which to pick, and why `.WithCrossPartitionAccess()` is not one of them on this path. [Partitioning — live subscriptions](guides/partitioning.md#live-subscriptions-on-a-partitioned-table).
- **Insert `autoIncrement`: omitting the column means `0` — generate (BL-429).** The docs had said this since 0.1.21; the engine accepted `0` and rejected an omitted column with `400 INVALID_REQUEST` (`Missing required column '…'`), so a client that simply left the identity column out of its payload got a 400 for following the documentation. Reported by a pilot customer. ⚠️ **Two boundaries are unchanged:** an explicit `null` is not a request to generate, and under `identityInsert: true` omitting the column is still an error. [HTTP API insert](reference/http-api.md#post-apidatabasesdbtablesnamerows), [Named queries — batch insert](guides/named-queries.md#batch-insert-batchparam).
- **Partition-grant `dimension` is case-sensitive (BL-430).** `POST …/partition-grants` `dimension` must match the table `permissionDimension` byte-for-byte (`"source"` ≠ `"Source"`). A casing mismatch still returns `201` and then every insert/query 403s. [Data Authorization §19.8](auth/authorization.md#198-admin-api-partition-grants). Engine work to case-fold or reject the mismatch is BL-430 (not yet shipped).

## 0.1.32 — 2026-09-17

**Decimal demotion, coalesced bulk-load MQ rebuilds.** Server **0.1.32**, `Aouda.Client` **0.1.32**, `@aouda/client` **0.1.23** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A decimal that overflows compact encoding no longer pins the segment in RAM (BL-565).** The page is written as `DecimalPlain` instead of failing the whole demotion.
- **Forced demotion skips a segment already proven unbuildable (BL-566).** Emergency pressure no longer reconstructs the same failing segment dozens of times.
- **A memory refusal names what sits in the untracked gap (BL-567),** including resident hot-segment bytes (`ResidentAttributedBytes`).
- **Overlapping bulk-load materialized-query rebuilds coalesce (BL-568).** At most one in-flight scan-fed generation per source table, plus one queued follow-up.

## 0.1.31 — 2026-09-17

**P52: smaller pieces, not a bigger ceiling.** Server **0.1.31**, `Aouda.Client` **0.1.31** (`CreateBatchWriter`), `@aouda/client` **0.1.23** (unchanged — TS batch-writer parity is BL-543), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **An over-budget ingest-fed materialized-query build now partitions and keeps going, instead of retiring into a full-table scan (P52 S01–S03).** A memory refusal no longer buys a scan; a hard-limited heap paces ingest instead of killing the process. [HTTP API](reference/http-api.md).
- **Ordinary keyed ingest no longer collapses once the table has cold segments (BL-560, closing BL-415).** Ordinary single-row update no longer 500s as `Duplicate primary key` (BL-529). Insert/update/delete no longer fail with `FileNotFoundException` because compaction unlinked a file mid-decode (BL-559).
- **A materialized query over another query's result table can be maintained (BL-530).** Republishing no longer strands the queries built on top of it (BL-563). A deferred query comes back on its own when the heap recovers (BL-547).
- **`Aouda.Client` gains `CreateBatchWriter()` for one-row-at-a-time producers (BL-542).** No wire change. TypeScript parity is BL-543.
- **Replication on a table that writes no WAL is refused (BL-545).** Elastic-share activity term is on by default (BL-552). A swallowed hot-segment load failure is a retryable activation, not missing rows.

## 0.1.30 — 2026-09-16

**P51 ingest amplification, P50 S09 bounded Filter, and BL-525 freshness.** Server **0.1.30**, `Aouda.Client` **0.1.30**, `@aouda/client` **0.1.23** (pin after npm — published line still **0.1.22**), Studio **0.0.26** (unchanged pin until npm). See [Compatibility](clients/compatibility.md).

- **A bulk load no longer rescans its table once per commit to rebuild materialized queries (BL-517 / P51).** The seed now reads every tier through the engine; a commit publishes incrementally.
- **A `Filter` rebuild is bounded by the shadow's flush trigger, not the match count (BL-503 / P50 S09).** Publication is an atomic two-name swap.
- **A freshness shortfall no longer permanently kills a live subscription (BL-525).** Omitted `onExceeded` is now `wait` on Primary/Standalone (explicit `fetchPrimary` is unchanged). A materialized query that is still building answers `MQ_NOT_READY` (409) instead of an unsatisfiable `TOKEN_FETCH_PRIMARY`. Both SDKs retry `MQ_NOT_READY`. [HTTP API](reference/http-api.md), [Freshness](guides/freshness.md).
- **Unsigned / float / decimal predicates no longer throw or match the wrong rows (BL-521).**
- **A hot segment's primary-key index partition is retired when the segment leaves the hot tier (BL-509).**

## 0.1.29 — 2026-09-15

**P50: a materialized query result is an ordinary table.** Server **0.1.29**, `Aouda.Client` **0.1.29**, `@aouda/client` **0.1.22** (unchanged — `workingSetTruncated` TS parity is a follow-up), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **Materialized queries now read and write through the engine's ordinary table path.** Incremental result changes emit `update` with `prev` again; `QueryMaterializedAsync` no longer returns empty after a checkpoint or demotion (Timestamp columns arrive as `DateTime`); a rebuild no longer leaves the previous generation beside the new one; deletes work after the result goes cold. `MemoryIntent.Mutable` is no longer forced on result tables.
- **`UpdateMode.Sync` means the update is never dropped for queue backpressure**, not that it runs on the dispatch thread. Neither mode is read-your-write; wait explicitly. [Materialized queries](guides/materialized.md).
- **Opt-in bounded Top-N-per-group rebuild (BL-502).** `Aouda:MaterializedQueries:Rebuild:TopNPartitioningEnabled` (default `false`) plus `TopNPartitioningReserve`. Truncated groups mark the query stale rather than answering short. `GET` MQ status / `Aouda.Client` gain `workingSetTruncated`.
- **Tombstoned primary keys are no longer reported live (BL-508).** Re-insert after delete works once the row has left the write buffer. Phone MFA verify updates in place and never returns a zero-byte 500. Ingest no longer spends minutes backing off 503s that did not fit the arithmetic. A standalone node no longer rejects its own just-issued consistency token.

## 0.1.28 — 2026-09-14

**PR #348 review follow-ups on the 0.1.27 durability train.** Server **0.1.28**, `Aouda.Client` **0.1.28**, `@aouda/client` **0.1.22** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **Rows deleted just before a flush can no longer come back at the next open (BL-507).** A failed pre-freeze deletion-mask write now fails the flush (rollback + retry) instead of publishing a discoverable segment whose deletions were never on disk. Same defect shape as BL-504 in 0.1.27.
- **Demoted edge tables keep their table kind in the segment manifest, and column-less demoted segments still get a manifest (BL-439 follow-ups).** Closes two holes left in the 0.1.27 demotion-manifest fix.

## 0.1.27 — 2026-09-14

**Durability and MQ correctness: PITR incarnation, demotion recovery, checkpoint sync, flush/horizon row-loss, MQ watermark fixes, and over-budget aggregate partitioning.** Server **0.1.27**, `Aouda.Client` **0.1.27**, `@aouda/client` **0.1.22** (unchanged — no TypeScript surface in this train), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A backup now records which WAL-root incarnation it was taken against (BL-330, BL-438).** PITR no longer picks an unrelated recreated local WAL by byte offset alone, and archive restores can place a backup among superseded incarnations. Older backups without the fields keep working (unknown = prior behaviour + warning).
- **Demoted cold segments are recoverable end to end (BL-439, BL-506).** Demotion writes `segment.manifest`, and a legitimately-null rebuild is no longer cached for the life of the process.
- **Checkpoint sync works (BL-328).** Staging is a sibling of the data directory, so apply no longer moves staging away with the parent and fails every attempt.
- **A failed hot-segment write fails the flush (BL-504), and a flush does not advance the redo horizon past an in-flight writer (BL-500).** Closes acknowledged-then-lost row paths on crash recovery.
- **Materialized-query watermark / consistency-token correctness (BL-487, BL-501, BL-498).** Cross-table tokens no longer wedge reads; create publishes the WAL head; a write during build/refresh is reported stale rather than silently omitted; budget-retired queries re-arm when the ceiling rises.
- **An over-budget aggregate materialized query can finish by partitioning (BL-477, BL-491)** instead of retiring permanently. New settings under `Aouda:MaterializedQueries:Rebuild:` (`PartitioningEnabled`, `MaxPartitions`). See [Materialized queries](guides/materialized.md).

## 0.1.26 — 2026-09-13

**Resource governance: work is classified, background yields to live traffic, and a host with headroom gets a faster Aouda.** Server **0.1.26**, `Aouda.Client` **0.1.26**, `@aouda/client` **0.1.22** (unchanged — no TypeScript surface in this train), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **Work is classified, and that classification is what admission spends (P49).** Every reservation carries a `WorkClass` — `Interactive`, `Streaming`, `Ingest`, `Background`, `Maintenance` — declared per endpoint rather than guessed from an HTTP verb. Background work (compaction, cold merge, WAL archive, MQ rebuild, …) slows while foreground traffic is active and expands when the server is quiet: under a saturating background load, foreground median latency stays at the idle baseline (~6–7 ms) where it previously doubled. Pacing is a delay, never a cancellation. `Aouda:Memory:PerClassAdmissionEnabled` (default `true`) turns the division off.
- **A CPU contract, and one endpoint that answers "what is using my memory and my cores."** `HostCpuProbe` reads a cgroup quota instead of trusting `Environment.ProcessorCount`. New settings: `Aouda:Cpu:ConfiguredCores` (unset) and `Aouda:Cpu:OversubscriptionFactor` (`2.0`). `GET /api/server/memory` gains reserved bytes by class, CPU facts with provenance (read the `source` field), work in flight by class, and `resourceMode` / `headroomRatio`. A climbing `resourceModeTransitions` count is a signal to investigate.
- **A host with large headroom shows higher RSS at the same data volume.** Deliberate: Aouda moves between `Constrained`, `Balanced` and `Abundant`, raising buffering so more RAM buys speed rather than only capacity. **Alert on RSS-versus-configured, not absolute RSS.** `Constrained` is byte-for-byte the pre-P49 behaviour.
- **A `HotOnly` pin now says what happens when honouring it would breach the ceiling.** `residency.hotOnlyBackstop`: `RefuseWrites` (default — writes take a typed retryable `503`) or `DemoteAnyway`. Raw-HTTP `PinAllInMemory` is retired (`400`, use `storageTemperature: HotOnly`). SDKs never sent it.
- **Queries whose result exceeds `Aouda:Query:MaxResultRows` (default 1 000 000), and a `POST …/named-queries/batch` that genuinely exceeds the class ceiling, now refuse with a typed `503`** rather than materialising. The bound existed; nothing enforced it. A `503` may now name which class of work was refused.
- **A named mutation's `values` / `set` entry has exactly three forms, and a typo now fails at schema apply (BL-479).** A literal (any JSON value that is not an object), a `{ "param": "<name>" }` hole, or — new — a `{ "value": <literal> }` constant. Anything else fails apply with `NAMED_MUTATION_VALUE_NODE_INVALID`. Reported by a pilot customer, whose `{ "value": 0 }` on an `autoIncrement` key returned a bare `400 INVALID_REQUEST` from deep inside column conversion. [Named queries — writing `values` and `set`](guides/named-queries.md#writing-values-and-set), [HTTP API — named mutations](reference/http-api.md#named-mutations).

## 0.1.25 — 2026-09-12

**Memory ceiling honesty (the Derive OOM-cascade incident) and materialized-query rebuild memory accounting + bulk refresh.** Server **0.1.25**, `Aouda.Client` **0.1.25**, `@aouda/client` **0.1.22** (unchanged — no TypeScript surface in this train), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **The memory ceiling now reflects what the host can actually have, not its total RAM (P48).** On a host with no container memory limit, Aouda previously derived its budget from total physical memory, ignoring every other co-located process — a 7.6 GB host running 28 containers gave Aouda a ~3 GB budget while only 136–202 MB was actually free, and the process eventually lost its own listener to `OutOfMemoryException`. The budget is now the smaller of a fraction of total and a fraction of real availability; a container/cgroup memory limit is unaffected (it's a promise, not a guess), and an explicit `maxTotalRamBytes` is unaffected. `GET /api/server/memory` and the startup log now show the real host-available figure and where it came from.
- **Admission and health checks can no longer both say "fine" while the process is one allocation from death (P48).** They previously measured only what the engine's own memory governor had *promised* to reserve, not what the .NET runtime had actually committed to the managed heap — decode buffers, aggregate state and result rows all count against the real heap without passing through that ledger. Admission now also refuses when the heap itself is genuinely close to its hard limit (sustained, so a healthy server running comfortably near a low configured limit is never refused), and the memory health check can now report Critical, which affects container/orchestrator readiness.
- **A process that is truly out of memory now exits instead of staying alive and unreachable forever (P48).** Previously, once the accept loop itself failed with an OOM, the process kept holding its port with no way to serve traffic and no way for an orchestrator to know to restart it — `/health` simply stopped responding rather than reporting unhealthy. A new watchdog now exits the process (cleanly, or via a hard fail-safe) once the heap is genuinely exhausted and a forced garbage collection doesn't recover it, so a restart policy can act. The shipped Docker/Compose/Helm configs gain a memory limit and a `/ready`-based health check. A detailed sizing/triage guide exists in the server repo ([`docs/dev/P48-Memory-Sizing-And-Limits.md`](https://github.com/aoudadb/aouda/blob/main/docs/dev/P48-Memory-Sizing-And-Limits.md)); porting it to this site is a follow-up.
- **Materialized-query rebuilds (`:refresh`, restart, schema changes) now account for their own memory and refuse honestly instead of risking an `OutOfMemoryException` (BL-474).** A wide aggregate rebuild previously reserved memory only for its scan batch, not for the per-group accumulator state that actually grows without bound — a 1-minute-bucket rollup over 15 million rows could take the whole process down. An over-budget rebuild can now spill its accumulator to the query's own result table and read groups back on demand (roughly 3× more groups fit in the same budget); if it still doesn't fit, the rebuild retires the largest query first so smaller sibling rollups still complete, and reports exactly which query, how much memory, and which setting to change. See [Materialized queries](guides/materialized.md).
- **Refresh several materialized queries sharing a source table in one call (BL-474).** `POST /api/databases/{db}/materialized-queries:refresh` (`sourceTable` + optional `staleOnly`, or an explicit `names` list) rebuilds every selected query from a single pass over the source table instead of one pass per query. `Aouda.Client` gains `MaterializedQueries.RefreshTableAsync`/`RefreshManyAsync`; the CLI gains `aouda mq refresh --source-table <table> [--stale-only]`. Existing single-query refresh (`{name}:refresh`, `RefreshAsync(name)`) is unchanged. No `@aouda/client` (TypeScript) surface yet.
- **A `PostLoadMqBehavior.Skip` bulk load could leave a materialized query silently serving a result missing that load's rows, even after a restart (BL-474).** It's now marked durably stale, so it reports `isStale`/`staleReason` and — this is a real behavior change — a server restarting before you refresh now rebuilds it at startup instead of reattaching the incomplete result.
- **Segment lifetime correctness fixes (BL-470/471/472, ADR 0047 D-5/D-6).** A hot segment sealed before a later schema change added a column could get permanently stuck unable to demote to cold storage; a background cold-segment merge that hit an already-occupied path could stall forever retrying the identical failure; and — the more serious one — a segment being moved between hot and cold tiers could, under a race with a concurrent background merge, resurrect its old catalog entry as a duplicate that survives a restart. All fixed; no API or documented behavior change.

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

