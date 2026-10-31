---
title: "Retention and Deleting Before a Time"
nav_order: 11.5
parent: "Guides"
---

# Aouda Functionality: Table Retention and Deleting Before a Time

Document status: New (**Horizon, 0.5.0**)
Primary owner: Aouda maintainers
Last updated: 2026-10-17

Coverage phases: Horizon (`S09`, `S10`, `S11`, `S12`)
Primary ADR: `docs/decisions/0063-time-horizons-windowed-results-retention-and-deleting-by-segment.md` (`D-9`, `D-10`, `D-11`)
Related: [Materialized Queries](materialized.md) (windowed results, and the history a query keeps over a table with retention),
[Real-time Streaming](real-time.md#horizons-and-range-deletes), [Bulk Load](bulk-load.md#loading-a-table-with-retention),
[Time-series and Clustering](time-series.md), [HTTP API](../reference/http-api.md)

Everything on this page is new in 0.5.0 (**Horizon, 0.5.0**). Nothing here exists in 0.4.0.

---

## Start Here

| If you need to know... | Go to |
|---|---|
| How to make a table keep only its recent rows | [Declaring retention](#declaring-retention) |
| What happens to a row older than `keep` | [The horizon](#the-horizon), [Below the horizon](#below-the-horizon) |
| What a write below the horizon answers | [Writes below the horizon: `expiredRows`](#writes-below-the-horizon-expiredrows) |
| How to delete everything before a time without paying per row | [Deleting everything before a time](#deleting-everything-before-a-time) |
| What a live subscriber sees | [What a subscriber sees](#what-a-subscriber-sees) |
| What a replica sees | [Replicas](#replicas) |
| What deleting rows costs in general | [Deleting in general](#deleting-in-general) |
| What is not done yet | [Known limitations](#known-limitations) |

---

## What retention is

A table can declare that it keeps only its recent rows. Rows whose time is older than the server's clock minus `keep` stop being
returned, stop being written, and leave the table **by whole segments**: no row is deleted one by one, nothing is logged per row,
and no data byte is written to drop them.

The shape it is built for is raw time-series data kept for a while, with materialized queries over it kept for ever — raw trades
for 90 days, daily candles for good (the downsampling pattern). A materialized query over a table with retention keeps its history
below the table's horizon; see [Materialized Queries](materialized.md).

Retention is a table's contract, not a side effect: a horizon exists only on a table that declares retention (and on a windowed
materialized query's result). A `DELETE` never installs one on a table without retention.

---

## Declaring retention

`policy.retention` is `{ "keep": "<n><unit>" }` — a whole number of minutes, hours, days or weeks (`m`, `h`, `d`, `w`): `"90m"`,
`"36h"`, `"90d"`, `"2w"`. Months and years are not units (`"3mo"` is refused).

**The requirement:** the table's **first cluster column** (the lowest `clusterOrder`) is a `Timestamp` or `Date`. It may be
nullable. That column is the one retention applies to.

**On create** (`POST /api/databases/{db}/tables`):

```json
{
  "database": "market",
  "name": "trades",
  "columns": [
    { "name": "Id", "type": "Int64", "primaryKeyOrder": 1 },
    { "name": "Ts", "type": "Timestamp", "clusterOrder": 1, "isNullable": true },
    { "name": "Price", "type": "Double" }
  ],
  "policy": { "storageTemperature": "Auto", "retention": { "keep": "90d" } }
}
```

**On an existing table** (`PUT /api/databases/{db}/tables/{name}/policy`). A body that only declares or changes retention needs no
`storageTemperature`; the table's temperature is kept:

```json
{ "database": "market", "retention": { "keep": "30d" } }
```

Declared on a table that already holds rows, it hides the rows below the new horizon at once — unless a rebuild of a materialized
query over the table is running, in which case the horizon is set by the horizon job's first round after the rebuild (below).

The policy response and the table detail (`GET …/tables/{name}`, under `policy`) report it, with the table's current horizon:

```json
{
  "storageTemperature": "Auto",
  "residency": { … },
  "retention": { "keep": "30d" },
  "horizon": "2026-09-16T08:41:00Z"
}
```

`retention` and `horizon` are omitted for a table without retention. The schema document takes the same object
(`"policy": { "retention": { "keep": "90d" } }`), and so do both SDKs: `TablePolicy.Retention` in `Aouda.Client`, `retention` on
`client.tables.createTable(…)` / `client.tables.updatePolicy(…)` in `@aouda/client` ([TypeScript client](../clients/typescript.md)).

### What is refused

Each refusal is a `400` that names its reason.

| Refused | Why, and what to do instead |
|---|---|
| A table whose first cluster column is not a `Timestamp` or `Date` (or that has no cluster column) | Retention drops by time slices of that column; declare the time column with `clusterOrder: 1`. |
| A `keep` that is not a whole number of `m` / `h` / `d` / `w` | — |
| **Removing** a declared retention | It cannot be removed. Over HTTP and schema apply an omitted or `null` `retention` leaves it as it is; only the embedded `SetTablePolicyAsync` refuses a policy without it (an `ArgumentException`). The horizon only rises and the rows below it are already gone, so there is nothing to go back to. Change `keep` instead — a longer one leaves the horizon where it is. |
| A **window** on a materialized query whose source has retention (directly, or as the first non-windowed table up a cascade) | A windowed result computes its part below the window from its source; once the source has dropped a range, that answer would change. Use an unwindowed query over the table with retention — it keeps its history. |
| Retention on a table that a window completes from | The same rule, seen from the table. |
| A query over a table with retention that does not split its groups by the retention column, and retention on a table such a query reads | See [What may read a table with retention](#what-may-read-a-table-with-retention). |
| An **array column** (**BL-035, next train**) | Not refused. An [array column](array-columns.md) is an ordinary column to retention: whole segments of an array table are dropped as for any table. It is not on this list. |
| Retention on an **edge table**, or on a table with a **vector column** | Traversals and nearest-neighbour reads apply no horizon, and vector segments carry no time to drop by; retention is for tabular tables. |
| **Dropping, retyping or un-clustering the retention column** (a `clusterOrder` change that moves retention to another column) while retention is declared | Every read hides the rows below the horizon by that column; without it they would be readable again. |

### What may read a table with retention

A materialized query over a table with retention must split its groups by that time, so that the groups below the horizon can be
kept as they were when a rebuild reads only the rows still there:

- an `aggregate` grouped by a time bucket of the retention column, or by the column itself;
- a `topNPerGroup` grouped by the retention column.

Anything else over such a table — a `latestPerKey`, a `firstPerKey`, a `filter`, an aggregate not grouped by the time — is refused at
create, and retention is refused on a table that such a query already reads. Incremental maintenance would keep their history and
a rebuild would drop it, answering the same query two ways. **Known limitation (BL-1060):** this blocks retention on a table that has
a `latestPerKey` or `firstPerKey` query over it.

A read of a table with retention is answered from the table, never routed to a materialized result. **Known limitation (BL-1061):**
the routing a current result gives other tables ([Materialized Queries](materialized.md)) does not apply to it.

---

## The horizon

The table's **horizon** is the instant below which its rows are gone: the server's clock minus `keep`, **on the minute**.

- It is **persisted, then published**: set in the catalog when retention is declared (create, policy, schema apply), and raised by
  the server's horizon job, which writes it to the catalog before any reader is given it. A reader therefore never sees a row that a
  restart would bring back.
- **A rebuild holds it.** While a materialized query over the table rebuilds, the horizon stays where the rebuild's cut was taken
  from: a policy change made meanwhile — retention declared, `keep` shortened, any other policy field — is saved at once, and the
  horizon it calls for is set by the job's first round after the rebuild. The rebuild therefore keeps every group it carries below
  its cut; raised under it, the groups between the cut and the new horizon would be lost.
- The job runs every slice / 8, and no more often than once a minute. The slice is the largest of hour / day / week / month that
  is at most `keep / 4`, and the minute when `keep` is under four hours (a `90d` keep has a week slice; `7d`, a day; `2h`, a
  minute).
- It **never moves back** — not when the clock is stepped back, not across a crash, not when `keep` is made longer.
- Every read takes the horizon of the snapshot it reads, so a horizon that rises while a read runs does not change that read.
- It is reported as `horizon` in the policy response and the table detail, and to subscribers (below).

---

## Below the horizon

**No read returns a row below the horizon** — rows, `COUNT(*)`, aggregates, `GROUP BY`, `DISTINCT`, `ORDER BY … LIMIT`, joins,
named queries and subscription snapshots alike. A **null** time in the retention column counts as below it. `GET …/tables`'
`rowCount` is not a read: it is the stored count, and includes rows hidden below the horizon until they leave the table.

**`UPDATE` and `DELETE` match nothing below it**, so their counts are what a read shows. A row stored below the horizon is not
changed, counted, logged or sent to the table's queries.

### Writes below the horizon: `expiredRows`

A row written with a time below the horizon — or with an explicit `null` in a nullable retention column — is **accepted, not stored,
and counted**. It is left out at the write's entry, before any key check, log record, buffer or change event (one upsert case
differs, below), and the response says how many: `expiredRows` on the insert response, the named mutation's insert and upsert
results, and the bulk-load `:commit` response ([HTTP API](../reference/http-api.md#post-apidatabasesdbtablesnamerows)).
`expiredRows` is omitted when it is 0 — always, on a table without retention. A null in a `NOT NULL` time column is refused, as on
any table. A row that **omits** a nullable retention column is not counted: it is stored, hidden by every read and dropped by the
next flush.

```json
{ "rowsInserted": 1, "expiredRows": 2, "executionMs": 3, "token": "…" }
```

Accepting rather than refusing keeps a history load with a few old rows from failing whole; the count is how the write tells you a
row it acknowledged will never be read. `POST …/rows/batch` and the WebSocket write stream do not report `expiredRows`.

Three cases worth knowing:

- **An upsert that replaces a key a read returns** with a version whose time lies below the horizon (or is null) is **logged and
  buffered**, hidden by every read, and dropped by the next flush: the key is no longer returned (as after an `UPDATE` that moves
  the time below it). The row is counted in `rowsUpdated` (a visible key was replaced) **and** in `expiredRows` (its new version is
  never read). The two counts overlap only for such a row, so `rowsInserted + rowsUpdated + expiredRows` can exceed the rows sent.
  An upsert row below the horizon that replaces no visible key is left out before it is logged, like an insert's.
- **A key held by a row below the horizon** stays taken until that row leaves the table (the next flush while it is buffered; expiry
  once its segment lies wholly below the horizon). Until then a plain insert of the same key is refused as a duplicate, and the
  refusal says so ("the key is held by a row below the table's retention horizon"); an upsert replaces it. A `UNIQUE` value held by
  such a row stays taken the same way, but its refusal is the ordinary unique violation, with no such explanation, and only an upsert
  of the same primary key replaces the row. Freeing the key at once would mean deleting a row whose history the table's materialized
  queries keep.
- **A table whose transforms are routes** stores no row of its own, so its retention does not judge a routed row — the target table's
  horizon does. (A **tee** copy is the exception today: a row below the ingress table's horizon is left out before its tee copies are
  planned — **Known limitation (BL-1070)**.)

### How the rows leave: whole segments

A table with retention keeps each segment inside one **time slice** of its retention column: the live flush and the coalescers cut and
merge within slices, and the [bulk load](bulk-load.md#loading-a-table-with-retention) writes one segment per slice and never spills
such a table. After each horizon advance, **expiry** retires every segment whose newest time lies below the horizon — from the
catalog's facts alone, in one catalog batch per table, with no row read and **no data byte written**. The files go once no reader that
pinned the segment still holds it. A three-year history with a one-year `keep` lands as one segment per month and leaves a month at a
time; the remaining segments are never rewritten. A restart brings nothing back. Expiry (and the retirement of a segment with no live
row) leaves a segment alone while a pending deferred bulk-load pass still owes it to the table's queries, or while it is a bulk
segment not yet acknowledged by a majority of replicas, until that is settled (**Horizon, 0.5.0**).

The cost: more, smaller segments than the same table without retention (one per slice), and at most about one slice stored beyond
`keep` — the segment straddling the horizon stays, its old rows hidden, until all of it lies behind.

---

## Deleting everything before a time

A `DELETE` whose **whole** predicate is the table's first cluster column (a `Timestamp` or `Date`) below a time does not scan, log and
mask row by row:

```json
DELETE /api/databases/market/tables/trades/rows
{
  "database": "market",
  "where": { "and": [ { "column": "Ts", "op": "lt", "value": "2026-07-01T00:00:00Z" } ] }
}
```

The shape is exactly one condition, `lt` or `lte`, on the first cluster column, with no `limit`, `orderBy` or `returning`, on a
tabular table with no vector column that no foreign key references. Anything else — a second condition, a lower bound, a `limit`, an
edge table — takes the ordinary row path, unchanged. For `lte` the cutoff is the successor of the value at the column's resolution
(one tick for a `Timestamp`, one day for a `Date`), so "below the cutoff" is exactly the statement's rows. `rowsDeleted` is exact either way.

What it does depends on whether the table declares retention.

### With retention: an early expiry

The table's horizon rises to the cutoff — persisted, then published — and expiry retires every segment now wholly below it. One small
record is logged for the replicas (the table and the cutoff, a few dozen bytes) and no data byte is written. From then on a write below
the cutoff is `expiredRows`, as below any horizon.

- `rowsDeleted` is the number of rows a read showed below the cutoff.
- A cutoff **past the server's clock** takes the ordinary row path and installs nothing: raising the horizon there would make every
  row written until then expire at its write.
- A cutoff at or below the current horizon deletes nothing (`rowsDeleted: 0`).
- A materialized query over the table treats it as an expiry: nothing is retracted from its result.

### Without retention: a statement-time range delete

The statement deletes the rows that exist when it runs and **installs no horizon** — a row written later with an older time is
visible, as it always was. It costs metadata, not rows:

- **one log record** carries the predicate (a crash after it replays it against the rows logged before it, and nothing after);
- every segment wholly below the cutoff is **retired whole** in one catalog batch — no mask, no rewrite;
- the segments that straddle the cutoff get mask bits for their matching rows only, found from their row groups' statistics without
  reading a row;
- the write buffer's matching rows are masked in memory;
- a null time is not deleted;
- the table's materialized queries are **rebuilt** when the statement deleted anything.

### What it costs, measured

Illustration, not a promise: Horizon `S11`'s measurement (W-6) on 15.3 M Derive-shaped trades bulk-loaded in process (a Debug build,
one run each), deleting the third of them before a day — 5,100,074 rows:

| | Time | WAL | Data bytes written | Segments |
|---|---|---|---|---|
| With retention (`365d`) | 72.6 ms | ~40 B (one catalog record) | 0 | 31 of 555 retired whole (the months wholly below the cutoff); the rest hidden below the horizon |
| Without retention | 668 ms | 127 B (one record in its transaction) | 0 (masks apart: 1.9 MB of mask bits) | 7 of 216 retired whole (24,745 rows); 182 straddling segments masked for 5,075,329 rows |
| The row path before this train | refused for ever as one statement; narrowed by trading day, 754 k rows took 18.4 min and 2.0 GiB of WAL before failing | | | |

Without retention the table keeps its usual layout — a bulk segment per series bucket over the whole history — so nearly every
segment straddles the cutoff, and the statement pays in mask bits rather than log records or rewrites. With retention the table is cut
by time slices, so whole months leave.

### `TRUNCATE` on a table with retention

(**Horizon, 0.5.0**) `TRUNCATE` empties the table. Its materialized queries are rebuilt and, as every rebuild over the table
does, **keep their history below the cut** (the horizon rounded up to the query's bucket); the group straddling the horizon is carried
as it was (BL-1063), so it may still count truncated rows from between the horizon and the cut. The groups at or after the cut are
recomputed from the empty table, so they are gone. An unfiltered `DELETE` instead retracts exactly the visible rows from the results.
Use `TRUNCATE` to empty the table and keep the history; no statement also clears a result's history — drop the query and create it
again.

---

## What a subscriber sees

A subscriber is not sent one event per expired or deleted row. Instead:

- a snapshot of a table with retention carries the table's `horizon` and `horizon_column` on `snapshot_complete`, and holds no row
  below it;
- each published horizon advance — the clock's, or an early expiry — sends one `horizon` message;
- a delete before a time on a table **without** retention sends one `range_delete` message.

The client drops what it holds below the time. Both SDKs do it for you (`evt.Removes(row)` in `Aouda.Client`,
`applyNotice(rows, event)` in `@aouda/client`). The contract — ordering, resume, filters, conflation, old clients — is in
[Real-time Streaming: Horizons and range deletes](real-time.md#horizons-and-range-deletes).

---

## Replicas

- A replica learns a retention declaration from the replicated policy — declared at create or later — and **advances its own horizon
  on its own clock** (a horizon the clock moves is not logged), so its horizon can differ from the primary's by the two clocks. (A
  windowed result's horizon is the primary's instead: see [Materialized Queries](materialized.md#window-expiry).)
- A table created by declarative schema apply (`/schema/apply`) reaches replicas and point-in-time restores like one created by
  `POST /tables`, with the retention declared with it (**Horizon, 0.5.0**).
- A range delete on a table without retention is replicated as its one log record, and reaches only a replica's **buffered** rows:
  rows below the cutoff in the segments the replica got from its checkpoint image stay visible there until its next image — the same
  as a `TRUNCATE` and a keyed delete today (**Horizon, 0.5.0**).
- **An early expiry reaches the replica** as its one logged record: the replica raises its horizon to the cutoff (the higher of the
  two), hides the rows below it at once and expires its segments, as the primary did. One that arrives while a rebuild on the replica
  holds the table's horizon is applied by the replica's next advance round after the rebuild, instead of failing after 30 s
  (**Horizon, 0.5.0**).
- An engine that is not a replica logs every horizon it holds (a table's retention, a windowed result's) once when it opens, so a
  horizon saved just before a crash still reaches replicas and point-in-time restores (**Horizon, 0.5.0**).

See [Replication and Clustering](replication.md).

---

## Deleting in general

These hold for every table, with or without retention (**Horizon, 0.5.0**). Row deletes keep their model — a deletion mask per
segment, read through — and lose four wastes:

- **`TRUNCATE` retires the table's segments** instead of writing a mask over every row of every segment. It is still one log record and
  still atomic for readers, and the disk is freed at once. (A segment another mechanism owns at that instant, such as a flush in
  progress, keeps the old mask path.)
- **A segment with no live row is retired whole** by the hot or cold coalescer's next pass — one catalog batch, nothing rewritten.
  Before, it stayed on disk and in every scan until some merge happened to pick it up.
- **A cold segment with at least 25 % of its rows deleted is rewritten alone within one coalescer tick, whatever its size.** Before,
  only segments under 65,536 rows were ever merged, so a large bulk-loaded segment kept its deleted rows for ever. (Measured: 200,000
  rows at 30 % deleted, rewritten in one tick, 1.2 s, into 140,000; at 20 %, left alone.) That holds for a segment whose metadata is
  resident; one not loaded is judged when it is next loaded. On a table with a horizon only a segment
  wholly at or after the horizon is rewritten; one reaching below it is expiry's to drop whole.
- **A scan skips a segment, or a row group, whose rows are all deleted** — no page is loaded.

See [Storage and Persistence](storage.md#deleted-rows-and-retired-segments-horizon-050) and
[Hot/Cold Storage](hot-cold.md#24-availability-status-implementation-honesty).

---

## Known limitations

Current behaviour, each with its card in the `aouda` repository's backlog:

- **Known limitation (BL-1063):** every rebuild of a materialized query over a table with retention, whatever caused it — a deleted
  minimum or maximum, a bulk load folded by the rebuild rather than incrementally, a `TRUNCATE`, a `:refresh`, a restart's rebuild —
  recomputes every group at or after the cut `K` (the horizon rounded up to the query's bucket) and carries every group below it, the
  one straddling the horizon included, as the old result held it (its rows below the horizon are gone, so it cannot be recomputed). A
  change to a carried group that only a rebuild picks up is therefore not reflected in it, its count and sum included. A straddling
  group exists only for a bucket coarser than a minute (an hour, day, week, month or year) when the horizon is not on its boundary. A
  result that is behind when it is rebuilt — it had not yet absorbed a change, such as a bulk load whose deferred pass had not run —
  loses below `K` whatever it had not absorbed. A query's **first** build carries nothing: it computes every group from the rows the
  table holds, and its straddling group counts only the rows at or after the horizon.
- **Known limitation (BL-1071):** a foreign key into a table with retention is checked at write time only — a parent row expires
  under its children, and a parent row stored below the horizon still satisfies the check.
- **Known limitation (BL-1069):** on a **partitioned** table with retention the live flush does not yet cut segments by time slice or
  leave out rows below the horizon (every read still hides them; expiry drops them later).
- **Known limitation (BL-1059):** rows below an early expiry's cutoff in segments that straddle it — and rows below the horizon in
  segments written before retention was declared — are hidden, not reclaimed, until the whole segment falls behind the horizon.
- **Known limitation (BL-1060):** only queries that split their groups by the retention column may read a table with retention;
  `latestPerKey`, `firstPerKey` and `filter` over it are refused.
- **Known limitation (BL-1061):** a read of a table with retention is not routed to a materialized result.
- A `TRUNCATE` sends subscribers no notice.
