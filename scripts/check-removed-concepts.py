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

A fourth rule (aouda BL-1867) rejects a **stand-in**: a line that a rewrite left where a line that
named a removed concept was. The sentences of the two commits that did it are refused wherever
they are, code included; and any prose line that a page holds three times or more, or that stands in more than three pages,
is refused, because a sentence that fits three places says what none of them was saying. A removed concept is
not retired by replacing its lines with one sentence: write what each place was saying, or delete
the line and repair the sentence, list or table around it.
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
    # Operability S20 (aouda BL-1832): request members kept only to be refused, deleted; the server refuses them as members nobody has.
    (r"pinAllInMemory", "pinAllInMemory", "`storageTemperature: HotOnly`"),
    (r"pkUniquenessOverride", "pkUniquenessOverride", "a bulk load's `validation`"),
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

# The lines the 0.16.0 rewrite put in place of others (a259eb2, f9afb4f, c9a710e). Exact fragments.
STAND_INS: list[str] = [
    "Access is a principal's statements. The credential is an `aouda_` key or a session",
    "A table carries no security member (**BL-1464",
    "# an aouda_ key or a session. GET /api/auth/whoami names the principal",
    "a principal, its statements, and an aouda_ key or a session (GET /api/auth/whoami)",
    "// WhoAmIAsync() — an aouda_ key (AoudaCredential.Key) or a session",
    "// client.whoami() — apiKey is an aouda_ key, or session, never both",
    "is an aouda_ key. aouda whoami --server",
    "a principal's statements, proved by an `aouda_` key or a session",
]

# The same, where the words are an ordinary sentence's too: only a whole line of them is a stand-in.
STAND_IN_LINES: list[str] = [
    "See [Access](auth/index.md) (**BL-1464",
    "See [Access](../auth/index.md) (**BL-1464",
]

# Pages the fourth rule does not read yet, each with its reason. Remove a row with its cause.
STAND_INS_PENDING: dict[str, str] = {
    # 16 lines. The maintainer keeps the Hub pages as they are (Operability Q-5, 2026-11-24).
    "guides/cloud-hub.md": "Operability Q-5",
}

# A prose line this long, of this many words, at most this many times in one page.
_REPEAT_LENGTH = 45
_REPEAT_WORDS = 5
_REPEAT_LIMIT = 2
# The same line, once each, in at most this many pages (three pages share the replication notice today).
_PAGES_LIMIT = 3

EXEMPT_FILES = {"auth/migrating-from-0-14.md", "CHANGELOG.md"}
EXEMPT_PREFIX = "_review/"

# Pages that must name a removed concept to say what became of it: a refusal table (`SETTING_REMOVED`), an upgrade
# table, a release-history row. The allowance is **per page and per name**, each with its reason: the same name on
# another page, and another removed name on the same page, are still hits (Operability S27, aouda BL-1868). A page is
# never exempt as a whole, so a live paragraph that teaches the removed concept is still found.
REMOVAL_TABLES: dict[str, dict[str, str]] = {
    "clients/compatibility.md": {
        "mk_": "the 0.16.0 row says which surface the train removed",
        "RLS": "the 0.16.0 row says which surface the train removed",
    },
    "guides/keys-that-survive-a-wipe.md": {
        "ServerKeyFile": "the table of settings the server refuses (`SETTING_REMOVED`) names each",
        "Keys:File": "the table of settings the server refuses (`SETTING_REMOVED`) names each",
    },
    "guides/plan.md": {
        "RootUser": "the plan's `settings` stage lists the removed settings it reports",
    },
    "guides/upgrading.md": {
        "authMode": "the upgrade table says what an old declaration now gets",
        "server_admin": "the upgrade table says what an old setup now gets",
        "create-admin": "the upgrade table says what an old script now gets",
        "API key": "the upgrade table says what an old setup now gets",
    },
}

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
                if name in REMOVAL_TABLES.get(path.replace("\\", "/"), {}):
                    break
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


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """(number, line) outside code fences and tables (a header or a field's row may repeat)."""
    lines: list[tuple[int, str]] = []
    fence = ""
    for number, line in enumerate(text.split("\n"), start=1):
        bare = re.sub(r"^[ >]*", "", line)
        opened = re.match(r"(`{3,}|~{3,})", bare)
        if fence:
            if opened and bare.startswith(fence) and not bare.strip(fence[0] + " \r"):
                fence = ""
            continue
        if opened:
            fence = opened.group(1)
            continue
        if not bare.startswith("|"):
            lines.append((number, line.strip()))
    return lines


def _is_stand_in(line: str) -> bool:
    return any(fragment in line for fragment in STAND_INS) or line.strip().startswith(tuple(STAND_IN_LINES))


def scan_stand_ins(path: str, text: str) -> list[str]:
    """The fourth rule: a canned line, or a prose line a page holds more than twice."""
    if path in STAND_INS_PENDING:
        return []
    findings = [
        f"{path}:{number}: a stand-in line — write what this place was saying, or delete it"
        for number, line in enumerate(text.split("\n"), start=1)
        if _is_stand_in(line)
    ]
    seen: dict[str, list[int]] = {}
    for number, line in _prose_lines(text):
        if len(line) >= _REPEAT_LENGTH and len(re.findall(r"[A-Za-z]{2,}", re.sub(r"`[^`]*`", "", line))) >= _REPEAT_WORDS:
            seen.setdefault(line, []).append(number)
    for line, numbers in seen.items():
        if len(numbers) > _REPEAT_LIMIT and not _is_stand_in(line):
            findings.append(f"{path}:{numbers[0]}: the same line {len(numbers)} times — say what each place is about: {line[:70]}")
    return findings


def scan_across_pages(pages: dict[str, str]) -> list[str]:
    """The fourth rule across pages: one sentence put once in each of many pages. A heading and a lead-in (`...:`) are a template's."""
    held: dict[str, list[str]] = {}
    for path, text in pages.items():
        for line in dict.fromkeys(line for _, line in _prose_lines(text)):
            if line.startswith("#") or line.endswith(":") or _is_stand_in(line):
                continue
            if len(line) >= _REPEAT_LENGTH and len(re.findall(r"[A-Za-z]{2,}", re.sub(r"`[^`]*`", "", line))) >= _REPEAT_WORDS:
                held.setdefault(line, []).append(path)
    return [
        f"{paths[0]}: the same line in {len(paths)} pages ({', '.join(paths[:4])}) — say what each place is about: {line[:70]}"
        for line, paths in held.items()
        if len(paths) > _PAGES_LIMIT
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--paths", nargs="*", default=[], help="fnmatch globs limiting the files checked")
    parser.add_argument("--no-vocabulary", action="store_true")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    findings: list[str] = []
    prose: dict[str, str] = {}
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
        if rel.endswith((".md", ".txt")):
            findings.extend(scan_stand_ins(rel.replace("\\", "/"), text))
            prose[rel.replace("\\", "/")] = text
    findings.extend(scan_across_pages(prose))
    for line in findings:
        print(line)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
