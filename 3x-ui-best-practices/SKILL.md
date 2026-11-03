---
name: 3x-ui-best-practices
description: Install, configure, maintain, and troubleshoot 3x-ui panels and their managed Xray inbounds, clients, subscriptions, and APIs. Use for 3x-ui deployment or upgrades, VLESS/REALITY link mismatches, panel authentication, traffic accounting, and connection failures in a 3x-ui setup. General VPN selection or standalone client configuration without a 3x-ui context is outside this skill.
---

# 3x-ui Best Practices

Work from the deployed panel and core versions, preserve existing service, and verify the user's actual connection path. Keep panel payloads, generated Xray configuration, and client share links distinct.

## Operating Rules

1. Treat existing panels as production. Start with read-only checks; an HTTP `POST` can still be diagnostic, while a nominally routine save may reload Xray.
2. Respect authorization already given. Before a disruptive action, make its exact target, effects, validation, and recovery concrete. Obtain explicit authorization for deletion, accounting reset, service restart/stop, update, DB import/restore, or live key rotation if the current request has not already authorized it. Routine requested edits do not need repeated confirmation.
3. Keep live credentials, UUIDs, private keys, subscription IDs/URLs, DB dumps, and raw runtime configs out of committed artifacts and ordinary summaries. Show redacted diffs; keep executable secret-bearing payloads in protected local files. Do not fetch secrets merely to inventory a panel.
4. Prefer client-specific APIs and minimal changes when the deployed version supports them. Read the current object and preserve unrelated fields before replacement updates. Never blindly retry a write after a timeout; read back first to determine whether it succeeded.
5. Follow the deployed OpenAPI and matching source, not a route or schema assumed from this repository. Nested JSON is preferred where supported; older APIs may require JSON-encoded objects. Preserve unknown fields and never automatically downgrade version-specific encryption.

## Discovery

1. Establish the goal, authorization, panel version, Xray version, native/Docker mode, client application/core version, database backend, and direct/CDN/reverse-proxy topology. Inspect available context first; ask only for missing facts needed for the next action.
2. Resolve the panel URL plus web base path once. Probe the deployed OpenAPI (commonly `<base>/panel/api/openapi.json`) and confirm content type and status. A 200 HTML login page is not API success. Avoid following authenticated redirects to another origin.
3. When advertised, start with `/panel/api/inbounds/options`, `/inbounds/list/slim`, `/clients/list/paged?page=1&pageSize=25`, and `/server/status`. Paths after the first item share `/panel/api`. Paginate when complete counts matter.
4. On 404 or missing client-first routes, inspect the deployed version's documented read-only alternatives. Do not upgrade, reset the access path, or guess write endpoints to make discovery work.
5. Bearer authentication is useful for `/panel/api/*` where supported. Some deployments keep `/panel/setting/*` and `/panel/xray/*` behind UI session + CSRF even if OpenAPI advertises global security. Retain that boundary.

## Installation and Maintenance

Read [references/operations-runbook.md](references/operations-runbook.md) for installation, upgrades, backup/restore, or network diagnosis.

- Record OS/architecture, occupied ports, existing SSH port and an accessible recovery console. Preserve SSH access before changing either cloud or host firewall rules.
- Select an explicit upstream release/image digest. Download and inspect installers before running them; do not treat a mutable `master` script or `latest` image as a reproducible deployment.
- Keep the panel on loopback/private access or restrict it to trusted admin addresses. Use HTTPS or an SSH tunnel; a random base path supplements authentication and is not access control.
- In Docker bridge mode, publish only required ports and distinguish TCP/UDP. Host networking changes the exposure boundary and does not use `ports`. Add Fail2ban capabilities only if that feature is required, then verify enforcement.
- Before upgrade, record panel/core/image versions and take a consistent database backup plus certificates and deployment configuration. Use SQLite's backup mechanism or an authorized stopped-service copy; never copy a live DB file alone. PostgreSQL requires its own backup procedure.
- Restore the old binary/image **together with a compatible pre-migration database** when rollback is necessary. A successful download or container start is not an accepted upgrade.

## Configuration

- A direct VPS with a compatible client can use VLESS over TCP/RAW + REALITY with classic `decryption="none"` and panel `encryption="none"`. This is a baseline, not a mandate to replace existing encryption.
- Classic Vision is a VLESS client flow over TCP/RAW + TLS/REALITY. Check the panel's `tlsFlowCapable` and the matching core; do not add Vision to Trojan just because a panel accepts the field. Newer VLESS Encryption modes require separate version-specific validation.
- REALITY needs a path that does not terminate its TLS handshake. An ordinary HTTPS CDN/reverse proxy is unsuitable; L4 pass-through is a different topology to verify. Choose and test the target from the VPS rather than copying a permanently recommended domain.
- For CDN paths, verify actual support for the selected WS/gRPC/HTTPUpgrade/XHTTP transport at both ends and at the intermediary. Do not assume all CDNs support every transport.
- Keep fallback children private/loopback. Inspect the exact core's fallback semantics; do not treat REALITY's handshake target as interchangeable with VLESS/Trojan fallbacks.
- Use sniffing only for a defined routing purpose. Prefer `routeOnly=true` if only routing decisions need the sniffed domain; preserve existing FakeDNS and destination-override behavior.
- `totalGB` is bytes; `expiryTime` commonly uses milliseconds, with zero unlimited. Some versions use negative expiry for first-use duration: inspect and preserve it. Confirm all attached inbounds before changing a shared client's flow or identity.

## Diagnosis and Changes

1. Separate panel reachability from the proxy data path. Check service/listener, firewall/Docker mapping, DNS A/AAAA, TLS/REALITY handshake, client eligibility, then routing/site-specific behavior. Read logs in a bounded time window and redact them.
2. Use supported status, slim inventory, traffic and log endpoints first. Retrieve full client/runtime configuration only when needed. Compare intended panel state, rendered core state, and imported client fields.
3. A running core or successful TCP connect proves only one layer. Test an actual client request from the affected network, then verify counters and subscriptions if relevant.
4. Prepare one minimal change with a redacted before/after, affected users, and rollback. Run the offline preflight, then validate with the deployed schema/core as available. API HTTP success alone is insufficient: check application success/error fields and read back persisted state.
5. On failure, stop repeated writes/restarts, preserve evidence, and report what is confirmed versus untested. Do not rotate keys, reset counters, or reinstall as a generic diagnostic step.

## Offline Helpers

Requires Python 3.10+; neither helper accesses a panel or network.

- Run `python3 scripts/validate_config.py <file|->` for inbound, raw client, or client-add payload preflight. It handles nested and legacy JSON, types, classic Vision, short IDs and unit mistakes. Exit codes: 0 no errors, 1 validation errors, 2 input/read failure. Warnings and a zero exit code do not certify deployed compatibility, reachability, or CDN topology.
- Run `python3 scripts/parse_share_link.py -` with a link on stdin. Credentials, names, paths and unknown query values are masked. Address/SNI/public-key metadata remains visible; review before sharing. `--show-secrets` is for explicitly needed private local inspection only. Avoid placing live links in command arguments/history.
- Run each helper with `--self-test`; repository maintainers also run `python3 -m unittest discover -s tests -v` from the repository root.

## References

- [references/api-and-config-reference.md](references/api-and-config-reference.md): endpoint risk classes, field tables, baseline payloads and the original observed deployment caveats; consult for API/config work.
- [references/operations-runbook.md](references/operations-runbook.md): version evidence, layered diagnosis, consistent backup, acceptance and rollback; consult for operational work.
- [README.md](README.md) / [README.zh_CN.md](README.zh_CN.md): human-facing guides and examples in English / Simplified Chinese.
