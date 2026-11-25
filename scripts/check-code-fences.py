#!/usr/bin/env python3
"""Fail when a text sweep has damaged the pages: code that lost its `()`, `[]` or indentation, or a passage swallowed whole.

Usage:
    python3 scripts/check-code-fences.py [--root DIR]                  # the pages as they are
    python3 scripts/check-code-fences.py [--root DIR] --base REF       # and what they lost since REF (a commit, `origin/main`)
                                         [--max-lines N]

Commit `42bfd3b` (the 0.17.0 marker sweep) is why it exists (BL-1865): its rewrite removed the `next train` markers and, with them,
every empty `()` and `[]`, every space before a `.` or a `,`, and the indentation of every line, in 80 pages; and its marker
pattern, which began at any `(**` and ended at the next `next train**)`, swallowed 18 passages between two unrelated citations,
tables and code among them. Nothing failed: a page of broken code is still a page.

Without `--base`, each code fence is checked for what only a missing `()`, `[]` or indentation leaves behind:

- `indent`    a line indented by one space right after a line that opens a block, or a `.call(` chain link at the margin;
- `value`     an assignment, argument or JSON member with no value (`= ;`, `"rows": ,`);
- `call`      `new Name;`, `await a.b;` (a method never called), an arrow or a `function` with no parameter list.

With `--base REF`, every page is also compared with REF:

- `stripped`  a line that differs from a line of REF only by lost `()`, `[]` or (in a fence) its indentation or inner spaces. More than
              `--max-lines` of them (default 2, so a deliberate edit of one line passes) fail;
- `swallowed` a line that is the head of one line of REF and the tail of a later one, with 120 characters or more gone between
              (it does not see a passage that went inside one line, or whole lines: read the diff for those).

Run it with `--base` after any edit made by a script (a sweep, a search-and-replace), and in a release PR (dev/Release-And-Version-Bump.md
section 2). A line that is right as it is goes into `_ALLOW`, with the reason. Exit status 1 when anything is found, 0 otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass

SKIP_DIRS = {".git", ".claude", "_site", "vendor", "node_modules", "_review", ".jekyll-cache", ".bundle"}
SCAN_SUFFIXES = (".md", ".txt")
SWALLOWED_CHARS = 120

# (path, stripped line) that a rule reads as damage and is right. Empty: add one only with its reason.
_ALLOW: set[tuple[str, str]] = set()

_FENCE = re.compile(r"^\s*(`{3,})\s*([\w+-]*)")
_CODE = {"ts", "typescript", "js", "javascript", "tsx", "jsx", "csharp", "cs"}
_JSON = {"json", "jsonc"}
_OPENS = re.compile(r"(?:[{\[(]|=>)\s*(?://.*|/\*.*\*/\s*)?$")
_VALUE = re.compile(r"(?<![=!<>+\-*/%&|^?:])=\s*(?:;|,|\)|$)(?!=)|[(,]\s*,|:\s*;")
_JSON_VALUE = re.compile(r'"\s*:\s*[,}\]]|[\[,]\s*,')
_CALL = re.compile(r"\bnew\s+[A-Za-z_][\w.]*(?:<[\w<>,\s.\[\]]*>)?\s*[;,)]"          # new Name;
                   r"|\)\.(?:execute|count|toList|delete|truncate|toListAsync|countAsync|ToListAsync|CountAsync|FirstOrDefaultAsync);"
                   r"|[(,=]\s*(?:async\s*)?=>"                                        # an arrow with no parameter list
                   r"|\bfunction\s+[A-Za-z_$][\w$]*\s*[:{]")
# Members that are awaited as they are (a task, not a method).
_AWAITABLE = {"Task", "Outcome", "outcome", "MqRebuildCompleted"}
_AWAIT = re.compile(r"\bawait\s+(?:[\w$]+\.)+([A-Za-z_$][\w$]*)\s*(?:;|$)")           # await a.b;
_STRING = re.compile(r"'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\\n])*`")
_LINE_COMMENT = re.compile(r"//.*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/")
_BRACKETS = re.compile(r"\(\s*\)|\[\s*\]")


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    line: int
    rule: str
    text: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.text.strip()[:140]}"


def fences(lines: list[str]) -> list[tuple[int, int, str]]:
    """Every code fence: (index of its first body line, index after its last, language). An unclosed one runs to the end."""
    found: list[tuple[int, int, str]] = []
    i = 0
    while i < len(lines):
        opening = _FENCE.match(lines[i])
        if opening:
            close = re.compile(r"^\s*`{" + str(len(opening.group(1))) + r",}\s*$")
            j = i + 1
            while j < len(lines) and not close.match(lines[j]):
                j += 1
            found.append((i + 1, j, opening.group(2).lower()))
            i = j
        i += 1
    return found


def _bare(line: str) -> str:
    """The code of a line: strings emptied, comments gone (a block comment may stand for a value, so it leaves a `0`)."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("0", _STRING.sub("''", line))).rstrip()


def check_fence(path: str, lines: list[str], start: int, end: int, language: str) -> list[Finding]:
    found: list[Finding] = []
    previous = ""
    for k in range(start, end):
        line = lines[k]
        if not line.strip():
            previous = ""
            continue
        rules: list[str] = []
        code = language in _CODE
        if code or language in _JSON:
            if re.match(r" [^ *]", line) and _OPENS.search(previous):
                rules.append("indent")
            if code and re.match(r"\.[A-Za-z]\w*[(<]?", line) and re.match(r"[A-Za-z]", previous) and not _bare(previous).endswith(";"):
                rules.append("indent")
            bare = _bare(line)
            if language in _JSON:
                if _JSON_VALUE.search(_STRING.sub('""', line)):
                    rules.append("value")
            else:
                # a `=` that ends a line continues on the next; a lone `,` starts an elided array element only with a name before it
                if _VALUE.search(bare) and not re.search(r"=\s*$", bare):
                    rules.append("value")
                awaited = _AWAIT.search(bare)
                if _CALL.search(bare) or (awaited and awaited.group(1) not in _AWAITABLE):
                    rules.append("call")
        found.extend(Finding(path, k + 1, rule, line) for rule in dict.fromkeys(rules) if (path, line.strip()) not in _ALLOW)
        previous = line
    return found


def check_text(path: str, text: str) -> list[Finding]:
    lines = text.split("\n")
    return [f for start, end, language in fences(lines) for f in check_fence(path, lines, start, end, language)]


def squash(line: str) -> str:
    """The line without what a sweep takes: whitespace, `()` and `[]`."""
    while True:
        shorter = _BRACKETS.sub("", line)
        if shorter == line:
            return re.sub(r"\s+", "", line)
        line = shorter


def _common_prefix(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def compare_text(path: str, base: str, text: str) -> tuple[list[Finding], list[Finding]]:
    """(stripped, swallowed) findings of a page against its REF text."""
    old, new = base.split("\n"), text.split("\n")
    in_old, in_new = Counter(old), Counter(new)
    fenced = {k for start, end, _ in fences(new) for k in range(start, end)}
    gone: dict[str, list[str]] = {}
    for line in old:
        if line not in in_new and squash(line):
            gone.setdefault(squash(line), []).append(line)
    stripped: list[Finding] = []
    swallowed: list[Finding] = []
    lost = [(i, squash(line)) for i, line in enumerate(old) if line not in in_new and squash(line)]
    flat = [squash(line) for line in old]
    for k, line in enumerate(new):
        key = squash(line)
        if line in in_old or not key:
            continue
        before = gone.get(key)
        if before:
            brackets = len(_BRACKETS.findall(line))
            for was in before:
                fewer = len(_BRACKETS.findall(was)) > brackets
                if fewer or (k in fenced and _lost_spaces(was, line)):
                    stripped.append(Finding(path, k + 1, "stripped", line))
                    before.remove(was)
                    break
            continue
        hit = _swallowed(key, lost, flat)
        if hit:
            swallowed.append(Finding(path, k + 1, "swallowed", f"{hit} characters of {path} are gone inside this line: {line}"))
    return stripped, swallowed


def _lost_spaces(was: str, line: str) -> bool:
    """The indentation went to nothing (or to one space), or spaces inside the line are gone. A dedent by a level is an edit."""
    indent = len(line) - len(line.lstrip())
    return (indent <= 1 < len(was) - len(was.lstrip())) or len(line.strip()) < len(was.strip())


def _swallowed(key: str, lost: list[tuple[int, str]], flat: list[str]) -> int:
    """How many squashed characters a splice of two of REF's lines lost, or 0. `key` = the head of one + the tail of a later one."""
    if len(key) < 40:
        return 0
    heads = [(i, line, _common_prefix(key, line)) for i, line in lost]
    # an edit inside one line (a marker taken out of it) keeps that line's head and its tail: not a splice
    if any(p >= 12 and line.endswith(key[p:]) for _, line, p in heads):
        return 0
    for i, head, p in heads:
        if p < 12 or p == len(key):
            continue
        tail = key[p:]
        if len(tail) < 12:
            continue
        for j, last in lost:
            if j <= i or not last.endswith(tail):
                continue
            missing = len(head) - p + sum(len(s) for s in flat[i + 1:j]) + len(last) - len(tail)
            if missing >= SWALLOWED_CHARS:
                return missing
    return 0


def pages(root: str) -> list[str]:
    out: list[str] = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        out.extend(os.path.relpath(os.path.join(directory, f), root).replace(os.sep, "/") for f in sorted(files) if f.endswith(SCAN_SUFFIXES))
    return out


def _git_show(root: str, ref: str, path: str) -> str | None:
    result = subprocess.run(["git", "-C", root, "show", f"{ref}:./{path}"], capture_output=True)
    return result.stdout.decode("utf-8-sig") if result.returncode == 0 else None


def check(root: str, base: str | None = None, max_lines: int = 2) -> list[Finding]:
    findings: list[Finding] = []
    stripped: list[Finding] = []
    for path in pages(root):
        with open(os.path.join(root, path), encoding="utf-8-sig", newline="") as f:
            text = f.read()
        findings.extend(check_text(path, text))
        was = _git_show(root, base, path) if base else None
        if was is not None and was != text:
            a, b = compare_text(path, was, text)
            stripped.extend(a)
            findings.extend(b)
    if len(stripped) > max_lines:
        findings.extend(stripped)
    return sorted(findings)


def main(argv: list[str]) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=os.path.dirname(here), help="the docs checkout to scan (default: this one)")
    parser.add_argument("--base", help="a commit of the same checkout: also report what the pages lost since it")
    parser.add_argument("--max-lines", type=int, default=2, help="stripped lines (--base) that still pass, over all pages (default: 2)")
    args = parser.parse_args(argv)
    if args.base and subprocess.run(["git", "-C", args.root, "rev-parse", "--verify", "--quiet", args.base + "^{commit}"],
                                    capture_output=True).returncode != 0:
        print(f"error: {args.base} is not a commit of {args.root} (git fetch there first)", file=sys.stderr)
        return 2

    findings = check(args.root, args.base, args.max_lines)
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} damaged line(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
