---
title: "Authentication Setup"
nav_order: 2
parent: "Getting Started"
---

# Authentication (**BL-1464, 0.16.0**)

One model. A **principal** is who is acting, a **policy** is what they may do, a **credential** proves which principal it is. The chapter is [Access](../auth/index.md). This page is the first run.

## Dev admin

On a laptop, with `ASPNETCORE_ENVIRONMENT=Development`:

```text
aouda start --dev-admin
```

The process prints one line on stdout and nowhere else:

```text
AOUDA-DEV-ADMIN email=<email> password=<password> key=<aouda_id>_<secret>
```

`key=` is a stored key of that principal, which holds the built-in role `admin` on `_serverauth`. New values at every start. The previous password and key stop working. The flag is refused in Production, beside another operator, or on a replication node.

Do not paste that line into a document. The examples below use placeholders.

## A declaration: a browser, a backend, a feeder

<!-- declaration-example -->
```json
{
  "version": 1,
  "keyRoot": { "env": "AOUDA_KEY_ROOT" },
  "server": {
    "principals": {
      "ops@example.com": {
        "roles": ["admin"],
        "credentials": { "password": { "env": "AOUDA_OPS_PASSWORD" } }
      }
    }
  },
  "databases": {
    "auth": {
      "kind": "auth",
      "signup": { "enabled": false },
      "roles": {
        "rates-feeder": {
          "statements": [
            {
              "actions": ["write"],
              "resources": ["rates/table/DepositQuote"],
              "where": { "column": "source", "op": "in", "value": ["tullett"] }
            }
          ]
        }
      },
      "principals": {
        "anonymous": {
          "statements": [
            { "actions": ["execute"], "resources": ["rates/query/latest"] }
          ]
        },
        "shop-backend": {
          "roles": ["writer"],
          "credentials": {
            "keys": [
              {
                "id": "aouda_exampleexampleex",
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
              }
            ]
          }
        },
        "rates-feeder": {
          "roles": ["rates-feeder"],
          "credentials": { "derivedKey": { "version": 1 } }
        }
      }
    },
    "rates": {
      "kind": "data",
      "authDatabase": "auth",
      "schema": "schema/rates.aouda.schema.json"
    }
  }
}
```

- The browser sends no key. It calls `rates/query/latest` on the data-plane listener as `anonymous`.
- The backend sends the stored key whose public id is `aouda_exampleexampleex`.
- The feeder's key is computed on the deploy host: `aouda keys derive auth/rates-feeder --declaration aouda.json`.

`aouda plan --declaration aouda.json`, then start with `--declaration aouda.json`.

## whoami

```text
aouda whoami --server http://127.0.0.1:5000 --json
```

The body is the principal, the credential's public id, and the statements. When a call is refused, the body's `remedy` says what is missing. See [whoami](../auth/whoami.md).

## Three states

| State | What is true |
|---|---|
| Setup mode | No principal holds `manage` on `server`. `POST /api/auth/setup` creates the first one. |
| Declared | `aouda.json` names the operator, the auth database and the principals. A wipe and a start bring them back. |
| Dev admin | `--dev-admin` minted a throwaway operator for this process. It is gone at the next start. |

There is not a separate server-auth product and an application-auth product. `_serverauth` is the auth database that may hold `manage` on `server`. An application auth database governs the data databases linked to it.
