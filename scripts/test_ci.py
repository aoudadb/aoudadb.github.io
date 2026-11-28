"""Tests of scripts/ci.py (aouda Operability S03, AC-18): every check runs, the exit is the worst, a page with a BOM is red."""
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci  # noqa: E402


def done(rc):
    return types.SimpleNamespace(returncode=rc)


class RunAllTests(unittest.TestCase):
    def test_a_check_that_fails_in_the_middle_does_not_stop_the_later_ones(self):
        ran = []

        def run(cmd, cwd=None):
            ran.append(cmd[0])
            return done(1 if cmd[0] == "b" else 0)
        results = ci.run_all([("a", ["a"]), ("b", ["b"]), ("c", ["c"]), ("d", lambda: [])], run=run, log=lambda *_: None)
        self.assertEqual(ran, ["a", "b", "c"])
        self.assertEqual(results, [("a", "ok"), ("b", "RED"), ("c", "ok"), ("d", "ok")])

    def test_the_exit_is_the_worst(self):
        with mock.patch.object(ci, "checks", lambda *a, **k: [("a", ["a"]), ("b", ["b"])]), \
                mock.patch.object(ci.subprocess, "run", lambda cmd, cwd=None: done(0 if cmd == ["a"] else 3)):
            self.assertEqual(ci.main(["--no-build"]), 1)
        with mock.patch.object(ci, "checks", lambda *a, **k: [("a", ["a"])]), \
                mock.patch.object(ci.subprocess, "run", lambda cmd, cwd=None: done(0)):
            self.assertEqual(ci.main(["--no-build"]), 0)

    def test_a_check_that_is_not_run_says_so_and_is_not_red(self):
        lines = []
        results = ci.run_all([("x", None, "not run: why")], log=lines.append)
        self.assertEqual(results, [("x", "not run")])
        self.assertIn("NOT RUN x - not run: why", lines[0])

    def test_a_command_that_cannot_start_is_red(self):
        results = ci.run_all([("x", ["/no/such/program"])], log=lambda *_: None)
        self.assertEqual(results, [("x", "RED")])


class ChecksTests(unittest.TestCase):
    def test_each_check_is_in_the_lane(self):
        names = [c[0] for c in ci.checks(base="abc", aouda="/a", site="/s")]
        self.assertEqual(names, ["jekyll-build", "check-anchors", "check-removed-concepts", "check-code-fences",
                                 "check-declaration-examples", "check-next-train", "no-bom", "unit-tests"])
        fences = dict((c[0], c[1]) for c in ci.checks(base="abc", aouda="/a", site="/s"))["check-code-fences"]
        self.assertEqual(fences[-2:], ["--base", "abc"])

    def test_without_an_aouda_checkout_next_train_is_named_as_not_run(self):
        item = dict((c[0], c) for c in ci.checks(base=None, aouda=None, site="/s"))["check-next-train"]
        self.assertIsNone(item[1])
        self.assertIn("docs-seam", item[2])


class BomTests(unittest.TestCase):
    def test_a_page_with_a_bom_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "guides"))
            with open(os.path.join(tmp, "guides", "a.md"), "wb") as f:
                f.write(b"\xef\xbb\xbf---\ntitle: a\n---\n")
            with open(os.path.join(tmp, "b.md"), "wb") as f:
                f.write(b"---\ntitle: b\n---\n")
            os.makedirs(os.path.join(tmp, "_site"))
            with open(os.path.join(tmp, "_site", "c.html"), "wb") as f:
                f.write(b"\xef\xbb\xbfbuilt")
            self.assertEqual(ci.bom_pages(tmp), [os.path.join("guides", "a.md")])

    def test_no_page_of_this_checkout_has_a_bom(self):
        self.assertEqual(ci.bom_pages(), [])


class ScriptTests(unittest.TestCase):
    def test_ci_sh_runs_ci_py(self):
        r = subprocess.run([os.path.join(ci.HERE, "ci.sh"), "--help"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--base", r.stdout)


if __name__ == "__main__":
    unittest.main()
