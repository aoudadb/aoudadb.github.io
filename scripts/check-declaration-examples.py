#!/usr/bin/env python3
"""Validate fenced declaration examples against schemas/aouda-declaration.v1.json.

A block is checked only when the line immediately before the fence is a marker:

    <!-- declaration-example -->
    <!-- declaration-example: fragment /databases/auth -->

A fragment is wrapped at that JSON pointer (and `version: 1` is added when the
pointer is not the document) before validation. Exit 1 names the file, the marker
line and the failing member's pointer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

from jsonschema import Draft202012Validator

_ACTIONS = {"read", "write", "delete", "execute", "manage", "set-identity", "*"}

_WHERE = {"and", "or", "groups"}

_MARKER = re.compile(r"^<!-- declaration-example(?:: fragment (/[A-Za-z0-9_./-]+))? -->\s*$")
_FENCE = re.compile(r"^```json\s*$")


def tracked_markdown(root: str) -> list[str]:
    result = subprocess.run(["git", "-C", root, "ls-files", "-z", "*.md"], check=True, capture_output=True)
    return [p.decode("utf-8").replace("\\", "/") for p in result.stdout.split(b"\0") if p]


def wrap(fragment: object, pointer: str) -> dict:
    node: object = fragment
    for part in reversed([p for p in pointer.split("/") if p]):
        node = {part: node}
    if isinstance(node, dict) and "version" not in node:
        node = {"version": 1, **node}
    if not isinstance(node, dict):
        raise ValueError("a fragment must wrap to an object")
    return node


def blocks(text: str) -> list[tuple[int, str | None, str]]:
    """(marker line, pointer or None, json text)."""
    lines = text.split("\n")
    found: list[tuple[int, str | None, str]] = []
    i = 0
    while i < len(lines):
        marker = _MARKER.match(lines[i])
        if marker and i + 1 < len(lines) and _FENCE.match(lines[i + 1]):
            start = i + 2
            end = start
            while end < len(lines) and lines[end].strip() != "```":
                end += 1
            found.append((i + 1, marker.group(1), "\n".join(lines[start:end])))
            i = end + 1
            continue
        i += 1
    return found


def check_file(path: str, text: str, validator: Draft202012Validator) -> list[str]:
    findings: list[str] = []
    for line, pointer, raw in blocks(text):
        where = f"{path}:{line}"
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            findings.append(f"{where}: not JSON ({exc.msg})")
            continue
        try:
            instance = wrap(document, pointer) if pointer else document
        except ValueError as exc:
            findings.append(f"{where}: {exc}")
            continue
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if errors:
            error = errors[0]
            member = "/" + "/".join(str(p) for p in error.absolute_path)
            findings.append(f"{where}: {member or '/'} {error.message}")
            continue
        _walk_actions(instance, "", findings, where)
    return findings


def _check_row_condition(node: object, pointer: str, findings: list[str], where: str) -> None:
    """A row condition is lists named `and`, `or`, `groups`; a group is one again; a condition in a list names its `column`."""
    if not isinstance(node, dict) or not node or not set(node) <= _WHERE:
        findings.append(f"{where}: {pointer} is not a row condition: its members are and, or, groups")
        return
    for member, items in node.items():
        if not isinstance(items, list) or not items:
            findings.append(f"{where}: {pointer}/{member} is not a list of at least one")
            continue
        for index, item in enumerate(items):
            if member == "groups":
                _check_row_condition(item, f"{pointer}/groups/{index}", findings, where)
            elif not isinstance(item, dict) or "column" not in item:
                findings.append(f"{where}: {pointer}/{member}/{index} is not a condition: it names no column")


def _walk_actions(node: object, pointer: str, findings: list[str], where: str) -> None:
    """What the server's reader refuses and the published schema does not: an action outside the six (plus `*`), and a `where`
    that is a bare condition (aouda BL-1867: the access chapter's own examples were, and a plan refuses them)."""
    if isinstance(node, dict):
        actions = node.get("actions")
        resources = node.get("resources")
        if isinstance(actions, list) and isinstance(resources, list):
            for index, action in enumerate(actions):
                if action not in _ACTIONS:
                    findings.append(
                        f"{where}: {pointer}/actions/{index} {action!r} is not one of "
                        "read, write, delete, execute, manage, set-identity"
                    )
            if "where" in node:
                _check_row_condition(node["where"], f"{pointer}/where", findings, where)
        for key, value in node.items():
            _walk_actions(value, f"{pointer}/{key}", findings, where)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_actions(value, f"{pointer}/{index}", findings, where)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--paths", nargs="*", default=[])
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    schema_path = os.path.join(root, "schemas", "aouda-declaration.v1.json")
    with open(schema_path, encoding="utf-8") as handle:
        schema = json.load(handle)
    validator = Draft202012Validator(schema)
    findings: list[str] = []
    for rel in tracked_markdown(root):
        if args.paths and not any(_match(rel, g) for g in args.paths):
            continue
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        with open(full, encoding="utf-8-sig", newline="") as handle:
            findings.extend(check_file(rel, handle.read(), validator))
    for line in findings:
        print(line)
    return 1 if findings else 0


def _match(path: str, pattern: str) -> bool:
    from fnmatch import fnmatch
    return fnmatch(path, pattern)


if __name__ == "__main__":
    sys.exit(main())
