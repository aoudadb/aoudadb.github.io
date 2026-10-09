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

- ⚠️ **Replication is not supported in this release (BL-839).** A replica cannot catch up after a disconnect: frames the
  primary writes while it is away are never sent to it. Run single-node. See [Replication](guides/replication.md).
- **Every refusal is answered as one (BL-921, BL-881).** A capacity refusal on any endpoint is `503` with `Retry-After`
  (`MEMORY_BUDGET_EXCEEDED`, or `WAL_CAPACITY_EXCEEDED` for a full log) and a write conflict is `409 WRITE_CONFLICT` — some
  endpoints answered `400`, `409` or `500`. A DELETE or UPDATE whose matched rows other writers keep changing gives up after 16
  attempts with nothing applied (`409 WRITE_CONFLICT`; retry); overlapping DELETEs and UPDATEs now commit as if one ran after
  the other, so a DELETE whose row a concurrent upsert moved out of its `WHERE` leaves that row. See
  [HTTP API — error codes](reference/http-api.md#error-codes).
- **A query over the result ceiling is `400 RESULT_TOO_LARGE`, with no `Retry-After`.** It was a `503` that a retry could never
  pass. Narrow or page the query, or raise `Aouda:Query:MaxResultRows`.
- **Token refresh (BL-841, BL-850).** A refresh refused for capacity is `503` + `Retry-After` and leaves the refresh token
  live — retry with the same token (it was a `500` that spent the token and signed the user out). Two refreshes with one token
  at once: exactly one succeeds, the other revokes the token family — refresh a shared session from one place. Sign-in, sign-up
  and password changes wait for their hash's memory and answer `503` + `Retry-After` when they cannot get it. See
  [Auth setup](auth/setup.md).
- **Bulk load (BL-831, BL-928, BL-924).** A column-batch `:append` is refused `503` before it decodes when memory is short (the
  session stays open; resume from the cursor). A `:commit` whose merge runs out of memory is `503`, never a `500` or a
  misaligned segment. `mqWaitMs` no longer waits on a query that is behind only because its upstream is being rebuilt. A key
  bulk loaded after its delete survives a crash. See [Bulk load](guides/bulk-load.md).
- **Materialized queries (BL-917, BL-882, BL-884, BL-927, BL-935).** A query over another query's result is stale when that
  upstream is dropped or its routing failed. A rebuild refused by a full WAL is behind and requeued, never `Error`, and a create
  whose first build is refused succeeds with the query behind. A rebuild no longer loses rows to a cold coalesce running under
  it, and a coalescing-window change is durable and safe to run concurrently. See [Materialized queries](guides/materialized.md).
- **Crash recovery (BL-823, BL-891, BL-837, BL-923).** On `Recent` / `BestEffort` tables a delete, update or upsert is replayed
  onto exactly the copies it matched; a deleted row stays deleted in every tier; buffered graph edges and vectors, and a
  branch's edges and vectors, survive a crash. ⚠️ **Clean cut:** the WAL's delete, merge, edge-insert and vector-insert frames
  are a new format, and a log holding an older build's such frames past its checkpoint (a crash with them unflushed) is refused at
  open — open it once with the build that wrote it and close it cleanly, or restore from a backup. A cleanly closed database is
  unaffected. See [Storage — troubleshooting](guides/storage.md#214-troubleshooting-by-symptom).
- ⚠️ **Backups are format 3 and restore the whole catalog (BL-840).** Keys, partitioning, cluster order, nullability and table
  and database policy survive a restore (a restored `Strict` table accepted duplicate keys). A backup taken by an older build
  is refused before the target is touched, naming the version found and 3: restore it with the build that took it. See
  [Backup](guides/backup.md).
- **The WAL's cap follows the disk and the workload, and its ladder is logged (BL-787).** `MaxWalBytes` is recomputed after
  reclaims as the larger of a tenth of the space the WAL can use and twice its largest working set, at most half that space;
  each `T25` / `T26` / `T27` crossing is one `[WAL]` log line. The memory broker also keeps the GC's committed bytes under
  0.90 × the heap limit (BL-914). See [Sizing](guides/sizing.md).
- **Files read at open are written whole (BL-933, BL-935).** A clean close can no longer leave `wal/slots.json`, or a
  materialized query's `definition.json`, empty and the database unopenable.

- **Time windows over bulk-loaded history read only the rows they can hold (ADR 0061).** A bulk load writes each series'
  rows together, so a time window used to decode the time column of every row group. Segments now record each series'
  time every 64 rows, and a filter that bounds the time column (`DateTime >= a AND DateTime < b`) reads only those
  granules — hot and cold alike. Same answers; a two-hour window over 1 M trades ~2.3 → ~1.4 ms. See
  [Bulk load](guides/bulk-load.md).
- **A join onto a table you may read only part of is answered with that part (BL-818).** Your row- and partition-level
  security for every joined table is applied on that join's side — exactly as on a direct read of the table — instead of the
  join being refused with `403`. A join can also carry its own filter on the joined table, `joins[i].where` (`joinWhere()` in
  both SDKs). Its values are read with the joined table's culture, and in a named-query definition its columns must be the
  joined table's — a definition naming a base-table column there is refused when it is applied. See
  [HTTP API — Join Clause](reference/http-api.md).
- **A named query's `selectExpr` names its columns exactly as the table does (BL-799).** A definition whose expression names
  `price` for a column `Price` is refused when it is applied; one stored before answers `400 COLUMN_NOT_FOUND`, as `/query`
  does, instead of `500`.
- **The latest (or first) row per key over HTTP (BL-801).** `/query` takes `perKey: { keys, orderBy, latest }` —
  `LatestPerKey` / `FirstPerKey`, routed to a materialized query of the same shape when one answers it. `latestPerKey()` /
  `firstPerKey()` in both SDKs.
- **Named queries carry `aggregates`, `groupBy` and `perKey` (BL-796).** A definition with them answers its keys and
  aggregates, as `/query` does, and is applied under `/query`'s rules (a shape `/query` would refuse fails `schema/apply`).
  Before, the keys were silently dropped and the named query answered plain rows.
- ⚠️ **`Aouda.Client`: `ClientColumnarResult.Data` holds the public values on both wires (BL-798).** A JSON answer's cells
  were `JsonElement`s and a frame answer's `long` / `DateTime` / `Guid` / `decimal`; now both are the values.
- ⚠️ **A computed column's `colRef` is case-sensitive (BL-799)**, as `where` and `select` are: a mis-cased name is `400
  COLUMN_NOT_FOUND`. It used to read the column in the default answer and `null` with `format=rows`.
- **`reference/timestamp.md` corrected (BL-808).** It said `Timestamp` is stored as Unix milliseconds with a per-column unit;
  it is, and always was, .NET UTC ticks, as the HTTP reference says.
- **Cold pages are checked again in the background (BL-815).** A scrubber re-reads every cold page and checks its CRC: 15
  minutes after open, then daily, under 64 MiB/s. A page corrupted on disk after it was first read is reported in the log and
  fails its reads with a corruption error instead of being returned as wrong values. See [Storage](guides/storage.md#213-operations-and-observability).
- **`AVG` without `groupBy` is answered from the segments' statistics (BL-807).** The same answer as before, without reading
  every row of the column.
- **A schema change's validation reads the table as one snapshot (BL-819).** Adding a primary key or a `NOT NULL`, or narrowing
  a column's type, checks the existing rows through the same read path as queries. A write landing during the check could
  before make it refuse a key that was unique ("duplicate primary-key value"); it no longer can.
- ⚠️ **The column `encoder` option is gone (BL-768).** It named an encoder preference that has changed nothing since columns
  choose an encoding per vector. `PATCH …/columns/{c}` no longer takes it (a request carrying only `encoder` is a `400`),
  column details no longer report it, and a schema file that still carries it applies with the key ignored. `@aouda/client`
  drops it from its types.
- **Removed: `stats.distinctServedFromPartitionMetadata`** on query responses, which no server has set since the
  partition-directory `DISTINCT` was retired; and the `.NET`-only `PartitionOptions.LateArrivalPolicy` /
  `LateArrivalThreshold` (BL-762), which did nothing — a late row is flushed like any other. The metrics endpoint's
  `timeSeries` object keeps only `manifestsRead`, and `partitioning` loses the `autoModePartitions` counter that was always 0.
- ⚠️ **Partition directory names are sanitised the same way on every platform.** A partition-key value containing `:` `*` `?`
  `"` `<` `>` `|` `\` or a control character became a directory of that name on Linux and an underscore on Windows; the Windows
  rule now applies everywhere. A **Linux** data directory written by an earlier build with such a character in a partition key is
  not migrated: a partition-scoped read would miss those rows. Re-load such a table after upgrading.
- **The embedded API refuses a string with an unpaired UTF-16 surrogate (BL-772)**, as HTTP's JSON parsing already did:
  `InsertRowsAsync`, `UpsertRowsAsync`, `UpdateRowsAsync` and `BulkLoadAsync` throw `ArgumentException` naming the row and column.
  Such a string has no UTF-8 form; it was stored as U+FFFD and could make a page's bounds skip a matching row. A valid surrogate
  pair (an emoji) is unaffected.
- **Rows are no longer lost or hidden after a restart beside coalesced, bulk-loaded or vector segments (BL-849).** In those
  layouts the write buffer's row ids could restart at the wrong number: rows inserted after a restart were not returned until they
  flushed, and rows still only in the write-ahead log could be lost in a crash (beside a bulk-loaded segment, or after a vector
  flush ran ahead of the table's own). Fixed; a branch's own inserts after its parent's coalesce are read as well.
- **An UPDATE racing a read no longer shows the old row beside the new one**, when the updated cold segment left memory between
  the read's two steps.
- **A range query no longer misses rows of a hot segment after a column was made derived (BL-770)**: the segment's statistics
  kept the old values.
- **The latest (or first) row per key, read without a materialized query, no longer sorts the table (BL-806).** `perKey` (and
  `LatestPerKey` / `FirstPerKey` in the SDKs) keeps one row per key as it scans: TSBS's `lastpoint` over 1 M rows went from
  3.2 s and 1.4 GB of allocation a query to ~36 ms. Same answers. A materialized query is still the way to keep it current for
  subscribers.
- **String filters (`=`, `IN`, `LIKE`, ranges) and string `groupBy` keys read cold pages without building a string per row.**
  A contains-`LIKE` over a ClickBench column went from ~120 ms to ~19 ms. Same answers.
- **An exported schema document uses LF line endings on every platform**, so the same schema exports as the same bytes on Linux
  and Windows.
- ⚠️ **Joins need a grant on every joined table, a 0.2.x data directory is refused at open, and a clean restore keeps hot
  rows (ColumnarRead architecture review).** A join — ad hoc, `…/query/count` or in a named query — needs the base table's
  grant on every joined table (it read them with no grant check before); the caller's row- and partition-level security on
  a joined table is applied on the join's side (BL-818, above). The catalog format is 5: a 0.2.x directory fails at open
  with `CatalogFormatException` (export with 0.2.x and reload; its cold segments used to read as zero rows), a 0.2.x backup
  restored here fails by segment on read, and a primary and its replicas must run the same build. A clean restore now
  catalogues `.hot` segments, whose rows it lost. `DISTINCT` over partition-key columns is a scan, so deleted or truncated
  partitions no longer appear (the directory-residue and 10,000-tuple refusals are gone, and the
  `stats.distinctServedFromPartitionMetadata` flag is removed, above). `Retry-After` is readable from a browser. The TypeScript `count()` posts `/query/count`
  instead of downloading every row, and both SDKs' counts drop aggregates and GROUP BY. Docs corrected beside it: the
  frame response's JSON fallbacks and its connection abort after the headers, the `Decimal` frame kind, row views in both
  SDKs, and the `Timestamp` unit (ticks, not milliseconds; BL-808, above). See [HTTP API](reference/http-api.md#post-apidatabasesdbquery),
  [Authorization](auth/authorization.md#196-combined-pls--rls) and [Storage](guides/storage.md#27-core-concepts-and-mental-model).
- **Fixed: wrong answers in routed reads and cold point reads (ColumnarRead group-6 review).** A read of
  a table answered from one of its materialized queries could disagree with the table: after a
  `TRUNCATE`, a column dropped (and added back) or renamed, or a new column default (the result kept the
  old rows; it is now marked stale and rebuilt); for a `SUM` whose group lost its last non-null value
  (0 instead of null); for a string `MIN` / `MAX` (culture order instead of code point); for a
  latest-per-key winner whose order value an update set to null; for a filter on a `Float32` or
  `UInt64` column; and a routed `LatestPerKey` page came back in the result's order rather than key
  order. Separately, a primary-key read of a cold segment holding an updated key twice (the old copy
  deleted) could return no row. See
  [Materialized queries](guides/materialized.md#routing-a-read-to-a-maintained-result).
- **Reads no longer copy the write buffer (ColumnarRead S19).** A read that reached unflushed rows
  flattened all of them into fresh arrays every time; it now reads the buffer where it is. Under a
  steady 50,000 rows/s insert load, a `COUNT` / `SUM` over the table went from 4.4 to 1.5 ms at the
  median, and the inserts' acknowledgement while reads run from 107 to 39 ms. Answers are unchanged.
- ⚠️ **A materialized query answers for its table only while it is current; a stale one no longer
  does (ColumnarRead S18).** A question a materialized query already holds the answer to — rows,
  columns, aggregates, GROUP BY (rolled up from finer time buckets), `COUNT(*)`, `DISTINCT` — is read
  from its result table on every read path and over HTTP (`POST …/query`, `…/query/count`), but only
  when the result is `Ready`, not stale, has nothing queued and has incorporated every write the read
  can see; otherwise the table answers. Before, only the embedded `ToResultAsync` routed, and a stale
  result (a `skip` or `deferred` load, a dropped update) answered for its table without the rows it
  was missing. A routed answer is the table's answer, and says so in `stats.routedTo`. See
  [Materialized queries](guides/materialized.md#routing-a-read-to-a-maintained-result).
- **The latest (or first) row per key, as a question (BL-450, ColumnarRead S18).**
  `TableQuery.LatestPerKey(orderBy, keys…)` / `FirstPerKey(…)` in the embedded API, read from a
  matching materialized query when one is current. Over HTTP and in both SDKs too (BL-801, above). See
  [Query](guides/query.md).
- **Point reads read what they return (ColumnarRead S17).** A filter that pins every series column
  (`Ticker = 'X' AND Source = 'Y'`) reads only that series' rows from each segment's run directory, and
  a primary-key read of a cold segment only the rows the key map located. Also fixed: a keyed read
  could come back empty for a key updated while it ran. See
  [Primary-key indexing](guides/pk-indexing.md).
- **Query results as column-batch frames, and aggregates and GROUP BY over HTTP (ColumnarRead S16).**
  `POST …/query` and a named query's execute answer with column-batch frames when `Accept` lists
  `application/vnd.aouda.column-batch`, with the rest of the envelope in `X-Aouda-*` headers (exposed
  to browsers by CORS); both SDKs ask for them and fall back to JSON. The query message gains
  `aggregates` (`count`, `sum`, `min`, `max`, `avg`, `countDistinct`) and `groupBy` (columns and
  `Timestamp` buckets); `limit`, including its default of 1,000, applies to the groups. The C#
  `RemoteTableQuery` gains `GroupBy`, `Sum`, `Avg`, `CountDistinct` … and `AggregateAsync()`, and the
  TypeScript `sum()` / `min()` / `max()` / `groupBy()` now send them (the server ignored what they sent
  before, and returned plain rows). JSON responses are written from the columns and streamed, with
  the same bytes; a `NaN` or infinite `Double` cell is now a `500 INTERNAL_ERROR` naming the column,
  before anything is sent. In `Aouda.Client`, `ClientColumnarResult.GetColumn<T>()` no longer returns
  `default` for every cell of a JSON answer, and `ToDataTable()` no longer throws on one. See
  [HTTP API](reference/http-api.md#aggregates-and-group-by).
- **Total matches counted by the read itself (ColumnarRead S15).** A named query with `count: true`
  counts `totalMatches` in the same read, over the same snapshot as its page; it ran a separate count
  that could disagree with the page under concurrent writes. In the embedded API,
  `TableQuery.WithTotalMatches()`, and `ToListAsync` rows are views over the result's columns rather
  than dictionaries (the members are unchanged).
- **A table query reads a vector column as null (ColumnarRead S14).** A `select`, `orderBy`,
  `distinct` or `count` naming one failed, and so did a DELETE or UPDATE on a table with a non-nullable
  vector column. Vectors are read by the nearest-neighbour operators. See
  [Graph and vector](guides/graph-vector.md).
- **A table's `memoryFilter` now orders demotion on a server (ColumnarRead S14).** It only ever took
  effect in the engine's tests. See [Hot/cold](guides/hot-cold.md).
- ⚠️ **Removed from the embedded .NET API (ColumnarRead S14, S16), unused:** `TableQuery.WhereJoined`,
  `GroupByJoined`, `SelectAll`, `ToJsonAsync`, `ToColumnarJsonAsync`, `ColumnarQueryResult.ToJson()`,
  `EngineInsertResult.FromRowCount` and `HotColdInspector`; `GroupAggregateAsync` on a join is refused.
  The adaptive bloom path is gone: `bloomFilterBytes` in the memory report and
  `bloom_filters.adaptiveBytes` in metrics read 0.
- **`/api/admin/metrics`: five always-zero counters removed, and the deleted scans' counters read 0
  (ColumnarRead S01, S14).** Gone: the `simd` subsystem, `query.fusedAggregateOps`,
  `storage.pageCache.entries`, `io.totalMs`, `timeSeries.segmentSummaryCount`. The `query` subsystem
  lists the read counters; `decodedValues`, `segmentsPrunedByPartitionKey` and `hotSegmentHits` /
  `hotSegmentMisses` move, while `rowsScanned`, `hotScanRows`, `coldScanRows`, `parallelScans`,
  `vectorizedOps` and the page-pruning counters stay at 0. See [Query](guides/query.md).
- **The page cache is on in every resource mode (ColumnarRead S13).** It was off in `Constrained`, the
  mode every database starts in; `Aouda:Memory:PageCacheEnabled = false` turns it off. Large scans
  run on several workers within the query's CPU grant, and a GROUP BY's, top-K's or `DISTINCT`'s
  growing state is charged to the query's budget as it grows. See
  [Server configuration](guides/server-configuration.md) and [Sizing](guides/sizing.md).
- ⚠️ **`SUM` over no value is `null` (BL-757, ColumnarRead S12)** — a filter that matched nothing, or a
  column null in every matching row, on every path; it answered `0` whenever a segment was read. Also:
  `MIN` / `MAX` of a `String` (code-point order) or `Bool` column answer the value instead of `null`;
  `SUM` of a `String`, `Bool`, `Guid`, `Timestamp` or `Date` column is refused; `DISTINCT` keeps a null
  apart from `0` / `false` / `""`; an `orderBy` without a `limit` puts nulls last ascending (a columnar
  answer put them first) and orders strings by code point. GROUP BY in the embedded API:
  `TableQuery.GroupBy(…)` with `GroupAggregateAsync()`; `AggregateAsync()` refuses a grouped query. See
  [Query](guides/query.md).
- **Every read runs on one scan that skips what its statistics rule out (ColumnarRead S11–S14).** Rows,
  columns, `COUNT(*)`, aggregates, GROUP BY, `ORDER BY … LIMIT`, `DISTINCT`, joins' sides and DELETE /
  UPDATE matching read through one pipeline that classifies each 8,192-row row group from its
  statistics and decodes only what a selected row needs. On 1 M cold trades, a full-table aggregate
  went from 74.1 ms to 0.72 ms. See [Query](guides/query.md).
- **Reads, writes and background reorganisation no longer see rows twice, miss them or bring deleted
  ones back (ColumnarRead S02–S17).** Dozens of windows during flushes, coalesces, promotions and
  demotions are closed, each with a test, among them: rows returned two or more times after maintenance
  (BL-751); an UPDATE or upsert that could durably lose its row; a DELETE that could durably delete a
  row inserted again under the same key; a `Strict` table accepting a duplicate unsigned key; nulls read
  as `0` after a promotion; a `Dedicated` partitioned table's partition-key column read as empty.
- **String ranges and null ordering (BL-750, BL-755, ColumnarRead S02).** `gt` / `gte` / `lt` / `lte`
  on a `String` column compare by code point (the server refused a string value; in process they
  matched nothing), and a null sort key sorts last ascending and first descending with a `limit` (it
  sorted as `0`). Also fixed: `COUNT(*)` of a table whose first column is a `Timestamp` (`0`), `MIN` /
  `MAX` of a `Timestamp` or `Date` (`null`), `OR` filters that skipped matching cold pages, and
  (BL-745) a query that met a corrupt page and truncated the column file: it now fails with
  `ColumnPageCorruptException` and leaves the file alone. See [HTTP API](reference/http-api.md).
- **Hot segments carry the same statistics footer, and a hot segment file from an earlier build is
  not read (ColumnarRead S10).** A `.hot` file (now version 2) stores, per 8,192-row slice of every
  column, the statistics a cold page records, plus the segment's sort-key index, series ranges and
  key range, so a restart no longer loses them. A version-1 `.hot` file is refused by name and its
  segment is rebuilt from its cold copy where one exists — as with S08 / S09, export with the earlier
  build and reload. Merging small hot segments now keeps rows in the table's cluster order.
- **A column whose type was widened is skipped by its page statistics again (ColumnarRead S10).**
  Pages written before an order-preserving type change (a wider integer, integer → `Double`,
  `Float32` → `Double`, `Date` → `Timestamp`) prune by their min / max converted to the new type,
  instead of being read in full. A change to `String` still reads every page.
- **Cold segments carry a statistics footer (ColumnarRead S09).** Every cold page records, besides
  min / max and its null count, whether it is constant, sorted or all-null, its run count, first and
  last value, an exact sum for integer and decimal columns, and up to 16 distinct values; every
  segment's `segment.manifest` (v4) holds those for each page, the first and last sort-key value of
  each 8,192-row group, and the row range of each series. Together they stay under 2 % of the
  segment's bytes. The deletion mask (`_deleted.pages`) records its deleted count. Nothing answers
  a query from them yet; later read-path work does. Footers, page headers and deletion masks written
  by an earlier build are refused by name: export with that build and reload.
- ⚠️ **Cold pages are layout v2, and a 0.2.x data directory does not open (ColumnarRead S08).** Every
  cold column is cut into 8,192-row pages, encoded in 2,048-row vectors that each decode on their own
  (frame-of-reference and delta bit-packing, run-length, constants; ALP for doubles; a sorted
  dictionary or plain UTF-8 for strings). Page min / max no longer count nulls, so more pages are
  skipped. Pages written by 0.2.x are refused by name ("a layout-v1 codec"): export with a 0.2.x
  build and reload. A column's `encoder` option no longer changes the encoding, and is removed (BL-768, above). Edge
  tables no longer write `csc_*.col` mirror files (nothing read them; `StoreCsc` still enables
  bidirectional `ShortestPath`). See [Sizing](guides/sizing.md).
- ⚠️ **Delta segments are removed (ColumnarRead S07).** Late-arriving rows are flushed inline with
  on-time rows (`LateArrivalPolicy` is removed, BL-762, above), and nothing writes
  or reads a table's `data/_delta/`. **Rows an older build left under `data/_delta/` are no longer
  read.** `AoudaEngine.SealOrphanedDeltaSegmentsAsync` is removed: a pre-0.1.5 database that still
  needs it (BL-146) must run it before upgrading.
  See [Time-series](guides/time-series.md) and [Partitioning](guides/partitioning.md).
- **A partition key's promotion to a dedicated directory no longer moves its earlier rows (ColumnarRead
  S07).** They stay in the shared bucket and are still read. See
  [Partitioning](guides/partitioning.md).
- **A read is one view (ColumnarRead S07).** A read's segments, deletion masks and unflushed rows are
  fixed at one instant: a concurrent MERGE, UPDATE, flush or coalesce is no longer seen half or
  twice. A read takes its segments from the catalog and never lists a directory; a catalog change is
  visible only once it is durable; and a read that cannot resolve a segment its catalog names fails
  instead of returning short. A restored database's catalog is the backup's own catalog image (BL-840, above);
  the open no longer rebuilds one from `catalog.chk`. See [Query](guides/query.md) and [Backup](guides/backup.md).

## 0.2.0 — 2026-09-30

**.NET 10, `Decimal(p,s)` columns, and writes that travel and land as columns.** Server **0.2.0**, `Aouda.Client` **0.2.0**, `@aouda/client` **0.2.0**, Studio **0.0.26** (pin stays **0.1.25** until Studio moves). See [Compatibility](clients/compatibility.md).

- ⚠️ **Aouda runs on .NET 10 (BL-739).** The server ships framework-dependent, so the **.NET 10
  ASP.NET Core runtime** must be on the machine *before* you upgrade. 0.1.40 and earlier ran on
  .NET 8, and a machine that has only that fails in the .NET host loader, before any Aouda code
  runs and with no Aouda error message. The install scripts check for it, the container image
  carries it (`aspnet:10.0-alpine`), and `aouda doctor` reports the version. See
  [Linux](deployment/linux.md#if-net-10-is-missing) and
  [Windows](deployment/windows.md#if-net-10-is-missing).
- ⚠️ **The .NET packages target `net10.0` (BL-739)** — `Aouda.Client`, `Aouda.Abstractions`,
  `Aouda.Embedded`, `Aouda.Testing` and the `Aouda.Cli` tool. A `net8.0` application cannot restore
  0.2.0: it stays on 0.1.40 until it retargets. .NET 8 leaves support on 2026-11-10.
- ⚠️ **`@aouda/client` 0.2.0 belongs with server 0.2.0.** It sends decimal and fractional columns in
  the frame's new `ScaledDecimal` kind, which a 0.1.40 server refuses with a `400` on a bulk-load
  append. `@aouda/client` 0.1.25 keeps working against 0.2.0. See
  [Compatibility](clients/compatibility.md).
- **`stalenessMs` on a materialized query's status (ColumnarMerge S01).** How old the oldest change
  the result does not yet reflect is, in milliseconds. For "how fresh is this query", read it and
  not `currentLag`, which under a steady insert stream grows for as long as the stream runs. See
  [HTTP API](reference/http-api.md).
- **`maxCoalesceMs`, a freshness knob for `Async` queries (ColumnarMerge S10).** A query's batches
  may wait up to that many milliseconds to be applied together: one write per changed group
  instead of one per commit. `0`–`60000`, default `0`; set in `aouda.schema.json`. See
  [Materialized queries](guides/materialized.md).
- **An insert maintains its aggregates and latest / first per key queries in its own commit
  (ColumnarMerge S11).** Cascades, and queries with a `maxCoalesceMs` window, still follow
  asynchronously.
- ⚠️ **A null is no longer compared or aggregated as `0` (BL-729, BL-734, BL-735).** `x < 5`,
  `x != 5` and `NOT (x = 5)` do not match a null, and `Min`, `Max` and `Count(column)` skip a
  column's nulls, as SQL does. A query that relied on the old answers returns different rows.
  See [HTTP API](reference/http-api.md) and [Query](guides/query.md).
- **Inserts can be sent as a column-batch frame (ColumnarCore S06).** `POST …/tables/{name}/rows`
  also takes one `application/vnd.aouda.column-batch` frame — the binary layout bulk-load `:append`
  already reads — and says so with `Accept-Post` on its responses and `insertColumnBatch` in
  `GET /admin/capabilities`. A frame inserts exactly what the same rows as JSON would. `Aouda.Client`
  and `@aouda/client` send frames once a server has advertised them, and JSON to an older server.
  Two visible differences for JSON callers: a body that is not valid JSON is now
  `400 INVALID_REQUEST`, and an empty body is `400 MISSING_DATABASE`. See
  [HTTP API insert](reference/http-api.md#post-apidatabasesdbtablesnamerows) (revision 2.8).
- **After a `415`, both SDKs stay on JSON for five minutes (BL-716).** A later response advertising
  frames no longer flips them back at once, so a mixed fleet behind one address stops costing an
  upload per flip. A string cell that is not valid UTF-8, or a non-finite `Double` in a frame, is
  now a `400` on every path.
- **`Decimal(p,s)` columns (ColumnarCore S13).** `"type": "Decimal", "precision": 18, "scale": 2`
  stores the column as a scaled 64-bit integer instead of a 16-byte decimal per cell. Values in and
  out carry exactly the declared scale (`10.50`); a value with more places, or too many integer
  digits, is a `400` naming the column. Frames gain a `ScaledDecimal` kind. ⚠️ **An older build
  cannot read a table with a `Decimal(p,s)` column** — upgrade a primary and its replicas together.
  Tables without one are untouched. See [Data types](reference/http-api.md#data-types).
- **An `Auto` bulk load's queries are written in its own commit (ColumnarCore S12)** when every query
  over the table is an aggregate or a latest / first per key. They used to be folded by the table's deferred pass after the commit,
  so the handle came back `pending`. Now `:commit` returns with `mqRebuildStatus: "completed"` and a
  publish backlog of 0 — and takes correspondingly longer. The pass still runs after the commit if
  the fold is refused memory, spills, or the table's queries change during the load. See
  [Bulk load](guides/bulk-load.md).
- **The deferred pass and a load's own fold are charged to the memory governor (BL-690).** A refusal
  halves the pass's later waves (down to a sixteenth) instead of going unseen; a fold that is given
  up releases its memory at once. See [Deferred loads](guides/materialized.md#deferred-loads).
- **Concurrent commits share one durable WAL write (ColumnarCore S07).** A commit is now one write
  and one flush, and commits arriving while one is on disk share the next. The log's frames are
  unchanged, so older logs replay as before.
- **An insert flush writes one segment (ColumnarCore S08).** A table on a high-cardinality `Auto`
  partition key used to flush one small segment per bucket its rows touched; it now writes one, as
  bulk loads already do. Reads return the same rows. A one-series read of such a table opens only
  the hot segments that can hold the series (BL-714).
- **The replay buffer keeps a table's changes only once something listens (ColumnarCore S09).** Writes
  made before a subscription watched the table are not retained, so a `resume_from` from before
  them gets the snapshot rather than an empty replay.
  The events a subscriber receives are unchanged. See [Real-time](guides/real-time.md).
- **A maintained `sum` in an in-commit update event carries the column's type (ColumnarCore S10)** —
  `Int64` for an integer column, as the insert event already did; the JSON is the same (`12`). A
  `sum` of a `Double` column now reads `3` where it read `3.0`.
- **Deletion masks have one layout (ColumnarCore S12, BL-725, BL-726).** A merge appends to a
  segment's mask instead of rewriting it. The version-1 layout is not read — a clean cut, pre-1.0 —
  and a mask that exists but cannot be read now fails the read instead of resurrecting the rows it
  deleted.
- **Materialized-query maintenance follows the server's CPU budget (ColumnarCore S15).** The deferred
  pass's workers come from `Aouda:Cpu:ConfiguredCores` or the probed quota, not the machine's core
  count. See [Sizing](guides/sizing.md#sizing-cpu).

## 0.1.40 — 2026-09-27

**Deferred bulk loads, column-batch bulk ingest, and admin MFA factor management.** Server **0.1.40**, `Aouda.Client` **0.1.40**, `@aouda/client` **0.1.25** (unchanged — the TypeScript side of deferred loads and column-batch appends ships in **0.2.0**), Studio **0.0.26** (pin stays **0.1.25**). This section and its matrix row were written on 2026-09-30, with the 0.2.0 train; the guides were updated when the work landed. See [Compatibility](clients/compatibility.md).

- **Operators can list and delete a user's MFA factors (BL-682).**
  `GET …/auth/admin/users/{id}/mfa/factors` returns the masked factor list, including an empty
  list. `DELETE …/mfa/factors/{factorId}` removes that factor and its challenges. Admin enroll
  still returns 409 while a phone factor exists and still does not change the number; replace a
  number by deleting on the admin route, then enrolling again.
- **Deferred bulk loads (BatchFirst S08 / S09).** `postLoadMqBehavior: "deferred"` writes only the
  table; the table's deferred pass folds the load into its materialized queries once bulk ingest
  into the table has been quiet for 2 s, or after 60 s at most. `pendingDeferredJobs` on a query's
  status counts the loads it still owes. See [Bulk load](guides/bulk-load.md) and
  [Deferred loads](guides/materialized.md#deferred-loads).
- **Bulk loads can be sent as column-batch frames (IngestAtSpeed S09).** `:begin` lists
  `"column-batch"` in `acceptedAppendFormats`, and `:append` then takes one
  `application/vnd.aouda.column-batch` frame per batch. NDJSON works as before. See
  [HTTP API](reference/http-api.md).
- **A default bulk load allocates auto-increment ids (IngestAtSpeed S02).** See
  [Bulk load](guides/bulk-load.md).
- **`GET /api/server/memory` gains `runtime` (IngestAtSpeed S01)**, the process's own counters. See
  [HTTP API](reference/http-api.md).

## 0.1.39 — 2026-09-24

**Materialized-query publishes that drain under a sustained bulk load.** Server **0.1.39**, `Aouda.Client` **0.1.39**, `@aouda/client` **0.1.25** (unchanged), Studio **0.0.26** (pin stays **0.1.25**). This section and its matrix row were written on 2026-09-30, with the 0.2.0 train. See [Compatibility](clients/compatibility.md).

- **Publishes drain during a sustained bulk load again (BL-661 / BL-662 / BL-663 / BL-664).** A
  publish into a query that already has rows uses the result table's primary-key index wherever it
  is authoritative, so it costs roughly what the job touched, whatever the result's size —
  including a result table the server has demoted to cold storage. See
  [Bulk load](guides/bulk-load.md).
- **A primary-key read through the query path skips the segments that cannot hold the key
  (BL-647).** See [Primary-key indexing](guides/pk-indexing.md).
- **The server image runs as `$APP_UID`, uid/gid 1654 (BL-660).** See
  [Docker](deployment/docker.md).

## 0.1.38 — 2026-09-24

**An installable server, and materialized queries that say when they are behind.** Server **0.1.38**, `Aouda.Client` **0.1.38**, `@aouda/client` **0.1.25** (unchanged — this train removes a field the TypeScript client never declared), Studio **0.0.26** (pin stays **0.1.25**). See [Compatibility](clients/compatibility.md).

- **Deployment has real pages now, and they describe what is actually shipped (BL-629).**
  New [Linux (systemd)](deployment/linux.md), [Windows Service](deployment/windows.md) and
  [Docker](deployment/docker.md) guides; [Deployment](deployment/) becomes a router to them;
  `getting-started` §16 is rewritten against what exists rather than what was planned.
  - ⚠️ **Several things these pages used to say were not true.** The deployment index named six
    hosting modes and had a page for one, in a table whose Windows row had three cells and two
    columns. The Windows and systemd examples used **`--contentRoot`**, which is an ASP.NET Core
    switch that does **not** set Aouda's data directory — a server started that way stores its
    databases wherever the process was launched from. The container examples named
    `image: aouda/server`, which was never published under that name; the real image is
    `ghcr.io/aoudadb/aouda-server`, and it is **private**. `Aouda.Setup` was described as
    "zero-dependency … self-contained"; it is neither, and its unit file is not the one
    `aouda service install` writes.
  - **Every install instruction now says where the artefact comes from and that it needs a token.**
    Aouda's artefacts are private: no public download, no `curl | sh`, no anonymous `docker pull`.
    A page that shows a command the reader cannot run is worse than a missing page, because they
    spend their time before they find out.
  - **The .NET 8 prerequisite is stated on every page, with the error you get without it.** Aouda
    ships framework-dependent, so a missing runtime fails in the .NET host loader *before any Aouda
    code runs* — there is no Aouda error message, and there cannot be.
  - **The memory limit is explained as what it actually is.** `MemoryMax` / `docker -m` is not only
    a cap: it creates the cgroup boundary that decides whether Aouda sizes its budget from a grant
    it was given (70 %) or a host it merely measured (40 %). Both figures, and the 2026-09-11
    incident that produced them, are now on the page.
  - **`aouda service install` replaces hand-written unit files**, and the Linux page shows the unit
    it generates — `Type=notify` so `systemctl start` waits for WAL recovery, with no start timeout
    so a long recovery is not killed and restarted from the beginning; a stop timeout covering the
    server's shutdown budget; `LimitNOFILE` because Aouda stores a file per column; and a hardening
    block. The install creates the `aouda` service account and owns the data and log directories
    itself, and `--dry-run` prints every step.
  - ⚠️ **Upgrading an older install: re-run `aouda service install`.** A service registered by the
    old install scripts has no `start` on its command line, and the current binary rejects that —
    so an in-place binary swap leaves a service that will not start. Both deployment pages say how.
  - **`aouda status` and `aouda doctor`** find an installed service from its registration, and the
    exit codes are one table, on the [Linux page](deployment/linux.md#exit-codes). A systemd
    credential (`--admin-password-credential` with `--admin-email`) now creates the first admin on
    the server's first start.
  - ⚠️ **No password appears on a command line in any example.** `create-admin --password` has been
    removed — a command line is world-readable at `/proc/<pid>/cmdline` and is kept by shell
    history and audit logs, so a deprecation warning would arrive after the leak. Use
    `--password-file`, `--password-stdin`, or a systemd `LoadCredential=`.
  - **New:** [Defaults reference § Logging defaults](guides/defaults-reference.md#logging-defaults)
    (BL-633). **The default log level is `Warning`**, and the docs had never said so anywhere — so a
    reader holding a page that says a line exists, and not seeing it, had no way to learn that it
    was filtered out rather than absent.

- **A materialized query that is behind its source says so (BL-642).** `currentLag` is how long it has been behind, or `null` when it is not — including a caught-up query that has been idle. `state: Ready` means the result is readable, not that it is current. Read `isStale`, `staleReason`, and `currentLag`.
- **`workingSetTruncated` is gone (BL-583).** It had been hard-wired `false` and was already omitted from every response. Read `isStale` / `staleReason` instead. `@aouda/client` never declared the field.
- **A materialized query's state bound is read from its definition (BL-623).** A `latestPerKey` is no longer partitioned and spilled because a time-bucketed aggregate on the same table could not be bounded. A time-bucketed build can close groups its sort-prefix watermark has passed; unordered input costs re-opens, not wrong answers.
- **Spill still on disk is a number (BL-624).** `GET /api/server/metrics` carries `mqSpillOutstandingBytes`, `mqSpillCeilingBytes`, `mqSpillCeilingExceeded`, and `mqPublishBacklog`. Crossing the ceiling is reported. It does not fail the load.
- **An upsert accepts the same `Timestamp` and `Date` values an insert does (BL-643).** A boolean or a fractional number is refused, same as insert.
- **Written down for behaviour that already shipped.** How a C# property becomes a column type, including the enum rule (a C# enum binds to its underlying integral type — `Int32` unless the enum declares `: byte`). One WebSocket per client, and the `@aouda/client` **0.1.25** fix (BL-635) where each subscription opened its own socket. Named `upsert`, `409 DUPLICATE_PRIMARY_KEY`, and subscribe-replace were already in the 0.1.37 notes.

## 0.1.37 — 2026-09-22

**NULL survives hot-segment restart; Derive Connect's three answers; memory provenance.** Server **0.1.37**, `Aouda.Client` **0.1.37**, `@aouda/client` **0.1.23** (unchanged), Studio **0.0.26** (unchanged pin). See [Compatibility](clients/compatibility.md).

- **A restart no longer turns every nullable fixed-width `NULL` into the type default (BL-628).** Hot segments now persist validity. This is what locked Derive's lab out after heap exhaustion: `mk_srv_` keys have `user_id = NULL`, which read back as `Guid.Empty` and failed every validation. Segments sealed before 0.1.37 cannot be repaired in place (BL-630).
- **Named mutation `"op": "upsert"` (BL-637), `409 DUPLICATE_PRIMARY_KEY` on insert (BL-636), and a repeat `subscribe` replaces instead of refusing (BL-638).** The three answers Derive Connect needed for presence heartbeats and live room lists.
- **`GET /api/server/memory` reports `budgetDerivation` and `headroom` operands (BL-611, BL-622).** No thresholds moved.
- **Expired auth rows are actually deleted (BL-616).** The sweep worker was never started; `aouda start` also now gets Server GC like `Aouda.Server.dll` (BL-621).

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

