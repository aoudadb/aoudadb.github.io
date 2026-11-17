#!/usr/bin/env python3
"""Fail when a public page still teaches a concept the principals cut deleted.

Usage:
    python3 scripts/check-removed-concepts.py [--root DIR] [--paths GLOB ...] [--no-vocabulary]

The list below is the exit check (overview section 5, Principals S18). A hit prints
`path:line: <name> — use <replacement>` and the process exits 1. Exemptions, exactly three:
`auth/migrating-from-0-14.md` (the migration page quotes every removed name on purpose),
`CHANGELOG.md` (release history) and anything under `_review/` (unpublished).

Patterns are word-anchored. `_` is a word character, so `numk_` and `aouda_<id>_mk_…` are
not hits, while `mk_svc_abc` and `` `mk_` `` are.

A second rule (on unless `--no-vocabulary`) rejects the old words for a kind: "service key",
"API key", RBAC, PLS, RLS, ADRA. A SendGrid (or other provider) credential is a "provider key"
on these pages, so the phrase "API key" is free for the check.

A third rule rejects a string shaped `aouda_[a-z2-7]{16}_[A-Za-z0-9]{49}` whose checksum is
ADR 0071 D-15's (IEEE CRC-32 of the first 66 characters, four big-endian bytes, six base62
digits, alphabet `0-9A-Za-z`). The script imports nothing from the engine; it reimplements
that checksum. A placeholder that fails the checksum is not a hit.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zlib

# (pattern, display name, replacement). Patterns are searched with re.IGNORECASE except where
# the name is an identifier whose case is the name; those patterns carry their own case by
# being written in the case the pages used, and IGNORECASE still catches Entitlement / AuthMode.
REMOVED: list[tuple[str, str, str]] = [
    (r"mk_", "mk_", "a key in the current format (`aouda_<id>_<secret>`)"),
    (r"X-User-Token", "X-User-Token", "the caller's own credential, or a limited key"),
    (r"user_token", "user_token", "the caller's own credential, or a limited key"),
    (r"userToken", "userToken", "the caller's own credential, or a limited key"),
    (r"authMode", "authMode", "a statement `where` (a table carries no security)"),
    (r"service_role", "service_role", "a principal with the statements the service needs"),
    (r"scoped_service", "scoped_service", "a principal with roles"),
    (r"server_admin", "server_admin", "a `_serverauth` principal holding role `admin`"),
    (r"Keys:File", "Keys:File", "principals in `aouda.json`"),
    (r"ServerKeyFile", "ServerKeyFile", "a declared `_serverauth` principal"),
    (r"RootUser", "RootUser", "a declared principal with a password seed"),
    (r"allowSelfSignup", "allowSelfSignup", "`signup.enabled` on the auth database"),
    (r"selfSignupRole", "selfSignupRole", "`signup.roles`"),
    (r"aouda\.identities\.json", "aouda.identities.json", "`aouda.json`"),
    (r"entitlements?", "entitlement", "an attribute read by a statement `where`"),
    (r"resolvers?", "resolver", "a statement `where`"),
    (r"partitionLevelSecurity", "partitionLevelSecurity", "a statement `where`"),
    (r"plsClaimBinding", "plsClaimBinding", "a statement `where` on `principal.id` or an attribute"),
    (r"permissionDimension", "permissionDimension", "an attribute"),
    (r"permissionColumn", "permissionColumn", "the column named in the statement `where`"),
    (r"rlsResolverName", "rlsResolverName", "a statement `where`"),
    (r"dataPlaneAccess", "dataPlaneAccess", "a statement on the `anonymous` principal"),
    (r"db_admin", "db_admin", "the built-in role `admin`"),
    (r"db_writer", "db_writer", "the built-in role `writer`"),
    (r"db_reader", "db_reader", "the built-in role `reader`"),
    (r"db_operator", "db_operator", "a role whose statements say what it may do"),
    (r"auth_admin", "auth_admin", "`manage` on `<auth>/principal/*` and `<auth>/role/*`"),
    (r"all-partitions", "all-partitions", "a statement with no `where`"),
    (r"all-rows", "all-rows", "a statement with no `where`"),
    (r"appAuth", "appAuth", "one credential (a key or a session)"),
    (r"serverAuth", "serverAuth", "one credential (a key or a session)"),
    (r"authAdmin", "authAdmin", "`client.access`"),
    (r"create-admin", "create-admin", "`aouda init`, setup mode, or a declared principal"),
    (r"access-grants", "access-grants", "`GET /api/auth/whoami`"),
    (r"access_grant_used", "access_grant_used", "the audit kind `unconditional_access`"),
    (r"policy/inspect", "policy/inspect", "`aouda policy explain`"),
    (r"policy inspect", "policy inspect", "`aouda policy explain`"),
    (r"api-key-prefix", "api-key-prefix", "the one key format"),
    (r"regenerate-keys", "regenerate-keys", "mint a new key, then delete the old one"),
    (r"configured-keys", "configured-keys", "the principal's credentials"),
]

# Old words for a kind. "API key" is included: a provider credential is called a provider key.
VOCABULARY: list[tuple[str, str, str]] = [
    (r"service key", "service key", "a key on a principal"),
    (r"API key", "API key", "a key (`aouda_<id>_<secret>`), or a provider key when it is someone else's"),
    (r"RBAC", "RBAC", "roles (named bundles of statements)"),
    (r"PLS", "PLS", "a statement `where`"),
    (r"RLS", "RLS", "a statement `where`"),
    (r"ADRA", "ADRA", "the policy (statements)"),
]

EXEMPT_FILES = {"auth/migrating-from-0-14.md", "CHANGELOG.md"}
EXEMPT_PREFIX = "_review/"

_BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_KEY = re.compile(r"aouda_[a-z2-7]{16}_[A-Za-z0-9]{49}")


def _base62_u32(value: int) -> str:
    digits = ["0"] * 6
    pos = 6
    number = value & 0xFFFFFFFF
    while number and pos:
        pos -= 1
        digits[pos] = _BASE62[number % 62]
        number //= 62
    return "".join(digits)


def checksum_of(body: str) -> str:
    """Six base62 characters: IEEE CRC-32 of the ASCII body, big-endian."""
    crc = zlib.crc32(body.encode("ascii")) & 0xFFFFFFFF
    return _base62_u32(crc)


def key_checksum_ok(token: str) -> bool:
    if not _KEY.fullmatch(token):
        return False
    return checksum_of(token[:66]) == token[66:]


def _compile(rows: list[tuple[str, str, str]]) -> list[tuple[re.Pattern[str], str, str]]:
    compiled = []
    for pattern, name, replacement in rows:
        # A trailing `_` is a word character, so `\b` after `mk_` would miss `mk_svc_abc`.
        # The spec's anchor is the leading one (`\bmk_`).
        tail = pattern[-1]
        word_tail = tail.isalnum() or (tail == "?" and len(pattern) > 1 and pattern[-2].isalnum())
        suffix = r"\b" if word_tail else ""
        compiled.append((re.compile(r"\b" + pattern + suffix, re.IGNORECASE), name, replacement))
    return compiled


_REMOVED = _compile(REMOVED)
_VOCAB = _compile(VOCABULARY)


def tracked_files(root: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    rels = [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]
    return [p.replace("\\", "/") for p in rels]


def exempt(path: str) -> bool:
    norm = path.replace("\\", "/")
    if norm in EXEMPT_FILES or norm.startswith(EXEMPT_PREFIX):
        return True
    return False


def _selected(path: str, globs: list[str]) -> bool:
    if not globs:
        return True
    from fnmatch import fnmatch
    norm = path.replace("\\", "/")
    return any(fnmatch(norm, g) for g in globs)


def scan_text(path: str, text: str, vocabulary: bool) -> list[str]:
    findings: list[str] = []
    rules = _REMOVED + (_VOCAB if vocabulary else [])
    for number, line in enumerate(text.split("\n"), start=1):
        for pattern, name, replacement in rules:
            if pattern.search(line):
                findings.append(f"{path}:{number}: {name} — use {replacement}")
                break
        for match in _KEY.finditer(line):
            if key_checksum_ok(match.group(0)):
                findings.append(
                    f"{path}:{number}: aouda_<id>_<secret> — use a placeholder whose checksum does not match "
                    "(a real key must not be published)"
                )
                break
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--paths", nargs="*", default=[], help="fnmatch globs limiting the files checked")
    parser.add_argument("--no-vocabulary", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    findings: list[str] = []
    for rel in tracked_files(root):
        if exempt(rel) or not _selected(rel, args.paths):
            continue
        if not rel.endswith((".md", ".txt", ".json")):
            continue
        # Published examples and schema are in scope; vendor gems are not tracked.
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8-sig", newline="") as handle:
            text = handle.read()
        findings.extend(scan_text(rel, text, vocabulary=not args.no_vocabulary))
    for line in findings:
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
