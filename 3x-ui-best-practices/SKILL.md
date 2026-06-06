---
name: 3x-ui-best-practices
description: Install, secure, inspect, configure, and troubleshoot 3x-ui/Xray panels, including fresh VPS or Docker setup, SSL/reverse proxy, inbounds, clients, VLESS/REALITY, TLS, fallbacks, subscriptions, API automation, live diagnostics, and recovery. Use when the user mentions 3x-ui, 3X-UI, Xray panel, inbounds, clients, VLESS, VMess, Trojan, Shadowsocks, Hysteria, WireGuard, REALITY, subscription links, panel API, install, debug, logs, traffic not counted, connection failure, or best-practice proxy/VPN configuration.
---

# 3x-ui Best Practices

Use this skill to work with 3x-ui as a full Xray control-plane lifecycle: install, harden, configure inbounds/clients, validate links, and troubleshoot failures.

## Operating Rules

1. Treat every panel as production unless the user says otherwise.
2. Never call destructive or disruptive endpoints without explicit user approval: delete, bulk delete, reset traffic, restart/stop Xray, update panel, import DB, restore DB, regenerate live TLS/Reality secrets, or overwrite settings.
3. Never write API tokens, Reality private keys, client UUIDs/passwords/auth values, subscription IDs, Telegram IDs, or live URLs containing secrets into committed artifacts unless the user explicitly asks for those exact values.
4. Prefer `/panel/api/inbounds/options`, `/panel/api/inbounds/list/slim`, and paged client lists for discovery. Fetch full inbound/client details only when the task requires secret-bearing fields.
5. Prefer client-first APIs (`/panel/api/clients/add`, `/update/:email`, `/bulkCreate`, `/bulkAttach`, `/bulkDetach`) over hand-editing `settings.clients[]` inside an inbound.
6. Use nested JSON for `settings`, `streamSettings`, and `sniffing`; 3x-ui still accepts legacy JSON-encoded strings, but nested objects are the modern API shape.
7. If using Bearer auth, assume it is reliable for `/panel/api/*`. Some deployed versions and source routes keep `/panel/setting/*` and `/panel/xray/*` behind UI session + CSRF even when OpenAPI describes global security.

## Discovery Workflow

1. Identify the panel base path and OpenAPI URL, usually `<panel-url>/panel/api/openapi.json` or `<panel-url>/<access-path>/panel/api/openapi.json`.
2. Read the OpenAPI first, then confirm against source or live responses if behavior matters.
3. Inventory current topology with read-only calls:
   - `GET /panel/api/inbounds/options`
   - `GET /panel/api/inbounds/list/slim`
   - `GET /panel/api/clients/list/paged?page=1&pageSize=25`
   - optional status: `GET /panel/api/server/status`
4. Summarize protocol, port, transport, security, sniffing, client count, and whether an inbound is `tlsFlowCapable`.
5. For any proposed write, present the exact payload and the rollback/validation plan before executing.

## Fresh Install Workflow

1. Gather target OS, architecture, provider firewall rules, desired panel port/path, domain/SSL availability, and whether Docker is required.
2. Choose installation mode:
   - Native one-line install for a normal Linux VPS where the user wants the upstream management menu.
   - Docker Compose when repeatability, simple backup, or isolated filesystem layout matters.
   - Docker host networking when many inbound ports will be created dynamically.
3. Before install, open SSH and intended panel/inbound ports in the provider firewall and local firewall.
4. Install 3x-ui, then immediately rotate admin credentials, set a custom web base path, enable HTTPS for the panel when a domain/cert is available, and consider 2FA.
5. If using Docker with Fail2ban/IP limits, include `NET_ADMIN` and `NET_RAW`. If not using host networking, publish every inbound port explicitly.
6. Verify with: panel login, service/container status, `/panel/api/openapi.json`, `/panel/api/server/status`, and a simple inbound/client link.

## Upgrade and Backup Workflow

1. Back up before any upgrade, migration, or risky write. The SQLite DB is `/etc/x-ui/x-ui.db` (native) or the `./db/` volume (Docker); also save `./cert/` when certificates are local. Prefer backing up with the service stopped, or use the panel/`x-ui` menu backup.
2. Native upgrade: rerun the official installer or use the `x-ui` menu update entry. Docker upgrade: `docker compose pull && docker compose up -d` while reusing the same `./db/` and `./cert/` volumes.
3. Record the prior version/image tag so a misbehaving migration can be rolled back to a known-good state.
4. After upgrade, confirm `/panel/api/server/status`, check that inbound/client counts are unchanged, and re-test one client link. Treat panel update and DB import/restore as high-risk: confirm with the user first.

## Configuration Guidance

Prefer these defaults unless the user's network constraints say otherwise:

- Public direct server, single 443 entry: VLESS over TCP with REALITY, `settings.decryption="none"`, `settings.encryption="none"`, sniffing enabled for `http` and `tls` at minimum.
- CDN/reverse-proxy path routing: VLESS/VMess/Trojan over WebSocket, gRPC, HTTPUpgrade, or XHTTP with TLS. Do not put REALITY behind a CDN reverse proxy.
- XTLS Vision flow: use only on VLESS over TCP with `security` of `tls` or `reality`; 3x-ui exposes `tlsFlowCapable` for this exact gate.
- Fallbacks: only use a VLESS or Trojan master on TCP with TLS or REALITY. Point fallback children to loopback/private listeners and document match rules (`alpn`, `path`, `dest`, `xver`).
- IP limits: require access logs and Fail2ban enforcement. Warn that IP tunnel/proxy chains can make IP limits inaccurate.
- Client identity: `email` is the unique stable key. `expiryTime=0` means no expiry, `totalGB=0` means no quota, and API quota values are bytes despite the historical `totalGB` name.

## Troubleshooting Workflow

1. Classify the failure: panel unreachable, login/auth problem, Xray stopped, client cannot connect, traffic not counted, IP limit not enforced, subscription broken, high CPU/disk, or routing/site access issue.
2. Use read-only checks first:
   - `GET /panel/api/server/status`
   - `POST /panel/api/server/logs/{count}`
   - `POST /panel/api/server/xraylogs/{count}`
   - `GET /panel/api/server/getConfigJson`
   - `GET /panel/api/inbounds/list/slim`
   - `GET /panel/api/clients/traffic/{email}`
   - `POST /panel/api/clients/onlines`
3. Compare intended config to runtime config. Watch for port conflicts, missing Docker port publishes, wrong base path, expired client, exhausted quota, disabled inbound/client, bad Reality SNI/public key/shortId, CDN in front of Reality, and missing access log for IP limits.
4. Only after evidence, propose a minimal fix and name its side effects, especially Xray restart, traffic reset, DB restore, or client secret rotation.

## API Use

Use environment variables in examples:

```bash
export XUI_BASE='https://example.com/access-path'
export XUI_API_TOKEN='...'
curl -fsS -H "Authorization: Bearer ${XUI_API_TOKEN}" \
  "${XUI_BASE}/panel/api/inbounds/options"
```

For writes:

1. Fetch the current object first.
2. Preserve fields the user did not ask to change.
3. Use the most specific endpoint (`setEnable` for enable flips, client endpoints for client changes).
4. Verify with a read-only endpoint and, if needed, generated links (`/panel/api/clients/links/:email`) without exposing secrets in the final answer.

## Scripts

Offline helpers in `scripts/` run on any surface (no network, no panel access). They complement — but never replace — showing the user each payload and command:

- Execute `scripts/validate_config.py <file|->` to validate an inbound or client-add payload before POSTing it: flow placement, VLESS `decryption`/`encryption`, XTLS-Vision gating, REALITY-behind-CDN, and byte-vs-GiB / ms-vs-seconds mistakes. The exit code is the error count; use it as the validate step before any write.
- Execute `scripts/parse_share_link.py '<link>'` to decode a VLESS/VMess/Trojan link into normalized fields to compare against an inbound; the credential is masked by default.

Run a script's `--self-test` to confirm it works. Do not add network-calling scripts: some surfaces have no network, and hiding live calls would undercut the show-then-confirm workflow.

## References

Read [references/api-and-config-reference.md](references/api-and-config-reference.md) when you need endpoint groups, field tables, protocol-specific `settings`, `streamSettings`, or example payloads.

Read [README.md](README.md) when the user wants English human-facing documentation, diagrams, or copy-pasteable configuration examples.

Read [README.zh_CN.md](README.zh_CN.md) when the user wants the same documentation in Simplified Chinese.

Use the offline helpers in [scripts/](scripts/): `validate_config.py` (validate a payload before writing) and `parse_share_link.py` (decode a share link, secrets masked).
