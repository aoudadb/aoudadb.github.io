---
title: "Studio"
nav_order: 15
parent: "Guides"
---

# Aouda Studio — Web Management Console

_Domain: Studio UI features, data explorer, cluster management, admin operations_
_Status: Studio 0.16.0 (Principals: Access and Declaration pages); behaviour marked **next train** is on the phase branch and not in a release_
_Primary Phases: P5, P6, P9, P12, P16, P34, P36, P37 (thin), P39, Principals, Operability_
_Repo: `aouda-studio` (Next.js / React)_

---

## 1) What This Covers

Aouda Studio is the web management console for Aouda. It provides:

- **Data Explorer** — browse, query, filter, edit, and navigate data (admin listener)
- **Schema Management** — view/edit tables, columns, ERD diagrams, insert-time compute
- **Named Artifacts** — catalog from `schema.export()`, test/subscribe by name, structured authoring via schema apply
- **Cluster Management** — node operations, topology, backup, configuration
- **Admin Console** — monitoring, access (principals, roles, sign-up, credentials, sessions, audit log), the declaration the server runs on, streaming (table + named query), bulk-load job monitor
- **Hub Integration** — team server management, authentication, multi-server switching
- **AI Integration** — natural language cluster operations

**Listener.** Studio always connects to the **admin** listener (`GET /api/databases` is the probe). Pointing it at the data-plane listener yields 404, not “no auth”. Studio is an operator client: it connects with a key or a session of a `_serverauth` principal. A browser app on the data-plane holds no key at all. See [Direct client access](direct-client-access.md).

---

## 2) Start Here

| I want to... | Go to |
|---|---|
| Access Studio instantly (no install) | §10 Hosted Studio at `studio.aouda.com` |
| Connect to a server from Studio | §10.1 Connect-to-Server Dialog |
| Browse and query table data | §3 Data Explorer |
| Run join or aggregate queries | §4 Query Worksheet |
| Manage cluster nodes | §6 Cluster Management |
| View backups and restore | §7 Backup Management |
| Manage table schemas and columns | §5.5 Schema Management |
| Toggle auto-increment on a column | §5.5 Toggle AutoId |
| Author unique / derived / checks / `call` / route / tee | §5.5 Insert-time compute |
| Catalog and test named queries / mutations | §5.6 Named Artifacts |
| See who may do what, and mint a key | §13 Access |
| See what the server's declaration file says, plan a reload, export it | §13 Declaration |
| Read a formula column, or ask why its cell has no value | §3 Formula columns |
| See a table's retention | §5.5 Storage Policy |
| Subscribe by named-query name | §13 Streaming Explorer |
| Seed an explicit auto-increment ID on Add Row | §5.5 Identity-insert |
| Manage branches | §5 Branches |
| Connect Studio to servers | §9 Hub Integration |
| Deploy Studio (self-hosted / Docker) | §11 Deployment |
| Install Aouda interactively (Aouda.Setup) | §12 Aouda.Setup Installer |

---

## 3) Data Explorer

### Table Browser

- Left sidebar: database selector, table list with row counts
- Main area: paginated data grid with virtual scrolling
- Cell editing: click to edit, inline validation, save on blur. A pending edit belongs to the row's primary key, so a reload, a sort or a delete that moves the rows does not move it onto another row (**next train**)
- An `Int64` or `UInt64` cell is a text cell: a value past 2^53 keeps its digits through an edit, the JSON export and a bulk expression operand (`$inc`, `$mul`, …), and text that is not a whole number in the type's range is refused with a message instead of being written as `0` (**BL-1111, next train**)
- Row operations: insert, duplicate, delete with confirmation

### Filter Builder

Visual filter builder with all engine operators:

| Operator | UI | Wire Format |
|----------|----|-------------|
| `=`, `!=`, `>`, `>=`, `<`, `<=` | Value input | Standard comparison |
| `IN` / `NOT IN` | Multi-value chip input | Array values |
| `LIKE` | Pattern input with `%` wildcard | String pattern |
| `IS NULL` / `IS NOT NULL` | Toggle (no value input) | Null check |
| `BETWEEN` | Two value inputs (low/high) | Range check |

Filters sync bidirectionally between the visual builder and the query bar text representation.

### Sorting and Pagination

- Click column header to sort (ascending → descending → none). With a column projection, the header you click is the column that sorts; before, it sorted the column at that position in the table (**BL-1246, next train**)
- `ORDER BY` in query bar
- `LIMIT` / `OFFSET` with page navigation
- Server-side count via `POST .../query/count` (safe for large tables)

### Bulk Mutation Panel

In the table data view, the **Bulk Mutation** tab provides a guided multi-step flow for
running WHERE-based updates, deletes, and truncations from the browser:

| Step | What you do |
|------|-------------|
| 1. Operation | Choose UPDATE, DELETE, or TRUNCATE |
| 2. WHERE builder | Build a predicate using the visual filter builder (same as the read query builder) |
| 3. SET editor (UPDATE) | Per-column literal or expression (`$inc`, `$mul`, `$dec`, `$div`, `$col`, `$ifNull`, `$upper`, `$lower`, `$trim`, `$concat`, `$substring`, `$round`, `$roundTo`, `$cast`) |
| 4. LIMIT (DELETE) | Optional — enables bounded rolling deletes with `hasMore` |
| 5. RETURNING | Multi-select column checklist for the response payload |
| 6. Preview | Runs `COUNT(*) WHERE …` and shows how many rows will be affected |
| 7. Confirm | Confirmation dialog: _"You are about to UPDATE/DELETE N rows. This cannot be undone."_ |
| 8. Results | Shows `rowsUpdated`/`rowsDeleted`, execution time, and RETURNING rows |

TRUNCATE needs an unconditional `delete` statement on the table ([Bulk Mutations §4](bulk-mutations.md#4-truncate)).
Studio does not check it: it asks you to type the table name to confirm, sends the request, and shows the server's refusal.
A delete limit that is not a whole number above 0 is refused in the panel (Execute stays off and the panel says why); before, `0`
or `-5` read as "no limit" and deleted every matching row (**BL-1111, next train**). A failed bulk delete reports "Deleted k of n",
refreshes the grid and keeps the dialog on the rows not yet deleted, and a batch delete ordered descending is sent descending, so
"delete the newest 10" deletes the newest (**BL-1111, BL-1838, next train**).

See [Bulk Mutations guide](bulk-mutations.md) for the full API reference.

### Relationship Navigation

- Foreign key columns are clickable links
- Navigate to related record detail view
- Breadcrumb trail for navigation history

### Entity Detail View

Per-record detail page with:
- All fields displayed and editable
- Related records listed by foreign key
- Delete with confirmation

### Formula columns (**next train**)

An [`Expression` column](formulas.md) holds one formula per row. Studio shows and explains one; it has no formula editor, so it does not create or edit one ([§5.5](#expression-columns)).

- **The formula cell** reads as the formula's text (`Revenue - Cost`, `coalesce(a, 0)`; cut at 200 characters; a copy of the cell is the formula's whole JSON), with an `fx` header icon labelled "Formula". A row whose formula is null (an input row) shows `input`, not `NULL`. The cell is read-only.
- **The driven cell.** The column an Expression column drives is **read-only in a formula row**: the server refuses a write there with `FORMULA_VALUE_WRITE_REFUSED`. In an input row it is edited like any cell, and in a row read without the Expression column (a projection) Studio cannot tell, so the server's refusal answers. A formula row's driven cell that holds no value reads **no value — why?**.
- **Why.** A click on a formula cell, or on a formula row's driven cell, opens a read-only dialog with the answer of [`explain`](formulas.md#a-cell-that-cannot-be-computed-null-and-explain): the formula, each cell it reads with its value now (or "not readable by this account", or "(itself a formula)"), the reason a cell has no value (a division by zero, an overflow, …), the stored value and the cells that read this one. A row with no formula says it is an input row. Studio asks the server only when you click, with the row's full primary key (exact past 2^53; a `Date` key as its day); a failed call shows its code and message.
- **Forms.** The add-row form and the bulk SET editor never offer a formula column, because a new row is an input row. The query center shows a formula as its text too, and its edit mode offers no field for one.

### Array columns (**BL-035, 0.9.0**)

(**BL-035, 0.9.0**) Studio shows an [array column](array-columns.md) in the grid, the query worksheet, the query centre, the named-artifact
test panel and the record view as **its first five elements, and the count when there are more** (`[0.5, 0.52, 0.53, 0.55, 0.56, …] · 400 values`);
a null stays `NULL` and an empty array is `[]`. An **expand** opens a dialog that lists every element (paged, with the index) and
copies the whole value as JSON. Copy, CSV and JSON export write the wire's JSON form (`-0` kept, a `Byte[]` as base64, `Int64`
digits). An array column is **read-only** in Studio: no edit, no field in the add-row form (a row added from Studio holds null
there, so on a NOT NULL array column the add is refused), and it cannot be a filter, sort, group-by, aggregate, join key or the target of a bulk SET. The schema editor offers the
six types when you create a table or add a column, and the alter-column dialog does not change an array column's type. This is
the Studio release of this train, which bundles the matching `@aouda/client`; it needs a server of the same train.

---

## 4) Query Worksheet

Multi-purpose query workspace for advanced operations.

### Join Query Builder

Build multi-table joins visually:
- Pick join type: INNER, LEFT, RIGHT, FULL OUTER, CROSS
- Select join key columns (supports multi-column keys)
- Post-join filters on prefixed column names (`Table.Column`)
- Chained joins (up to 8 tables)
- Results in data grid with prefixed column headers

### Aggregate Query Builder

- Aggregate functions: SUM, MIN, MAX, COUNT
- GROUP BY column selection
- Combined with WHERE filters
- Results as grouped data grid

### Filter Groups and the SQL Preview

The worksheet's filter is a list of **groups**: the groups are joined by **OR**, and the conditions inside a group by the group's connector, a button that cycles **AND**, **OR** and **OR GROUP** (which starts a new group). The **SQL PREVIEW** is what runs, and so is the column projection you chose (**Studio BL-QUX-01, BL-QUX-03, next train**; before, OR between groups was not sent and the projection was not executed, and the page said so). The wire has no OR of AND groups, so Studio sends the filter as an AND of OR clauses; a filter that works out to more than 64 clauses (or 256 comparisons) is refused with a message that says to simplify it, and never run as an AND of everything. A condition with nothing to say yet (an empty `IN` list, a `BETWEEN` with no bounds) is neither sent nor shown in the preview.

### Expression SELECT (Computed Columns)

In the Projection section of the Query Worksheet, click **+ Computed column** to add a
server-side computed column:

1. Enter an alias name.
2. Select an expression type from the dropdown (arithmetic, coalesce, conditional).
3. Configure the operands (column references or literal values).
4. Run the query — computed columns appear as additional columns in the result grid.

Computed columns are evaluated server-side per row; they are not stored. See
[Bulk Mutations guide §8](bulk-mutations.md#8-expression-select--computed-columns).

### Free-Form Queries

Query bar accepts structured query syntax that maps directly to `@aouda/client` query builder methods. Supports all filter operators, sorting, pagination, projection.

---

## 5) Branches

Full branch management interface:

| Operation | UI |
|-----------|-----|
| List branches | Table view with name, creation date, status |
| Create branch | Dialog with name input |
| Delete branch | Confirmation dialog |
| Diff | Side-by-side view of changes between branch and main |
| Merge | Merge dialog with conflict indication |
| Branch-scoped query | Select branch context, then use data explorer normally |
| Branch-scoped insert | Insert data on a specific branch |

---

## 5.5) Schema Management

Studio's schema management surface lets you inspect and evolve table schemas entirely from the browser — no CLI or schema file required.

### Accessing the Schema View

Navigate to a table, then open the **Schema** tab. The schema view has these panels:

1. **Columns table** — all columns with type, nullability, key role, reference, auto-increment, unique, and derived.
2. **Storage Policy** — per-table temperature policy (`Auto`, `HotOnly`, `ColdPreferred`) and, read-only, the table's retention.
3. **Who can reach this table** — the statements that name the table (see [§13 Access](#access)).
4. **Checks / route / tee** — write-time predicates and insert routing (see below).
5. **Durability Overrides**, then **Keys**, **Relationships (outgoing)** and **Indexes**.

Who may read or write a table is not a setting of the table: it is in the statements of principals and roles ([§13 Access](#access)). On a database whose schema the declaration file owns, the editing controls are disabled and badged with the file and the pointer ([§13 Declaration](#declaration)).

### The Columns Table

Each row in the columns table shows:

| Column | Description |
|--------|-------------|
| **Name** | Column name |
| **Type** | Aouda data type (e.g. `Int64`, `String`, `Timestamp`); an Expression column reads `Expression → drives <column>` (**next train**) |
| **Nullable** | Yes / No |
| **Key** | `PK (1)` for primary key with ordinal, `Partition`, `Cluster`, or `—` |
| **Reference** | Foreign key target in `→ table.column` format, or `—` |
| **Auto-increment** | `Yes` badge when `isAutoIncrement = true`, otherwise `—` |
| **Unique** | Toggle for non-PK, non-auto-increment columns (`unique: true` in `aouda.schema.json`) |
| **Derived** | Write-time expression; callers must not send a value (`TRANSFORM_DERIVED_READONLY`) |
| **Actions** | Per-row menu (see below) — shown only when the schema view is editable |

### Column Actions Menu

Click the `⋮` icon on any column row to open the actions dropdown. Available actions depend on the column:

| Action | Availability | What it does |
|--------|-------------|--------------|
| **Rename** | All columns | Opens a dialog to enter a new column name and apply it via the schema engine |
| **Toggle AutoId** | Integer columns only (`Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`) | Toggles `autoIncrement` on or off — see below |
| **Delete** | All columns | Opens a confirmation dialog and drops the column (destructive — cannot be undone) |

### Toggle AutoId — Enabling or Disabling Auto-Increment

The **Toggle AutoId** action changes the `autoIncrement` flag on an existing integer column. This avoids the "drop column and re-create" pattern that was previously required.

**How it works internally:**

Studio uses the schema export → patch → apply pattern:
1. Exports the full current schema document.
2. Flips `autoIncrement: true/false` on the target column in the document.
3. Calls `POST /api/databases/{db}/schema/apply` with the patched document (no `allowDestructive` flag — this change is never destructive).

**The Toggle AutoId dialog:**

When you click **Toggle AutoId**, a confirmation dialog opens showing:

- The target column and table names.
- The direction of the change:
  - **Manual → Auto** — the server will manage future inserts for this column.
  - **Auto → Manual** — you must supply explicit values for this column going forward.
- A yellow warning note when enabling auto-increment: _"The counter will recover from the MAX existing value in this column on first insert."_ This means the counter does not start at 1 — it starts at `MAX(existing values) + 1`, so manually-inserted IDs are never overwritten.

Click **Apply** to confirm, or **Cancel** to close without any change.

**After a successful toggle:**

- The **Auto-increment** column in the columns table updates immediately (the `Yes` badge appears or disappears).
- Studio invalidates and refetches the schema from the server so the displayed state is always current.

**Errors:**

If the apply fails (e.g. the server rejects a non-integer column, or the server has `WRITE_NOT_ALLOWED`), the error message appears inside the dialog. The dialog stays open so you can read the error and decide how to proceed. Your schema is never left in a partial or corrupted state — the apply is atomic.

**What columns are eligible?**

Only columns whose type is one of: `Int16`, `Int32`, `Int64`, `UInt16`, `UInt32`, `UInt64`, `Byte`. The "Toggle AutoId" menu item does not appear for `String`, `Double`, `Timestamp`, `Decimal`, `Guid`, or any other non-integer type. The server enforces the same constraint as an additional guard.

**Identity-insert on Add Row:** When the table has at least one auto-increment column, Add Row shows an **identity-insert** checkbox. Unchecked (default) omits the flag; auto-increment columns stay off the form and the client sends the `0` sentinel. Checked: auto-increment columns appear as required numbers; form `"0"` is stored as numeric `0`; the insert is `insert(payload, { identityInsert: true })`. This does **not** flip Toggle AutoId. Derived columns stay omitted. See [Getting Started — Seeding explicit IDs](../getting-started/index.md).

Toggle AutoId remains the UI for permanently switching Auto ↔ Manual on the column.

### Adding a Column

Click **Add column** above the columns table to open the Add Column dialog. Fill in:
- Column name
- Type (dropdown)
- Nullable flag
- Optional: primary key order, auto-increment, references

`Expression` is not in the type list (see [Expression columns](#expression-columns)).

### Renaming a Column

Click `⋮` → **Rename** on the column row. Enter the new name and click Rename. The server applies the rename via the catalog.

### Deleting a Column

Click `⋮` → **Delete** on the column row. Confirm by typing the column name in the confirmation dialog. **This operation is permanent and cannot be undone.** All data in that column is lost.

### Table-Level Actions

Above the columns table, three table-level action buttons are available:

| Button | What it does |
|--------|-------------|
| **Add column** | Open the Add Column dialog |
| **Rename table** | Rename the table across the catalog |
| **Delete table** | Drop the table and all its data (confirmation required) |
| **Generate Types** | Generate TypeScript type definitions from the current schema |
| **Ask AI** | Open the AI schema assistant (requires an LLM provider's key in Studio preferences) |

### Storage Policy

The Storage Policy card shows the current `storageTemperature` for the table:

| Value | Meaning |
|-------|---------|
| `Auto` | Engine decides hot vs. cold based on access recency and memory budget |
| `HotOnly` | Segments always stay in memory |
| `ColdPreferred` | Segments move to disk as soon as possible |

Change the value in the dropdown and click **Save** to apply the policy change. This calls `POST /api/databases/{db}/tables/{table}/policy` directly (imperative DDL, not via the declarative schema apply path).

**Retention** (**next train**) is shown under the temperature, read-only: "Keeps 90d — rows before 2026-08-27 09:00 UTC are gone" (the horizon is always UTC), or "None — every row is kept". A retention is declared in the schema file and changed there; it can be changed, never removed ([Retention](retention.md)). The table list's per-table summary carries no retention, so the page header of a table does not show it (**BL-1885, next train**).

### Expression columns

An [`Expression` column](formulas.md) is declared in the schema file or with the SDK. Studio has no formula editor, so it does not create one: the Add-column dialog and the Create-table form say so, and `Expression` is not a type they offer. The schema view lists such a column as `Expression → drives <column>` and offers only **Rename** and **Delete** on it; the server refuses a change of its type, default, unique or derivation. How its cells read in the grid is in [§3 Formula columns](#formula-columns-next-train). (**next train**)

### Schema Diff View (Migrations Page)

When you apply a schema change from the **Migrations** tab (Settings → Schema → Migrations), Studio shows a **Schema Diff View** before applying. Each planned change is color-coded:

| Color | Meaning |
|-------|---------|
| Green | Additive — safe change (e.g. `Add column`, `Add table`) |
| Red | Destructive — requires `allowDestructive` opt-in (e.g. `Drop column`, `Drop table`) |
| Blue | Alteration — safe column-level modification (e.g. `Toggle auto-increment`) |
| Muted grey | Other safe change (e.g. `Update policy`, `Update durability`) |

When the diff includes `UpdateColumnAutoIncrement` changes, the summary line shows `N column(s) altered` alongside the total change count.

Named-query / named-mutation / materialized-query changes render as human labels (create / replace / drop). **BL-174:** if the pasted desired JSON **has** a `materializedQueries` key — including `{}` — that map is desired state and **live MQs not listed will be dropped** (empty `{}` drops all; apply requires Allow Destructive). If the key is **omitted** or `null`, live MQs are left unmanaged and Studio does **not** warn-as-drop. See [Schema CI/CD](schema-cicd.md).

### Opening a table to the browser

A table has no switch for it (**BL-1464, 0.16.0**). A browser runs named queries and mutations only, and may run one when `anonymous`, `signup` or
the user's role holds an `execute` statement for it. Write the statement in **Settings → Access**, or in `aouda.json` when the declaration owns the
object; put its `where` in the same change for anything a user owns.

Details: [Direct client access](direct-client-access.md).

### Insert-time compute — unique, derived, checks, `call`, route / tee

Persisted through schema **export → patch → apply** (same pipeline as other schema edits). HTTP GET table does not always echo these fields; Studio reads them from `schema.export()`. Contract: [Insert-time transforms](insert-transforms.md).

| Control | Where | Notes |
|---------|--------|------|
| **Unique** | Columns table | Not on PK / auto-increment. Duplicates rejected across HRA, hot, and cold. |
| **Derived** | Columns table → Derived… | `ScalarExprNode` at write time. Add Row leaves the field read-only. Closed `call` allowlist: `upper`, `lower`, `trim`, `concat`, `substring`, `round`, `roundTo`, `cast`. |
| **Checks** | Table checks card | Named predicates; first failing row fails the **whole batch**. |
| **`call` on SET** | Bulk Mutation SET editor + computed columns | Same allowlist. Unknown `fn` cannot be chosen. |
| **route / tee** | Schema transform card | One kind per table. Mix of route+tee or a cycle fails apply (`SCHEMA_TRANSFORM_CYCLE`). Unmatched route is `TRANSFORM_ROUTE_UNMATCHED` (error, not a silent fallback). Tee copies to matching targets while ingress still stores. |

### 5.6) Named Artifacts

Sidebar: **SCHEMA → Named Artifacts**. Hidden with SCHEMA for Data Owner (correct).

Named queries and named mutations live in `aouda.schema.json`. Identity is the **unique name**. Inventory is `schema.export()` only. There is **no** runtime `POST …/register`. Omitting a name deletes the definition (one Delete).

| Action | What Studio does |
|--------|------------------|
| Catalog | `schema.export()` — name, deprecated, table, projection, cost `1+joinCount` |
| Test | Name-only `namedQueries.execute` / `batch` (cap 32) / `namedMutations.execute`. Deprecation is a warning, not a failure. Mutations always run as **invoker** (no definer / `runAs`). |
| Author | Structured wizard (table, projection, AND where, joins ≤ 3, required limit cap). Identifier positions are dropdowns — parameters cannot name tables, columns, or operators. Persist via export → patch map → diff → apply. |
| Edit | Starts from the stored definition and writes back every member you do not change exactly as stored; saving without edits sends the stored definition unchanged. A member the wizard has no field for (`count`, `aggregates`, `groupBy`, `perKey`, `orderByChoices`, `freshness`, `batchParam`), or cannot show exactly (a where with `or` / `groups` / `ignoreCase` / `whenParamPresent`, a join's `where` or multi-column keys, a nested expression, more than one sort column, a parameter's `serverTime`), is listed under **Kept exactly as stored** with its JSON and is read-only there: change it in the schema file and apply it. (**BL-1470, 0.16.0**) |
| Parameter **required** | Ticked by default, as the server reads an omitted `required` as `true`; unticking writes `"required": false`. (**BL-1470, 0.16.0**) |
| Generate Types | Optional Args/Row types. Execute and subscribe use the schema name as a string. |

SQL-ish authoring (ADR 0040 D-24) is not in Studio. Full contract: [Named queries](named-queries.md).

---

## 6) Cluster Management

The **CLUSTER** section (**Nodes**, **Replication**, **AI Ops**) is shown on a node that is not standalone, to a credential that may administer ([What Studio Shows to Whom](#what-studio-shows-to-whom)). An operation acts on **the node Studio is connected to**, and runs when you press the button: there is no confirmation dialog.

### Cluster Operations

| Operation | Where | Server API |
|-----------|-------|------------|
| Add node | **Nodes → Cluster operations**: *Replica set name*, *Role* (`secondary` or `witness`), *Primary address*, *This node address*, then **Add node**: this node joins that replica set | `POST /admin/cluster/join` |
| Remove node | **Nodes → Cluster operations**: **Remove this node** leaves the cluster | `DELETE /admin/cluster/leave` |
| Drain | **Nodes**, the **Drain** button on a member's row (off for a member already draining) | `POST /admin/cluster/drain/{addr}` |
| Promote | **Replication → Status**: **Promote this node** asks for an election | `POST /admin/cluster/promote` |
| Failover | **Replication → Status**: **Trigger failover** steps this primary down | `POST /admin/cluster/failover` |
| Timing | **Replication → Cluster configuration**: *Heartbeat interval (ms)* and *Election timeout (ms)* are editable (**Save cluster timing**); the replica set name, the members and this node are not | `PATCH /admin/cluster/config` |

### Cluster Topology Visualization

**Nodes** shows a **Topology** diagram with one card per member, the primary first and witnesses last (a witness has a dashed border):
- The role badge, **This node** and **Draining** badges, and the member's address
- **Lag**, from the member's per-database lag in `GET /admin/replication/status` (`members`), the largest of its databases in bytes, with a count of the databases whose lag is unknown. Studio no longer takes lag from the topology, which carries none (**BL-1477, next train**)
- **Hidden from reads** and **Not a read candidate**, from the topology

A member the server has no WAL position for, or no primary position to measure against, shows **Lag: unknown** (it showed `0 B`). The status needs `manage` on `server` and the topology does not: when the status cannot be read the cards stay and say **Lag: not available**, where the page said "No members in topology" (**BL-1477, next train**). There are no connection lines between the cards, and no healthy / lagging / disconnected state: a lag of 1 MiB or more is shown amber and 10 MiB or more red.

Below the diagram the **Cluster nodes** table lists each member's address, role, temperature profile, hidden, read candidate, drain state and an **Open** link. **Replication** adds the node's own **Status** (role, primary, whether it can accept writes, fencing token), **Replication placement** (read candidates and members), **Per-database lag** (WAL position, primary position, lag in bytes, this node's own) and **Coverage** (per-table replication subscriptions).

### Node Detail View

**Nodes → Open** on a member opens **Node details** for that address. It refreshes every 5 seconds:
- **Cluster member snapshot**: role, whether it is this node, read candidate, hidden (from the topology)
- **Runtime node info**: version, node id, uptime, process id, machine, OS, CPU count, working set and GC heap, and "Disk usage: N/A". These come from `/admin/node`, so they are **the connected node's**, whichever member's page it is
- **WAL and lag snapshot**: this node's own per-database view, from `perDatabaseLag`, again the connected node's
- **Member lag** (**BL-1477, next train**): the member's own per-database WAL position and lag from the status `members`, with "unknown" where the server has no primary position. "Unknown" also covers a member the server has not heard from; "Not available" means the status lists no such member or this account may not read it

---

## 7) Backup Management

The **Backups** page (`/admin/backups`) below is the planned Studio surface (**BL-332, next train**).
Released Studio (0.16.0) lists backups, triggers one, and restores an **exact** backup on one click, with no confirmation, from the
list or from its recovery timeline of backup points; it saves the schedule through `PATCH /admin/config` and has no point-in-time
restore, retention or prune. The server's own point-in-time restore is available over HTTP, both SDKs and `aouda backup restore`
([Backup and restore](backup.md)).

| Feature | UI |
|---------|-----|
| Trigger backup | Button; the answer names the backup and how long it took. A call that times out is shown as "may still be running", never as failed |
| Available backups | Table of backup **sets** (one set covers every database, the auth database first): id, state badge — `complete`, `incomplete` (a member failed; **not restorable**: "take a new backup") or `refused` (the reason, with any database name masked if it is key-shaped) — a `PITR base` / `no PITR` badge, the databases it holds, a **Restore** button (exact restore; disabled for an incomplete or refused set) and a **Detail** row |
| Set detail | Per database: the cut time (UTC), the redo-start position `R` and the WAL position `P`, the manifest and whether the database is a point-in-time base; members with no manifest and manifests the set record does not name are listed |
| Restore | Select backup → confirmation → progress indicator. The confirmation says: every database is replaced and restarted; anything committed after the backup is discarded; **users, roles and keys return to that time too — a key created after it stops working**; the page reloads its data. Nothing is sent until the box is ticked and **Restore** pressed |
| Point-in-time restore | A **base backup** (the default: the newest backup at or before the target, chosen by the server, or a specific one) and a **target time**, with its UTC equivalent shown; the page states the window — from the oldest backup that can be a base to now — and the server refuses a time its WAL archive cannot reach. A target before the chosen backup is refused before anything is sent. The same confirmation, saying "after the target". A restore lands on a commit boundary ([what a point-in-time restore returns](backup.md#4-what-a-point-in-time-restore-returns)) |
| Schedule | Cron expression, destination and incremental flag, saved with `PUT /admin/backup/schedule` — it keeps the retention policy |
| Retention | Keep last N backups, keep N days, PITR window (whole days). **Save replaces the whole policy**; with none, "every backup is kept" — nothing is pruned by default. The newest restorable backup is always kept, and so is any backup the point-in-time window still needs |
| Prune | **Preview** first (nothing deleted): each backup's outcome and the rule that decided it, and per database the backups and blobs deleted and bytes reclaimed; then a confirmed **Prune**, which shows what the server *actually* deleted (it computes the plan again when it executes) |
| Restore onto a new server | Static help, no control: the server does not restore into another directory over HTTP. Start a fresh server with the same archive destination and restore the set from this page, or restore offline with `aouda backup restore <set id> --from <destination> --to <empty data dir>`. S3 credentials are the server's configuration and are never shown; see [Restore to a new host](restore-to-a-new-host.md) |
| Errors | Every backup error is shown with its code, its message and the server's `remedy` text; a **Retry** button for `409 BACKUP_IN_PROGRESS` and for a timed-out call that is safe to repeat |

Studio's AI tools and the MCP `aouda_backup_restore` tool restore an **exact** backup only; point-in-time restore, retention and prune are
operator acts and are not offered to an agent. After a restore Studio discards its data clients' consistency tokens: a token from before
the restore is ahead of the rewound node, and every read carrying it would answer `409 TOKEN_UNSATISFIED` until it is discarded.

---

## 8) Configuration Editors

### Memory Budget Editor

Visual gauge showing current usage vs. budget. Slider or numeric input for immediate adjustment. Changes take effect without server restart.

### Cluster Configuration

**Replication → Cluster configuration** (a cluster node): the replica set name and this node are shown read-only; the heartbeat interval and the election timeout are editable ([Cluster Operations](#cluster-operations)).

### Hot/Cold Policy Editor

Per-table storage temperature policy editor. Controls when data migrates between hot (in-memory) and cold (on-disk) storage.

### Database Options

- Max memory per database
- Replication mode
- Default policies

### Server Configuration View

Read-only display of all server configuration. Mutable settings are editable inline.

### Replication Settings

- Replication modes
- Read preference defaults

---

## 9) Hub Integration

### Two Operating Modes

| Mode | How to Activate | Behavior |
|------|----------------|----------|
| Direct | Set `NEXT_PUBLIC_AOUDA_URL` (build-time) or `AOUDA_STUDIO_DEFAULT_SERVER` (runtime) | Single server, no login required |
| Hub | Set `NEXT_PUBLIC_HUB_URL` (build-time) | Login to Hub, browse org servers, switch between them |

### Environment Variables

Studio uses two categories of environment variables:

**Build-time variables** (`NEXT_PUBLIC_*`) — baked into the JavaScript bundle at `next build`. Must be set before building the Docker image or running `npm run build`.

| Variable | Purpose | Default |
|----------|---------|---------|
| `NEXT_PUBLIC_AOUDA_URL` | Default server URL (fallback when `AOUDA_STUDIO_DEFAULT_SERVER` is not set at runtime) | `http://localhost:5000` |
| `NEXT_PUBLIC_HUB_URL` | Hub API URL; when non-empty, enables Hub login mode | `""` (disabled) |

**Runtime variables** — read by the Next.js server process at startup. Can be set on the Docker container without rebuilding the image.

| Variable | Purpose | Default |
|----------|---------|---------|
| `AOUDA_STUDIO_DEFAULT_SERVER` | Default Aouda server URL (takes precedence over `NEXT_PUBLIC_AOUDA_URL`) | — |
| `AOUDA_STUDIO_HUB_URL` | Hub API URL at runtime | — |
| `AOUDA_STUDIO_THEME` | UI theme: `system`, `light`, or `dark` | `system` |
| `AOUDA_STUDIO_CONFIG_PATH` | Path to `aouda-studio.config.json` | `./aouda-studio.config.json` |

**Resolution order** for `defaultServer`:
1. `AOUDA_STUDIO_DEFAULT_SERVER` (runtime env)
2. `defaultServer` field in `aouda-studio.config.json`
3. `NEXT_PUBLIC_AOUDA_URL` (build-time env)
4. Hard-coded default: `http://localhost:5000`

### Server Switcher

Top bar component that:
1. Shows current connected server
2. In Hub mode: dropdown with org selector and server list
3. Health check on server selection
4. Auto-applies stored vault credentials
5. Prompts for credentials when none stored

### Authentication Flow

1. Hub login (email/password → JWT tokens)
2. Server selection from registry
3. Server auth detection (health check)
4. Credential lookup in Hub vault
5. If no credential → auth dialog (a key or email/password)
6. Optional "Save to Hub" for credential vault storage

---

## 10) Hosted Studio at `studio.aouda.com`

`https://studio.aouda.com` is the publicly-hosted deployment of Aouda Studio on Vercel. It requires no installation — open it in Chrome or Edge and connect to any Aouda server running anywhere.

### 10.1 Connect-to-Server Dialog

The first time you visit `studio.aouda.com`, a **Connect to Server** dialog opens automatically. Enter the URL of your Aouda server and a key of a `_serverauth` principal.

| Field | Description |
|-------|-------------|
| Server URL | Full URL of the Aouda server, e.g. `http://localhost:5000` or `https://my-server.example.com` |
| Key | A key (`aouda_...`) of a principal of the server auth database. Leave it blank only for a server in setup mode (Studio then says the server has no administrator yet); otherwise the server asks for a credential and the dialog stays open. See [Connecting with a Key](#connecting-with-a-key) |
| Remember key | Checked by default — persists the URL and key in browser `localStorage` |

Once connected, the server URL appears in the top navigation bar. Click it at any time to open the Connect dialog again and switch to a different server.

The chosen server URL and key survive page reloads (stored in `localStorage`). They can be cleared by opening the dialog and connecting with no values, or by clearing browser storage.

**Always use the admin listener URL.** A data-plane listener returns 404 for `GET /api/databases` and `/_studio/config`. Studio treats that 404 as "this is a data-plane URL" — connect to the admin port instead. See [Direct client access](direct-client-access.md#studio-and-hub).

### 10.2 Server URL Resolution Priority

When Studio initializes, the server URL is resolved in this order:

1. `localStorage` (set by the Connect dialog — highest priority)
2. `window.__AOUDA_STUDIO_CONFIG__.defaultServer` (runtime config from `/_studio/config`)
3. `NEXT_PUBLIC_AOUDA_URL` build-time env var
4. Hard-coded fallback: `http://localhost:5000`

This means the Connect dialog always overrides any build-time or runtime default.

### 10.3 Browser Compatibility for `localhost` Access

When using `studio.aouda.com` (HTTPS) to connect to `http://localhost:5000` (HTTP), browsers have different mixed-content policies:

| Browser | Works? | Notes |
|---------|--------|-------|
| **Chrome / Edge** | ✅ Yes | Special localhost exception for mixed content — works out of the box |
| **Firefox** | ❌ No (default) | Blocks HTTP requests from HTTPS pages; toggle `security.mixed_content.block_active_content` to override |
| **Safari** | ❌ No | Same block as Firefox |

**Recommendation:** Use Chrome or Edge for local development with `studio.aouda.com`. For Firefox/Safari localhost support, see P35+ Embedded Studio (served from the same origin, no mixed-content issue).

### 10.4 Security Model for Remote Server Access

When exposing an Aouda server over the network (to reach it from `studio.aouda.com`), use a layered approach:

**Layer 1 — Network: IP Allowlisting (recommended first line of defence)**

Restrict which IPs can reach the Aouda port. Since `studio.aouda.com` sends requests *from your browser* (not from Vercel), the source IP is your own home/office IP — the same one you would allowlist for SSH or PostgreSQL.

```bash
# Linux (ufw)
ufw allow from <your-ip> to any port 5000

# Windows Defender Firewall — inbound rule, port 5000, source = your IP
# Cloud — AWS Security Group / Azure NSG / GCP Firewall: source = your IP
```

**Layer 2 — Transport: TLS via Reverse Proxy**

Aouda.Server speaks plain HTTP. For remote access, put it behind a TLS-terminating reverse proxy:

- **Caddy** (simplest — automatic Let's Encrypt): `reverse_proxy localhost:5000`
- **nginx / Traefik**: standard proxy configs

Aouda does not manage TLS certificates. The reverse proxy is the TLS boundary.

Then set `Aouda:ForwardedHeaders` so Aouda trusts that proxy. Until you do, per-IP rate limits, lockout attribution, and `_audit_log` client IPs are the proxy's address. Worked nginx and cloud-LB examples: [Behind a reverse proxy](../deployment/reverse-proxy.md).

**Layer 3 — Application: a credential on every call**

Every admin-listener endpoint needs a credential. Use a key (`aouda_...`) with the Connect dialog, of a principal that holds only the statements its user needs; `admin` is the role of an operator.

**Layer 4 — Optional: VPN / Zero-Trust**

For high-security environments, expose Aouda only inside a VPN (Tailscale, WireGuard, etc.) — `studio.aouda.com` works identically through a VPN tunnel.

### 10.5 CORS Configuration

Aouda.Server must allow `https://studio.aouda.com` as a browser origin. The defaults already include it:

| Config state | Allowed browser origins |
|---|---|
| Nothing set (defaults) | `https://hub.aouda.dev`, `https://studio.aouda.com`, plus optional `AOUDA_STUDIO_ORIGIN` |
| `AOUDA_CORS_ORIGINS` set | **Only** the comma-separated list — defaults NOT merged in |
| `AOUDA_STUDIO_ORIGIN` set (no `CorsOrigins`) | Defaults **plus** the custom origin appended |

**Important pitfall:** If you set `AOUDA_CORS_ORIGINS` and omit `https://studio.aouda.com`, browsers at `studio.aouda.com` cannot call your server (CORS preflight fails).

```bash
# Correct: include all origins you need
AOUDA_CORS_ORIGINS=https://studio.aouda.com,https://hub.aouda.dev,http://localhost:3000

# Alternative: add one extra origin without replacing defaults
AOUDA_STUDIO_ORIGIN=http://localhost:3000
```

For local development with a custom Studio port, use `AOUDA_STUDIO_ORIGIN` to keep `studio.aouda.com` in the defaults while adding localhost.

### 10.6 `GET /_studio/config` Endpoint

A public (no auth required) endpoint returns static bootstrap metadata:

```json
{ "serverUrl": "/", "theme": "system" }
```

This is used by the future embedded Studio (P35+) to configure itself when served from the same origin as the server. In P34 it establishes the routing and public-route plumbing. It is always safe to expose; it reveals no data or configuration beyond the JSON above.

---

## 11) Deployment

### Docker

```bash
docker login ghcr.io        # the image is private, like the server's: a token with read:packages
docker run -p 3000:3000 \
  -e AOUDA_STUDIO_DEFAULT_SERVER=http://aouda:5000 \
  ghcr.io/aoudadb/aouda-studio:<version>
```

The image is **`ghcr.io/aoudadb/aouda-studio`** (**BL-1982, next train**; `aouda/studio`, the name older pages carried, was never published), `linux/amd64`. Studio and the server move together (the protocol version): run the Studio image of the server's release.

Fully self-contained: no external CDN, font, or icon dependencies. Works air-gapped.

### Studio's CI (**next train**)

Studio's own tests run against mocks. A **real-server smoke test** also exists (`npm run test:smoke` in `aouda-studio`): it runs Studio's own hooks and library, with the real `@aouda/client`, against a server (`AOUDA_SMOKE_URL`, `AOUDA_SMOKE_KEY`) through connect, browse (a formula table and a table with a retention), query (a formula cell, an exact `Int64` key, `explain` naming a division by zero) and listing backups. It fails, never skips, when there is no server, and `npm run test` never includes it. The workflow that runs it on every pull request, from the server's release archive, is prepared for the maintainer to publish; it is a check on Studio's source, not something you deploy.

### Docker Compose

Included in Aouda server's `docker-compose.yml` and `docker-compose.cluster.yml`.

### Kubernetes Helm

Enable in Helm chart: `studio.enabled=true`. Auto-configured to connect to the Aouda headless service.

### Vercel (studio.aouda.com)

The `aouda-studio` repository is configured for Vercel deployment:

- `vercel.json` configures the install command to resolve `@aouda/client` from npm (not from the local `file:` path used in development).
- `NEXT_STANDALONE_OUTPUT` is not set on Vercel (uses Vercel's Next.js runtime instead of standalone Docker output).
- No `NEXT_PUBLIC_AOUDA_URL` is set on Vercel — users connect at runtime via the Connect dialog.

Environment variables for the Vercel project:

| Variable | Required | Description |
|----------|----------|-------------|
| `AOUDA_CLIENT_PACKAGE` | Optional | npm version of `@aouda/client` to use (default: `latest`) |
| `NEXT_PUBLIC_HUB_URL` | No | Leave empty for direct mode at `studio.aouda.com` |

Manual ops required once per deployment: create the Vercel project, attach the `studio.aouda.com` custom domain, and set `AOUDA_CLIENT_PACKAGE` if pinning a version.

### Local Config File

`aouda-studio.config.json` provides server connections when Hub is unavailable:
```json
{
  "servers": [
    { "name": "Local", "url": "http://localhost:5000" }
  ]
}
```

---

## 12) Aouda.Setup Installer

`Aouda.Setup` is a .NET 10 console app, published as a single file, that offers an interactive
alternative to the install scripts.

> ⚠️ **It is not self-contained and it is not zero-dependency.** Like every Aouda artefact it is
> **framework-dependent**: the **.NET 10 ASP.NET Core runtime must already be installed** (**BL-739, 0.2.0**; .NET 8 for 0.1.40 and earlier) on the
> machine. Without it the process fails in the .NET host loader before any Aouda code runs, so
> there is no Aouda error message to read. Install it first:
> `apt-get install aspnetcore-runtime-10.0`, `winget install Microsoft.DotNet.AspNetCore.10`, or
> <https://dotnet.microsoft.com/download/dotnet/10.0>.

> ⚠️ **The unit file it writes is not the one `aouda service install` writes.** It predates that
> command and carries neither the resource limits nor the hardening — no `MemoryMax`, no
> `LimitNOFILE`, `Type=simple` rather than `Type=notify`. For a production Linux host, prefer
> [`aouda service install`](../deployment/linux.md#install), which is the tested path.

### When to Use Aouda.Setup vs. Install Scripts

| Scenario | Use |
|----------|-----|
| First-time install by a developer or end user, on a workstation | `Aouda.Setup` |
| **A production server, on either platform** | **`aouda service install`** — [Linux](../deployment/linux.md), [Windows](../deployment/windows.md) |
| CI/CD automation, scripted deploy pipelines | `scripts/install-aouda.ps1` / `install-aouda.sh`, which preflight the runtime and then call `aouda service install` |
| Container / Kubernetes deployment | [Docker](../deployment/docker.md) / Helm — no installer needed |

### Interactive Prompt Sequence

Double-click `Aouda.Setup.exe` (Windows) or run `sudo ./Aouda.Setup` (Linux — the binary keeps its name on both platforms). The app walks you through five prompts with sensible defaults:

```
Welcome to Aouda Setup
======================
Install mode:
  [1] Windows Service / systemd (recommended — starts automatically with OS)
  [2] Manual / on-demand (run with: Aouda.Server start)
> 1

Port [5433]:
>

Install directory [C:\Program Files\Aouda]:
>

Data directory [C:\ProgramData\Aouda\data]:
>

Admin email:
> admin@example.com

Admin password (input hidden):
>
```

Press Enter to accept defaults. The setup app then:
1. Copies binaries to the install directory (skips any `appsettings*.json` in the release zip)
2. Registers and starts the Windows Service (or systemd unit) with `--data-path` and `--port` on the command line
3. Creates the first admin through the running server, and mints its key
4. Creates Start Menu shortcut (Windows) or `.desktop` shortcut (Linux)
5. Prints the completion banner

No `appsettings.json` is created. End users do not need to know about ASP.NET configuration files. See [Server configuration](server-configuration.md).

### Completion Banner

```
=============================================
Aouda is running!

Server URL : http://localhost:5433
Studio     : http://localhost:5433  (future embedded mode)
Cloud      : https://studio.aouda.com → connect to http://localhost:5433
Key        : aouda_...

Recommended browser for localhost: Chrome or Edge
Store the key in a secret manager now: this is the only time it is shown.
=============================================
```

The key is a stored key of the admin it created. Copy it to a secret manager immediately — it is not stored anywhere after the banner is dismissed.

### Service Registration Details

**Windows (Windows Service via `sc.exe`):**
- Service name: `Aouda`
- Start type: automatic
- Binary path: `"C:\Program Files\Aouda\Aouda.Server.exe" --data-path "C:\ProgramData\Aouda\data" --port 5433`
- If the service already exists, `sc.exe config` updates the binary path before starting

**Linux (systemd):**
- Unit file: `/etc/systemd/system/aouda.service`
- `WorkingDirectory`: install directory
- `ExecStart`: `/opt/aouda/Aouda.Server --data-path /var/lib/aouda --port 5433`
- `User=aouda`, `Group=aouda`
- Data/log directories created with correct ownership (`chown -R aouda:aouda`)
- `systemctl daemon-reload && systemctl enable aouda && systemctl restart aouda`

Requires elevation: run as Administrator on Windows, `sudo` on Linux.

### Shortcut Details

| Platform | Shortcut location | Target URL |
|----------|-------------------|------------|
| Windows | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Aouda Studio.url` | `http://localhost:<port>` |
| Linux | `~/.local/share/applications/aouda.desktop` | `xdg-open http://localhost:<port>` |

The shortcut points to the **local server URL** (not `studio.aouda.com`). In direct-mode Docker or future embedded Studio, the same URL serves Studio. For the hosted Studio, visit `studio.aouda.com` and use the Connect dialog.

### Manual / On-Demand Install Mode

If you select mode `[2]` (manual), `Aouda.Setup` skips service registration and instead prints how to start the server manually:

```
Aouda installed (manual / on-demand mode).

To start the server:
  Windows: "C:\Program Files\Aouda\Aouda.Server.exe" --data-path "C:\ProgramData\Aouda\data" --port 5433
  Linux:   /opt/aouda/Aouda.Server --data-path /var/lib/aouda --port 5433

Server URL : http://localhost:5433  (once running)
Cloud      : https://studio.aouda.com → connect to http://localhost:5433
```

### Admin Bootstrap Logic

`Aouda.Setup` bootstraps the admin account using this sequence:

1. Waits for `GET /health` to return 200 (up to 30 retries × 2 seconds = 60 seconds). That only proves the process is alive; wait for `GET /ready` (and `GET /api/databases/{name}` `state=Active`) before schema apply.
2. Calls `POST /api/auth/setup` with email + password. If the server returns 403 `ALREADY_CONFIGURED` (admin already exists), falls back to `POST /api/auth/signin`.
3. Uses the returned token to call `POST /api/auth/_serverauth/principals/{email}/keys` and obtain a stored key, shown once.

In manual mode no server is running yet, so it creates no admin and prints the commands instead: start the server, then `aouda init`.

### Existing Install Scripts (Preserved)

`scripts/install-aouda.ps1` (Windows) and `scripts/install-aouda.sh` (Linux) are unchanged. They remain the preferred tool for CI/CD pipelines and scripted deployments where non-interactive, parameter-driven installs are needed.

---

## 13) Admin Features

### Log Viewer

**ADMIN → Logs** (`/admin/logs`) reads the recent in-memory log of the node Studio is connected to (`GET /admin/node/logs`):

- **Level** is a minimum: All levels, Trace, Debug, Information, Warning, Error or Critical.
- **Contains** is a text filter. The table shows up to 300 entries: UTC timestamp, level, category and message.
- **Refresh** reads again, and the **Auto** box reads again every 5 seconds. Studio polls; it does not use the server's SSE log stream (`GET /admin/node/logs/stream`).

### Slow Query Log

**ADMIN → Slow queries** is the same node log filtered by a message text (default `slow`) and a minimum level. It is marked a preview surface: it lists the log lines the server wrote and adds no timing or query detail of its own. Widen the filters if it is empty.

### Alert Configuration

**ADMIN → Alerts** evaluates three rules **in the browser**, from the server's metrics and a `/health` ping every 30 seconds: *Memory pressure* (a threshold in % of the server's maximum), *Replication lag* (a maximum in bytes; not on a standalone server) and *Server unreachable* (the browser's `/health` request failed). The rules and the history (kind, severity, message, time) are kept in the browser's `localStorage`, so they run only while Studio is open and are not shared between browsers. **Clear history** empties the list.

### Connection Monitor

**ADMIN → Connections** shows the server URL and the auth scope Studio uses ("Server auth (global)"), the live sessions of the server auth database (`GET /api/auth/admin/sessions`, paged by 20; **Revoke this session** and **Revoke all for this user** from the row's menu), and a metrics summary: active connections, materialized queries, queries per second.

### Multi-Server Dashboard

In Hub mode: aggregate health overview across all registered servers.

### What Studio Shows to Whom

Studio reads `GET /api/auth/whoami` for the connected credential and uses its statements as a **hint for which pages to show**. It allows and denies nothing: every call goes to the server, and a control the server refuses shows the server's message, its code and its `remedy`. Until `whoami` has answered, the entries below stay hidden.

| The credential holds | Studio shows |
|---|---|
| anything | The data, schema and query pages, **Dashboard** and **Monitoring** (the **Full** profile) |
| `manage` on `server` or on a database | In addition: the operational pages (**Backups**, **Databases**, **Logs**, **Alerts**, **Slow queries**, **Connections**, **Streaming**, **Bulk Load**), the **SETTINGS** section, the write controls on **Materialized**, **Named Artifacts** and **Migrations**, and **CLUSTER** on a node that is not standalone |
| `manage` on `server` | In addition: **Settings → Access** and **Settings → Declaration** |

The profile switcher (**Full** or **Data Owner**) is a preference of the browser, not a permission: **Data Owner** shows only Tables, pinned tables and saved views.

### Connecting with a Key

The Connect dialog (the first-run dialog, or the server URL in the top bar) takes the **Server URL** and, optionally, a key (`aouda_<id>_<secret>`) of a `_serverauth` principal. **Remember key on this browser** is on by default. Studio asks the admin listener first, with no credential (`GET /api/databases`), and shows what the answer means:

| The server answers | Studio shows |
|---|---|
| `401` or `403` | The Connect dialog stays open: a credential is needed |
| `404` | That URL is the data-plane listener; connect to the admin one |
| `503 SETUP_REQUIRED` | **This server has no administrator yet.** The first administrator is made on the server's machine (`aouda init`, `aouda start --dev-admin`, or a declared `_serverauth` principal holding `manage` on `server`), never from a web page. Studio checks again for ten minutes, or on **Check again** |
| `503 SERVER_STARTING` | "The server is starting up", and tries again after the server's `Retry-After` |
| `200` | A message that this server is of another release than this Studio |

A key is then proved with `GET /api/auth/whoami`; a refusal is shown as the server wrote it, with its `remedy`. Studio holds **one** credential, a key or a session, stored with its kind; it never works the kind out from the text. A saved credential the server refuses is dropped and the dialog asks again. The connection card on **Settings → Access** takes a key too (**Connect**, **Disconnect**) and shows "Connected as `<authDatabase>/<name>`".

### Materialized Queries Browser

- **Materialized** (under DATA, for the Full profile) lists the queries of the current database: name, source table, type, a state badge (Ready, Building, Rebuilding, Error, …), a **Behind** pill when the result is not current, **Freshness** and the row count. **Ready** still means readable.
- A query that is behind reads "Behind for 1 min 30 s" (the server's `currentLagMs`), and its detail page and **Definition** sheet give the full `staleReason` as text. A current query shows "Updated <time>" and no lag. (**Studio BL-MQ-01, BL-MQ-02, next train**)
- The detail page shows the query's result in a read-only grid, with **Definition** and **Refresh**.
- With a credential that may administer (the second row above): **Create** (a dialog: name, source table, pattern type and its filter, group-by and order-by columns) and **Drop**. On a database whose schema the declaration file owns, both are disabled and badged ([Declaration](#declaration)).

This page talks to the **runtime** MQ HTTP API. Schema-file desired state is a different axis: a **present** `materializedQueries` map on apply (including `{}`) drops live MQs that are not listed. See §5.5 Schema Diff View and [Schema CI/CD](schema-cicd.md).

### Access

**Settings → Access** (`/settings/access`; **BL-1464, 0.16.0**) is the page for the principals, roles, sign-up, credentials and sessions of one auth database at a time. Its menu entry shows for a credential that holds `manage` on `server`; the page itself is the server's to refuse. See [Principals](../auth/principals.md), [Credentials](../auth/credentials.md) and [Declared access](declared-access.md) for the model.

- **Auth database.** *Server* is `_serverauth`; one more button per application auth database (a database of kind `application`). With none, the page says so: choose *Create `auth` and link* when you create a database, or declare one. The auth database and the tab are in the address: `/settings/access?authDatabase=<name>&tab=<id>`.
- **Tabs.** *Who am I*, *Principals*, *Roles*, *Sign-up* (application auth databases only, `_serverauth` takes no signup), *Sessions* and *Audit log* (both *Server* only; **BL-1986, next train**), and *OIDC discovery*. Below, `…` is `/api/auth/{authDatabase}`.

| Tab | Shows, and lets an operator | Server routes | The principal needs `manage` on |
|---|---|---|---|
| *Who am I* | [`whoami`](../auth/whoami.md) of the connection's own credential: the principal (id, source, disabled), the credential (type, id, source, version, root, created, expires, parent, a limited key's statements, a session's `signedInWith`, `aal`, issuer and subject), the listener, the `permissionVersion`, the roles, attributes and every statement with where it came from. A **Policy database** field filters the policy to one database. **Create a limited key** (below) | `GET /api/auth/whoami[?database=]`, `POST /api/auth/keys` | nothing: any credential may ask who it is, and may limit itself |
| *Principals* | The list, searched by name and filtered by source (all, declared, runtime, signup, builtin). **Create principal** (a slug or an email; a password only for an email; description, roles and attributes; statements, added with the editor a principal's page has, and **Create** waits for a valid `where`; **BL-1988, next train**: the form's *Add statement* used to add a statement it did not show). For one principal: save its name (a rename keeps the id), description, roles, statements and attributes; **Disable** / **Enable**; **Delete** (type the name; its credentials and sessions end). `anonymous` takes statements and attributes only, and Studio says that what is granted there is public | `…/principals`, `…/principals/{name}` | `<auth>/principal/*` for the list and a create; the principal for the rest. A write must also cover every statement it grants |
| *Roles* | The roles, built-ins (`admin`, `writer`, `reader`) read-only; **Create role**; a role's description and statements, who holds it and how many principals it reaches; **Delete** names its holders | `…/roles`, `…/roles/{name}` | `<auth>/role/*`, or the role |
| *Sign-up* | **enabled**, the roles and the statements a signed-up principal gets, **Save sign-up**. It warns that people who sign up can do nothing until you grant them something | `…/signup` | `<auth>` |
| *Sessions* (*Server* only) | The sessions of the server auth database (user, device, IP, created, expires); **Revoke this session**, **Revoke all for this user** | `/api/auth/admin/sessions` | the server auth database and its principals |
| *Audit log* (*Server* only) | The audit rows, filtered by user id, action, and a from / to date | `/api/auth/admin/audit-log` | the server auth database and its principals |
| *OIDC discovery* | The OIDC discovery URL and the JWKS URL of the auth database, each with **Copy** | none (the URLs are built) | nothing |

**Credentials of a principal.** The principal's page lists each credential by id and kind (a stored key, a limited key, a derived key, an OIDC trust, whether a password is set), with its name, source, who made it, when it expires and its parent. A secret is never listed.

- **Mint key** (name and expiry are optional; no expiry is the default). The key is shown **once**, in a box that is not an input, with **Copy**; closing without copying asks first, and the box clears itself after ten minutes or when the connection changes. The server keeps only a hash.
- **Add trust** (an OIDC trust): issuer (`https://…`), audience, subject and optional claims; a workload exchanges its issuer's token at `POST /api/auth/oidc/token`. An issuer the server cannot reach by discovery needs `jwks`, which exists only in the declaration.
- **Revoke** a stored or limited key, and **Delete** one (an OIDC trust is **Remove**): the sessions and sockets holding it end at once, or, for a trust, within the sessions' lifetime (at most an hour). Revoking the credential Studio is using says that you will be signed out. A limited key dies with its parent.
- **Create a limited key** (on *Who am I*): a short-lived key for the connected principal alone. **expiresIn** is an ISO 8601 duration (presets 15 min to 24 h); choose *Narrow to these statements* (one statement) or *No narrowing — expires only*. It can only narrow what the principal holds.

**Statements.** The editor offers the actions `read`, `write`, `execute`, `manage`, `delete`, `set-identity` and `*`, the resources (`server`, `<db>`, `<db>/table/<t>`, `<db>/query/<q>`, `<db>/mutation/<m>`, `<authdb>/principal/<n>`, `<authdb>/role/<r>`), a **Where (JSON)** field, **Embargo seconds** on a `read`, and an **unrestricted** box that asks for confirmation. A member the form does not show is carried unchanged. A warning the server returns with a save (a statement that names a column its table lacks) is shown under the statements. A statement's `where` is also summarised as text; for a `where` that has both `and` and `or` that text carries no parentheses, so read the JSON when it matters.

**Declared objects.** A declared principal, role or `signup` setting is read-only: a badge says "Declared in `<file>` at `<pointer>`", the fields are disabled, and the one thing the server still allows is offered: **Disable** / **Enable** for a declared principal, and **Revoke** for a declared key or derived key ("Revoked here, still declared": the revocation is kept on this server only, and the file still declares the key, so remove it there). A `409 DECLARED_IN_CONFIGURATION` is shown as the server wrote it.

**Refusals.** A refusal shows the server's code and message and its `remedy`: the statement to grant (`grant`), a `where` to add (`add-where`), the credential to use (`use-credential-of`), or "an operator must act". Studio offers the next step and performs none; it never turns `unrestricted` on for you.

**A table's schema view** has a **Who can reach this table** card (**Show** / **Hide**): the statements of the governing auth databases that name the table, with who holds each, a link to the Access page, and a note that anonymous and signup rows are reachable by anyone. It is a listing, not a decision (a limited key, a credential or `disabled` are not applied); it needs `manage` on the principals to read, and says when it is incomplete.

What a declared principal that is not connected would be allowed is [`aouda policy explain`](../reference/cli.md#policy-explain), offline.

> **Sessions and Audit log are the server auth database's** (`/api/auth/admin/…`; **BL-1986, next train**). An application auth database has neither route, so Studio offers the two tabs only for *Server*, and a `?tab=sessions` or `?tab=audit` address on an application auth database opens the first tab. Before this train the two tabs were offered there and answered `404`.

### Declaration

**Settings → Declaration** (`/settings/declaration`; **BL-1463, 0.16.0**) shows what the server runs on and lets an operator ask what a reload would do. Its menu entry, like Access, shows for a credential that holds `manage` on `server`. Every call below asks `manage` on `server`, on the admin listener. See [Declare a server in one file](declaration.md).

| Part | What it shows or does | Server route |
|---|---|---|
| Header | Where the declaration comes from ("Declared by a file", "Declared in code by the host (no file)", or "Nothing is declared"), the file, the overlay, the environment, the plan hash (**Copy hash**), and the last start or reload: its origin, time, outcome and counts of errors, warnings, info and changes | `GET /api/admin/declaration` |
| Tree | The declaration document the server runs on, as a tree with **Copy pointer** on each node. A credential is its public id only; a key-shaped string anywhere is shown as `aouda_<id>`. Shown when the source is a file | the same |
| Findings | The findings of the last start or reload: severity, code, stage, where, message and fix | the same |
| **Plan** | Runs a **dry-run** reload and shows the outcome ("Clean", "N changes would be applied by `aouda reload`" or "Errors"), the stages, the findings, the schema changes per database and file, the counts of the other changes and what was not checked. It cannot apply anything: "Studio cannot apply a declaration. Change the file, then run `aouda reload`." | `POST /api/admin/reload?dryRun=true` |
| **Export** | On an explicit press, the server's current state as `aouda.json` and its schema files (**Copy** or **Download** each), an **Origins** tab (which pointers are declared and which were created at runtime, not in the file) and the server's notes. The file holds the SHA-256 of each stored key: it cannot sign in, but it is secret-class, so save it to the repository that owns your `aouda.json`, not to a chat. Studio keeps none of it after the dialog closes | `GET /api/admin/declaration/export` (no-store) |

The export writes an audit row, so a node that does not accept writes (a secondary) answers `503 READ_ONLY`: export from the primary. A refusal (`401`, `403`) is shown with its code and `remedy`; with no credential the page says the server refused it, and **Export** stays off until the view has loaded.

**A declared database or schema is not edited in Studio** (**BL-1463, 0.16.0**). The **Databases** list badges a declared database and disables its **Drop**; **Create database** refuses a declared name before sending it; on a declared schema the Columns, Storage Policy, Checks and route / tee editors, the materialized-query and named-artifact editors, **Create table** and the **Migrations** apply wizard are disabled and badged with the file and the pointer, and Migrations shows **Plan** instead (a branch merge can be planned, not executed). A database declared without a schema keeps its schema editors. Data writes stay live. A `409 DECLARED_IN_CONFIGURATION` is shown as the server wrote it. While the declaration cannot be read (loading, refused, failed), nothing is disabled: the server's `409` is the authority.

### Streaming Explorer

Sidebar: **ADMIN → Streaming**. Two modes:

| Mode | What you send | When to use |
|------|----------------|-------------|
| **Table** | Table name + optional filter (`WhereClause` JSON) | Operator ad-hoc on the admin listener (unchanged) |
| **Named query** | Schema name + args JSON + optional conflate | The data-plane subscribe path — same name as execute |

Name mode calls `namedQueries.subscribe(name, args, { conflate })`. It never sends a table name or filter. Conflate uses wire field `interval_ms` and holds **value updates only** (no-op on insert-only streams). The append-only log surfaces `gap`, `values_skipped`, and deprecation on `snapshot_complete` (warning, not a failed subscribe). Gap frames are auto-resumed by the client on a live socket. See [Named queries — Subscribe by name](named-queries.md#subscribe-by-name) and [browser-tier read limits](browser-tier-read-limits.md#conflate-is-a-no-op-on-insert-only-streams).

### Bulk Load (monitor)

Sidebar: **ADMIN → Bulk Load**. This page **lists and can force-abort jobs**. It does **not** upload files or call `:begin`.

Tables with derived columns, checks, or transforms reject `:begin` unless the client that starts the job sets **exactly one** of `applyTransforms` (server applies compute) or `preTransformed` (rows already match the target shape). Both flags → `BULK_LOAD_TRANSFORM_INTENT_CONFLICT`; neither → `BULK_LOAD_TRANSFORM_INTENT_REQUIRED`. Failed jobs show the code plus that explanation. Set the flag in the SDK or CLI that calls `:begin`. See [Insert-time transforms — Bulk load](insert-transforms.md).

---

## 14) Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 14 (App Router) |
| UI Components | shadcn/ui |
| Styling | Tailwind CSS |
| Data Fetching | TanStack Query |
| Data Grid | Glide Data Grid (`@glideapps/glide-data-grid`) |
| State (local) | React `useState` |
| State (global) | Zustand stores |
| State (server) | TanStack Query cache |
| Client SDK | `@aouda/client` |
| Testing | Vitest + React Testing Library |

---

## 15) Phase Coverage Matrix

| Phase | Delivered | Key Task Docs |
|-------|----------|---------------|
| P5 | App shell, data grid, filter builder, cell editing, row ops, relationship nav, entity detail, schema views, ERD, dashboard | `aouda-studio/docs/tasks/P5-*` |
| P6 | Multi-database support, database management UI | `aouda-studio/docs/tasks/P6-*` |
| P9 | Server settings, database settings, table policy editor, enhanced dashboard, monitoring, cluster/replication pages, auth placeholders, backup placeholder | `aouda-studio/docs/tasks/P9-*` |
| P12 | Users panel, roles/permissions panel, sessions/audit log panel | `aouda-studio/docs/tasks/P12-*` |
| P16 Epic B | Hub integration, server switcher, connection auth, Docker image, config file, offline mode, env vars | `aouda-studio/docs/tasks/P16-SB3-*`, `P16-SB4-*` |
| P16 Epic C | Cluster ops (add/remove/promote/failover), node detail, backup management, memory editor, topology viz, all config editors | `aouda-studio/docs/tasks/P16-SC1-*` through `P16-SC3-*` |
| P16 Epic D | Log viewer, query worksheet, role-based UI, key authentication, settings, alerts, slow query, PITR, join UI, aggregate UI, branches UI, advanced filters, materialized queries, admin keys | `aouda-studio/docs/tasks/P16-SD1-*` through `P16-SD5-*` |
| P16 Epic F | Studio cloud integration (projects, clusters) | `aouda-studio/docs/tasks/P16-SF3-*` |
| P16 Epic G | Natural language cluster operations | `aouda-studio/docs/tasks/P16-SG2-*` |
| P34 | Hosted Studio at `studio.aouda.com` (Vercel), Connect-to-Server dialog, localStorage persistence, first-run detection, CORS for `studio.aouda.com`, `/_studio/config` endpoint, `Aouda.Setup` cross-platform installer | `aouda/docs/tasks/P34/StudioDist-*` |
| P36 | Column evolution UI (alter type/null/encoder/references, PK, reorder, Toggle AutoId via `alterColumn`) | `aouda-studio/docs/tasks/P36-*` |
| P37 | Data-plane 404 connect copy | `aouda-studio` P37 slices |
| P39 | Operator parity: named artifacts, insert-time compute, route/tee, named-query subscribe, schema-file MQ maps, identity-insert, bulk-load intent copy | `aouda-studio/docs/tasks/P39/` |
| Principals (0.16.0) | Access page (principals, roles, statements, sign-up, credentials, OIDC trusts, limited keys, who you are), Declaration page (view, plan, export), declared databases and schemas read-only, one credential from `whoami`, the old auth and keys pages removed | `aouda/docs/tasks/Principals/` |
| Operability (**next train**) | Reads the cut contracts (member lag from the replication status, a numeric materialized-query lag), a grid that sorts, edits and deletes what it shows, filter groups the worksheet runs, Expression columns and `explain`, retention, point-in-time restore and prune, a real-server smoke test | `aouda/docs/tasks/Operability/` |
