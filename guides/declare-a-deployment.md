---
title: "Declare a deployment"
nav_order: 2.4
parent: "Guides"
---

# Declare a deployment: one complete, working set (**BL-1463, 0.16.0**)

This page is one working set for a multi-service deployment that is **declared** instead of scripted: two data databases and one auth database, the principals and statements every service needs, a compose file, a plan before the deploy, a wipe-and-start, and a reload. Copy the files together.

The rules live on the pages this one stitches: [Declare a server in one file](declaration.md), [Declared access](declared-access.md), [Keys that survive a wipe](keys-that-survive-a-wipe.md), [Plan a declaration](plan.md), [Docker](../deployment/docker.md).

## The set

```text
compose.yaml
declaration/ mounted read-only at /etc/aouda
 aouda.json version, databases, roles, principals
 deposit.schema.json
 ledger.schema.json
secrets/ never committed
 key-root.txt the key root (aouda keys new-root)
 ops.key deposit-service.key ledger-service.key tullett-feeder.key
```

| Piece | What it is |
|---|---|
| `derive_auth` | The auth database. Holds the roles and the principals of both data databases |
| `deposit`, `ledger` | Data databases, each linked to `derive_auth`, each with a schema file |
| `ops` | A principal of `_serverauth` with the built-in role `admin` and a derived key. Operates the server and runs `aouda reload` |
| `deposit-service`, `ledger-service` | One principal per data database, derived key, statements for the routes that service calls |
| `anonymous` on `derive_auth` | The principal a browser with no credential acts as. Give it the statements the browser may run. A browser holds no key |
| `tullett-feeder` | A principal with a derived key and `execute` on `insert_quote` only |

### `declaration/aouda.json`

Named by `Aouda:Declaration`. There is no default path. The shape is the file's own, not an `appsettings.json`.

```json
{
 "version": 1,
 "keyRoot": { "file": "/run/secrets/aouda_key_root" },
 "server": {
 "principals": {
 "ops": {
 "roles": ["admin"],
 "credentials": { "derivedKey": { "version": 1 } }
 }
 }
 },
 "databases": {
 "derive_auth": {
 "kind": "auth",
 "roles": {
 "quote_writer": {
 "description": "Runs insert_quote and reads the quotes it wrote",
 "statements": [
 { "actions": ["execute"], "resources": ["deposit/mutation/insert_quote"] },
 { "actions": ["read"], "resources": ["deposit/table/quotes"] }
 ]
 }
 },
 "principals": {
 "deposit-service": {
 "statements": [
 { "actions": ["read", "write", "execute"], "resources": ["deposit/table/*", "deposit/mutation/*", "deposit/query/*"] }
 ],
 "credentials": { "derivedKey": { "version": 1 } }
 },
 "ledger-service": {
 "statements": [
 { "actions": ["read", "write"], "resources": ["ledger/table/*"] }
 ],
 "credentials": { "derivedKey": { "version": 1 } }
 },
 "tullett-feeder": {
 "roles": ["quote_writer"],
 "credentials": { "derivedKey": { "version": 1 } }
 },
 "anonymous": {
 "statements": [
 { "actions": ["execute"], "resources": ["deposit/query/quotes.latest"] }
 ]
 }
 }
 },
 "deposit": { "kind": "data", "authDatabase": "derive_auth", "schema": "deposit.schema.json" },
 "ledger": { "kind": "data", "authDatabase": "derive_auth", "schema": "ledger.schema.json" }
 }
}
```

A derived key is computed from `keyRoot`, the auth database, the principal's name and the version. The same root after a wipe is the same key. The server stores no copy of the key. `aouda keys derive derive_auth/tullett-feeder --declaration declaration/aouda.json --root-file secrets/key-root.txt --key-file secrets/tullett-feeder.key` prints it into a new `0600` file.

### Schema files

`deposit.schema.json` declares the table `quotes` and the named mutation `insert_quote`. `ledger.schema.json` declares `ledger`'s tables. A path in `schema` is relative to the directory of `aouda.json`. A table carries no security members: who may read or write it is a statement, above.

### `compose.yaml` {#compose-yaml}

```yaml
services:
 aouda:
 image: ghcr.io/aoudadb/aouda-server:<version>
 stop_grace_period: 130s
 mem_limit: 2g
 cpus: 4
 ports:
 - "127.0.0.1:5000:5000"
 environment:
 Aouda__Declaration: /etc/aouda/aouda.json
 volumes:
 - aouda-data:/data
 -./declaration:/etc/aouda:ro
 secrets:
 - aouda_key_root

secrets:
 aouda_key_root:
 file:./secrets/key-root.txt

volumes:
 aouda-data:
```

The image is private: log in first ([Docker](../deployment/docker.md)).

**Mount the directory, not the file.** A compose line `./aouda.json:/etc/aouda/aouda.json:ro` binds one file, and Docker pins that file's inode: an editor that saves by renaming, a `git checkout` and `mv` all replace the inode, and the container keeps reading the old content. A **directory** mount follows the name. The reload reads the path the process started with; it does not watch the file.

**The container reads the key root as uid 1654.** Compose bind-mounts a `file:` secret with the host file's owner and mode. A `0600` file owned by you is unreadable in the container (`SECRET_UNREADABLE`, exit `1`, a restart loop). `chmod 0444` the secret file and `chmod 700` the directory that holds it.

## Make the root and the keys

```bash
mkdir -p secrets && chmod 700 secrets
aouda keys new-root --root-file secrets/key-root.txt
aouda keys derive server/ops --declaration declaration/aouda.json --root-file secrets/key-root.txt --key-file secrets/ops.key
aouda keys derive derive_auth/deposit-service --declaration declaration/aouda.json --root-file secrets/key-root.txt --key-file secrets/deposit-service.key
aouda keys derive derive_auth/ledger-service --declaration declaration/aouda.json --root-file secrets/key-root.txt --key-file secrets/ledger-service.key
aouda keys derive derive_auth/tullett-feeder --declaration declaration/aouda.json --root-file secrets/key-root.txt --key-file secrets/tullett-feeder.key
chmod 0444 secrets/key-root.txt
```

`keys new`, `keys new-root` and `keys derive` are the key commands. A key is `aouda_<id>_<secret>`. Nothing here takes the key as an argument.

## Plan it before you start it

```bash
docker compose run --rm --no-deps --entrypoint aouda aouda plan --declaration /etc/aouda/aouda.json
```

Exit `0` means the start would not refuse the declaration. Exit `1` means it would. Exit `64` is misuse.

On a CI runner, with no key root mounted:

```bash
aouda plan --declaration declaration/aouda.json --skip-secrets
```

Against a running server, the key is that server's operator key, passed by variable:

```bash
aouda plan --declaration declaration/aouda.json --skip-secrets \
 --server https://aouda.internal:5000 --key-env AOUDA_PLAN_KEY
```

Exit `0` is nothing to change, `2` is changes, `77` is the key refused, `69` is the server unreachable. The fuller job is [A CI job](plan.md#a-ci-job-aouda-plan-on-every-pull-request).

## Wipe and start

```bash
docker compose down -v
docker compose up -d
until curl -fsS http://127.0.0.1:5000/ready >/dev/null; do sleep 2; done; echo ready
```

**Wait on `/ready`, never on `/health`.** `/health` is `200` while the start is still running. When the loop ends, the three databases exist, the schema files have been applied, and the declared principals are back with the same derived keys. `ops` holds `admin`, so the server is not in setup mode.

A start that refuses its declaration prints every finding and **exits `78`**. Under `restart: unless-stopped` that is a restart loop: read the container's output ([A container that keeps restarting](../deployment/docker.md#a-container-that-keeps-restarting)).

Check the operator key:

```bash
AOUDA_TOKEN=$(cat secrets/ops.key) aouda whoami --server http://127.0.0.1:5000 --json
```

## The feeder

`tullett-feeder` may `execute` `insert_quote` and `read` `quotes`, and nothing else. The key is the derived key above.

```bash
curl -s -X POST http://127.0.0.1:5000/api/databases/deposit/named-mutations/insert_quote/execute \
 -H "Authorization: Bearer $(cat secrets/tullett-feeder.key)" \
 -H "Content-Type: application/json" \
 -d '{"args":{"ticker":"EQNR","px":301.5}}'
```

A call the statements do not allow is `403 AUTH_POLICY_DENIED` with a `remedy` of `grant` on the admin listener. On the data plane, a named mutation the caller may not execute is `404 NAMED_MUTATION_NOT_FOUND`. `aouda policy explain --declaration declaration/aouda.json --as derive_auth/tullett-feeder --action execute --resource deposit/mutation/insert_quote` answers the same question offline.

A browser does not send a key. It calls the data-plane listener, and the server acts as `anonymous`.

## Change it without a restart

Edit `declaration/aouda.json` and run:

```bash
aouda reload --server http://127.0.0.1:5000 --key-file secrets/ops.key
```

Exit `0` is nothing to change, `2` is applied, `1` is refused (`422 RELOAD_REFUSED`) or partial. A changed `Aouda:Declaration` path takes a restart: the reload keeps reading the file the process started with. What a reload applies and what takes a restart is [one table](server-configuration.md#reload-or-restart).

To rotate one principal's key, bump its `derivedKey.version` and reload. Derive the new key. The old one is refused at once.

## What a wipe still loses

The declaration comes back: databases, schema, roles, principals, derived keys. Rows do not. A runtime principal (someone who signed up, a key minted through the API) does not. A revocation does not: the same root derives the same key, so the lasting fix for a leaked derived key is a new version in the file. Passwords are seeds, applied when the principal is created, not a copy of the password.

## Related

- [Declared access](declared-access.md) and [Credentials](../auth/credentials.md)
- [whoami](../auth/whoami.md) and the [CLI](../reference/cli.md)
- [Kubernetes](../deployment/kubernetes.md#declare-the-databases-bl-1463-0160)
