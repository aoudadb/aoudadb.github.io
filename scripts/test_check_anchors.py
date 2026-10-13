"""Tests for check-anchors.py: python3 -m unittest discover -s scripts -p "test_*.py" (builds throwaway trees only)."""

import importlib.util
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("check_anchors", os.path.join(_HERE, "check-anchors.py"))
check_anchors = importlib.util.module_from_spec(_spec)
sys.modules["check_anchors"] = check_anchors
_spec.loader.exec_module(check_anchors)


def _write(root: str, rel: str, body: str) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<html><body>{body}</body></html>")


class CheckAnchorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.site = self._tmp.name
        _write(self.site, "index.html", '<a href="/guides/sizing/">sizing</a>')
        _write(self.site, "guides/sizing/index.html",
               '<h2 id="what-happens">What happens</h2><a name="legacy"></a>'
               '<a href="#what-happens">here</a><a href="#top">top</a>')
        os.makedirs(os.path.join(self.site, "assets", "img"), exist_ok=True)
        open(os.path.join(self.site, "assets", "img", "logo.svg"), "w").close()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def links(self, *hrefs: str) -> list:
        _write(self.site, "guides/defaults-reference/index.html", "".join(f'<a href="{h}">x</a>' for h in hrefs))
        return [f for f in check_anchors.check(self.site) if f.page == "/guides/defaults-reference/"]

    def test_a_link_to_an_existing_anchor_or_page_is_fine(self):
        self.assertEqual([], self.links(
            "/guides/sizing/#what-happens", "../sizing/#what-happens", "/guides/sizing/#legacy",
            "/guides/sizing/", "/guides/sizing", "/guides/sizing/index.html#what-happens", "/assets/img/logo.svg"))

    def test_a_missing_anchor_is_reported_with_the_page_it_was_looked_for_on(self):
        (finding,) = self.links("/guides/sizing/#what-happens-next")
        self.assertEqual("no #what-happens-next on /guides/sizing/", finding.problem)

    def test_a_percent_encoded_or_entity_encoded_fragment_is_decoded(self):
        _write(self.site, "guides/sizing/index.html", '<h2 id="über-uns">x</h2><h2 id="a&amp;b">y</h2>')
        self.assertEqual([], self.links("/guides/sizing/#%C3%BCber-uns", "/guides/sizing/#a&amp;b"))

    def test_a_dot_md_link_left_by_the_relative_links_plugin_is_reported(self):
        (finding,) = self.links("Getting-Started.md")
        self.assertEqual("a .md link to a page that does not exist", finding.problem)

    def test_a_link_to_no_page_is_reported(self):
        (finding,) = self.links("/guides/nothing-here/")
        self.assertEqual("no such page", finding.problem)

    def test_same_page_fragments_are_checked(self):
        _write(self.site, "guides/sizing/index.html", '<h2 id="a">a</h2><a href="#a">ok</a><a href="#b">bad</a>')
        findings = [f for f in check_anchors.check(self.site) if f.page == "/guides/sizing/"]
        self.assertEqual(["#b"], [f.href for f in findings])

    def test_external_links_are_not_checked(self):
        self.assertEqual([], self.links("https://example.com/#nope", "mailto:a@b.c", "//cdn.example.com/x.js"))

    def test_a_baseurl_is_stripped_and_a_link_outside_it_reported(self):
        _write(self.site, "guides/defaults-reference/index.html",
               '<a href="/docs/guides/sizing/#what-happens">ok</a><a href="/other/x/">out</a>')
        findings = [f for f in check_anchors.check(self.site, baseurl="/docs/") if f.page == "/guides/defaults-reference/"]
        self.assertEqual([("/other/x/", "outside the site's baseurl")], [(f.href, f.problem) for f in findings])

    def test_main_exits_one_on_a_finding_and_zero_on_none(self):
        self.links("/guides/sizing/#nope")
        self.assertEqual(1, check_anchors.main([self.site]))
        self.links("/guides/sizing/#what-happens")
        self.assertEqual(0, check_anchors.main([self.site]))
        self.assertEqual(2, check_anchors.main([os.path.join(self.site, "missing")]))


if __name__ == "__main__":
    unittest.main()
