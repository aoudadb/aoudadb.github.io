---
title: "Architecture"
nav_order: 6
parent: "Auth and Authorization"
---

# Architecture (**BL-1464, 0.16.0**)

Every deployment below is the same three concepts. What changes is which principal holds which statements, and which listener the caller uses.

## Pattern A — a server you administer

One `_serverauth` principal with role `admin`, declared in `server.principals`, credential a stored or derived key. Studio and `aouda` talk to the admin listener with that key. Data databases are linked to an application auth database or left unlinked (then `_serverauth` governs them).

## Pattern B — a browser

The browser holds **no key**. It uses the data-plane listener. `anonymous` has `execute` on the named queries the page may run, and nothing else. A person who signs in uses their session as the bearer. There is no key to embed in the page.

## Pattern C — a backend

The backend is a principal in the application auth database with the statements the application needs (`writer`, or narrower). Its key is derived when the process is deployed from the same declaration as the server, or stored when a person minted it once. The backend sends that key as the bearer. It does not forward a second token. To act as a person it uses that person's session, or a [limited key](credentials.md#limited-keys) minted from it, as the only credential on the call.

## Pattern D — a feeder

A declared principal, a derived key, a `where` on the rows it may write. The key is computed on the deploy host (`aouda keys derive`) and injected as a file. The server stores the hash, not the key. A wipe plus a start brings the same principal back; `keys derive` prints the same key while the version and the root are unchanged.

## Pattern E — a CI job

The job has no long-lived Aouda key. An OIDC trust on a principal maps the job's issuer and subject. `aouda login --oidc` exchanges the job's identity token for a session, and the job sends that session. See [OIDC](credentials.md#oidc).

## Where each one runs

| | Admin listener | Data-plane listener |
|---|---|---|
| Operator, Studio, deploy | Key or session of a `_serverauth` principal | |
| Backend, feeder | When the call is an admin route | When the call is a named artifact or a row the policy allows |
| Browser | | No credential (`anonymous`), or the person's session |
| Sign-in, signup, the probes | | No credential, by route |

A route that is not on the data-plane listener is `404` there for every caller, including an operator. Ad-hoc query is an admin-listener route.

## One policy language

Patterns A–E do not get a different rule because of who is calling. The route's action and resource are checked against the principal's statements. The [route table](../reference/http-api.md#access-principals-credentials-and-policy) is that list.
