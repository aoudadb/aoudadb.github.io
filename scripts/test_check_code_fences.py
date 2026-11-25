"""Tests for check-code-fences.py: what a sweep leaves behind is found, real code is not.

    python3 -m unittest discover -s scripts -p "test_*.py"
"""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location("check_code_fences", os.path.join(_HERE, "check-code-fences.py"))
ccf = importlib.util.module_from_spec(_SPEC)
sys.modules["check_code_fences"] = ccf
_SPEC.loader.exec_module(ccf)

# What 42bfd3b did: the commit the check exists for, and its parent (the pages before it).
_SWEEP = "42bfd3b"


def page(code: str, language: str = "typescript") -> str:
    return f"# Page\n\n```{language}\n{code}\n```\n"


def rules(text: str) -> list[str]:
    return [f.rule for f in ccf.check_text("a.md", text)]


def swept(text: str) -> str:
    """The text as 42bfd3b's rewrite left it."""
    import re
    while True:
        shorter = re.sub(r"\(\)|\[\]", "", text)
        if shorter == text:
            break
        text = shorter
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"[ \t]+([.,;:])", r"\1", text)


_TS = '''import { applyNotice } from '@aouda/client';

const client = new AoudaClient({
  serverUrl: 'http://localhost:5000',
  database: 'mydb',
});
await client.connect();
const store = new MemoryConsistencyTokenStore();
let rows: Trade[] = [];
function bind(): void {
  rows = [];
}
const users = await client.table('users')
  .where('active', '=', true)
  .limit(10)
  .execute();
// Fragments at the margin, as the operator list has them:
.where('name', 'like', 'A%')
.where('email', 'isNull')
stream.on('end', () => { rows = []; });
'''

_CS = '''await client.WaitUntilReadyAsync();   // up to 60 s
var rows = await client.GetTable("orders")
    .Where("status", "eq", "open")
    .ToListAsync();
var outcome = await handle.Outcome;   // a task, not a method
await allAttached.Task;
long[] rowKeys = /* chunk IDs */;
var vectors = new float[] { /* 1 */, /* 2 */ };
static byte[] Bits(int rows, Func<int, bool> isSet)
{
    var bits = new byte[(rows + 7) / 8];
    for (int i = 0; i < rows; i++)
        if (isSet(i)) bits[i >> 3] |= (byte)(1 << (i & 7));
    return bits;
}
services.AddSingleton(new Options());
Func<Task> run = async () => await Task.Yield();
'''

_JSON = '''{
  "signup": { "enabled": true, "statements": [] },
  "notInSet": [],
  "data": [[100, 101], [[1.5, 2.5], null]],
 "row": { "rates": [0.0125, 0] }
}'''


class StaticRules(unittest.TestCase):
    def test_real_code_passes(self):
        for code, language in ((_TS, "typescript"), (_CS, "csharp"), (_JSON, "json")):
            self.assertEqual(ccf.check_text("a.md", page(code, language)), [])

    def test_swept_code_fails_by_every_rule(self):
        self.assertEqual(set(rules(page(swept(_TS)))), {"indent", "value", "call"})
        self.assertEqual(set(rules(page(swept(_CS), "csharp"))), {"indent", "call"})
        self.assertEqual(set(rules(page(swept(_JSON), "json"))), {"indent", "value"})

    def test_each_damage_alone(self):
        for code, rule in (
            ("await client.connect;", "call"),
            ("const s = new MemoryConsistencyTokenStore;", "call"),
            ("const d = new Date.toISOString,", "call"),
            ("stream.on('end', => { go(1); });", "call"),
            ("function bind: void {", "call"),
            ("let rows: Trade = ;", "value"),
            ("f(a, , b);", "value"),
            ("const c = new Client({\n serverUrl: 'x',\n});", "indent"),
            ("const u = client.table('users')\n.where('a', '=', 1);", "indent"),
        ):
            with self.subTest(code):
                self.assertEqual(rules(page(code)), [rule])
        self.assertEqual(rules(page('{ "roles":, "n": 1 }', "json")), ["value"])
        self.assertEqual(rules(page('{\n "roles": 1\n}', "json")), ["indent"])

    def test_strings_comments_prose_and_other_languages_are_not_code(self):
        self.assertEqual(rules(page("log('let a = ; await x.y;'); // new Foo; = ;")), [])
        self.assertEqual(rules("Call `await client.connect;` and `let a = ;`.\n"), [])
        self.assertEqual(rules(page("serve {\n listen 80;\n}", "nginx")), [])
        self.assertEqual(rules(page("/**\n * A JSDoc body is indented by one space.\n */")), [])

    def test_a_fence_in_a_list_and_a_fence_of_four_are_read(self):
        self.assertEqual(rules("- Item:\n\n  ```ts\n  await client.connect;\n  ```\n"), ["call"])
        self.assertEqual(rules("````md\n```ts\nawait client.connect;\n```\n````\n"), [])


class AgainstBase(unittest.TestCase):
    def both(self, base: str, text: str) -> tuple[list[str], list[str]]:
        stripped, swallowed = ccf.compare_text("a.md", base, text)
        return [f.text for f in stripped], [f.text for f in swallowed]

    def test_a_stripped_line_in_prose_and_in_a_fence(self):
        base = "Call `connect()` first.\n" + page(_TS)
        text = swept(base)
        stripped, swallowed = self.both(base, text)
        self.assertIn("Call `connect` first.", stripped)
        self.assertIn("await client.connect;", stripped)
        self.assertIn(" serverUrl: 'http://localhost:5000',", stripped)
        self.assertEqual(swallowed, [])

    def test_put_back_dedented_and_reflowed_lines_pass(self):
        base = "Call `connect()` first.\n" + page(_TS)
        self.assertEqual(self.both(swept(base), base), ([], []))
        self.assertEqual(self.both("```json\n{\n    \"a\": {\n```\n", "```json\n{\n  \"a\": {\n```\n"), ([], []))
        self.assertEqual(self.both("- one\n   two of the list's item\n", "- one\n  two of the list's item\n"), ([], []))

    def test_a_marker_taken_out_passes(self):
        base = ("| Backup while the server takes writes (no quiesce) | Available (**BL-337, next train**) |\n"
                "| Exact restore, against the server or offline into an empty directory | Available |\n"
                "| Restore onto a new host from the destination alone | Available (**BL-334, next train**) |\n"
                "A restore syncs what it wrote before it reports success\n(**BL-1687, next train**).\n")
        text = ("| Backup while the server takes writes (no quiesce) | Available |\n"
                "| Exact restore, against the server or offline into an empty directory | Available |\n"
                "| Restore onto a new host from the destination alone | Available |\n"
                "A restore syncs what it wrote before it reports success.\n")
        self.assertEqual(self.both(base, text), ([], []))

    def test_a_swallowed_passage_is_found(self):
        base = ("The level is set in `aouda.json` (**BL-1463, 0.16.0**; it was a setting, which is refused now).\n\n"
                "The default is `Replicate`. That single key is the entire profile, and there is no separate mode flag to discover.\n\n"
                "| | `Replicate` |\n|---|---|\n"
                "| Frames | Written for every `strict` load too; **no setting elides them** (**BL-1118, next train**). An `os` load writes none |\n")
        text = "The level is set in `aouda.json`. An `os` load writes none |\n"
        stripped, swallowed = self.both(base, text)
        self.assertEqual(stripped, [])
        self.assertEqual(len(swallowed), 1)
        self.assertRegex(swallowed[0], r"^\d{3} characters of a\.md are gone inside this line: The level is set")


class CommandLine(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = self._dir.name

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", self.root, "-c", "user.name=t", "-c", "user.email=t@example.com", *args], check=True, capture_output=True)

    def write(self, name: str, text: str) -> None:
        with open(os.path.join(self.root, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def run_main(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ccf.main(["--root", self.root, *args])
        return code, out.getvalue() + err.getvalue()

    def test_status_and_output(self):
        self.write("ok.md", page(_TS))
        self.assertEqual(self.run_main(), (0, ""))
        self.write("bad.md", page("await client.connect;"))
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("bad.md:4: call: await client.connect;", out)
        self.assertIn("1 damaged line(s)", out)

    def test_base_and_max_lines(self):
        self.write("a.md", "Call `a()`.\nCall `b()`.\nCall `c()`.\n")
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.write("a.md", "Call `a`.\nCall `b`.\nCall `c()`.\n")
        self.assertEqual(self.run_main("--base", "HEAD")[0], 0)
        self.assertEqual(self.run_main("--base", "HEAD", "--max-lines", "1")[0], 1)
        self.write("a.md", "Call `a`.\nCall `b`.\nCall `c`.\n")
        code, out = self.run_main("--base", "HEAD")
        self.assertEqual(code, 1)
        self.assertIn("a.md:3: stripped: Call `c`.", out)
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(self.run_main("--base", "no-such-ref")[0], 2)


class TheSweep(unittest.TestCase):
    """42bfd3b itself, from this repo's history (skipped in a clone that does not hold it)."""

    def setUp(self):
        if subprocess.run(["git", "-C", _HERE, "cat-file", "-e", f"{_SWEEP}^:README.md"], capture_output=True).returncode != 0:
            self.skipTest(f"this clone does not hold {_SWEEP} and its parent")

    def tree(self, ref: str) -> dict[str, str]:
        names = subprocess.run(["git", "-C", os.path.dirname(_HERE), "ls-tree", "-r", "--name-only", ref],
                               capture_output=True, check=True, text=True).stdout.split("\n")
        return {n: ccf._git_show(os.path.dirname(_HERE), ref, n) for n in names
                if n.endswith(ccf.SCAN_SUFFIXES) and n.split("/")[0] not in ccf.SKIP_DIRS}

    def test_the_sweep_fails_and_its_parent_passes(self):
        before, after = self.tree(f"{_SWEEP}^"), self.tree(_SWEEP)
        self.assertEqual([str(f) for n, t in before.items() for f in ccf.check_text(n, t)], [])
        found = [f for n, t in after.items() for f in ccf.check_text(n, t)]
        self.assertGreater(len(found), 1400)
        self.assertGreater(len({f.path for f in found}), 50)
        self.assertEqual({f.rule for f in found}, {"indent", "value", "call"})

        compared = [ccf.compare_text(n, t, after[n]) for n, t in before.items() if n in after and after[n] != t]
        self.assertGreater(sum(len(stripped) for stripped, _ in compared), 5000)
        swallowed = {f.path for _, s in compared for f in s}
        self.assertLessEqual({"clients/dotnet.md", "guides/hot-cold.md", "guides/plan.md", "guides/single-node-deployment.md"}, swallowed)


if __name__ == "__main__":
    unittest.main()
