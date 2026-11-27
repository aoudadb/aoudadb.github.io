"""Tests for check-declaration-examples.py. Throwaway trees; the published schema is copied in."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "check_declaration_examples", os.path.join(_HERE, "check-declaration-examples.py")
)
cde = importlib.util.module_from_spec(_spec)
sys.modules["check_declaration_examples"] = cde
_spec.loader.exec_module(cde)

_SCHEMA = os.path.join(_HERE, "..", "schemas", "aouda-declaration.v1.json")


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _repo(page: str) -> str:
    root = tempfile.mkdtemp(prefix="s18-decl-")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "s18@example.com")
    _git(root, "config", "user.name", "s18")
    os.makedirs(os.path.join(root, "schemas"))
    os.makedirs(os.path.join(root, "auth"))
    shutil.copyfile(_SCHEMA, os.path.join(root, "schemas", "aouda-declaration.v1.json"))
    with open(os.path.join(root, "auth", "example.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(page)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


_VALID = """\
<!-- declaration-example -->
```json
{ "version": 1, "databases": { "auth": { "kind": "auth", "signup": { "enabled": false } } } }
```
"""

_AUTH_MODE = """\
<!-- declaration-example -->
```json
{ "version": 1, "authMode": "auth-db-rls" }
```
"""

_BAD_ACTION = """\
<!-- declaration-example -->
```json
{
  "version": 1,
  "databases": {
    "auth": {
      "kind": "auth",
      "principals": {
        "feeder": {
          "statements": [ { "actions": ["admin"], "resources": ["rates/table/DepositQuote"] } ]
        }
      }
    }
  }
}
```
"""

_BARE_WHERE = _BAD_ACTION.replace('"admin"', '"read"').replace(
    '"resources": ["rates/table/DepositQuote"]',
    '"resources": ["rates/table/DepositQuote"], "where": { "column": "source", "op": "eq", "value": "x" }',
)


class DeclarationExampleTests(unittest.TestCase):
    def test_a_where_that_is_a_bare_condition_is_refused_by_the_schema_and_a_list_of_one_passes(self) -> None:
        # aouda BL-1869: the refusal is the published schema's, not a rule of this script.
        root = _repo(_BARE_WHERE)
        self.assertEqual(cde.main(["--root", root]), 1)
        with open(os.path.join(root, "schemas", "aouda-declaration.v1.json"), encoding="utf-8") as handle:
            validator = cde.Draft202012Validator(json.load(handle))
        findings = cde.check_file("a.md", _BARE_WHERE, validator)
        self.assertEqual(len(findings), 1)
        self.assertIn("/where", findings[0])
        listed = _BARE_WHERE.replace('{ "column": "source", "op": "eq", "value": "x" }', '{ "and": [ { "column": "source", "op": "eq", "value": "x" } ] }')
        self.assertEqual(cde.main(["--root", _repo(listed)]), 0)

    def test_a_where_is_read_to_its_conditions_by_the_schema(self) -> None:
        with open(_SCHEMA, encoding="utf-8") as handle:
            validator = cde.Draft202012Validator(json.load(handle))

        def found(row_condition: str) -> list[str]:
            page = _BARE_WHERE.replace('{ "column": "source", "op": "eq", "value": "x" }', row_condition)
            return cde.check_file("a.md", page, validator)

        one = '{ "column": "source", "op": "eq", "value": "x" }'
        self.assertEqual(found(f'{{ "groups": [ {{ "and": [ {one} ] }}, {{ "or": [ {one}, {one} ] }} ] }}'), [])
        for broken in (
            f'{{ "and": {one} }}',  # not a list
            '{ "and": [] }',
            f'{{ "groups": [ {one} ] }}',  # a group is a row condition, not a condition
            f'{{ "and": [ {{ "or": [ {one} ] }} ] }}',  # a nested one is in groups
            '{}',
            '"source"',
        ):
            self.assertEqual(len(found(broken)), 1, broken)

    def test_valid_block_passes(self) -> None:
        root = _repo(_VALID)
        self.assertEqual(cde.main(["--root", root]), 0)

    def test_unknown_member_fails(self) -> None:
        root = _repo(_AUTH_MODE)
        findings = cde.check_file(
            "auth/example.md",
            _AUTH_MODE,
            cde.Draft202012Validator(json.load(open(os.path.join(root, "schemas", "aouda-declaration.v1.json"), encoding="utf-8"))),
        )
        self.assertTrue(findings, findings)
        self.assertIn("authMode", findings[0])

    def test_action_outside_the_six_fails(self) -> None:
        root = _repo(_BAD_ACTION)
        schema = json.load(open(os.path.join(root, "schemas", "aouda-declaration.v1.json"), encoding="utf-8"))
        findings = cde.check_file("auth/example.md", _BAD_ACTION, cde.Draft202012Validator(schema))
        self.assertTrue(findings, findings)
        self.assertIn("admin", findings[0])
        self.assertIn("/actions/", findings[0])


if __name__ == "__main__":
    unittest.main()
