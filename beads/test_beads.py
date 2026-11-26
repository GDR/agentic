#!/usr/bin/env python3
"""Unit tests for embeddable Beads sync helper and local Web GUI."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import sync
import ui


class BeadsSyncTests(unittest.TestCase):
    def test_sync_rule_idempotent_and_git_exclude_in_repo_and_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            rule_src = Path(__file__).resolve().parent / "rule.md"
            skills_src = Path(__file__).resolve().parent.parent / "skills" / "beads"

            subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(root), check=True)
            (root / "README.md").write_text("hi\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=str(root), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(root), check=True)

            sync.sync_project(root, rule_src, skills_src=skills_src)
            dest = root / ".agents" / "rules" / "beads.md"
            self.assertEqual(dest.read_text(encoding="utf-8"), rule_src.read_text(encoding="utf-8"))
            self.assertTrue((root / ".agents" / "skills" / "beads-triage" / "SKILL.md").is_file())
            self.assertTrue((root / ".agents" / "skills" / "beads-work" / "SKILL.md").is_file())

            exclude_file = root / ".git" / "info" / "exclude"
            exclude_text = exclude_file.read_text(encoding="utf-8")
            self.assertIn("# BEGIN agentic-beads", exclude_text)
            self.assertIn("/.agents/rules/beads.md", exclude_text)
            self.assertIn("/.agents/skills/beads-triage/", exclude_text)
            self.assertIn("/.agents/skills/beads-work/", exclude_text)

            # Idempotent second run
            sync.sync_project(root, rule_src, skills_src=skills_src)
            self.assertEqual(exclude_file.read_text(encoding="utf-8"), exclude_text)

            # Linked worktree updates common git exclude
            wt = Path(tmp) / "wt"
            subprocess.run(["git", "worktree", "add", "-q", "-b", "feat", str(wt)], cwd=str(root), check=True)
            sync.sync_project(wt, rule_src, skills_src=skills_src)
            self.assertTrue((wt / ".agents" / "rules" / "beads.md").is_file())
            self.assertTrue((wt / ".agents" / "skills" / "beads-work" / "SKILL.md").is_file())
            self.assertEqual(exclude_file.read_text(encoding="utf-8"), exclude_text)

    def test_refuses_symlink_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "external.md"
            target.write_text("keep me", encoding="utf-8")
            rules_dir = root / ".agents" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "beads.md").symlink_to(target)

            rule_src = Path(__file__).resolve().parent / "rule.md"
            sync.sync_project(root, rule_src, exclude_git=False)
            self.assertEqual(target.read_text(encoding="utf-8"), "keep me")

    def test_rule_under_25_lines(self) -> None:
        rule_src = Path(__file__).resolve().parent / "rule.md"
        lines = rule_src.read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 25)


class BeadsUiTests(unittest.TestCase):
    def test_validate_issue_id(self) -> None:
        self.assertEqual(ui.validate_issue_id("proj-a1b.2"), "proj-a1b.2")
        for bad in ("", "../etc", "-flag", "id with space", "id;rm"):
            with self.assertRaises(ValueError):
                ui.validate_issue_id(bad)

    def test_http_endpoints_with_mocked_bd(self) -> None:
        sample_issues = [
            {"id": "demo-1", "title": "Epic", "status": "open", "priority": 1, "issue_type": "epic"},
            {
                "id": "demo-1.1",
                "title": "Task 1",
                "status": "open",
                "priority": 1,
                "issue_type": "task",
                "parent": "demo-1",
            },
        ]

        def fake_run_bd(args: list[str], cwd: Path) -> object:
            if args == ["list", "--all"]:
                return sample_issues
            if args == ["ready"]:
                return sample_issues
            return {"ok": True}

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            (repo_root / ".beads").mkdir()
            handler_cls = type("TestBeadsHandler", (ui.BeadsHandler,), {"repo_root": repo_root})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with mock.patch.object(ui, "run_bd", side_effect=fake_run_bd):
                    html = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode("utf-8")
                    self.assertIn("Beads — Local Task Board", html)
                    state = json.loads(
                        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=5).read().decode("utf-8")
                    )
                    self.assertEqual(len(state["issues"]), 2)
                    self.assertEqual(len(state["ready"]), 2)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
