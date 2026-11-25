"""Tests for check-removed-concepts.py. Throwaway git repos only."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "check_removed_concepts", os.path.join(_HERE, "check-removed-concepts.py")
)
crc = importlib.util.module_from_spec(_spec)
sys.modules["check_removed_concepts"] = crc
_spec.loader.exec_module(crc)

_KIT_CANDIDATES = [
    os.environ.get("AOUDA_KEY_TEST_KIT", ""),
    r"D:\GitHub\aouda\.claude\worktrees\principals-overview-s18\tests\Aouda.Engine.Auth.Tests\Credentials\Keys\KeyTestKit.cs",
    r"C:\Data\GitHub\aouda\tests\Aouda.Engine.Auth.Tests\Credentials\Keys\KeyTestKit.cs",
]


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _repo(files: dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="s18-removed-")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "s18@example.com")
    _git(root, "config", "user.name", "s18")
    for rel, text in files.items():
        path = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


class RemovedConceptsTests(unittest.TestCase):
    def test_each_listed_word_is_reported(self) -> None:
        lines = [name for _pattern, name, _replacement in crc.REMOVED + crc.VOCABULARY]
        page = "\n".join(lines) + "\n"
        root = _repo({"guides/real-time.md": page})
        code = crc.main(["--root", root])
        self.assertEqual(code, 1)
        # Re-scan to read the lines (main prints them).
        findings = []
        for rel in crc.tracked_files(root):
            with open(os.path.join(root, rel), encoding="utf-8") as handle:
                findings.extend(crc.scan_text(rel, handle.read(), vocabulary=True))
        joined = "\n".join(findings)
        for name in lines:
            self.assertIn(name, joined, name)

    def test_exemptions_are_silent(self) -> None:
        body = "mk_ X-User-Token authMode service key\n"
        root = _repo(
            {
                "auth/migrating-from-0-14.md": body,
                "CHANGELOG.md": body,
                "_review/note.md": body,
                "guides/ok.md": "A principal holds a statement.\n",
            }
        )
        self.assertEqual(crc.main(["--root", root]), 0)

    def test_word_anchors(self) -> None:
        page = "numk_ stays. aouda_exampleexampleex_mk_notakey stays.\n`mk_` goes.\nmk_svc_abc goes.\n"
        root = _repo({"guides/real-time.md": page})
        findings = []
        for rel in crc.tracked_files(root):
            with open(os.path.join(root, rel), encoding="utf-8") as handle:
                findings.extend(crc.scan_text(rel, handle.read(), vocabulary=False))
        text = "\n".join(findings)
        self.assertNotIn("numk_", text)
        self.assertIn("mk_", text)
        self.assertEqual(text.count("guides/real-time.md:"), 2)

    def test_valid_checksum_is_a_hit_and_a_placeholder_is_not(self) -> None:
        body = "aouda_" + "abcdefghijklmnop" + "_" + ("0" * 43)
        token = body + crc.checksum_of(body)
        self.assertTrue(crc.key_checksum_ok(token))
        placeholder = "aouda_exampleexampleex_PLACEHOLDERPLACEHOLDERPLACEHOLDERPLACEHOLDERPLACE"
        self.assertFalse(crc.key_checksum_ok(placeholder))
        root = _repo({"guides/backup.md": token + "\n" + placeholder + "\n"})
        findings = []
        for rel in crc.tracked_files(root):
            with open(os.path.join(root, rel), encoding="utf-8") as handle:
                findings.extend(crc.scan_text(rel, handle.read(), vocabulary=False))
        self.assertEqual(len(findings), 1)
        self.assertIn("placeholder", findings[0])

    def test_known_answer_vectors_from_s07(self) -> None:
        kit = next((p for p in _KIT_CANDIDATES if p and os.path.isfile(p)), None)
        if kit is None:
            self.skipTest("KeyTestKit.cs is not on this machine")
        with open(kit, encoding="utf-8") as handle:
            text = handle.read()
        keys = crc._KEY.findall(text)
        self.assertGreaterEqual(len(keys), 3)
        for key in keys:
            self.assertTrue(crc.key_checksum_ok(key), key)

    def test_service_key_vocabulary(self) -> None:
        root = _repo({"guides/real-time.md": "Use a service key.\n"})
        self.assertEqual(crc.main(["--root", root]), 1)
        self.assertEqual(crc.main(["--root", root, "--no-vocabulary"]), 0)

    def test_paths_limit(self) -> None:
        root = _repo(
            {
                "guides/real-time.md": "mk_\n",
                "guides/backup.md": "mk_\n",
            }
        )
        self.assertEqual(crc.main(["--root", root, "--paths", "guides/backup.md", "--no-vocabulary"]), 1)
        # The limited run still fails because backup.md has the name. A clean limit passes.
        self.assertEqual(crc.main(["--root", root, "--paths", "auth/*.md", "--no-vocabulary"]), 0)

    # ── The fourth rule: stand-ins (BL-1867) ──

    def test_each_stand_in_is_refused_once_is_enough(self) -> None:
        for fragment in crc.STAND_INS:
            page = f"Before.\n{fragment} and more.\nAfter.\n"
            findings = crc.scan_stand_ins("guides/a.md", page)
            self.assertEqual([f.split(" ")[0] for f in findings], ["guides/a.md:2:"], fragment)
        for start in crc.STAND_IN_LINES:
            self.assertEqual(len(crc.scan_stand_ins("guides/a.md", f"  {start}, 0.16.0**).\n")), 1, start)

    def test_a_stand_in_in_code_is_refused(self) -> None:
        page = "```typescript\nconst c = new AoudaClient({\n// client.whoami() — apiKey is an aouda_ key, or session, never both.\n});\n```\n"
        self.assertEqual(len(crc.scan_stand_ins("clients/typescript.md", page)), 1)
        self.assertEqual(crc.main(["--root", _repo({"clients/typescript.md": page})]), 1)

    def test_an_ordinary_sentence_is_not_a_stand_in(self) -> None:
        page = (
            "A key is minted on the principal. See [Access](../auth/index.md) (**BL-1464, 0.16.0**).\n"
            "A principal may act; its credential is an `aouda_` key or a session.\n"
            "`client.whoami()` says who the credential is.\n"
        )
        self.assertEqual(crc.scan_stand_ins("guides/a.md", page), [])

    def test_a_prose_line_three_times_is_refused_and_twice_is_not(self) -> None:
        line = "Who may do it is decided by the statements of the caller, as everywhere else."
        twice = f"One.\n{line}\nTwo.\n- {line}\n{line}\n"
        self.assertEqual(crc.scan_stand_ins("guides/a.md", twice), [])  # a list item is another line
        thrice = twice + f"\n  {line}\n"
        findings = crc.scan_stand_ins("guides/a.md", thrice)
        self.assertEqual(len(findings), 1)
        self.assertIn("guides/a.md:2: the same line 3 times", findings[0])

    def test_code_tables_and_paths_may_repeat(self) -> None:
        page = (
            "```csharp\nawait using var server = await AoudaTestServer.StartAsync(new AoudaTestServerOptions());\n```\n" * 4
            + "> ```bash\n> docker compose up -d with many words on one line of a quoted fence\n> ```\n" * 4
            + "| Field | Type | Required | Allowed values | What it is and why it matters |\n" * 4
            + "- `src/Aouda.Server/Controllers/TablesController.cs and a long path in code`\n" * 4
        )
        self.assertEqual(crc.scan_stand_ins("guides/a.md", page), [])

    def test_a_pending_page_is_not_read_and_still_exists(self) -> None:
        self.assertEqual(list(crc.STAND_INS_PENDING), ["guides/cloud-hub.md"])
        self.assertEqual(crc.scan_stand_ins("guides/cloud-hub.md", crc.STAND_INS[0]), [])
        repo = os.path.dirname(_HERE)
        for path, reason in crc.STAND_INS_PENDING.items():
            self.assertTrue(reason)
            with open(os.path.join(repo, *path.split("/")), encoding="utf-8") as handle:
                text = handle.read()
            self.assertTrue(any(crc._is_stand_in(l) for l in text.split("\n")), f"{path} is clean: remove its row")

    def test_no_published_page_holds_one(self) -> None:
        repo = os.path.dirname(_HERE)
        findings = []
        for rel in crc.tracked_files(repo):
            if crc.exempt(rel) or not rel.endswith((".md", ".txt")):
                continue
            full = os.path.join(repo, *rel.split("/"))
            if os.path.isfile(full):
                with open(full, encoding="utf-8-sig", newline="") as handle:
                    findings.extend(crc.scan_stand_ins(rel, handle.read()))
        self.assertEqual(findings, [])


class TheRewrite(unittest.TestCase):
    """The commits that did it. Needs the history (a shallow clone has none)."""

    def _count(self, ref: str) -> int:
        repo = os.path.dirname(_HERE)
        listed = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", ref], capture_output=True, text=True)
        if listed.returncode != 0:
            self.skipTest(f"{ref} is not in this clone")
        total = 0
        for rel in listed.stdout.split():
            if rel.endswith((".md", ".txt")) and not crc.exempt(rel):
                text = subprocess.run(["git", "-C", repo, "show", f"{ref}:{rel}"], capture_output=True, text=True, encoding="utf-8").stdout
                total += len(crc.scan_stand_ins(rel, text))
        return total

    def test_the_rewrite_fails_and_what_was_before_passes(self) -> None:
        self.assertEqual(self._count("c8ca688^"), 0)
        self.assertGreater(self._count("f9afb4f"), 600)
        self.assertGreater(self._count("a259eb2"), 400)


if __name__ == "__main__":
    unittest.main()
