---
title: "Email, SMS & Notifications"
nav_order: 7
parent: "Auth and Authorization"
---

# Email, SMS & Notifications

> Part of the [Application Auth Guide](../getting-started/auth.md). Configure these settings on the **Aouda server** (not in your consumer application). Your app calls auth HTTP endpoints; Aouda delivers OTPs by email or SMS when the corresponding provider is enabled.

---

## 1. Overview

Application Auth uses server-level notification services:

| Service | Used for | Provider when configured | Default (no provider) |
|---------|----------|--------------------------|------------------------|
| **Email** (`IEmailService`) | Password reset OTP, invite emails (`sendInviteEmail`) | [SendGrid](#3-email-sendgrid) | `NullEmailService` — logs a warning, **does not send** |
| **SMS** (`ISmsService`) | MFA phone OTP (`POST .../auth/mfa/challenge` for `type: phone`) | [GatewayAPI](#4-sms-gatewayapi) | `NullSmsService` — logs a warning, **does not send** |

**Important:**

- Providers are registered **once per Aouda server process** and shared by all application auth databases on that server.
- Delivery is **best-effort**: auth endpoints still return success even if SendGrid/GatewayAPI fails; failures are logged as warnings.
- OTPs are **never** stored in plain text and **never** appear in server logs (only "email not sent" / "SMS not sent" when the null provider is active).
- There is **no** API to retrieve an OTP after the fact. For real password-reset or MFA testing you must configure a provider (or use admin password override instead).

**What needs which channel:**

| Feature | Email | SMS |
|---------|:-----:|:---:|
| Self-service password reset (`request-password-reset`) | Required | — |
| Invite / first-time password (`sendInviteEmail`, `POST .../invite`) | Required | — |
| MFA TOTP (authenticator app) | — | — |
| MFA phone factor | — | Required |

See [Use Case: Self-Service Password Reset](use-cases.md#20-use-case-self-service-password-reset) and [Use Case: Two-Factor Authentication (MFA)](use-cases.md#21-use-case-two-factor-authentication-mfa).

---

## 2. Configuration

All settings live under the `Aouda:Auth` configuration section. They apply to `aouda start`, Docker, and embedded ASP.NET hosts that call `AddAoudaServer(configuration)`.

### 2.1 appsettings.json (recommended for local development)

Place `appsettings.json` in the directory from which you run `aouda start` (or pass `--config` via the host's standard ASP.NET configuration if you embed the server).

```json
{
  "Aouda": {
    "DataPath": "./data",
    "Port": 5433,
    "Auth": {
      "Email": {
        "Provider": "sendgrid",
        "SendGridApiKey": "SG.xxxxxxxxxxxx",
        "FromAddress": "noreply@yourdomain.com",
        "FromName": "Your App",
        "InviteUrl": "https://app.yourdomain.com/set-password",
        "PasswordResetUrl": "https://app.yourdomain.com/set-password"
      },
      "Sms": {
        "Provider": "gatewayapi",
        "ApiKey": "your-gatewayapi-token",
        "Sender": "YourApp"
      }
    }
  }
}
```

Omit `Email` or set `Provider` to anything other than `sendgrid` to use the null email provider. Omit `Sms` or set `Provider` to anything other than `gatewayapi` to use the null SMS provider.

`InviteUrl` and `PasswordResetUrl` are optional but strongly recommended — without them the email contains only a bare OTP code with no link to your app. See [§3.4](#34-set-password-deep-link-app-url-configuration).

### 2.2 Environment variables

ASP.NET Core nested configuration uses `__` (double underscore):

| Setting | Environment variable example |
|---------|------------------------------|
| Email provider | `Aouda__Auth__Email__Provider=sendgrid` |
| SendGrid API key | `Aouda__Auth__Email__SendGridApiKey=SG.xxx` |
| From address | `Aouda__Auth__Email__FromAddress=noreply@example.com` |
| From display name | `Aouda__Auth__Email__FromName=My App` |
| Invite deep-link URL | `Aouda__Auth__Email__InviteUrl=https://app.example.com/set-password` |
| Password-reset deep-link URL | `Aouda__Auth__Email__PasswordResetUrl=https://app.example.com/set-password` |
| SMS provider | `Aouda__Auth__Sms__Provider=gatewayapi` |
| GatewayAPI token | `Aouda__Auth__Sms__ApiKey=...` |
| SMS sender label | `Aouda__Auth__Sms__Sender=MyApp` |

`aouda start` also loads variables prefixed with `AOUDA_` for top-level server options (for example `AOUDA_DATA_PATH`). Notification keys use the `Aouda__Auth__...` form above.

### 2.3 Docker

```bash
docker run -p 5433:5433 -v aouda-data:/data \
  -e Aouda__Auth__Email__Provider=sendgrid \
  -e Aouda__Auth__Email__SendGridApiKey=SG.xxx \
  -e Aouda__Auth__Email__FromAddress=noreply@yourdomain.com \
  -e "Aouda__Auth__Email__FromName=Your App" \
  -e Aouda__Auth__Email__InviteUrl=https://app.yourdomain.com/set-password \
  -e Aouda__Auth__Email__PasswordResetUrl=https://app.yourdomain.com/set-password \
  -e Aouda__Auth__Sms__Provider=gatewayapi \
  -e Aouda__Auth__Sms__ApiKey=your-token \
  -e Aouda__Auth__Sms__Sender=YourApp \
  aouda/server
```

Restart the server after changing notification configuration.

### 2.4 Complete settings reference

| Setting | Type | Default | Valid values | Notes |
|---------|------|---------|--------------|-------|
| `Aouda:Auth:Email:Provider` | string? | `null` | `sendgrid` (case-insensitive) enables SendGrid; any other value → null provider | Server-wide |
| `Aouda:Auth:Email:SendGridApiKey` | string? | `null` | SendGrid API key with Mail Send permission | Bearer token on `https://api.sendgrid.com` |
| `Aouda:Auth:Email:FromAddress` | string? | `null` | Verified sender in SendGrid | Required for real delivery |
| `Aouda:Auth:Email:FromName` | string? | `"Aouda"` | Display name in From header and email body | |
| `Aouda:Auth:Email:InviteUrl` | string? | `null` | Full URL of your app's set-password page | When set, invite email includes a clickable link; see §3.4 |
| `Aouda:Auth:Email:PasswordResetUrl` | string? | `null` (falls back to `InviteUrl`) | Full URL of your app's reset-password page | Defaults to `InviteUrl` when not set; see §3.4 |
| `Aouda:Auth:Sms:Provider` | string? | `null` | `gatewayapi` (case-insensitive) enables GatewayAPI; any other value → null provider | Server-wide |
| `Aouda:Auth:Sms:ApiKey` | string? | `null` | GatewayAPI API token | Sent as `Authorization: Token <key>` |
| `Aouda:Auth:Sms:Sender` | string? | `"Aouda"` | Alphanumeric sender id shown to recipient | GatewayAPI account must allow sender |

Related server auth bootstrap (unrelated to app-user email/SMS):

| Setting | Purpose |
|---------|---------|
| `Aouda:Auth:RootUser:Email` | Optional first server admin email (config bootstrap) |
| `Aouda:Auth:RootUser:Password` | Optional first server admin password — remove after setup |

---

## 3. Email (SendGrid)

When `Aouda:Auth:Email:Provider` is `sendgrid`, Aouda uses the SendGrid v3 Mail Send API (`POST /v3/mail/send`).

### 3.1 Email types

Email content depends on whether `InviteUrl` / `PasswordResetUrl` are configured (see [§3.4](#34-set-password-deep-link-app-url-configuration)).

**With URL configured (recommended):**

| Flow | Trigger | Subject | Body |
|------|---------|---------|------|
| Password reset | `POST .../auth/request-password-reset` | `Reset your {FromName} password` | Link to reset page + manual-entry code + 15-minute expiry note |
| Invite | `POST .../admin/users` with `sendInviteEmail: true`, or `POST .../admin/users/{id}/invite` | `You've been invited to {FromName}` | Link to set-password page + manual-entry code + 15-minute expiry note |

Example invite email body:

```
You've been invited to Your App.

Set your password here:
https://app.yourdomain.com/set-password?otp=984094&email=user%40example.com

If the link does not open, visit the page and enter this code:
984094

This code expires in 15 minutes. If you did not expect this invitation, ignore this email.
```

**Without URL configured (bare-code fallback):**

| Flow | Subject | Body |
|------|---------|------|
| Password reset | `Reset your password` | `Your password reset code is: {otp}` + expiry note |
| Invite | `You've been invited — set your password` | `You've been invited. Use this code to set your password: {otp}` + expiry note |

Both flows use the same 6-digit OTP and `POST .../auth/reset-password` to complete the password change.

### 3.2 SendGrid setup checklist

1. Create a SendGrid account and verify your sender domain or single sender.
2. Create an API key with **Mail Send** (restricted key is fine).
3. Set `FromAddress` to a verified sender.
4. Configure `appsettings.json` or environment variables (§2), including `InviteUrl` and `PasswordResetUrl`.
5. Restart Aouda (`aouda start`).
6. Trigger a reset for a **registered** user and check SendGrid activity; check Aouda logs for `SendGridEmailService: non-2xx` warnings.

### 3.3 Local development without SendGrid

With no provider (default), `request-password-reset` still returns `200 { "ok": true }` but **no email is sent**. Log line:

```text
NullEmailService: password reset email not sent to 'user@example.com' (no email provider configured). Configure Aouda:Auth:Email:Provider=sendgrid to enable email delivery.
```

You cannot complete the customer reset flow without either SendGrid or an admin override (`PUT .../admin/users/{id}/password`). This is intentional (anti-enumeration and security).

### 3.4 Set-password deep link (app URL configuration)

Out of the box, invite and password-reset emails contain only a bare 6-digit OTP. Configuring `InviteUrl` and `PasswordResetUrl` enables Aouda to include a clickable link directly to your app's set-password page — the same pattern used by Supabase (`SITE_URL`), Firebase Auth (`continueUrl`), and Auth0.

#### How it works

1. Aouda generates the OTP and appends it as query parameters to your configured URL:
   ```
   {InviteUrl}?otp={otp}&email={url-encoded-email}
   ```
   Example: `https://app.yourdomain.com/set-password?otp=984094&email=user%40example.com`

2. Aouda sends the email with both the clickable link **and** the bare code (so the user can still complete the flow if their email client or corporate security gateway strips or follows the link).

3. Your app's set-password page reads `otp` and `email` from the query string to pre-fill the form.

4. When the user submits, your page calls `POST .../auth/reset-password` with the anon key — no secret is required on the page itself.

#### Configuration

Add to Aouda's server config (both URLs often point to the same page):

```json
{
  "Aouda": {
    "Auth": {
      "Email": {
        "InviteUrl": "https://app.yourdomain.com/set-password",
        "PasswordResetUrl": "https://app.yourdomain.com/set-password"
      }
    }
  }
}
```

- **`InviteUrl`** — used in invite emails sent when a user is admin-created with `sendInviteEmail: true`.
- **`PasswordResetUrl`** — used in self-service password-reset emails. Falls back to `InviteUrl` when not set (useful when both flows use the same page).
- Both URLs must be a base path **without** query parameters; Aouda appends `?otp=...&email=...` automatically.

#### What your set-password page must do

1. **Read** `otp` and `email` from the query string on page load and pre-fill the form inputs.
2. **On submit**: call `POST /api/databases/{db}/auth/reset-password` with the anon key:
   ```json
   { "email": "user@example.com", "otp": "984094", "newPassword": "NewPassword123!" }
   ```
3. On success, Aouda returns `aal1` tokens — sign the user in and redirect to your app.
4. If MFA is enrolled, the login response will include `"mfaRequired": true` — redirect to your MFA challenge page.

The page does **not** need a service key or any secret. `reset-password` is a public endpoint authenticated only by the OTP.

#### Why not magic links?

Single-use tokens embedded directly in URLs are consumed by corporate email security scanners (Barracuda, Proofpoint, etc.) before the user sees the email. The OTP-with-prefill pattern is the safer alternative: the link pre-fills the form, but the user must still click "Set Password" — protecting against scanner consumption while remaining low-friction.

---

## 4. SMS (GatewayAPI)

When `Aouda:Auth:Sms:Provider` is `gatewayapi`, Aouda sends MFA phone challenges via GatewayAPI (`POST https://gatewayapi.eu/rest/mtsms`).

### 4.1 Message format

```text
Your Aouda verification code is: {otp}. Expires in 10 minutes.
```

Phone numbers must be **E.164** at enrolment (for example `+447911123456`).

### 4.2 GatewayAPI setup checklist

1. Create a GatewayAPI account and obtain an API token.
2. Configure an allowed sender name matching `Aouda:Auth:Sms:Sender`.
3. Set configuration (§2) and restart the server.
4. Enrol a phone factor (`POST .../auth/mfa/enroll` with `type: "phone"`), then `POST .../auth/mfa/challenge` and confirm SMS delivery.

### 4.3 Local development without SMS

TOTP MFA does not require SMS. For phone MFA, without GatewayAPI you will see:

```text
NullSmsService: OTP SMS not sent to '+44...' (no SMS provider configured).
```

The challenge is still created; verification will fail unless you use TOTP or recovery codes instead.

---

## 5. End-to-end local test (password reset)

Prerequisites: Aouda CLI, SendGrid credentials, an auth-enabled database with API keys. Full local server setup is in [Reference §27](reference.md#27-local-developer-setup-for-consumer-applications).

```powershell
# 1. Server directory with appsettings.json (§2.1, including InviteUrl / PasswordResetUrl)
cd C:\dev\aouda-derive
aouda start --port 5433 --data-dir .\data

# 2. Bootstrap server admin (first run only) — see setup.md
# 3. Create auth-enabled DB and save mk_anon_ / mk_svc_ keys — see setup.md §7

# 4. Sign up or admin-create a user
curl -X POST http://localhost:5433/api/databases/myapp/auth/signup `
  -H "Authorization: Bearer mk_anon_..." `
  -H "Content-Type: application/json" `
  -d '{ "email": "alice@example.com", "password": "SecurePass123!" }'

# 5. Request reset (email must be configured)
curl -X POST http://localhost:5433/api/databases/myapp/auth/request-password-reset `
  -H "Authorization: Bearer mk_anon_..." `
  -H "Content-Type: application/json" `
  -d '{ "email": "alice@example.com" }'

# 6. Read OTP from email link or body, then reset
curl -X POST http://localhost:5433/api/databases/myapp/auth/reset-password `
  -H "Authorization: Bearer mk_anon_..." `
  -H "Content-Type: application/json" `
  -d '{ "email": "alice@example.com", "otp": "482391", "newPassword": "NewSecure456!" }'
```

With `PasswordResetUrl` configured, the email will contain a link like
`https://app.yourdomain.com/set-password?otp=482391&email=alice%40example.com`.
Your consumer application's page reads these query params to pre-fill the form (see §3.4).

---

## 6. Consumer application configuration

Notification keys belong in **Aouda's** server config, not in your app's `appsettings.Development.json`.

Your application needs:

| Key | Purpose |
|-----|---------|
| `AoudaAuth:ServerUrl` | Aouda base URL |
| `AoudaAuth:DatabaseName` | App database name (auth endpoints are under this name) |
| `AoudaAuth:Authority` | `http://localhost:5433/api/databases/myapp` for JWT validation |
| `AoudaAuth:AnonKey` or `ServiceKey` | `mk_anon_...` for public reset endpoints; `mk_svc_...` for admin invite/create |

Example (app repo):

```json
{
  "AoudaAuth": {
    "Authority": "http://localhost:5433/api/databases/myapp",
    "Audience": "_auth",
    "ServerUrl": "http://localhost:5433",
    "DatabaseName": "myapp",
    "AnonKey": "mk_anon_...",
    "ServiceKey": "mk_svc_..."
  }
}
```

Use the **anon** key for `request-password-reset` and `reset-password` from browser-facing code paths (same as signup/signin). Use the **service** key only on trusted backends (admin user create, invite resend).

---

## 7. Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `200` on request-reset but no email | Null email provider or SendGrid failure | Check logs for `NullEmailService` or `SendGridEmailService`; verify §3.2 |
| Email arrives but contains only a bare code, no link | `InviteUrl` / `PasswordResetUrl` not configured | Add both keys to Aouda server config (§3.4) |
| Reset always returns `AUTH_RESET_TOKEN_INVALID` | Wrong OTP, unregistered email, expired token, or exhausted attempts (5 wrong tries) | Request new code; confirm user exists in auth DB |
| Invite email not sent | `sendInviteEmail` not set or email not configured | Admin create with `"sendInviteEmail": true`; configure SendGrid |
| MFA challenge created but no SMS | Null SMS provider | Configure GatewayAPI (§4) or use TOTP |
| SendGrid 403 in logs | Unverified `FromAddress` | Verify sender in SendGrid dashboard |
| Config ignored after edit | Server not restarted | Restart `aouda start` or container |

---

## See also

- [Setup & User Flows](setup.md) — Enable auth, API keys, signup/signin
- [Use Cases](use-cases.md) — Password reset (§20), MFA (§21), onboarding (§19)
- [Reference](reference.md) — Endpoint tables, errors, local developer setup (§27)
- [Local developer setup](reference.md#27-local-developer-setup-for-consumer-applications) — `aouda start`, keys, IDE workflows
