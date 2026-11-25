---
title: "Behind a reverse proxy"
nav_order: 2
parent: "Deployment"
---

# Behind a reverse proxy

Aouda records **client IP** for per-IP rate limits (`auth_signin` 20/min, `auth_signup` 5/min, password-reset 20/min), the unauthenticated identity-quota fallback, lockout attribution, and every `_audit_log` row.

`HttpContext.Connection.RemoteIpAddress` is the **TCP peer**. Put nginx, Caddy, a cloud load balancer, or a CDN in front — which any public data-plane deployment does — and every request appears to come from the proxy. All of those controls then share **one** bucket: one attacker starves login for everyone, their own attempts are no longer isolated, and audit rows cannot attribute an incident.

**Until you configure trusted proxies, per-IP rate limits, lockout attribution, and audit-log client IPs are wrong behind a reverse proxy.** Direct exposure of Kestrel (no proxy) does not need this; leave it off.

Aouda does **not** honour `X-Forwarded-For` by default. Loopback is **not** trusted unless you list it. Honouring the header with an empty trust list is a startup error — that configuration lets any client spoof its address.

First-run admin creation (`POST /api/auth/setup`) always uses the **TCP peer**, never `X-Forwarded-For`. A spoofed `X-Forwarded-For: 127.0.0.1` cannot unlock setup from off-box.

---

## Configure

Enable the feature **and** name the proxies that terminate TLS in front of Aouda. Both are required.

```json
{
  "Aouda": {
    "ForwardedHeaders": {
      "Enabled": true,
      "KnownProxies": "10.0.0.4",
      "KnownNetworks": "10.0.0.0/8",
      "ForwardLimit": 1
    }
  }
}
```

| Key | Env | CLI | Default |
|---|---|---|---|
| `Aouda:ForwardedHeaders:Enabled` | `AOUDA_FORWARDEDHEADERS__ENABLED` | `--trusted-proxies-enabled` | `false` |
| `Aouda:ForwardedHeaders:KnownProxies` | `AOUDA_FORWARDEDHEADERS__KNOWNPROXIES` | `--trusted-proxies` | unset |
| `Aouda:ForwardedHeaders:KnownNetworks` | `AOUDA_FORWARDEDHEADERS__KNOWNNETWORKS` | `--trusted-proxy-networks` | unset |
| `Aouda:ForwardedHeaders:ForwardLimit` | `AOUDA_FORWARDEDHEADERS__FORWARDLIMIT` | — | `1` |

`KnownProxies` is a comma-separated list of IP literals. `KnownNetworks` is a comma-separated list of CIDR blocks. `ForwardLimit` is how many forwarded hops to take — `1` for a single reverse proxy; raise it only when you have a documented chain (CDN + load balancer) and every hop is in the trust list.

`X-Forwarded-Proto` is honoured together with `X-Forwarded-For` so scheme-sensitive URLs match the public TLS listener. `X-Forwarded-Host` is **not** honoured; set `Aouda:BaseUrl` for issuer URLs.

---

## Worked example: nginx

Aouda listens on loopback. nginx terminates TLS and forwards to it.

```nginx
upstream aouda_data {
    server 127.0.0.1:5434;
}

server {
    listen 443 ssl http2;
    server_name data.example.com;

    location / {
        proxy_pass http://aouda_data;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }
}
```

Aouda must trust **nginx's address as Kestrel sees it** — here `127.0.0.1`, because nginx is on the same host. List that address; do not leave loopback trusted implicitly.

```bash
AOUDA_FORWARDEDHEADERS__ENABLED=true
AOUDA_FORWARDEDHEADERS__KNOWNPROXIES=127.0.0.1
AOUDA_FORWARDEDHEADERS__FORWARDLIMIT=1
```

If nginx runs on another host or as a sidecar, use that host's IP or its CIDR in `KNOWNNETWORKS` instead of loopback.

Caddy's `reverse_proxy` sets `X-Forwarded-For` and `X-Forwarded-Proto` by default; the Aouda side is the same: enable the feature and name Caddy's peer address.

---

## Worked example: cloud load balancer

An AWS Application Load Balancer, GCP HTTP(S) Load Balancer, or Azure Application Gateway sits in a VPC and forwards to the Aouda node. The TCP peer is an address in the load-balancer subnet, not a single static IP.

Trust the subnet (or the VPC CIDR) and keep `ForwardLimit` at `1` unless a CDN sits in front of the LB:

```bash
AOUDA_FORWARDEDHEADERS__ENABLED=true
AOUDA_FORWARDEDHEADERS__KNOWNNETWORKS=10.0.0.0/8
AOUDA_FORWARDEDHEADERS__FORWARDLIMIT=1
```

Replace `10.0.0.0/8` with the prefix that actually sources the LB probes and data-plane traffic. If a CDN (CloudFront, Cloud CDN, Front Door) prepends another `X-Forwarded-For` hop, add the CDN-to-LB network to the trust list and set `ForwardLimit=2` so the original client address is the one that remains.

Do **not** set `KnownNetworks` to `0.0.0.0/0`. That trusts every client as a proxy.

Kubernetes Ingress / Service `type: LoadBalancer` is the same shape: the peer is the node or the LB, not the browser. See [Kubernetes](kubernetes.md).

---

## What you should see

On startup, with the feature on, Aouda logs the number of trusted proxies, networks, and the forward limit. With the feature off and the process bound off loopback, it logs that client IPs are transport peer addresses — that is legitimate for a direct-exposure host, and a reminder to configure this when you add an edge.
