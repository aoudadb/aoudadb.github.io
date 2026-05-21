---
title: "Testing"
nav_order: 3
parent: "Getting Started"
---

# Testing Applications Built on Aouda

This guide covers how to write **integration tests for applications that use Aouda** — including applications that use Aouda Auth (signup, signin, OIDC Discovery, JWTs).

> **Before reading this guide:** If you are testing Aouda itself (building Aouda's engine tests), use the existing patterns in `tests/Aouda.Server.Tests/` and `tests/Aouda.Cli.Tests/`. This guide is for **consumer application developers** testing their own code that talks to Aouda.

**Related:** [Getting-Started.md](Getting-Started.md) (embedded vs server), [Getting-Started-Auth.md](Getting-Started-Auth.md) (application auth), [ADR 0024 — Testing package](../decisions/0024-testing-package.md).

---

## Table of Contents

1. [Why Aouda.Testing?](#1-why-aouda-testing)
2. [Installation](#2-installation)
3. [Basic Usage — No Auth](#3-basic-usage--no-auth)
4. [Auth-Enabled Usage](#4-auth-enabled-usage)
5. [Auth Helpers — Creating Users and Tokens](#5-auth-helpers--creating-users-and-tokens)
6. [Testing a Gateway or Backend API](#6-testing-a-gateway-or-backend-api)
7. [xUnit Patterns](#7-xunit-patterns)
8. [NUnit Patterns](#8-nunit-patterns)
9. [MSTest Patterns](#9-mstest-patterns)
10. [Multi-Database Setups](#10-multi-database-setups)
11. [Test Isolation and Parallel Tests](#11-test-isolation-and-parallel-tests)
12. [CI/CD](#12-cicd)
13. [Choosing the Right Testing Strategy](#13-choosing-the-right-testing-strategy)

---

## 1. Why Aouda.Testing?

### The Problem Without It

Aouda Auth requires the HTTP server. The OIDC Discovery endpoint, JWKS endpoint, JWT middleware, signup, signin, refresh, and signout flows are all HTTP-layer features — they are not available in `Aouda.Embedded`.

This means that if your application uses Aouda Auth, writing integration tests that exercise the real auth flow requires a running Aouda server:

```bash
# Without Aouda.Testing — you need this running before dotnet test:
aouda dev --database myapp --auth
# → prints mk_anon_... and mk_svc_... keys
# → tests only work if this process is running
```

This is **friction**. It breaks `dotnet test` self-sufficiency, complicates CI pipelines, and blocks the AI-agent workflow entirely.

### What Aouda.Testing Provides

`Aouda.Testing` spins up a **complete, in-process Aouda HTTP server** inside your test project. No real ports, no external process, no setup steps:

```csharp
await using var aouda = await AoudaTestServer.StartAsync(new AoudaTestServerOptions
{
    Databases = [new TestDatabase("myapp", EnableAuth: true)]
});

// aouda is a fully functional Aouda server with auth enabled.
// HttpClient talks to the in-process server — no network involved.
// DisposeAsync stops the server and deletes all ephemeral data.
```

### When to Use Aouda.Testing

| Test Type | Tool | Why |
|-----------|------|-----|
| Unit tests for logic that calls Aouda | Mock `IAoudaClient` / `IUserService` | Fast, no infrastructure, tests your logic in isolation |
| Integration tests for auth flows (signin, refresh, OIDC) | **Aouda.Testing** | Real auth behavior; tests that your code integrates correctly |
| Integration tests for data operations with auth enforcement | **Aouda.Testing** | Real PLS/permission enforcement |
| Integration tests for a gateway that calls Aouda Auth | **Aouda.Testing** + `WebApplicationFactory` | Real end-to-end flow through your API |
| Load and stress tests | `Aouda.TestHarness` (separate Aouda tool) | Not a consumer concern |

> **Rule of thumb:** Mock Aouda for unit tests that test your business logic. Use `Aouda.Testing` for tests that test how your application **integrates** with Aouda.

---

## 2. Installation

Add the `Aouda.Testing` package to your test project:

```xml
<ItemGroup>
  <PackageReference Include="Aouda.Testing" Version="0.1.0" />
</ItemGroup>
```

> `Aouda.Testing` is MIT-licensed. It can be referenced by any project regardless of license.
>
> **Do not add `Aouda.Testing` to production application projects.** It is a test-only dependency. Use `PrivateAssets="all"` if your test project outputs a NuGet package:
> ```xml
> <PackageReference Include="Aouda.Testing" Version="0.1.0" PrivateAssets="all" />
> ```

`Aouda.Testing` automatically pulls in the full Aouda server stack as a transitive dependency. This is expected — you are running the actual Aouda engine inside your tests.

---

## 3. Basic Usage — No Auth

The simplest case: a server with one database and no authentication.

```csharp
await using var aouda = await AoudaTestServer.StartAsync();

// Verify the server is up
var health = await aouda.HttpClient.GetAsync("/health");
health.EnsureSuccessStatusCode();

// Insert and query data via HTTP
using var insertResponse = await aouda.HttpClient.PostAsJsonAsync(
    "/api/databases/default/tables/orders/rows",
    new { rows = new[] { new { id = 1, total = 99.99 } } });
Assert.True(insertResponse.IsSuccessStatusCode);
```

By default, `StartAsync()` creates one database named `"default"` with no authentication. Data is **ephemeral** — deleted when `DisposeAsync` is called.

- **`HttpClient`** — Pre-configured for the in-process server; use it for raw HTTP assertions.
- **`ServerUrl`** — Base URL string (always `"http://localhost"` with TestHost).
- **`DataPath`** — On-disk directory for this run. With default options, this is a **temporary** folder removed in `DisposeAsync`.

> **Note on typed clients for no-auth databases:** `CreateClient(name)` and `CreateAnonClient(name)` require auth to be enabled for that database — they call `ServiceKey`/`AnonKey` which throw otherwise. For databases without auth, use `server.HttpClient` directly, or construct `AoudaClient` manually pointing at `server.HttpClient`.

### Configuring the Database Name

```csharp
await using var aouda = await AoudaTestServer.StartAsync(new AoudaTestServerOptions
{
    Databases = [new TestDatabase("myapp")]
});

// Use HttpClient directly for a no-auth database
using var response = await aouda.HttpClient.GetAsync(
    "/api/databases/myapp/tables/orders/query");
```

---

## 4. Auth-Enabled Usage

### Starting a Server with Auth

```csharp
await using var aouda = await AoudaTestServer.StartAsync(new AoudaTestServerOptions
{
    Databases = [new TestDatabase("myapp", EnableAuth: true)]
});
```

When `EnableAuth: true`, the database is linked to a Aouda auth database (`_auth`) and two API keys are generated automatically.

### Accessing the Keys

```csharp
string serviceKey = aouda.ServiceKey("myapp");  // mk_svc_... (full access, never share with clients)
string anonKey    = aouda.AnonKey("myapp");      // mk_anon_... (anonymous role, safe for frontends)
```

### OIDC Authority for JWT Validation

If your application validates Aouda JWTs using `options.Authority` (standard ASP.NET Core JWT Bearer):

```csharp
string oidcAuthority = aouda.OidcAuthority("myapp");
// → "http://localhost/api/databases/myapp"
// → OIDC discovery document at: {oidcAuthority}/auth/.well-known/openid-configuration
// → Use as: options.Authority = oidcAuthority
```

### Using the Service-Role Client

The service-role client has full access to the database and bypasses Partition-Level Security — use it for admin operations and test setup:

```csharp
var adminClient = aouda.CreateClient("myapp"); // service_role key
await adminClient.GetTable("products").InsertAsync(new { id = 1, name = "Widget", tenant_id = "acme" });
```

### Using the Anon Client

The anon client presents the `anonymous` role — same as an unauthenticated frontend:

```csharp
var anonClient = aouda.CreateAnonClient("myapp"); // anon key

// Can access auth endpoints (signup, signin)
// Cannot access data tables without PLS-compliant JWT
```

---

## 5. Auth Helpers — Creating Users and Tokens

Test setup often needs to create users and obtain tokens. `Aouda.Testing` provides helpers that call the auth engine directly — bypassing the HTTP layer for maximum speed.

### Creating a User

```csharp
string userId = await aouda.CreateUserAsync("myapp", "alice@test.com", "Pass123!");
// User created with the default "user" role. Returns the new user's ID string.
```

### Signing In (Getting a Token)

```csharp
string token = await aouda.SignInAsync("myapp", "alice@test.com", "Pass123!");
// token is a valid RS256 JWT that your application can validate via OIDC Discovery
```

### Getting a Pre-Authenticated HttpClient

The most common test pattern: create a user, sign in, and get an `HttpClient` that sends `Authorization: Bearer <token>` on every request.

```csharp
HttpClient aliceClient = await aouda.CreateUserHttpClientAsync(
    "myapp", "alice@test.com", "Pass123!");

// All requests from aliceClient carry Alice's JWT
var response = await aliceClient.GetAsync("/api/databases/myapp/tables/orders/query");
```

### Why These Helpers Use the Engine Directly

`CreateUserAsync` and `SignInAsync` call `IUserService` and `ITokenService` inside the in-process server — they do not go through HTTP. This means:

- Setup is ~0.1 ms, not ~5 ms
- No `Authorization: Bearer` header needed for setup calls
- The first request that touches the auth HTTP API is your test itself

The only operations that go through the HTTP layer are the ones you are actually testing.

---

## 6. Testing a Gateway or Backend API

The most powerful pattern: test your entire application stack with Aouda as the real auth backend.

Here is the standard setup for a .NET API gateway (`WebApplicationFactory`) that authenticates via Aouda Auth:

```csharp
public class AuthControllerTests : IClassFixture<AoudaTestFixture>, IAsyncLifetime
{
    private readonly AoudaTestFixture _aouda;
    private WebApplicationFactory<Program> _factory = null!;
    private HttpClient _api = null!;

    public AuthControllerTests(AoudaTestFixture aouda) => _aouda = aouda;

    public async Task InitializeAsync()
    {
        _factory = new WebApplicationFactory<Program>()
            .WithWebHostBuilder(b => b.ConfigureServices(services =>
            {
                // Override your application's Aouda connection settings
                // to point at the in-process test server:
                services.Configure<AoudaAuthConfig>(o =>
                {
                    o.ServerUrl    = _aouda.Server.ServerUrl;
                    o.DatabaseName = "derive";
                    o.ServiceKey   = _aouda.Server.ServiceKey("derive");
                    o.Authority    = _aouda.Server.OidcAuthority("derive");
                    o.Audience     = "_auth";
                });
            }));

        _api = _factory.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _api.Dispose();
        await _factory.DisposeAsync();
    }

    [Fact]
    public async Task Login_ValidCredentials_ReturnsTokens()
    {
        // Arrange: create a user in the in-process Aouda server
        await _aouda.Server.CreateUserAsync("derive", "alice@test.com", "Pass123!");

        // Act: call your application's login endpoint (not Aouda's directly)
        var loginResponse = await _api.PostAsJsonAsync("/auth/login", new
        {
            email = "alice@test.com",
            password = "Pass123!"
        });

        // Assert: your API returns tokens
        loginResponse.EnsureSuccessStatusCode();
        var body = await loginResponse.Content.ReadFromJsonAsync<LoginResult>();
        Assert.NotNull(body?.AccessToken);
    }
}
```

**Derive / gateway pattern:** If your app talks to Aouda via a base URL, inject the test server's base address (from `AoudaTestServer.ServerUrl` and your factory's `HttpClient.BaseAddress`) through configuration or `WebHostBuilder` overrides so the same code paths run in tests as in production.

Exact JWT and OIDC wiring for .NET and TypeScript clients is covered in [Getting-Started-Auth.md](Getting-Started-Auth.md); this guide only ensures the **Aouda side** of the contract is available inside `dotnet test`.

---

## 7. xUnit Patterns

### Pattern 1: `IClassFixture` — Server per Test Class

The package ships `AoudaTestFixture` (`Aouda.Testing.Adapters.xUnit`). Because `Aouda.Testing` is a library that does not depend on xUnit, `AoudaTestFixture` does not implement `IAsyncLifetime` directly — your concrete fixture class must also implement it:

```csharp
using Aouda.Testing;
using Aouda.Testing.Adapters.xUnit;
using Xunit;

public sealed class MyAoudaFixture : AoudaTestFixture, IAsyncLifetime
{
    protected override AoudaTestServerOptions Options => new()
    {
        Databases = [new TestDatabase("myapp", EnableAuth: true)]
    };
}

public class ApiTests : IClassFixture<MyAoudaFixture>
{
    private readonly MyAoudaFixture _fixture;

    public ApiTests(MyAoudaFixture fixture) => _fixture = fixture;

    [Fact]
    public async Task Health_ok()
    {
        var response = await _fixture.Server.HttpClient.GetAsync("/health");
        response.EnsureSuccessStatusCode();
    }
}
```

### Pattern 2: `ICollectionFixture` — Shared Server Across Multiple Test Classes

```csharp
// Define a collection
[CollectionDefinition("Aouda")]
public class AoudaCollection : ICollectionFixture<MyAoudaFixture> { }

// Apply to test classes
[Collection("Aouda")]
public class OrderTests
{
    private readonly MyAoudaFixture _fixture;
    public OrderTests(MyAoudaFixture fixture) => _fixture = fixture;
    // ...
}

[Collection("Aouda")]
public class ProductTests
{
    private readonly MyAoudaFixture _fixture;
    public ProductTests(MyAoudaFixture fixture) => _fixture = fixture;
    // ...
}
```

> **Warning on shared state:** When multiple test classes share a server, they share all database state. Tests must either clean up after themselves or use unique table/row identifiers. For most scenarios, per-class fixtures (`IClassFixture`) are simpler and safer.

### Pattern 3: Custom Fixture with Auth

```csharp
public class AuthFixture : AoudaTestFixture, IAsyncLifetime
{
    protected override AoudaTestServerOptions Options => new()
    {
        Databases = [new TestDatabase("myapp", EnableAuth: true)]
    };
}

public class AuthTests : IClassFixture<AuthFixture>
{
    private readonly AuthFixture _fixture;
    public AuthTests(AuthFixture fixture) => _fixture = fixture;

    [Fact]
    public async Task Signin_ValidUser_ReturnsJwt()
    {
        await _fixture.Server.CreateUserAsync("myapp", "test@example.com", "Pass123!");
        string token = await _fixture.Server.SignInAsync("myapp", "test@example.com", "Pass123!");
        Assert.False(string.IsNullOrEmpty(token));
    }
}
```

### `IClassFixture` vs `ICollectionFixture` and parallelism

- **`IClassFixture<T>`** — One server per **test class** (shared by all tests in the class).
- **`ICollectionFixture<T>`** — Share one server across **multiple test classes** in the same collection.

xUnit runs test classes in parallel by default. Two classes each with their own `IClassFixture` each get a **separate** fixture instance — and therefore separate `AoudaTestServer` instances (each with its own ephemeral `DataPath`). If you use a **shared** collection fixture, all tests in that collection share one server.

---

## 8. NUnit Patterns

### Shared Server for a Test Fixture

```csharp
using Aouda.Testing.Adapters.NUnit;
using NUnit.Framework;

[TestFixture]
public class OrderTests : AoudaNUnitFixture
{
    protected override AoudaTestServerOptions Options => new()
    {
        Databases = [new TestDatabase("myapp", EnableAuth: true)]
    };

    [Test]
    public async Task Insert_Order_IsQueryable()
    {
        var adminClient = Server.CreateClient("myapp");
        await adminClient.GetTable("orders").InsertAsync(new { id = 1, amount = 100.0m });
        var rows = await adminClient.GetTable("orders").ToListAsync();
        Assert.That(rows, Has.Count.GreaterThanOrEqualTo(1));
    }
}
```

`AoudaNUnitFixture` uses `[OneTimeSetUp]` and `[OneTimeTearDown]` to start and stop the server once per test fixture class.

### Shared Server Across Multiple Test Classes (SetUpFixture)

For assembly-wide or namespace-wide shared setup, wrap `AoudaNUnitFixture` in a NUnit `[SetUpFixture]`:

```csharp
[SetUpFixture]
public class AoudaSetup : AoudaNUnitFixture
{
    protected override AoudaTestServerOptions Options => new()
    {
        Databases = [new TestDatabase("myapp", EnableAuth: true)]
    };

    public static AoudaTestServer SharedServer { get; private set; } = null!;

    [OneTimeSetUp]
    public new async Task SetUpAsync()
    {
        await base.SetUpAsync();
        SharedServer = Server;
    }
}
```

Tests in the same namespace can then access `AoudaSetup.SharedServer` directly.

---

## 9. MSTest Patterns

`AoudaMSTestFixture` (`Aouda.Testing.Adapters.MSTest`) does **not** attach `[ClassInitialize]` / `[ClassCleanup]` on base static methods — MSTest static methods cannot be overridden for options injection. Instead call the provided `StartServerAsync` / `StopServerAsync` helpers from **your** class's static lifecycle methods:

```csharp
using Aouda.Testing;
using Aouda.Testing.Adapters.MSTest;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[TestClass]
public sealed class AoudaMstestTests : AoudaMSTestFixture
{
    [ClassInitialize]
    public static async Task ClassInit(TestContext _)
    {
        await StartServerAsync(new AoudaTestServerOptions
        {
            Databases = [new TestDatabase("myapp", EnableAuth: true)]
        });
    }

    [ClassCleanup]
    public static async Task ClassCleanup()
    {
        await StopServerAsync();
    }

    [TestMethod]
    public async Task Health_ok()
    {
        var response = await Server.HttpClient.GetAsync("/health");
        Assert.AreEqual(System.Net.HttpStatusCode.OK, response.StatusCode);
    }
}
```

---

## 10. Multi-Database Setups

### Multiple Databases on One Server

```csharp
await using var aouda = await AoudaTestServer.StartAsync(new AoudaTestServerOptions
{
    Databases =
    [
        new TestDatabase("orders",   EnableAuth: true),
        new TestDatabase("products", EnableAuth: true),
        new TestDatabase("analytics")              // no auth needed
    ]
});

// Each auth-enabled database gets its own service key and anon key
string ordersKey   = aouda.ServiceKey("orders");
string productsKey = aouda.ServiceKey("products");

// Analytics is open — use HttpClient directly (no auth key)
var analyticsResponse = await aouda.HttpClient.GetAsync("/api/databases/analytics/tables/events/query");
```

### Shared Auth Database Across Multiple Databases

When your application uses Pattern C (Standalone Auth Service) or has multiple databases sharing one user registry, Aouda's auth database linking handles this automatically:

```csharp
await using var aouda = await AoudaTestServer.StartAsync(new AoudaTestServerOptions
{
    Databases =
    [
        // First database with auth creates _auth automatically
        new TestDatabase("orders_db",   EnableAuth: true),
        // Second database with auth links to the same _auth
        new TestDatabase("products_db", EnableAuth: true),
    ]
});

// Same users, same sessions across both databases (single _auth database)
await aouda.CreateUserAsync("orders_db", "alice@test.com", "Pass123!");
// Alice can now sign in to either orders_db or products_db
```

---

## 11. Test Isolation and Parallel Tests

### Ephemeral by Default

Every `AoudaTestServer` uses a unique temp directory for its data. When `DisposeAsync` is called, that directory is deleted. This means:

- Two test classes using `IClassFixture<AoudaTestFixture>` each get their own server instance with clean state.
- Tests within the same class share a server — use unique IDs or clean up after each test.
- `dotnet test --parallel` works without cross-test contamination (each class has its own server).

### Running Tests in Parallel (xUnit)

By default, xUnit runs test classes in parallel. Each class gets its own `AoudaTestServer` via its own `IClassFixture` instance. No special configuration is needed.

If you use `ICollectionFixture` (shared server across classes), xUnit serializes all tests in the collection — the shared server is not accessed concurrently by default. Add `[Collection("Aouda")]` to all classes that should share.

### When You Need Persistence Within a Test Session

Rare scenario: your test must restart the server and verify that data survived. Use `DataPath`:

```csharp
var dataPath = Path.Combine(Path.GetTempPath(), $"aouda_test_{Guid.NewGuid():N}");
try
{
    // First session — write data
    await using (var aouda = await AoudaTestServer.StartAsync(new()
    {
        DataPath = dataPath,
        Databases = [new TestDatabase("myapp")]
    }))
    {
        await aouda.HttpClient.PostAsJsonAsync(
            "/api/databases/myapp/tables/settings/rows",
            new { rows = new[] { new { key = "version", value = "1" } } });
    }

    // Second session — verify data survived
    await using (var aouda = await AoudaTestServer.StartAsync(new()
    {
        DataPath = dataPath,
        Databases = [new TestDatabase("myapp")]
    }))
    {
        var response = await aouda.HttpClient.GetAsync(
            "/api/databases/myapp/tables/settings/query");
        Assert.True(response.IsSuccessStatusCode);
    }
}
finally
{
    Directory.Delete(dataPath, recursive: true);
}
```

### Setup Mode

The test server applies the same **disabled setup mode** integration hook used inside Aouda's own tests, so first-run setup wizards do not block automated tests.

---

## 12. CI/CD

No special CI configuration is needed. `Aouda.Testing` uses `Microsoft.AspNetCore.TestHost` — the server runs entirely in-memory with no real ports. If `dotnet test` passes locally, it passes in CI.

There is no requirement for:
- A running Aouda process
- Docker
- Port availability
- Environment variables with API keys

```yaml
# GitHub Actions — works as-is
- name: Run tests
  run: dotnet test --no-build --verbosity minimal
```

Keys generated by `AoudaTestServer` are never printed to stdout or logs. They are only accessible via `ServiceKey()` and `AnonKey()` within the test code.

---

## 13. Choosing the Right Testing Strategy

### Decision Tree

```
Do your tests exercise Aouda Auth flows?
│
├── No (data operations only, no auth)
│   ├── Operations are purely in-memory, process-local?
│   │   └── YES → Aouda.Embedded (no HTTP needed)
│   └── Operations go through HTTP / test gateway integration?
│       └── YES → Aouda.Testing (AoudaTestServer without auth)
│
└── Yes (auth flows involved)
    ├── Testing your own business logic that CALLS auth methods?
    │   └── Mock IAoudaAuthServiceClient or similar → unit test, no Aouda needed
    └── Testing how your application INTEGRATES with Aouda Auth?
        └── Aouda.Testing (AoudaTestServer with EnableAuth: true)
```

### Comparison Table

| | `Aouda.Embedded` | `Aouda.Testing` | Running `aouda dev` |
|---|---|---|---|
| **Auth flows** | ❌ Not available | ✅ Full auth | ✅ Full auth |
| **External process** | ❌ None | ❌ None | ✅ Required |
| **Ports used** | None | None | Real port (5433) |
| **Test isolation** | Per-instance | Per-instance (ephemeral) | Shared state |
| **CI-friendly** | ✅ Zero setup | ✅ Zero setup | ⚠️ Process management |
| **Data operations** | ✅ Full | ✅ Full | ✅ Full |
| **HTTP client access** | ❌ | ✅ | ✅ |
| **OIDC / JWKS** | ❌ | ✅ | ✅ |
| **Use case** | Unit tests, local data | Integration tests with auth | Local dev / manual testing |

### Recommended Project Structure

A well-structured test suite for a Aouda application typically has two layers:

```
MyApp.Tests/
├── Unit/
│   ├── OrderServiceTests.cs        ← mock Aouda client, test business logic
│   └── AuthMiddlewareTests.cs      ← mock JWT validation, test middleware logic
└── Integration/
    ├── AoudaFixture.cs             ← custom AoudaTestFixture for the app
    ├── AuthControllerTests.cs      ← Aouda.Testing + WebApplicationFactory
    └── DataApiTests.cs             ← Aouda.Testing for real data with auth
```

Unit tests mock Aouda entirely — they are fast and test your application logic in isolation. Integration tests use `Aouda.Testing` to test that your application actually works with a real Aouda server and real auth. Both layers complement each other.

---

## Quick Reference

| Type | Role |
|------|------|
| **`AoudaTestServer`** | `StartAsync` / `DisposeAsync`, `HttpClient`, `DataPath`, `ServerUrl`, keys, clients, auth helpers |
| **`AoudaTestServerOptions`** | `Databases`, `DataPath`, `Port` (informational under TestHost) |
| **`TestDatabase`** | `Name`, `EnableAuth` |
| **`AoudaTestFixture`** | xUnit-oriented; also implement **`IAsyncLifetime`** in your concrete class |
| **`AoudaNUnitFixture`** | NUnit; override `Options`; `[OneTimeSetUp]`/`[OneTimeTearDown]` handled |
| **`AoudaMSTestFixture`** | MSTest; call **`StartServerAsync`** / **`StopServerAsync`** from your `[ClassInitialize]` / `[ClassCleanup]` |

---

## See Also

- [Getting Started with Aouda](Getting-Started.md) — Core data operations and embedded mode
- [Aouda Application Auth Service Guide](Getting-Started-Auth.md) — Auth architecture, quick start, patterns
- [ADR 0024: Aouda.Testing Package](../decisions/0024-testing-package.md) — Design decisions behind this package
- [ADR 0023: Authentication & Authorization](../decisions/0023-authentication-and-authorization.md) — Auth architecture overview
