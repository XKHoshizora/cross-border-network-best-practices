#!/usr/bin/env python3
"""Offline validator for 3x-ui inbound and client payloads.

This script never touches the network. It reads a JSON payload (an inbound
object, a `/panel/api/clients/add` body, or a raw client object) and checks it
against the invariants documented in references/api-and-config-reference.md,
*before* you POST it to a live panel. Use it as the "validate" step of a
plan-validate-execute workflow on high-stakes changes.

Usage:
    python scripts/validate_config.py inbound.json
    cat client.json | python scripts/validate_config.py -
    python scripts/validate_config.py --self-test

Exit codes: 0 = no errors, 1 = validation errors, 2 = input/read failure.
Warnings do not affect the exit code. This is a panel-payload preflight, not
an Xray schema validator or a network/CDN detector.

Contents: Report; shape normalization; client/inbound checks; CLI; self-test.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

# --- Justified constants (no voodoo numbers; see Ousterhout's law) -----------

PORT_MIN, PORT_MAX = 0, 65535  # valid TCP/UDP port range

# A traffic quota is stored in BYTES by the API despite the historical field
# name `totalGB`. Any positive quota under 1 KiB is almost certainly a GB/GiB
# count typed by mistake (e.g. 50 meaning "50 GiB", which is really 50 bytes).
SMALL_QUOTA_BYTES = 1024
BYTES_PER_GIB = 1024 ** 3

# Unix-epoch milliseconds crossed 10**12 on 2001-09-09. Today's value is ~1.7e12.
# So any positive expiry below 10**12 is almost certainly a *seconds* timestamp
# that should have been multiplied by 1000.
MS_TIMESTAMP_FLOOR = 10 ** 12

PROTOCOLS = {
    "vless", "vmess", "trojan", "shadowsocks", "wireguard",
    "hysteria", "http", "mixed", "tunnel", "tun",
}
NETWORKS = {"raw", "tcp", "kcp", "ws", "grpc", "httpupgrade", "xhttp", "hysteria"}
SECURITIES = {"none", "tls", "reality"}
SNIFF_DESTS = {"http", "tls", "quic", "fakedns"}
CLIENT_FLOWS = {"", "xtls-rprx-vision", "xtls-rprx-vision-udp443"}
# XTLS Vision flow is only valid on these protocols, over TCP, with TLS/REALITY.
VISION_PROTOCOLS = {"vless"}


class Report:
    """Collects findings and tracks whether any are fatal."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def error(self, msg: str) -> None:
        self.items.append(("ERROR", msg))

    def warn(self, msg: str) -> None:
        self.items.append(("WARN", msg))

    def info(self, msg: str) -> None:
        self.items.append(("INFO", msg))

    @property
    def error_count(self) -> int:
        return sum(1 for level, _ in self.items if level == "ERROR")

    def render(self) -> str:
        if not self.items:
            return "OK: no findings."
        icon = {"ERROR": "✗", "WARN": "!", "INFO": "·"}
        lines = [f"{icon[level]} {level}: {msg}" for level, msg in self.items]
        summary = (
            f"\n{self.error_count} error(s), "
            f"{sum(1 for l, _ in self.items if l == 'WARN')} warning(s)."
        )
        return "\n".join(lines) + summary


def _has_control_chars(s: str) -> bool:
    return any(unicodedata.category(ch).startswith("C") for ch in s)


def validate_client(client: dict, report: Report, *, where: str = "client") -> None:
    """Validate a single client object (shared by inbound + client-add modes)."""
    email = client.get("email")
    if not email:
        report.error(f"{where}: missing required `email` (the unique stable key).")
    elif not isinstance(email, str):
        report.error(f"{where}: `email` must be a string.")
    elif any(c in email for c in " /\\") or _has_control_chars(email):
        report.error(
            f"{where}: `email` must not contain spaces, '/', '\\', or control chars."
        )

    flow = client.get("flow", "")
    if not isinstance(flow, str) or flow not in CLIENT_FLOWS:
        report.error(
            f"{where}: invalid `flow`; allowed: "
            f"{sorted(f for f in CLIENT_FLOWS if f)} or empty."
        )

    quota = client.get("totalGB")
    if quota is not None:
        if type(quota) is not int or quota < 0:
            report.error(f"{where}: `totalGB` must be a non-negative integer (bytes).")
        elif 0 < quota < SMALL_QUOTA_BYTES:
            report.warn(
                f"{where}: `totalGB`={quota} looks like a GiB count, but the API uses "
                f"BYTES. {quota} GiB = {quota * BYTES_PER_GIB} bytes."
            )

    expiry = client.get("expiryTime")
    if expiry is not None:
        if type(expiry) is not int:
            report.error(f"{where}: `expiryTime` must be an integer (ms).")
        elif expiry < 0:
            report.warn(f"{where}: negative expiry may encode start-on-first-use duration; verify deployed semantics and preserve it.")
        elif 0 < expiry < MS_TIMESTAMP_FLOOR:
            report.warn(
                f"{where}: `expiryTime`={expiry} looks like a SECONDS timestamp; the "
                f"API expects milliseconds (multiply by 1000)."
            )

    limit_ip = client.get("limitIp")
    if limit_ip is not None:
        if type(limit_ip) is not int or limit_ip < 0:
            report.error(f"{where}: `limitIp` must be a non-negative integer.")
        elif limit_ip > 0:
            report.info(
                f"{where}: `limitIp`={limit_ip} requires Fail2ban + Xray access log "
                f"(./access.log) to actually be enforced."
            )


def _check_vision_flow(client: dict, protocol: str, network: str,
                       security: str, report: Report) -> None:
    flow = client.get("flow", "")
    if not flow:
        return
    label = "<redacted>"
    if protocol not in VISION_PROTOCOLS:
        report.error(f"client {label!r}: `flow` is only valid on {sorted(VISION_PROTOCOLS)}.")
    if network not in {"tcp", "raw"}:
        report.error(f"client {label!r}: classic Vision requires network=tcp/raw.")
    if security not in {"tls", "reality"}:
        report.error(
            f"client {label!r}: classic Vision requires security tls/reality."
        )


def validate_inbound(inbound: dict, report: Report) -> None:
    if "flow" in inbound:
        report.error("`flow` belongs on each client, not at the inbound top level.")

    port = inbound.get("port")
    if type(port) is not int:
        report.error("`port` is required and must be an integer.")
    elif not (PORT_MIN <= port <= PORT_MAX):
        report.error(f"`port`={port} is outside {PORT_MIN}-{PORT_MAX}.")
    elif port == 0:
        report.warn("`port`=0 means no fixed port; confirm this is intentional.")

    protocol = inbound.get("protocol")
    if not isinstance(protocol, str) or not protocol:
        report.error("`protocol` must be a non-empty string.")
    elif protocol not in PROTOCOLS:
        report.warn("Protocol is outside this helper profile; verify with deployed schema/core.")

    if not inbound.get("remark"):
        report.info("`remark` is empty; a name like 'vless-reality-443' aids operations.")

    settings = inbound.get("settings") or {}
    if protocol == "vless":
        for key in ("decryption", "encryption"):
            val = settings.get(key)
            if val is not None and (not isinstance(val, str) or not val):
                report.error(f"VLESS `settings.{key}` must be a non-empty string.")
            elif val not in (None, "none"):
                report.warn(f"VLESS `settings.{key}` uses version-specific encryption; validate with the matching core, do not rewrite to none.")

    stream = inbound.get("streamSettings") or {}
    network = stream.get("network", "tcp")
    security = stream.get("security", "none")
    if stream:
        if not isinstance(network, str):
            report.error("`streamSettings.network` must be a string.")
        elif network not in NETWORKS:
            report.warn("Transport is outside this helper profile; verify with deployed schema/core.")
        if not isinstance(security, str) or security not in SECURITIES:
            report.error("`streamSettings.security` must be none, tls, or reality.")
        if security == "reality":
            rs = stream.get("realitySettings") or {}
            if not rs.get("serverNames"):
                report.error("REALITY requires a non-empty `serverNames[]`.")
            if "shortIds" not in rs:
                report.warn("REALITY usually defines `shortIds[]` (clients pick one).")
            if not rs.get("privateKey"):
                report.warn("REALITY `privateKey` is empty (placeholder is fine in docs).")
            inner = rs.get("settings") or {}
            if not inner.get("publicKey"):
                report.warn("REALITY clients need `settings.publicKey`; it looks empty.")
            report.info("Verify the REALITY path has no TLS-terminating CDN/reverse proxy; topology cannot be inferred from this payload.")
            for sid in rs.get("shortIds", []):
                if not re.fullmatch(r"(?:[0-9a-fA-F]{2}){0,8}", sid):
                    report.error("REALITY shortIds must be even-length hex strings of at most 16 characters (empty allowed if intentional).")

    sniff = inbound.get("sniffing") or {}
    bad_dests = set(sniff.get("destOverride", [])) - SNIFF_DESTS
    if bad_dests:
        report.error("`sniffing.destOverride` has unsupported entries.")

    for index, client in enumerate(settings.get("clients", []) or []):
        validate_client(client, report,
                        where=f"client[{index}]")
        if isinstance(protocol, str) and isinstance(network, str) and isinstance(security, str):
            if client.get("flow") and protocol == "vless" and settings.get("decryption") not in (None, "none"):
                report.warn("Vision with VLESS Encryption needs matching-core validation; classic transport gate skipped.")
            else:
                _check_vision_flow(client, protocol, network, security, report)


def validate(payload: dict, report: Report) -> None:
    """Auto-detect the payload shape and dispatch."""
    if "client" in payload:
        # /panel/api/clients/add body: {"client": {...}, "inboundIds": [...]}
        validate_client(payload["client"], report)
        if payload["client"].get("flow"):
            report.warn("Client-only payload cannot prove flow compatibility; inspect every target inbound first.")
        ids = payload.get("inboundIds")
        if ids is not None and (not isinstance(ids, list) or not all(type(i) is int and i > 0 for i in ids)):
            report.error("`inboundIds` must be a list of positive integers (not booleans).")
        elif not ids:
            report.warn("`inboundIds` is empty; the client will not attach to any inbound.")
    elif "protocol" in payload or "streamSettings" in payload:
        validate_inbound(payload, report)
    elif "email" in payload:
        validate_client(payload, report)
    else:
        report.error("Unrecognized payload: expected an inbound, a client-add body, or a client.")


def normalize_shapes(payload: dict, report: Report) -> None:
    """Decode legacy objects and reject wrong types without echoing input values."""
    def obj(parent, key, legacy=False):
        if key not in parent:
            return {}
        value = parent[key]
        if legacy and isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, RecursionError):
                report.error(f"`{key}` contains invalid legacy JSON.")
                return {}
            parent[key] = value
            report.warn(f"`{key}` is legacy JSON-encoded text; preserve the target API's expected shape.")
        if not isinstance(value, dict):
            report.error(f"`{key}` must be an object.")
            return {}
        return value

    settings = obj(payload, "settings", True)
    stream = obj(payload, "streamSettings", True)
    sniff = obj(payload, "sniffing", True)
    if "client" in payload:
        obj(payload, "client")
    reality = obj(stream, "realitySettings")
    obj(reality, "settings")
    for parent, key, item_type in (
        (settings, "clients", dict), (sniff, "destOverride", str),
        (reality, "serverNames", str), (reality, "shortIds", str),
    ):
        if key in parent:
            value = parent[key]
            if not isinstance(value, list) or not all(isinstance(i, item_type) for i in value):
                report.error(f"`{key}` must be an array of {item_type.__name__} values.")


def run(text: str) -> Report:
    report = Report()
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        report.error("invalid JSON input.")
        return report
    if not isinstance(payload, dict):
        report.error("top-level JSON must be an object.")
        return report
    normalize_shapes(payload, report)
    if not report.error_count:
        validate(payload, report)
    return report


def _self_test() -> int:
    cases = [
        # (name, payload, expect_errors_bool)
        ("good vless reality inbound", {
            "remark": "vless-reality-443", "port": 443, "protocol": "vless",
            "settings": {"clients": [{"email": "a@example.test", "flow": "xtls-rprx-vision"}],
                         "decryption": "none", "encryption": "none"},
            "streamSettings": {"network": "tcp", "security": "reality",
                               "realitySettings": {"serverNames": ["www.yahoo.com"],
                                                   "shortIds": ["ab"], "privateKey": "x",
                                                   "settings": {"publicKey": "y"}}},
            "sniffing": {"destOverride": ["http", "tls"]},
        }, False),
        ("flow at inbound top level", {"port": 443, "protocol": "vless", "flow": "xtls-rprx-vision"}, True),
        ("bad port", {"port": 70000, "protocol": "vless"}, True),
        ("vless decryption wrong type", {
            "port": 443, "protocol": "vless",
            "settings": {"decryption": 123, "encryption": "none"}}, True),
        ("vision flow on ws", {
            "port": 8443, "protocol": "vless",
            "settings": {"clients": [{"email": "b@example.test", "flow": "xtls-rprx-vision"}],
                         "decryption": "none", "encryption": "none"},
            "streamSettings": {"network": "ws", "security": "tls"}}, True),
        ("bad sniff dest", {"port": 443, "protocol": "vless",
                            "settings": {"decryption": "none", "encryption": "none"},
                            "sniffing": {"destOverride": ["http", "bogus"]}}, True),
        ("client-add ok", {"client": {"email": "c@example.test", "totalGB": 0}, "inboundIds": [1]}, False),
        ("email with space", {"client": {"email": "bad email"}, "inboundIds": [1]}, True),
        ("quota looks like GiB", {"client": {"email": "d@example.test", "totalGB": 50}, "inboundIds": [1]}, False),
        ("expiry looks like seconds", {"client": {"email": "e@example.test", "expiryTime": 1700000000}, "inboundIds": [1]}, False),
    ]
    failures = 0
    for name, payload, expect_errors in cases:
        report = run(json.dumps(payload))
        got_errors = report.error_count > 0
        ok = got_errors == expect_errors
        print(f"[{'PASS' if ok else 'FAIL'}] {name} "
              f"(errors={report.error_count}, expected_errors={expect_errors})")
        if not ok:
            failures += 1
            print(report.render())
    # The two heuristic cases must produce a WARN even though they are not errors.
    for name, payload in [
        ("quota GiB warn", {"client": {"email": "d@example.test", "totalGB": 50}}),
        ("expiry seconds warn", {"client": {"email": "e@example.test", "expiryTime": 1700000000}}),
    ]:
        report = run(json.dumps(payload))
        has_warn = any(level == "WARN" for level, _ in report.items)
        print(f"[{'PASS' if has_warn else 'FAIL'}] {name} (warn emitted={has_warn})")
        if not has_warn:
            failures += 1
    print(f"\nself-test: {'all passed' if failures == 0 else f'{failures} FAILED'}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?",
                        help="JSON file to validate, or '-' for stdin.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run built-in checks against example payloads and exit.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.path:
        parser.error("provide a JSON file path, '-' for stdin, or --self-test")

    try:
        if args.path == "-":
            text = sys.stdin.read()
        else:
            with open(args.path, encoding="utf-8") as source:
                text = source.read()
    except (OSError, UnicodeError):
        print("error: unable to read UTF-8 input.", file=sys.stderr)
        return 2
    report = run(text)
    print(report.render())
    return 1 if report.error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
