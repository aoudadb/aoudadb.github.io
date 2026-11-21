"""Tests for check-next-train.py: python3 -m unittest discover -s scripts -p "test_*.py" (builds throwaway trees only)."""

import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("check_next_train", os.path.join(_HERE, "check-next-train.py"))
cnt = importlib.util.module_from_spec(_spec)
sys.modules["check_next_train"] = cnt
_spec.loader.exec_module(cnt)

AOUDA = """﻿# Aouda Changelog

## Unreleased

- **Still coming (BL-300).**

## Releases

### 0.13.0 — 2026-11-12

#### Changed

- **Renamed (BL-100, breaking).**
  - Declared entitlements (BL-200, **not yet shipped**) will write more.
- **Another (BL-101 review).**

### 0.12.0 — 2026-11-12

- **Older (BL-100 rework, BL-102).**

## Historical notes

- BL-400 was mentioned here.
"""

CLIENT = "# @aouda/client\n\n## 0.13.0\n\n### Minor Changes\n\n- BL-103 wrappers\n\n## 0.12.0\n\n- BL-104\n"


class FindMarkersTests(unittest.TestCase):
    def ids(self, text):
        return [ids for _, ids in cnt.find_markers(text)]

    def test_every_spelling_in_use(self):
        self.assertEqual(self.ids("a (**BL-1, next train**) b"), [["BL-1"]])
        self.assertEqual(self.ids("a (**BL-1, BL-2, next train**) b"), [["BL-1", "BL-2"]])
        self.assertEqual(self.ids("a (**BL-1 review, next train**) b"), [["BL-1"]])
        self.assertEqual(self.ids("(aouda BL-1, next train, breaking)"), [["BL-1"]])
        self.assertEqual(self.ids("// BL-1, next train: one option"), [["BL-1"]])
        self.assertEqual(self.ids("since **BL-1, Next-Train**)"), [["BL-1"]])
        self.assertEqual(self.ids("(**BL-1**, next train)"), [["BL-1"]])

    def test_a_marker_without_an_id_is_skipped(self):
        self.assertEqual(self.ids("Lead S12 (next train)"), [])
        self.assertEqual(self.ids("(**Next train:** the default was 2 GiB)"), [])

    def test_only_the_list_before_the_words_counts(self):
        self.assertEqual(self.ids("BL-9 was fixed, and later (**BL-1, next train**)"), [["BL-1"]])

    def test_two_markers_on_one_line(self):
        self.assertEqual(self.ids("(**BL-1, next train**) and (**BL-2, next train**)"), [["BL-1"], ["BL-2"]])


class ParseReleasedTests(unittest.TestCase):
    def test_earliest_release_wins_and_unreleased_and_historical_are_not_released(self):
        released = cnt.parse_released(AOUDA, "aouda")
        self.assertEqual(released["BL-100"].version, "0.12.0")
        self.assertEqual(released["BL-101"].version, "0.13.0")
        self.assertEqual(released["BL-102"].version, "0.12.0")
        self.assertNotIn("BL-300", released)  # under Unreleased
        self.assertNotIn("BL-400", released)  # after "## Historical notes"

    def test_a_line_that_says_not_yet_shipped_does_not_count(self):
        self.assertNotIn("BL-200", cnt.parse_released(AOUDA, "aouda"))

    def test_a_range_citation_is_not_a_release(self):
        """BL-1498: 0.4.0's `Cards: BL-1001 … BL-1004.` (verbatim) made BL-1001 "released in 0.4.0"; it is the realtime API-key re-check."""
        changelog = (
            "## Releases\n\n### 0.14.0 — 2026-11-15\n\n- **Re-check on a key (BL-1001, security).**\n\n"
            "### 0.4.0 — 2026-09-01\n\n  `SignOutAsync(Others | Global)` throws when nothing was ended. Cards: BL-1001 … BL-1004.\n"
        )
        released = cnt.parse_released(changelog, "aouda")
        self.assertEqual(released["BL-1001"].version, "0.14.0")   # the single mention, not the range's end
        self.assertNotIn("BL-1004", released)
        only_a_range = cnt.parse_released("## Releases\n\n### 0.4.0 — d\n\n- Cards: BL-1001 … BL-1004.\n", "aouda")
        self.assertEqual(only_a_range, {})

    def test_every_range_spelling_is_skipped_and_a_list_is_not(self):
        for text in ("BL-5 … BL-9", "BL-5 – BL-9", "BL-5 — BL-9", "BL-5..BL-9", "BL-5...BL-9", "BL-5 to BL-9", "**BL-5** … **BL-9**", "BL-5-BL-9"):
            self.assertEqual(cnt.parse_released(f"## Releases\n\n### 0.1.0 — d\n\n- {text}\n", "aouda"), {}, text)
        listed = cnt.parse_released("## Releases\n\n### 0.1.0 — d\n\n- BL-5, BL-9 and BL-7 (BL-5 … BL-6)\n", "aouda")
        self.assertEqual(sorted(listed), ["BL-5", "BL-7", "BL-9"])

    def test_client_changelog_sections(self):
        released = cnt.parse_released(CLIENT, "@aouda/client")
        self.assertEqual((released["BL-103"].version, released["BL-104"].version), ("0.13.0", "0.12.0"))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.released = {**cnt.parse_released(CLIENT, "@aouda/client"), **cnt.parse_released(AOUDA, "aouda")}

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, body):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    def test_stale_marker_is_reported_with_file_line_id_release_and_fix(self):
        self.write("guides/a.md", "intro\nA thing (**BL-100, next train**) here.\n")
        findings = cnt.check(self.root, self.released)
        self.assertEqual(len(findings), 1)
        text = str(findings[0])
        self.assertTrue(text.startswith("guides/a.md:2: BL-100 shipped in aouda 0.12.0"), text)
        self.assertIn("(**BL-100, 0.12.0**)", text)

    def test_unreleased_and_unknown_ids_pass(self):
        self.write("a.md", "(**BL-300, next train**) (**BL-200, next train**) (**BL-999, next train**)\n")
        self.assertEqual(cnt.check(self.root, self.released), [])

    def test_an_allow_listed_phase_card_stays_next_train(self):
        """0.14.0 names BL-1463 for a Declare slice. A marker for the rest of that card is not stale."""
        # The set changes with each train (a card whose released mention is an older note); the mechanism is what is pinned here.
        with mock.patch.object(cnt, "_ALLOW", {"BL-1463", "BL-1464"}):
            self.write("a.md", "(**BL-1463, next train**) and (**BL-100, next train**)\n")
            findings = cnt.check(self.root, self.released)
        self.assertEqual([f.bl for f in findings], ["BL-100"])

    def test_client_only_id_names_the_client(self):
        self.write("clients/ts.md", "(**BL-103, next train**)\n")
        self.assertEqual([(f.repo, f.version) for f in cnt.check(self.root, self.released)], [("@aouda/client", "0.13.0")])

    def test_skipped_directories_and_non_markdown_are_not_scanned(self):
        self.write("_review/x.md", "(**BL-100, next train**)\n")
        self.write(".claude/worktrees/w/x.md", "(**BL-100, next train**)\n")
        self.write("scripts/x.py", "(**BL-100, next train**)\n")
        self.assertEqual(cnt.check(self.root, self.released), [])

    def test_a_bom_in_a_page_is_tolerated(self):
        self.write("a.md", "﻿(**BL-100, next train**)\n")
        self.assertEqual(len(cnt.check(self.root, self.released)), 1)


if __name__ == "__main__":
    unittest.main()
