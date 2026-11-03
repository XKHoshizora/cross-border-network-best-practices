#!/usr/bin/env python3
"""Parse a VLESS/VMess/Trojan share link into normalized fields, offline.

This script never touches the network. It decodes a share link so you can
compare a client's transport/security parameters (sni, fp, pbk, sid, type,
security, flow, path, host) against the inbound configuration — WITHOUT
exposing the credential. The per-user secret (VLESS UUID, Trojan password,
VMess id) is masked by default; pass --show-secrets only if you truly need it.

Usage:
    python scripts/parse_share_link.py 'vless://...#name'
    pbpaste | python scripts/parse_share_link.py -
    python scripts/parse_share_link.py --self-test

Credentials, names, paths, and unrecognized parameters are masked by default.
Address/SNI/public-key metadata remains visible: review output before sharing.
Use stdin for live links to avoid putting credentials into shell history/argv.

Contents: redaction; decoding; protocol parsers; dispatch; self-test; CLI.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from urllib.parse import parse_qs, unquote, urlsplit

# Allow only known diagnostic fields; extensions may contain credentials.
VISIBLE_PARAMS = {"type", "security", "encryption", "flow", "sni", "fp", "pbk",
                  "sid", "alpn", "net", "tls", "scy", "host"}


def mask(secret: str, reveal: bool) -> str:
    return secret if reveal or not secret else "(masked)"


def safe_params(params: dict, reveal: bool) -> dict:
    return {key: value if reveal or key in VISIBLE_PARAMS else "(masked)"
            for key, value in params.items()}


def endpoint(address, port):
    if not isinstance(address, str) or not address or any(c.isspace() for c in address):
        raise ValueError("missing or invalid address")
    if isinstance(port, bool) or not isinstance(port, (int, str)):
        raise ValueError("missing or invalid port")
    if isinstance(port, str) and not port.isascii():
        raise ValueError("invalid port")
    if isinstance(port, str) and not port.isdigit():
        raise ValueError("invalid port")
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return address, port


def _b64decode(data: str) -> bytes:
    # Share links use unpadded base64url or base64; tolerate both.
    data = data.strip().replace("-", "+").replace("_", "/")
    data += "=" * (-len(data) % 4)
    return base64.b64decode(data, validate=True)


def _flatten_qs(query: str) -> dict[str, str]:
    params = parse_qs(query, keep_blank_values=True)
    if any(len(values) != 1 for values in params.values()):
        raise ValueError("duplicate query parameter")
    return {key: values[0] for key, values in params.items()}


def parse_vless_trojan(link: str, scheme: str, reveal: bool) -> dict:
    parts = urlsplit(link)
    userinfo, separator, _ = parts.netloc.rpartition("@")
    if not separator:
        raise ValueError("missing credential")
    secret = unquote(userinfo)
    if not secret:
        raise ValueError("missing credential")
    address, port = endpoint(parts.hostname, parts.port)
    cred_field = "uuid" if scheme == "vless" else "password"
    return {
        "protocol": scheme,
        "address": address,
        "port": port,
        cred_field: mask(secret, reveal),
        "params": safe_params(_flatten_qs(parts.query), reveal),
        "name": mask(unquote(parts.fragment), reveal) if parts.fragment else None,
    }


def parse_vmess(link: str, reveal: bool) -> dict:
    raw = link[len("vmess://"):]
    obj = json.loads(_b64decode(raw))
    if not isinstance(obj, dict):
        raise ValueError("VMess data must be an object")
    if not isinstance(obj.get("id"), str) or not obj["id"]:
        raise ValueError("missing VMess credential")
    address, port = endpoint(obj.get("add"), obj.get("port"))
    if "ps" in obj and not isinstance(obj["ps"], str):
        raise ValueError("invalid VMess name")
    # VMess packs everything into a JSON blob; lift the transport/security keys
    # into `params` so the output shape matches vless/trojan.
    param_keys = ("net", "type", "host", "path", "tls", "sni", "alpn", "fp", "scy")
    if any(key in obj and not isinstance(obj[key], str) for key in param_keys):
        raise ValueError("VMess transport fields must be strings")
    return {
        "protocol": "vmess",
        "address": address,
        "port": port,
        "uuid": mask(str(obj.get("id", "")), reveal),
        "params": safe_params({k: obj[k] for k in param_keys if k in obj}, reveal),
        "name": mask(obj.get("ps", ""), reveal),
    }


def parse_link(link: str, reveal: bool = False) -> dict:
    link = link.strip()
    if link.startswith("vless://"):
        return parse_vless_trojan(link, "vless", reveal)
    if link.startswith("trojan://"):
        return parse_vless_trojan(link, "trojan", reveal)
    if link.startswith("vmess://"):
        return parse_vmess(link, reveal)
    raise ValueError("unsupported scheme; expected vless://, vmess://, or trojan://")


def _self_test() -> int:
    failures = 0

    vless = ("vless://11111111-2222-4333-8444-555555555555@host.example.com:443"
             "?type=tcp&security=reality&encryption=none&flow=xtls-rprx-vision"
             "&sni=www.yahoo.com&fp=chrome&pbk=PUBLICKEY&sid=ab12&spx=%2F#my-node")
    out = parse_link(vless)
    checks = [
        out["protocol"] == "vless",
        out["address"] == "host.example.com",
        out["port"] == 443,
        out["uuid"] == "(masked)",
        out["params"]["security"] == "reality",
        out["params"]["sni"] == "www.yahoo.com",
        out["params"]["pbk"] == "PUBLICKEY",      # public key is NOT masked
        out["name"] == "(masked)",
    ]
    # reveal mode shows the full secret
    checks.append(parse_link(vless, reveal=True)["uuid"] == "11111111-2222-4333-8444-555555555555")

    trojan = "trojan://s3cretpass@host.example.com:443?security=tls&type=tcp#t"
    tout = parse_link(trojan)
    checks += [tout["protocol"] == "trojan", "masked" in tout["password"],
               tout["params"]["security"] == "tls"]

    vmess_obj = {"v": "2", "ps": "vm", "add": "host.example.com", "port": "443",
                 "id": "11111111-2222-4333-8444-555555555555", "net": "ws",
                 "path": "/ws", "tls": "tls", "sni": "a.example.com"}
    vmess = "vmess://" + base64.b64encode(json.dumps(vmess_obj).encode()).decode()
    vout = parse_link(vmess)
    checks += [vout["protocol"] == "vmess", vout["address"] == "host.example.com",
               vout["port"] == 443, "masked" in vout["uuid"],
               vout["params"]["net"] == "ws", vout["params"]["path"] == "(masked)"]

    for i, ok in enumerate(checks):
        if not ok:
            print(f"[FAIL] check #{i}")
            failures += 1
    print(f"self-test: {'all passed' if failures == 0 else f'{failures} FAILED'} "
          f"({len(checks)} checks)")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("link", nargs="?", help="Share link, or '-' to read from stdin.")
    parser.add_argument("--show-secrets", action="store_true",
                        help="Reveal credentials, names, paths and extension parameters; private local use only.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run built-in checks against example links and exit.")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.link:
        parser.error("provide a share link, '-' for stdin, or --self-test")

    link = sys.stdin.read() if args.link == "-" else args.link
    try:
        result = parse_link(link, reveal=args.show_secrets)
    except (ValueError, UnicodeError, RecursionError):
        # Parser exceptions may embed credentials or the original URL.
        print("error: invalid share link; check scheme, encoding, credential, host, port and duplicate parameters.", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
