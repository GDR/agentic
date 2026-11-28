#!/usr/bin/env python3
"""Unit tests for embeddable Beads sync helper."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import sync


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
            self.assertTrue((root / ".agents" / "skills" / "beads-plan" / "SKILL.md").is_file())
            self.assertTrue((root / ".agents" / "skills" / "beads-triage" / "SKILL.md").is_file())
            self.assertTrue((root / ".agents" / "skills" / "beads-work" / "SKILL.md").is_file())

            exclude_file = root / ".git" / "info" / "exclude"
            exclude_text = exclude_file.read_text(encoding="utf-8")
            self.assertIn("# BEGIN agentic-beads", exclude_text)
            self.assertIn("/.agents/rules/beads.md", exclude_text)
            self.assertIn("/.agents/skills/beads-plan/", exclude_text)
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


if __name__ == "__main__":
    unittest.main()
