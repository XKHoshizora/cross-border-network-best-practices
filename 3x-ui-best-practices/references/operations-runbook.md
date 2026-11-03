# Version-aware operations runbook

## Evidence and scope

Documentation review: 2026-11-04. No live deployment was tested during this review. Record panel, Xray, client, image digest, API/schema source, and observation date for each actual deployment. The original API reference describes an observed 3.x panel without an exact version; it is not a compatibility guarantee for all releases.

Primary sources to check against the installed release:

- [3x-ui official documentation](https://docs.sanaei.dev/) and [release history](https://github.com/MHSanaei/3x-ui/releases): installation and version selection.
- [Xray VLESS](https://xtls.github.io/config/inbounds/vless.html) and [Trojan](https://xtls.github.io/config/inbounds/trojan.html): protocol-specific fields; Vision belongs to VLESS, not a generic TLS client field. New VLESS Encryption modes change assumptions of the classic profile.
- [Xray transport](https://xtls.github.io/config/transport.html): transport/security combinations. New core documentation may use different field names from a panel's persisted API model; do not mass-rename panel fields from the current manual.
- [SQLite online backup](https://www.sqlite.org/backup.html): consistent snapshots while writers are active.
- [Docker packet filtering](https://docs.docker.com/engine/network/packet-filtering-firewalls/): published container ports and host firewall interactions.

## Before installation

Record existing listeners, actual SSH port, firewall backend, address family, and recovery-console access. Test a second SSH session after a firewall change. Do not assume SSH is on port 22 or enable a new firewall ruleset blindly.

Use a selected release tag/digest and preserve the prior artifact. A digest pins content, not trust: verify the upstream source and any published checksums/signatures. For native scripts, download from the selected official ref, inspect it, and check which application/core version it will fetch before execution.

Keep the panel private initially. Publish only the proxy ports needed by the selected protocol, with explicit TCP/UDP mappings. Docker-published traffic may bypass UFW's normal input rules; inspect Docker's actual firewall backend and verify exposure externally. With host networking, every bound listener uses the host network; remove `ports` and audit listener addresses.

Do not grant `NET_ADMIN`/`NET_RAW` merely because a sample does. If Fail2ban is requested, grant only the required capabilities and verify that a test ban blocks the intended client without blocking shared proxies or administrators. Forwarded-IP headers are trusted only from a controlled proxy.

## API compatibility and write recovery

1. Resolve base path and advertised schema with read-only requests. Distinguish HTTP error, redirect, HTML login, malformed JSON, and application-level failure in a 200 response.
2. Match the payload to that API version. The panel may accept nested objects, legacy encoded strings, or a client-first API unavailable on older versions. Do not convert the panel model into raw Xray JSON.
3. Save the relevant pre-change object securely and preserve unknown fields. For a shared client, enumerate its inbound attachments before changing transport-dependent fields.
4. Submit once. If the request times out, read back the object and inventory before deciding whether to retry. Bulk operations may partially succeed; reconcile per-item results rather than replaying the whole batch.
5. Confirm persisted state and runtime state, then perform a real client request. Avoid dumping a full runtime config or subscription into a report.

## Backup and rollback

A backup contains credentials. Use a restricted directory (`umask 077`), unique timestamped names, encrypted off-host storage where appropriate, and a retention policy. Sending a DB to Telegram or another external service is a separate disclosure decision, not a default backup step.

For SQLite, prefer the SQLite backup API/CLI `.backup` for an online consistent snapshot. Example on a native install with the correct database path and permissions:

```bash
umask 077
backup_dir="/root/xui-backup-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$backup_dir"
sqlite3 /etc/x-ui/x-ui.db ".backup '$backup_dir/x-ui.db'"
sqlite3 "$backup_dir/x-ui.db" 'PRAGMA integrity_check;'
```

Require successful commands and an `ok` integrity result before proceeding. In Docker, use the resolved mounted SQLite path and compatible tooling, or stop the relevant service with authorization and archive the entire persistent volume. Do not copy only a live `x-ui.db`: WAL state may contain committed data. Never delete WAL/SHM files to “fix” a lock. If a backup fails after stopping a service, restore its previous running state and halt the upgrade.

For PostgreSQL, use a matching `pg_dump` workflow and validate recovery with the appropriate PostgreSQL tools; SQLite commands do not apply. Also preserve certificates, Compose/service files, environment configuration in secret storage, and panel/core/image versions.

Test restoration in an isolated environment before relying on the backup. Do not expose a cloned panel publicly or let a restore drill send scheduled notifications. Integrity checks alone do not prove application recovery.

After a failed migration, stop writes; preserve the failed state separately if needed. Roll back the panel/core artifact and the matching pre-migration DB together, with correct ownership and paths. Simply starting the old image against the migrated DB may not work. Restore discards post-backup writes: make the recovery point explicit before execution.

## Diagnose by layer

| Layer | Evidence | Interpretation / next step |
| --- | --- | --- |
| Panel | Local listener, exact base path, HTTPS response, auth/content type | Panel reachability does not prove inbound reachability. |
| Service | Process/container state, bounded error logs, rendered config | Running status does not prove the config was accepted or traffic passed. |
| Network | Listener bind, TCP/UDP mapping, cloud + host firewall, client-side probe | Check IPv4 and IPv6 separately; a bad AAAA record can affect only some clients. |
| TLS/REALITY | SNI, target reachability from VPS, key correspondence, shortId, time, client support | Certificate success alone does not prove proxy authentication. Do not rotate keys to diagnose a mismatch. |
| Client | Enable, quota, expiry semantics, attachment, imported transport/link | Compare actual client state, not only what a subscription currently generates. |
| Routing | Domain resolution, routing order, direct/proxied comparison, destination response | A destination 403 may be application policy; it does not by itself prove a broken tunnel. |
| Performance | Time/region, repeated latency/loss/throughput samples, CPU/memory/disk | Avoid blanket BBR/MTU/DNS changes or provider recommendations from one speed test. |

For “small requests work, large transfers hang,” inspect path MTU/PMTUD and filtering with evidence before changing MTU. For UDP-only failures, inspect UDP mappings, client transport support and intermediary behavior. Keep measurements bounded; do not run unrequested load tests.

## Acceptance and handoff

Record the version/topology, confirmed cause, minimal change, and evidence for each acceptance check: panel login, core status, paginated counts, affected client request, and relevant traffic/subscription behavior. State tests not performed and the next check needed. Include the rollback artifact location without printing its contents. Never claim “fixed” solely from an API 200, an open port, or a successful restart.
