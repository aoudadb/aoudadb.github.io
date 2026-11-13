#!/usr/bin/env python3
"""Fail when a `next train` marker names a BL id whose work is already in a released version.

Usage:
    python3 scripts/check-next-train.py [--root DIR] [--aouda DIR] [--client-ts DIR] [--studio DIR] [--ref REF]

A page marks behaviour that is on `main` but not yet released as `(**BL-NNN, next train**)`. When the train ships, the marker
must become `(**BL-NNN, X.Y.Z**)` (dev/Release-And-Version-Bump.md section 2); one left behind tells a reader the page
describes a server they cannot install yet.

The spellings in use (all found by the one rule "a BL id list directly before the words `next train`"):

    (**BL-1234, next train**)     (**BL-1234, BL-1235, next train**)     (**BL-1234 review, next train**)
    (aouda BL-1234, next train)   BL-1234, next train: one option ...    since **BL-1234, next train**)

A marker with no BL id (`Lead S12 (next train)`, `(**Next train:** ...)`) cannot be checked and is skipped.

How "released" is decided: a BL id that appears in a released version's section of a sibling checkout's changelog is released.

    --aouda      docs/CHANGELOG.md   `### X.Y.Z - date` under `## Releases`   (default: a sibling `aouda`)
    --client-ts  CHANGELOG.md        `## X.Y.Z`                               (default: a sibling `aouda-client-ts`)
    --studio     CHANGELOG.md        `## X.Y.Z - date`                        (default: a sibling `aouda-studio`)

Siblings are looked for next to this repo and next to each parent directory above it (so a worktree under
`.claude/worktrees/` finds them too). A changelog is read from `origin/main` of that checkout (`--ref` to change it; run
`git fetch` there first, this script never does) and, when that ref does not exist, from the file on disk. The aouda changelog is
required; the other two are skipped with a note when no checkout is found.

A line of a released section that says the work is NOT shipped (`not yet shipped`, `unreleased`, `next train`, `planned`) does
not count: the 0.13.0 section names BL-1380 that way. Exit status 1 when a marker is stale, 0 otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass

SKIP_DIRS = {".git", ".claude", "_site", "vendor", "node_modules", "_review", ".jekyll-cache", ".bundle"}
SCAN_SUFFIXES = (".md", ".txt")

_MARKER = re.compile(r"next[\s-]+train", re.IGNORECASE)
# A BL id list straight before the words: "BL-1", "BL-1, BL-2", "BL-1 review", "aouda BL-1" (the prefix is skipped).
_IDS_BEFORE = re.compile(r"(BL-\d+(?:[ \t]+[A-Za-z]+)?(?:[*`_]*[ \t]*[,/&][ \t]*[*`_]*BL-\d+(?:[ \t]+[A-Za-z]+)?)*)$")
_BL = re.compile(r"BL-(\d+)")
_VERSION_HEADING = re.compile(r"^(#{1,6})[ \t]+v?(\d+\.\d+\.\d+)\b")
_ANY_HEADING = re.compile(r"^(#{1,6})[ \t]+\S")
_NOT_SHIPPED = re.compile(r"not\s+yet\s+(?:shipped|released)|unreleased|next\s+train|planned|not\s+shipped", re.IGNORECASE)


@dataclass(frozen=True)
class Release:
    repo: str
    version: str
    line: int


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    bl: str
    repo: str
    version: str
    changelog_line: int

    def __str__(self) -> str:
        return (f"{self.path}:{self.line}: {self.bl} shipped in {self.repo} {self.version} "
                f"(its CHANGELOG, line {self.changelog_line}): replace `next train` with `{self.version}`, "
                f"i.e. (**{self.bl}, {self.version}**)")


def find_markers(text: str) -> list[tuple[int, list[str]]]:
    """Every `next train` marker that names BL ids: (1-based line, [ids]) in reading order."""
    found: list[tuple[int, list[str]]] = []
    for number, line in enumerate(text.split("\n"), start=1):
        for match in _MARKER.finditer(line):
            prefix = line[: match.start()].rstrip(" \t*`_,")
            ids = _IDS_BEFORE.search(prefix)
            if ids:
                found.append((number, ["BL-" + n for n in _BL.findall(ids.group(1))]))
    return found


def parse_released(text: str, repo: str) -> dict[str, Release]:
    """BL id -> the earliest released section of this changelog that mentions it (sections run newest first)."""
    released: dict[str, Release] = {}
    version: str | None = None
    level = 0
    for number, line in enumerate(text.lstrip("﻿").split("\n"), start=1):
        heading = _ANY_HEADING.match(line)
        if heading:
            depth = len(heading.group(1))
            as_version = _VERSION_HEADING.match(line)
            if as_version:
                version, level = as_version.group(2), depth
                continue
            if version is not None and depth <= level:
                version = None  # "## Unreleased", "## Historical notes": the released run is over
            continue
        if version is None or _NOT_SHIPPED.search(line):
            continue
        for n in _BL.findall(line):
            released[f"BL-{n}"] = Release(repo, version, number)  # a later (older) section overwrites: earliest wins
    return released


def scan(root: str) -> list[tuple[str, int, list[str]]]:
    """Every marker under root: (path relative to root, line, ids)."""
    out: list[tuple[str, int, list[str]]] = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if not name.endswith(SCAN_SUFFIXES):
                continue
            path = os.path.join(directory, name)
            with open(path, encoding="utf-8-sig") as f:
                text = f.read()
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            out.extend((rel, line, ids) for line, ids in find_markers(text))
    return out


def check(root: str, released: dict[str, Release]) -> list[Finding]:
    findings: list[Finding] = []
    for rel, line, ids in scan(root):
        for bl in ids:
            hit = released.get(bl)
            if hit:
                findings.append(Finding(rel, line, bl, hit.repo, hit.version, hit.line))
    return sorted(set(findings))


def _find_sibling(start: str, name: str) -> str | None:
    here = os.path.abspath(start)
    while True:
        candidate = os.path.join(here, name)
        if os.path.isdir(os.path.join(candidate, ".git")) or os.path.isfile(os.path.join(candidate, ".git")):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def _read_changelog(repo_dir: str, rel: str, ref: str) -> str:
    try:
        result = subprocess.run(["git", "-C", repo_dir, "show", f"{ref}:{rel}"], capture_output=True, check=True)
        return result.stdout.decode("utf-8-sig")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"note: {repo_dir} has no {ref}:{rel}; reading the file on disk", file=sys.stderr)
        with open(os.path.join(repo_dir, rel), encoding="utf-8-sig") as f:
            return f.read()


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=os.path.dirname(here), help="the docs checkout to scan (default: this one)")
    parser.add_argument("--aouda", help="path to the aouda checkout (default: a sibling)")
    parser.add_argument("--client-ts", help="path to the aouda-client-ts checkout (default: a sibling, optional)")
    parser.add_argument("--studio", help="path to the aouda-studio checkout (default: a sibling, optional)")
    parser.add_argument("--ref", default="origin/main", help="the ref whose changelogs count as released (default: origin/main)")
    args = parser.parse_args(argv)

    sources = [("aouda", args.aouda, "aouda", "docs/CHANGELOG.md", True),
               ("@aouda/client", args.client_ts, "aouda-client-ts", "CHANGELOG.md", False),
               ("Studio", args.studio, "aouda-studio", "CHANGELOG.md", False)]
    released: dict[str, Release] = {}
    for label, given, sibling, rel, required in sources:
        repo_dir = given or _find_sibling(args.root, sibling)
        if repo_dir is None:
            if required:
                print(f"error: no aouda checkout found next to {args.root}; pass --aouda", file=sys.stderr)
                return 2
            print(f"note: no {sibling} checkout found, its changelog is not checked (pass --{sibling.replace('aouda-', '')})",
                  file=sys.stderr)
            continue
        for bl, release in parse_released(_read_changelog(repo_dir, rel, args.ref), label).items():
            released.setdefault(bl, release)  # aouda first: the server's release wins over a client's

    findings = check(args.root, released)
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} stale `next train` marker(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
