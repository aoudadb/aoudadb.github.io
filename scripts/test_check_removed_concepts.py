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


if __name__ == "__main__":
    unittest.main()
