#!/usr/bin/env python3
"""Check every internal link of the built site: the page it names exists, and so does its #anchor.

Usage:
    bundle exec jekyll build -d /path/to/site
    python3 scripts/check-anchors.py /path/to/site [--baseurl /prefix]

Reads the HTML Jekyll wrote (so it sees the ids kramdown and the theme generate, not a guess at them) and checks each
`href` that stays on the site:

- the page exists (`/guides/sizing/`, `/guides/sizing/index.html`, or a file such as an asset);
- a link still ending in `.md` is reported: `jekyll-relative-links` rewrites a link to a page that exists, so one left
  as `.md` names a file that is not there;
- its fragment (`#what-happens-when-...`) is an `id` (or an `<a name>`) on the target page.

External links (`http:`, `https:`, `mailto:`, ...) are not fetched. Exit status 1 when anything is broken, 0 otherwise.
Written from LoadSpeed K45's one-off checker (LoadSpeed K55).
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlparse

_EXTERNAL = ("http:", "https:", "mailto:", "tel:", "javascript:", "data:", "ftp:")
_ID = re.compile(r"""\s(?:id|name)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_HREF = re.compile(r"""<a\b[^>]*?\shref\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


@dataclass(frozen=True, order=True)
class Finding:
    page: str
    href: str
    problem: str

    def __str__(self) -> str:
        return f"{self.page}: {self.href} - {self.problem}"


def page_url(site: str, path: str) -> str:
    """The URL a built file is served at: `a/b/index.html` -> `/a/b/`, `x.html` -> `/x.html`."""
    rel = os.path.relpath(path, site).replace(os.sep, "/")
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def read_site(site: str) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Every page's ids and its links, keyed by the page's URL."""
    ids: dict[str, set[str]] = {}
    links: dict[str, list[str]] = {}
    for directory, _, files in os.walk(site):
        for name in files:
            if not name.endswith(".html"):
                continue
            path = os.path.join(directory, name)
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
            url = page_url(site, path)
            ids[url] = {html.unescape(i) for i in _ID.findall(text)}
            links[url] = [html.unescape(h) for h in _HREF.findall(text)]
    return ids, links


def _exists_on_disk(site: str, path: str) -> bool:
    local = os.path.join(site, unquote(path).lstrip("/"))
    return os.path.isfile(local) or os.path.isfile(os.path.join(local, "index.html"))


def check(site: str, baseurl: str = "") -> list[Finding]:
    """The broken internal links of the site built into `site`."""
    baseurl = baseurl.rstrip("/")
    ids, links = read_site(site)
    findings: set[Finding] = set()
    for page, hrefs in links.items():
        for href in hrefs:
            if not href or href.startswith(_EXTERNAL) or href.startswith("//"):
                continue
            target = urlparse(urljoin(baseurl + page, href))
            path = target.path or baseurl + page
            if baseurl:
                if not (path == baseurl or path.startswith(baseurl + "/")):
                    findings.add(Finding(page, href, "outside the site's baseurl"))
                    continue
                path = path[len(baseurl):] or "/"

            if path in ids:
                key = path
            elif path + "/" in ids:
                key = path + "/"
            elif path.endswith("/index.html") and path[: -len("index.html")] in ids:
                key = path[: -len("index.html")]
            else:
                key = None

            if key is None:
                if path.endswith(".md"):
                    findings.add(Finding(page, href, "a .md link to a page that does not exist"))
                elif not _exists_on_disk(site, path):
                    findings.add(Finding(page, href, "no such page"))
                continue

            fragment = unquote(target.fragment)
            if fragment and fragment != "top" and fragment not in ids[key]:
                findings.add(Finding(page, href, f"no #{fragment} on {key}"))
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site", help="the directory `jekyll build` wrote (e.g. _site)")
    parser.add_argument("--baseurl", default="", help="the site's baseurl, if it was built with one")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.site):
        print(f"{args.site}: not a directory (build the site first: bundle exec jekyll build)", file=sys.stderr)
        return 2
    findings = check(args.site, args.baseurl)
    for f in findings:
        print(f)
    pages = sum(1 for _ in read_site(args.site)[0])
    print(f"{len(findings)} broken internal link(s) across {pages} page(s).", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
