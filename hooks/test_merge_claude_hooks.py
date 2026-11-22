#!/usr/bin/env python3
"""Unit tests for hooks/merge_claude_hooks.py."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parent / "merge_claude_hooks.py"


class MergeClaudeHooksTests(unittest.TestCase):
    def _run_merge(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT_PATH), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_wrong_arg_count_exits_one(self) -> None:
        for args in ((), ("only-one",), ("a", "b", "c")):
            with self.subTest(args=args):
                proc = self._run_merge(*args)
                self.assertEqual(proc.returncode, 1)
                self.assertIn("usage:", proc.stderr)

    def test_creates_settings_from_scratch_with_0644_mode(self) -> None:
        gate_cmd = "/nix/store/aaa-agentic-commit-skill-gate-claude"
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "nested" / ".claude" / "settings.json"
            proc = self._run_merge(str(target), gate_cmd)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(target.is_file())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(
                data,
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": gate_cmd,
                                        "timeout": 10,
                                    }
                                ],
                            }
                        ]
                    }
                },
            )

    def test_preserves_unrelated_keys_is_idempotent_and_replaces_old_gate(self) -> None:
        old_gate = "/nix/store/old111-agentic-commit-skill-gate-claude"
        new_gate = "/nix/store/new222-agentic-commit-skill-gate-claude"
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "settings.json"
            target.write_text(
                json.dumps(
                    {
                        "permissions": {"deny": ["Bash(git push*)"]},
                        "hooks": {
                            "PostToolUse": [{"matcher": "Edit", "hooks": []}],
                            "PreToolUse": [
                                {
                                    "matcher": "Write",
                                    "hooks": [{"type": "command", "command": "/bin/true"}],
                                },
                                {
                                    "matcher": "Bash",
                                    "hooks": [
                                        {"type": "command", "command": old_gate, "timeout": 10},
                                        {"type": "command", "command": "/usr/local/bin/other"},
                                    ],
                                },
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            first = self._run_merge(str(target), new_gate)
            self.assertEqual(first.returncode, 0, first.stderr)
            after_first = target.read_text(encoding="utf-8")
            parsed = json.loads(after_first)
            self.assertEqual(parsed["permissions"], {"deny": ["Bash(git push*)"]})
            self.assertEqual(parsed["hooks"]["PostToolUse"], [{"matcher": "Edit", "hooks": []}])
            self.assertEqual(
                parsed["hooks"]["PreToolUse"],
                [
                    {"matcher": "Write", "hooks": [{"type": "command", "command": "/bin/true"}]},
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/local/bin/other"}]},
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": new_gate, "timeout": 10}],
                    },
                ],
            )

            second = self._run_merge(str(target), new_gate)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), after_first)

    def test_skips_safely_on_invalid_targets_and_shapes(self) -> None:
        gate_cmd = "/nix/store/aaa-agentic-commit-skill-gate-claude"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            real_file = root / "real.json"
            real_file.write_text('{"keep": true}\n', encoding="utf-8")
            symlink_target = root / "symlink.json"
            symlink_target.symlink_to(real_file)
            proc = self._run_merge(str(symlink_target), gate_cmd)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("warning:", proc.stderr)
            self.assertEqual(real_file.read_text(encoding="utf-8"), '{"keep": true}\n')

            dir_target = root / "dir.json"
            dir_target.mkdir()
            proc = self._run_merge(str(dir_target), gate_cmd)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("warning:", proc.stderr)
            self.assertTrue(dir_target.is_dir())

            bad_cases = [
                ("invalid.json", "{not valid json"),
                ("array.json", "[]"),
                ("bad_hooks.json", '{"hooks": []}'),
                ("bad_pre.json", '{"hooks": {"PreToolUse": {}}}'),
            ]
            for filename, content in bad_cases:
                with self.subTest(filename=filename):
                    p = root / filename
                    p.write_text(content, encoding="utf-8")
                    proc = self._run_merge(str(p), gate_cmd)
                    self.assertEqual(proc.returncode, 0)
                    self.assertIn("warning:", proc.stderr)
                    self.assertEqual(p.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
