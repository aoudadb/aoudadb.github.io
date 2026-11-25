---
title: "Client integration"
nav_order: 7
parent: "Auth and Authorization"
---

# Client integration (**BL-1464, 0.16.0**)

Both SDKs take **one credential**: a key, or a session. There is no second option for "which kind of caller", and no header beside the bearer. The pages with the method names are [.NET](../clients/dotnet.md) and [TypeScript](../clients/typescript.md). This page is the shape.

## One option

**.NET.** `Credential = AoudaCredential.Key(key)` or `AoudaCredential.Session(...)`. `WhoAmIAsync()` calls `GET /api/auth/whoami` for the client's database. `WhoAmIAsync(null)` asks for the whole policy.

**TypeScript.** `apiKey` **or** `session`, never both. `apiKey` is checked at construction (shape, checksum, retired format) before any request, and the error names the reason, never the value. `client.whoami()` is the same call.

A key is not refreshed. A session is. Four factories cover how you obtained the credential: a key string, a key file, a password sign-in, an OIDC exchange. Pick the one that matches what you hold.

## whoami

Call it at startup. The `principal.name`, `credential.type` and `policy.statements` are what the server will enforce. A refusal later carries a `remedy` of the same shape [whoami](whoami.md#remedy) documents; both SDKs surface it as a typed value (`sign-in`, `fix-key`, `renew`, `none`, `use-credential-of`, `grant`, `add-where`).

## Acting for a person

A backend that acts for many people does one of three things:

1. **One client per person**, each holding that person's session. Clients are cheap; they share the socket pool.
2. **Forward the person's session** as the only bearer on that call.
3. **Mint a limited key** from the person's session (`POST /api/auth/keys`, or the SDK's limited-key call) and use that key for the narrow action.

There is no per-call credential on a shared client, and no second header. A shared-client override is not built.

## The access and declaration clients

`client.access` (TypeScript) and the .NET access client call the principals, roles, signup and credential routes. A write to an object the declaration file owns throws `AoudaDeclaredInConfigurationException` / the conflict error with `DECLARED_IN_CONFIGURATION`.

`client.declaration` reads `GET /api/admin/declaration` and the export. Both need `manage` on `server`.

## A backend-for-frontend

A BFF that signs the person in holds the session in its own cookie and sends the session as the bearer to Aouda. The browser never sees a key. The BFF's own key, if it has one, is for the calls it makes as itself, on a different client.

If the BFF (or another gateway) validates the session JWT itself, match `aud` to what the token carries. An ordinary sign-in with no `databases` limit is `aud: ["*"]`; a fixed audience of `auth` or `_auth` fails every such token. Details: [What a session token carries](reference.md#what-a-session-token-carries).
