#!/usr/bin/env python3
"""Sync embeddable Beads rule and git-exclude entries into a consumer project."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

EXCLUDE_BEGIN = "# BEGIN agentic-beads"
EXCLUDE_END = "# END agentic-beads"


def _git_common_dir(root: Path) -> Path | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    raw = proc.stdout.strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_absolute() else (root / p).resolve()


def _update_git_exclude(root: Path, entries: list[str]) -> None:
    git_dir = _git_common_dir(root)
    if git_dir is None:
        return
    exclude_path = git_dir / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude_path.read_text(encoding="utf-8") if exclude_path.exists() else ""

    lines = existing.splitlines()
    out: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == EXCLUDE_BEGIN:
            skipping = True
            continue
        if skipping:
            if line.strip() == EXCLUDE_END:
                skipping = False
            continue
        out.append(line)

    while out and out[-1] == "":
        out.pop()

    if entries:
        if out:
            out.append("")
        out.append(EXCLUDE_BEGIN)
        out.extend(entries)
        out.append(EXCLUDE_END)

    new_text = ("\n".join(out) + "\n") if out else ""
    if new_text != existing:
        exclude_path.write_text(new_text, encoding="utf-8")


def sync_project(
    root: Path,
    rule_src: Path,
    *,
    sync_rule: bool = True,
    exclude_git: bool = True,
    auto_init: bool = False,
) -> None:
    root = root.resolve()
    excluded: list[str] = []

    if sync_rule:
        dest = root / ".agents" / "rules" / "beads.md"
        if dest.is_symlink():
            print(f"agentic-beads warning: refusing to overwrite symlink {dest}", file=sys.stderr)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            desired = rule_src.read_text(encoding="utf-8")
            current = dest.read_text(encoding="utf-8") if dest.exists() else None
            if current != desired:
                dest.write_text(desired, encoding="utf-8")
            excluded.append("/.agents/rules/beads.md")

    if exclude_git:
        _update_git_exclude(root, excluded)

    if auto_init and not (root / ".beads").exists():
        init_res = subprocess.run(
            ["bd", "init", "--non-interactive", "--skip-agents", "--skip-hooks", "--init-if-missing"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if init_res.returncode != 0:
            msg = (init_res.stderr or init_res.stdout).strip()
            print(f"agentic-beads warning: bd init failed: {msg}", file=sys.stderr)
        else:
            subprocess.run(
                ["bd", "config", "set", "export.auto", "true"],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Sync embeddable Beads rule into a project")
    parser.add_argument("--root", default=".", help="Consumer project root")
    parser.add_argument("--rule", required=True, help="Source path to beads rule.md")
    parser.add_argument("--no-rule", action="store_true", help="Skip syncing .agents/rules/beads.md")
    parser.add_argument("--no-exclude", action="store_true", help="Skip updating .git/info/exclude")
    parser.add_argument("--auto-init", action="store_true", help="Initialize .beads/ if missing")
    args = parser.parse_args(argv)

    if os.environ.get("AGENTIC_BEADS_DISABLE") == "1":
        return 0

    sync_project(
        Path(args.root),
        Path(args.rule),
        sync_rule=not args.no_rule,
        exclude_git=not args.no_exclude,
        auto_init=args.auto_init,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
