#!/usr/bin/env python3
"""Unit tests for hooks/commit_skill_gate.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK_PATH = Path(__file__).resolve().parent / "commit_skill_gate.py"
sys.path.insert(0, str(HOOK_PATH.parent))

import commit_skill_gate  # noqa: E402

SKILL_PATH = "/home/u/Workspaces/gdr/agentic/skills/git/git-commit-branch/SKILL.md"


class CommandDetectionTests(unittest.TestCase):
    def test_detects_git_commit_variants(self) -> None:
        positives = [
            'git commit -m "fix(core): handle edge case"',
            'git -C /repo commit -m "x"',
            "git --git-dir=/a --work-tree=/b commit --amend",
            'git -c user.name=a commit -m "x"',
            'cd /r && git add . && git commit -m "x"',
            "nix develop --command bash -euo pipefail -c 'just fmt && git commit -m \"x\"'",
            'nix develop -c git commit -m "x"',
            'bash -lc \'git commit -m "x"\'',
            'env FOO=1 git commit -m "x"',
            'sudo -u dev git commit -m "x"',
            'timeout 30 git commit -m "x"',
            'echo "unclosed && git commit -m x',
        ]
        for cmd in positives:
            with self.subTest(cmd=cmd):
                self.assertTrue(commit_skill_gate.command_runs_git_commit(cmd))

    def test_ignores_non_commit_commands(self) -> None:
        negatives = [
            "git status",
            "git add .",
            "git commit-tree abcdef",
            "git commit-graph write",
            "git commit --help",
            "git commit -h",
            'git log --grep="git commit"',
            'grep "git commit" README.md',
            'echo "read skill before git commit"',
            "python3 -c 'print(\"git commit\")'",
        ]
        for cmd in negatives:
            with self.subTest(cmd=cmd):
                self.assertFalse(commit_skill_gate.command_runs_git_commit(cmd))


class HookExecutionTests(unittest.TestCase):
    def _run_hook(self, payload: dict[str, object], *extra_args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        return subprocess.run(
            [sys.executable, "-B", str(HOOK_PATH), *extra_args],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=run_env,
            check=False,
        )

    def _write_transcript(self, lines: list[dict[str, object]]) -> Path:
        fd, raw = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        p = Path(raw)
        p.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8")
        self.addCleanup(lambda: p.unlink(missing_ok=True))
        return p

    def test_antigravity_non_commit_allows_without_transcript(self) -> None:
        proc = self._run_hook(
            {
                "toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}},
                "transcriptPath": "/nonexistent/transcript.jsonl",
            },
            "--harness",
            "antigravity",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {"decision": "allow"})

    def test_antigravity_denies_without_actual_skill_read(self) -> None:
        transcript = self._write_transcript(
            [
                {"type": "USER_INPUT", "content": f"use {SKILL_PATH}"},
                {"type": "PLANNER_RESPONSE", "content": f"Checking {SKILL_PATH} in prose"},
                {
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [
                        {"name": "edit_file", "args": {"Path": json.dumps(SKILL_PATH)}},
                        {"name": "run_command", "args": {"CommandLine": f"cat {SKILL_PATH}"}},
                    ],
                },
                {"type": "GENERIC", "content": f"Blocked: read {SKILL_PATH} first"},
            ]
        )
        for tpath in ("", "/nonexistent/transcript.jsonl", str(transcript)):
            with self.subTest(tpath=tpath):
                proc = self._run_hook(
                    {
                        "toolCall": {"name": "run_command", "args": {"CommandLine": 'git commit -m "feat: a"'}},
                        "transcriptPath": tpath,
                    }
                )
                self.assertEqual(proc.returncode, 0)
                data = json.loads(proc.stdout)
                self.assertEqual(data["decision"], "deny")
                self.assertIn("git-commit-branch/SKILL.md", data["reason"])

    def test_antigravity_allows_after_protojson_read_file(self) -> None:
        transcript = self._write_transcript(
            [
                {
                    "type": "PLANNER_RESPONSE",
                    "tool_calls": [
                        {"name": "read_file", "args": {"Path": json.dumps(SKILL_PATH)}},
                    ],
                }
            ]
        )
        proc = self._run_hook(
            {
                "toolCall": {"name": "run_command", "args": {"CommandLine": 'git commit -m "feat: a"'}},
                "transcriptPath": str(transcript),
            }
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {"decision": "allow"})

    def test_antigravity_allows_view_file_and_tilde_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tpath = Path(tmpdir) / "transcript.jsonl"
            tpath.write_text(
                json.dumps(
                    {
                        "type": "PLANNER_RESPONSE",
                        "tool_calls": [{"name": "view_file", "args": {"AbsolutePath": SKILL_PATH}}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            proc = self._run_hook(
                {
                    "toolCall": {"name": "run_command", "args": {"CommandLine": 'git commit -m "feat: a"'}},
                    "transcriptPath": "~/transcript.jsonl",
                },
                env={"HOME": tmpdir},
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(json.loads(proc.stdout), {"decision": "allow"})

    def test_claude_non_commit_exits_quietly(self) -> None:
        proc = self._run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
                "transcript_path": "/nonexistent/transcript.jsonl",
            },
            "--harness",
            "claude",
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")

    def test_claude_denies_when_unloaded_or_prose_only(self) -> None:
        transcript = self._write_transcript(
            [
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": f"I know {SKILL_PATH}"}]},
                }
            ]
        )
        proc = self._run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit -m "feat: a"'},
                "transcript_path": str(transcript),
            }
        )
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("git-commit-branch", data["hookSpecificOutput"]["permissionDecisionReason"])

    def test_claude_allows_read_skill_and_slash_command(self) -> None:
        cases = [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/home/u/.claude/skills/git-commit-branch/SKILL.md"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": "git-commit-branch"},
                        }
                    ]
                },
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Skill",
                            "input": {"skill": "agentic:git-commit-branch"},
                        }
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": "<command-name>/git-commit-branch</command-name>",
                },
            },
        ]
        for entry in cases:
            with self.subTest(entry=entry):
                transcript = self._write_transcript([entry])
                proc = self._run_hook(
                    {
                        "tool_name": "Bash",
                        "tool_input": {"command": 'git commit -m "feat: a"'},
                        "transcript_path": str(transcript),
                    }
                )
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
