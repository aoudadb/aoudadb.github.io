#!/usr/bin/env python3
"""The docs' own lane (aouda Operability S03): every check this repository has, each run whatever an earlier one said; the exit is the worst.
scripts/ci.sh calls it; the pull-request workflow (prepared in aouda's tools/ci/workflows/docs/ci.yml) calls ci.sh.

    scripts/ci.sh [--base REF] [--aouda DIR] [--site DIR] [--no-build]

- the Jekyll build into a scratch directory (`bundle exec jekyll build`), then check-anchors.py over what it wrote;
- check-removed-concepts.py, check-code-fences.py (and with --base its half that reads what a page lost since REF),
  check-declaration-examples.py;
- check-next-train.py when an aouda checkout is there (--aouda, or the sibling it finds): it reads aouda's changelog, and aouda is
  private, so a pull request here cannot - aouda's nightly runs it against this repository instead (`tools/ci/lane.sh docs-seam`);
- no page has a BOM (Jekyll does not see the front matter after one, and publishes the page as a raw file);
- the scripts' unit tests.

Standard library only."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGES = (".md", ".html", ".markdown", ".txt", ".yml", ".yaml", ".json")
SKIP_DIRS = {".git", "_site", ".jekyll-cache", "vendor", "node_modules", ".bundle", ".claude", "__pycache__"}


def bom_pages(root=ROOT):
    """Every page or data file that starts with a UTF-8 BOM."""
    out = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(PAGES):
                path = os.path.join(dirpath, name)
                with open(path, "rb") as f:
                    if f.read(3) == b"\xef\xbb\xbf":
                        out.append(os.path.relpath(path, root))
    return sorted(out)


def find_aouda(root=ROOT, given=None):
    """An aouda checkout: the one given, else the sibling check-next-train.py would find; None when there is none."""
    if given:
        return os.path.abspath(given) if os.path.exists(os.path.join(given, "docs", "CHANGELOG.md")) else None
    here = os.path.abspath(root)
    while True:   # as check-next-train.py looks: an `aouda` checkout beside this one or beside any directory above it
        c = os.path.join(here, "aouda")
        if os.path.exists(os.path.join(c, ".git")) and os.path.exists(os.path.join(c, "docs", "CHANGELOG.md")):
            return c
        if os.path.dirname(here) == here:
            return None
        here = os.path.dirname(here)


def checks(base=None, aouda=None, site=None, build=True, py=None):
    """[(name, argv or a callable returning problems, or None with the line that says why it is not run)]."""
    py = py or sys.executable or "python3"
    out = []
    if build:
        out.append(("jekyll-build", ["bundle", "exec", "jekyll", "build", "--quiet", "-d", site]))
        out.append(("check-anchors", [py, os.path.join(HERE, "check-anchors.py"), site]))
    else:
        out.append(("jekyll-build", None, "not run (--no-build); check-anchors needs it"))
    out.append(("check-removed-concepts", [py, os.path.join(HERE, "check-removed-concepts.py"), "--root", ROOT]))
    out.append(("check-code-fences", [py, os.path.join(HERE, "check-code-fences.py"), "--root", ROOT] + (["--base", base] if base else [])))
    out.append(("check-declaration-examples", [py, os.path.join(HERE, "check-declaration-examples.py"), "--root", ROOT]))
    if aouda:
        out.append(("check-next-train", [py, os.path.join(HERE, "check-next-train.py"), "--root", ROOT, "--aouda", aouda]))
    else:
        out.append(("check-next-train", None, "not run: no aouda checkout here (it reads aouda's private changelog); "
                                              "aouda's nightly runs it: tools/ci/lane.sh docs-seam"))
    out.append(("no-bom", lambda: [f"{p}: starts with a BOM (Jekyll publishes it as a raw file)" for p in bom_pages()]))
    out.append(("unit-tests", [py, "-m", "unittest", "discover", "-s", HERE, "-p", "test_*.py"]))
    return out


def run_all(items, run=None, log=print):
    """Every check runs; returns [(name, status)] with status ok | RED | not run."""
    run = run or subprocess.run
    results = []
    for item in items:
        name, what = item[0], item[1]
        started = time.monotonic()
        if what is None:
            log(f"ci: NOT RUN {name} - {item[2]}")
            results.append((name, "not run"))
            continue
        if callable(what):
            problems = what()
            for p in problems:
                log(f"    {p}")
            ok = not problems
        else:
            try:
                ok = run(what, cwd=ROOT).returncode == 0
            except (OSError, subprocess.SubprocessError) as e:
                log(f"    {name}: {e}")
                ok = False
        results.append((name, "ok" if ok else "RED"))
        log(f"ci: {'ok ' if ok else 'RED'} {name} ({time.monotonic() - started:.0f} s)")
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="the pull request's base: check-code-fences.py's --base half")
    ap.add_argument("--aouda", help="an aouda checkout, for check-next-train.py (default: a sibling, if there is one)")
    ap.add_argument("--site", help="where Jekyll writes (default: a scratch directory, removed after)")
    ap.add_argument("--no-build", action="store_true", help="no Jekyll build (and so no check-anchors)")
    args = ap.parse_args(argv)
    scratch = None
    site = args.site
    if not site:
        scratch = tempfile.mkdtemp(prefix="docs-site-")
        site = scratch
    try:
        results = run_all(checks(args.base, find_aouda(ROOT, args.aouda), site, not args.no_build))
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    red = [n for n, s in results if s == "RED"]
    print(f"ci: {'RED ' + ', '.join(red) if red else 'green'} - {len(results)} checks, {len(red)} red, "
          f"{sum(1 for _, s in results if s == 'not run')} not run")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
