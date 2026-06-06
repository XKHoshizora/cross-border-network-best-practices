# 3x-ui API and Configuration Reference

This reference is for agents that need precise 3x-ui/Xray API and config shape details. It is based on the MHSanaei/3x-ui repository, its wiki, and a live OpenAPI document from a 3.x panel.

## Contents

- [Live Panel Shape Observed](#live-panel-shape-observed)
- [Authentication](#authentication)
- [Install Reference](#install-reference)
- [Endpoint Risk Classes](#endpoint-risk-classes)
- [Troubleshooting Matrix](#troubleshooting-matrix)
- [Inbound Top-Level Fields](#inbound-top-level-fields)
- [Client Fields](#client-fields)
- [Protocol Settings](#protocol-settings)
- [Stream Settings](#stream-settings)
- [Best-Practice Payloads](#best-practice-payloads)

## Live Panel Shape Observed

The inspected live panel had this sanitized topology:

- Inbounds: 1
- Protocol: `vless`
- Port: `443`
- Transport/security: `tcp` + `reality`
- Sniffing: enabled
- `streamSettings` keys: `network`, `tcpSettings`, `security`, `realitySettings`
- `settings` keys: `clients`, `decryption`, `encryption`
- Client count in slim list: 1

Do not write live secrets into docs. `realitySettings.privateKey`, client `id`, client `password`, client `auth`, and `subId` are secret-bearing.

## Authentication

Use Bearer tokens for `/panel/api/*`:

```bash
curl -fsS -H "Authorization: Bearer ${XUI_API_TOKEN}" \
  "${XUI_BASE}/panel/api/inbounds/options"
```

Bearer auth is implemented by the API controller on the `/panel/api` route group. The source also has separate `/panel/setting` and `/panel/xray` route groups protected by UI login + CSRF. If a live OpenAPI advertises Bearer security globally but those routes redirect to the panel shell, do not fight it; either use UI session flow with CSRF or avoid those endpoints.

## Install Reference

Native install:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh)
```

Notes:

- The installer generates a random username, password, and web base path.
- Use `x-ui` after install to reopen the management menu for service control, credentials, SSL certificate management, and firewall/IP-limit tasks.
- If GitHub download fails at DNS/timeout, retry with `curl --ipv4` or fix DNS before rerunning.

Docker Compose baseline:

```yaml
services:
  3xui:
    image: ghcr.io/mhsanaei/3x-ui:latest
    container_name: 3xui_app
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - ./db/:/etc/x-ui/
      - ./cert/:/root/cert/
    environment:
      XRAY_VMESS_AEAD_FORCED: "false"
      XUI_ENABLE_FAIL2BAN: "true"
    ports:
      - "2053:2053"
      - "443:443"
    restart: unless-stopped
```

Docker notes:

- The `ports` block must publish every inbound port unless using `network_mode: host`.
- Fail2ban enforcement needs `NET_ADMIN`; IPv6 iptables also needs `NET_RAW`.
- Change default Docker credentials (`admin`/`admin`) immediately.
- For PostgreSQL, set `XUI_DB_TYPE=postgres` and `XUI_DB_DSN=postgres://...`; SQLite default DB lives under `/etc/x-ui/`.

Post-install hardening checklist:

- Rotate admin username/password.
- Set a non-obvious web base path.
- Enable HTTPS for the panel when a domain/cert is available.
- Enable 2FA where practical.
- Open only required firewall ports: SSH, panel, subscription, and inbound ports.
- Consider restricting panel port to trusted admin IPs.
- Enable Fail2ban/IP-limit management if client `limitIp` will be used.
- Configure access log as `./access.log` if IP limit enforcement is needed.

## Endpoint Risk Classes

Safe discovery endpoints:

| Method | Path | Use |
| --- | --- | --- |
| `GET` | `/panel/api/inbounds/options` | Small picker: id, remark, protocol, port, `tlsFlowCapable`. |
| `GET` | `/panel/api/inbounds/list/slim` | Inbound shape without full client secrets. |
| `GET` | `/panel/api/inbounds/get/{id}` | Full inbound. Use only when full client fields are needed. |
| `GET` | `/panel/api/clients/list/paged` | Scalable client table. |
| `GET` | `/panel/api/clients/get/{email}` | Full client by unique email. |
| `GET` | `/panel/api/clients/links/{email}` | Protocol URLs for one client; contains secrets. |
| `GET` | `/panel/api/clients/subLinks/{subId}` | Protocol URLs by subscription id; contains secrets. |
| `GET` | `/panel/api/server/status` | System and Xray state. |
| `GET` | `/panel/api/server/getNewUUID` | Generate a UUID. |
| `GET` | `/panel/api/server/getNewX25519Cert` | Generate Reality X25519 keypair. |
| `GET` | `/panel/api/server/getNewmldsa65` | Generate post-quantum ML-DSA-65 pair. |

Mutating but routine endpoints:

| Method | Path | Use |
| --- | --- | --- |
| `POST` | `/panel/api/inbounds/add` | Create inbound; may require Xray reload. |
| `POST` | `/panel/api/inbounds/update/{id}` | Replace full inbound. Preserve fields. |
| `POST` | `/panel/api/inbounds/setEnable/{id}` | Toggle only enabled state. |
| `POST` | `/panel/api/clients/add` | Create client and attach to inbounds. |
| `POST` | `/panel/api/clients/update/{email}` | Replace client row. Preserve fields. |
| `POST` | `/panel/api/clients/{email}/attach` | Attach existing client. |
| `POST` | `/panel/api/clients/{email}/detach` | Detach existing client. |
| `POST` | `/panel/api/clients/bulkCreate` | Sequential bulk create; reports skips. |
| `POST` | `/panel/api/inbounds/{id}/fallbacks` | Replace fallback list. |

High-risk endpoints that require explicit approval:

- Delete: `/panel/api/inbounds/del/{id}`, `/bulkDel`, `/panel/api/clients/del/{email}`, `/bulkDel`, group delete.
- Accounting reset: inbound/client reset traffic endpoints, `resetAllTraffics`.
- Service disruption: `/panel/api/server/stopXrayService`, `/restartXrayService`, `/installXray/{version}`, `/updatePanel`.
- Backup/restore/import: `/panel/api/server/importDB`, `/panel/api/inbounds/import`, `/panel/api/backuptotgbot`.

## Troubleshooting Matrix

| Symptom | First checks | Likely causes | Low-risk next step |
| --- | --- | --- | --- |
| Panel unreachable | Service/container status, firewall, panel port/path, TLS cert path | Closed port, wrong base path, expired/bad panel SSL, service stopped | Verify local `curl` to panel port, then external firewall. |
| API token returns redirect/404 | Request path and endpoint group | Token valid only on `/panel/api/*` in some versions | Use `/panel/api/*`; for settings use UI session + CSRF. |
| Client cannot connect | `/server/status`, `/inbounds/list/slim`, client link, Xray logs | Disabled inbound/client, wrong port publish, Reality key/SNI mismatch, CDN in front of Reality | Compare generated link with inbound `streamSettings`; check Docker port publish. |
| Reality link fails | `serverNames`, `shortIds`, public key, target, flow | Wrong SNI, reused/invalid shortId, client missing `fp/pbk/sid`, using CDN/reverse proxy | Regenerate link via `/clients/links/{email}` and compare client app fields. |
| Traffic remains zero | Runtime config, routing rules, client email, API rule order | Xray config error, missing email, migrated DB inconsistency, API routing rule not first | Check `/server/getConfigJson`, Xray logs, then update panel if migrated. |
| IP limit ineffective | access log, Fail2ban status, Docker caps, proxy headers | Missing `./access.log`, no `NET_ADMIN`, CDN/tunnel hides real IP | Enable access log and Fail2ban; for proxy chains ensure real IP forwarding. |
| Subscription broken | subscription server enabled/path/port, `subId`, client enabled | Wrong subscription path, port not open, expired/disabled client | Use `/clients/subLinks/{subId}` for API-level link validation. |
| Disk filling | log paths and sizes | access log grows quickly | Disable access log if IP limit is unused, or rotate/truncate logs. |
| Database locked | disk latency, log writes, SQLite load | Slow disk or heavy access logging | Disable access log, reduce write load, consider PostgreSQL for scale. |
| High CPU | process list, Xray logs, active clients | abuse, too-small server, outdated panel/core | Update, install Fail2ban, inspect active clients and routes. |

Read-only diagnostic commands:

```bash
curl -fsS -H "Authorization: Bearer ${XUI_API_TOKEN}" \
  "${XUI_BASE}/panel/api/server/status"

curl -fsS -X POST -H "Authorization: Bearer ${XUI_API_TOKEN}" \
  "${XUI_BASE}/panel/api/server/xraylogs/100"

curl -fsS -H "Authorization: Bearer ${XUI_API_TOKEN}" \
  "${XUI_BASE}/panel/api/inbounds/list/slim"

curl -fsS -H "Authorization: Bearer ${XUI_API_TOKEN}" \
  "${XUI_BASE}/panel/api/clients/traffic/alice%40example.test"
```

## Inbound Top-Level Fields

| Field | Type | Meaning and guidance |
| --- | --- | --- |
| `id` | integer | Server-assigned row id. Omit on create. |
| `remark` | string | Human-readable name; include protocol, port, and purpose. |
| `enable` | boolean | Runtime enabled flag. Use `setEnable` for toggles. |
| `listen` | string | Bind address. Empty usually means all interfaces; use `127.0.0.1` for fallback children. |
| `port` | integer | 0-65535. Must not conflict with another inbound/listener. |
| `protocol` | enum | `vmess`, `vless`, `trojan`, `shadowsocks`, `wireguard`, `hysteria`, `http`, `mixed`, `tunnel`, `tun`. |
| `expiryTime` | integer | Inbound expiry timestamp; `0` means unlimited. |
| `total` | integer | Inbound traffic quota in bytes; `0` means unlimited. |
| `trafficReset` | enum | `never`, `hourly`, `daily`, `weekly`, `monthly`. |
| `settings` | object | Protocol-specific settings; nested JSON preferred. |
| `streamSettings` | object | Transport/security settings for `vmess`, `vless`, `trojan`, `shadowsocks`, `hysteria`; omitted/empty for others. |
| `tag` | string | Unique Xray tag. Can be auto-generated; preserve on update unless intentionally renaming. |
| `sniffing` | object | Traffic sniffing override. Usually enable `http` and `tls`. |
| `nodeId` | integer or null | Remote node target. `0` is normalized to null in source. |

## Client Fields

| Field | Type | Applies to | Meaning |
| --- | --- | --- | --- |
| `email` | string | all tracked clients | Unique stable key; no spaces, slash, backslash, control chars. |
| `id` | UUID | VLESS/VMess | Per-client UUID; server can generate if omitted in client API. |
| `password` | string | Trojan/Shadowsocks | Secret. Trojan uses it directly; Shadowsocks may generate method-specific key. |
| `auth` | string | Hysteria | Secret auth token; server can generate if omitted in client API. |
| `security` | enum | VMess | `auto`, `aes-128-gcm`, `chacha20-poly1305`, `none`, `zero`. |
| `flow` | enum | VLESS/Trojan over TCP TLS/Reality | ``, `xtls-rprx-vision`, `xtls-rprx-vision-udp443`. Runtime normalizes UDP443 to Vision. |
| `reverse` | object | VLESS | Optional simple reverse-proxy `{tag, sniffing}`. |
| `subId` | string | tracked clients | Subscription id; server can generate. Treat as secret-bearing. |
| `limitIp` | integer | tracked clients | Max simultaneous IPs; `0` disables. Needs Fail2ban/access log enforcement. |
| `totalGB` | integer | tracked clients | API stores bytes despite name. `0` means unlimited. |
| `expiryTime` | integer | tracked clients | Unix timestamp in milliseconds in API examples; `0` means never expires. |
| `enable` | boolean | tracked clients | Disabled clients are omitted from runtime config. |
| `tgId` | integer | tracked clients | Telegram user id; `0` means none. |
| `group` | string | tracked clients | Optional grouping label. |
| `comment` | string | tracked clients | Operator note. |
| `reset` | integer | tracked clients | Auto-reset period in days; `0` disables. |
| `created_at`, `updated_at` | integer | inbound settings clients | Server fills milliseconds on add/update. |

## Protocol Settings

| Protocol | `settings` fields |
| --- | --- |
| `vless` | `clients[]`, `decryption` default `none`, `encryption` default `none`, `fallbacks[]`, optional `testseed[4]` for Vision padding seed. |
| `vmess` | `clients[]` with `id`, `security`, `email`, limits, expiry, subscription, comments. |
| `trojan` | `clients[]` with `password`, limits, expiry, subscription, comments; `fallbacks[]`. |
| `shadowsocks` | `method`, `password`, `network` (`tcp`, `udp`, `tcp,udp`), `clients[]`, `ivCheck`. |
| `hysteria` | `version` (default `2`), `clients[]` with `auth`. |
| `wireguard` | `secretKey`, optional `mtu`, `peers[]`, `noKernelTun`; peers have `publicKey`, optional `privateKey`, `preSharedKey`, `allowedIPs`, `keepAlive`. |
| `http` | `accounts[]` of `{user, pass}`, `allowTransparent`; no billable client tracking. |
| `mixed` | `auth` (`password` or `noauth`), optional `accounts[]`, `udp`, `ip`. |
| `tunnel` | `rewriteAddress`, `rewritePort`, `portMap`, `allowedNetwork`, `followRedirect`. |
| `tun` | `name`, `mtu`, `gateway[]`, `dns[]`, `userLevel`, `autoSystemRoutingTable[]`, `autoOutboundsInterface`. |

Fallback object:

| Field | Meaning |
| --- | --- |
| `name` | Operator label. |
| `alpn` | Match ALPN such as `h2` or `http/1.1`. |
| `path` | Match HTTP path for WS/gRPC-style child. |
| `dest` | Explicit destination, or empty to use child listen/port. |
| `xver` | PROXY protocol version to send to child; commonly `0` or `2`. |

## Stream Settings

`streamSettings` is a combination of one `network` branch, one `security` branch, and optional extras.

Networks:

| `network` | Settings key | Fields |
| --- | --- | --- |
| `tcp` | `tcpSettings` | `acceptProxyProtocol`, optional `header` of `{type:"none"}` or `{type:"http", request, response}`. |
| `kcp` | `kcpSettings` | `mtu`, `tti`, `uplinkCapacity`, `downlinkCapacity`, `cwndMultiplier`, `maxSendingWindow`. |
| `ws` | `wsSettings` | `acceptProxyProtocol`, `path`, `host`, `headers`, `heartbeatPeriod`. |
| `grpc` | `grpcSettings` | `serviceName`, `authority`, `multiMode`. |
| `httpupgrade` | `httpupgradeSettings` | `acceptProxyProtocol`, `path`, `host`, `headers`. |
| `xhttp` | `xhttpSettings` | `path`, `host`, `mode`, padding/session/seq/uplink fields, `headers`, optional `xmux`; server ignores outbound-only knobs but links may carry them. |
| `hysteria` | `hysteriaSettings` | `version`, `auth`, `udpIdleTimeout`, optional `masquerade`. Only valid with Hysteria protocol. |

Security:

| `security` | Settings key | Fields |
| --- | --- | --- |
| `none` | none | No security payload. |
| `tls` | `tlsSettings` | `serverName`, versions, ciphers, `rejectUnknownSni`, certs, `alpn`, ECH fields, client `settings.fingerprint`, `echConfigList`, `pinnedPeerCertSha256`. |
| `reality` | `realitySettings` | `show`, `xver`, `target`, `serverNames[]`, `privateKey`, client `settings.publicKey`, `settings.fingerprint`, `settings.spiderX`, `shortIds[]`, optional ML-DSA fields. |

Extras:

| Field | Meaning |
| --- | --- |
| `sockopt` | Advanced socket options; use sparingly and preserve existing values. |
| `externalProxy` | Emits multiple share links through external proxies. |
| `finalmask` | Advanced mask configuration; preserve unless intentionally editing. |

Sniffing:

```json
{
  "enabled": true,
  "destOverride": ["http", "tls"],
  "metadataOnly": false,
  "routeOnly": false,
  "ipsExcluded": [],
  "domainsExcluded": []
}
```

Valid `destOverride`: `http`, `tls`, `quic`, `fakedns`.

## Best-Practice Payloads

Create VLESS TCP REALITY inbound, with generated Reality keys substituted:

```json
{
  "enable": true,
  "remark": "vless-reality-443",
  "listen": "",
  "port": 443,
  "protocol": "vless",
  "expiryTime": 0,
  "total": 0,
  "trafficReset": "never",
  "settings": {
    "clients": [],
    "decryption": "none",
    "encryption": "none",
    "fallbacks": []
  },
  "streamSettings": {
    "network": "tcp",
    "tcpSettings": {
      "acceptProxyProtocol": false,
      "header": { "type": "none" }
    },
    "security": "reality",
    "realitySettings": {
      "show": false,
      "xver": 0,
      "target": "www.yahoo.com:443",
      "serverNames": ["www.yahoo.com"],
      "privateKey": "<generated-private-key>",
      "minClientVer": "",
      "maxClientVer": "",
      "maxTimediff": 0,
      "shortIds": ["<generated-short-id>"],
      "mldsa65Seed": "",
      "settings": {
        "publicKey": "<generated-public-key>",
        "fingerprint": "chrome",
        "serverName": "",
        "spiderX": "/",
        "mldsa65Verify": ""
      }
    }
  },
  "sniffing": {
    "enabled": true,
    "destOverride": ["http", "tls"],
    "metadataOnly": false,
    "routeOnly": false,
    "ipsExcluded": [],
    "domainsExcluded": []
  }
}
```

Create a client on an existing VLESS/REALITY inbound:

```json
{
  "client": {
    "email": "alice@example.test",
    "flow": "xtls-rprx-vision",
    "totalGB": 53687091200,
    "expiryTime": 0,
    "limitIp": 2,
    "tgId": 0,
    "comment": "50 GiB, no expiry",
    "enable": true
  },
  "inboundIds": [1]
}
```

The server will generate `id` and `subId` if omitted. Include `flow` only if `tlsFlowCapable` is true for the target inbound.
