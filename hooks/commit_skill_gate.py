#!/usr/bin/env python3
"""PreToolUse hook blocking `git commit` until the commit skill is read."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")"}
SHELL_NAMES = {"sh", "bash", "zsh", "dash", "ksh"}
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

GIT_VALUE_FLAGS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--config-env",
    "--exec-path",
}

ENV_VALUE_FLAGS = {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "--argv0"}
SUDO_VALUE_FLAGS = {
    "-u",
    "--user",
    "-g",
    "--group",
    "-C",
    "--close-from",
    "-h",
    "--host",
    "-p",
    "--prompt",
    "-r",
    "--role",
    "-t",
    "--type",
    "-U",
    "--other-user",
    "-D",
    "--chdir",
    "-T",
    "--command-timeout",
}
TIMEOUT_VALUE_FLAGS = {"-k", "--kill-after", "-s", "--signal"}
FALLBACK_COMMIT_RE = re.compile(
    r"(?:^|[;&|(\n])\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:sudo\s+|env\s+|command\s+)?"
    r"(?:/\S*/)?git\b(?:(?!\s*(?:&&|\|\||[;&|\n])).)*?\scommit\b(?![-_])"
)


def _split_simple_commands(cmd: str) -> list[list[str]]:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True

    commands: list[list[str]] = []
    current: list[str] = []
    for tok in lex:
        if tok in SEPARATORS or (tok and set(tok) <= SEPARATORS):
            if current:
                commands.append(current)
                current = []
        else:
            current.append(tok)
    if current:
        commands.append(current)
    return commands


def _unwrap_env(args: list[str]) -> list[list[str]]:
    results: list[list[str]] = []
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            i += 1
            break
        if tok in {"-S", "--split-string"}:
            if i + 1 < len(args):
                results.extend(_split_simple_commands(args[i + 1]))
                i += 2
                continue
            break
        if tok.startswith("--split-string="):
            results.extend(_split_simple_commands(tok.split("=", 1)[1]))
            i += 1
            continue
        if tok in ENV_VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if ENV_ASSIGN_RE.match(tok):
            i += 1
            continue
        break
    if i < len(args):
        results.append(args[i:])
    return results


def _unwrap_sudo(args: list[str]) -> list[str]:
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            i += 1
            break
        if tok in SUDO_VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if ENV_ASSIGN_RE.match(tok):
            i += 1
            continue
        break
    return args[i:]


def _unwrap_timeout(args: list[str]) -> list[str]:
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            i += 1
            break
        if tok in TIMEOUT_VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        # First positional argument to `timeout` is the duration.
        i += 1
        break
    return args[i:]


def _unwrap_nice(args: list[str]) -> list[str]:
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            i += 1
            break
        if tok in {"-n", "--adjustment"}:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        break
    return args[i:]


def _unwrap_nix(args: list[str]) -> list[str]:
    i = 0
    subcommand = None
    while i < len(args):
        tok = args[i]
        if tok.startswith("-"):
            if tok in {"--extra-experimental-features", "--option", "-I"}:
                i += 2
            else:
                i += 1
            continue
        subcommand = tok
        i += 1
        break
    if subcommand not in {"develop", "shell"}:
        return []
    while i < len(args):
        tok = args[i]
        if tok in {"-c", "--command"}:
            return args[i + 1 :]
        i += 1
    return []


def _extract_shell_c_scripts(args: list[str]) -> list[str]:
    scripts: list[str] = []
    i = 0
    saw_c = False
    while i < len(args):
        tok = args[i]
        if tok == "--":
            i += 1
            break
        if tok in {"-o", "+o"}:
            i += 2
            continue
        if tok.startswith("-") and tok != "-" and not tok.startswith("--"):
            flags = tok[1:]
            if "c" in flags:
                saw_c = True
            if flags.endswith("o"):
                i += 2
            else:
                i += 1
            continue
        if tok.startswith("--"):
            i += 1
            continue
        if saw_c:
            scripts.append(tok)
        break
    if saw_c and not scripts and i < len(args):
        scripts.append(args[i])
    return scripts


def _is_git_commit_args(args: list[str]) -> bool:
    i = 0
    subcommand = None
    while i < len(args):
        tok = args[i]
        if tok == "--":
            break
        if tok in GIT_VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        subcommand = tok
        i += 1
        break
    if subcommand != "commit":
        return False
    remaining = args[i:]
    if "-h" in remaining or "--help" in remaining:
        return False
    return True


def _tokens_run_git_commit(tokens: list[str]) -> bool:
    idx = 0
    while idx < len(tokens) and ENV_ASSIGN_RE.match(tokens[idx]):
        idx += 1
    if idx >= len(tokens):
        return False

    tokens = tokens[idx:]
    prog = os.path.basename(tokens[0])
    rest = tokens[1:]

    if prog == "env":
        return any(_tokens_run_git_commit(inner) for inner in _unwrap_env(rest))
    if prog == "sudo":
        return _tokens_run_git_commit(_unwrap_sudo(rest))
    if prog == "timeout":
        return _tokens_run_git_commit(_unwrap_timeout(rest))
    if prog == "nice":
        return _tokens_run_git_commit(_unwrap_nice(rest))
    if prog == "command":
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok in {"-v", "-V"}:
                return False
            if tok == "--":
                i += 1
                break
            if tok.startswith("-"):
                i += 1
                continue
            break
        return _tokens_run_git_commit(rest[i:])
    if prog in {"builtin", "nohup"}:
        return _tokens_run_git_commit([t for t in rest if t != "--"] if rest[:1] == ["--"] else rest)
    if prog == "exec":
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok == "--":
                i += 1
                break
            if tok == "-a":
                i += 2
                continue
            if tok.startswith("-"):
                i += 1
                continue
            break
        return _tokens_run_git_commit(rest[i:])
    if prog == "time":
        i = 0
        while i < len(rest):
            tok = rest[i]
            if tok == "--":
                i += 1
                break
            if tok in {"-f", "-o", "--format", "--output"}:
                i += 2
                continue
            if tok.startswith("-"):
                i += 1
                continue
            break
        return _tokens_run_git_commit(rest[i:])
    if prog == "nix":
        inner = _unwrap_nix(rest)
        return _tokens_run_git_commit(inner) if inner else False
    if prog == "nix-shell":
        i = 0
        while i < len(rest):
            if rest[i] in {"--run", "--command"} and i + 1 < len(rest):
                if command_runs_git_commit(rest[i + 1]):
                    return True
                i += 2
                continue
            i += 1
        return False
    if prog in SHELL_NAMES:
        return any(command_runs_git_commit(script) for script in _extract_shell_c_scripts(rest))
    if prog == "git":
        return _is_git_commit_args(rest)
    return False


def command_runs_git_commit(cmd: str) -> bool:
    """Return True if shell command invokes `git commit`."""
    if not cmd or "git" not in cmd or "commit" not in cmd:
        return False
    try:
        commands = _split_simple_commands(cmd)
    except ValueError:
        if "--help" in cmd or " -h" in cmd:
            return bool(FALLBACK_COMMIT_RE.search(re.sub(r"\s(?:--help|-h)\b", "", cmd)))
        return bool(FALLBACK_COMMIT_RE.search(cmd))
    return any(_tokens_run_git_commit(tokens) for tokens in commands)


def _unwrap_protojson_str(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            decoded = json.loads(s)
            if isinstance(decoded, str):
                return decoded
        except json.JSONDecodeError:
            return s[1:-1]
    return s


def _matches_skill_path(raw: object, skill_name: str) -> bool:
    unwrapped = _unwrap_protojson_str(raw)
    if not unwrapped:
        return False
    norm = unwrapped.replace("\\", "/").rstrip("/")
    suffix = f"{skill_name}/SKILL.md"
    return norm == suffix or norm.endswith(f"/{suffix}")


def _antigravity_record_read_skill(record: dict[str, Any], skill_name: str) -> bool:
    tool_calls = record.get("tool_calls")
    if not isinstance(tool_calls, list):
        return False
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        if tc.get("name") not in {"read_file", "view_file"}:
            continue
        args = tc.get("args")
        if not isinstance(args, dict):
            continue
        for key in ("Path", "AbsolutePath", "path", "file_path"):
            if _matches_skill_path(args.get(key), skill_name):
                return True
    return False


def _extract_claude_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _claude_record_read_skill(record: dict[str, Any], skill_name: str) -> bool:
    blocks: list[dict[str, Any]] = []
    if record.get("type") == "tool_use":
        blocks.append(record)
    msg = record.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        blocks.extend(b for b in msg["content"] if isinstance(b, dict))
    if isinstance(record.get("content"), list):
        blocks.extend(b for b in record["content"] if isinstance(b, dict))

    for block in blocks:
        if block.get("type") != "tool_use":
            continue
        name = block.get("name")
        inp = block.get("input")
        if not isinstance(inp, dict):
            continue
        if name in {"Read", "View"}:
            if _matches_skill_path(inp.get("file_path") or inp.get("path"), skill_name):
                return True
        elif name == "Skill":
            raw_skill = str(inp.get("skill") or inp.get("name") or "").strip()
            if raw_skill.split(":")[-1] == skill_name:
                return True

    if record.get("type") == "user":
        marker = f"<command-name>/{skill_name}</command-name>"
        if isinstance(msg, dict) and marker in _extract_claude_text(msg.get("content")):
            return True
        if marker in _extract_claude_text(record.get("content")):
            return True
    return False


def transcript_read_skill(transcript_path: str, skill_name: str, harness: str) -> bool:
    """Return True if the session transcript records reading or loading `skill_name`."""
    if not transcript_path:
        return False
    path = Path(os.path.expanduser(transcript_path))
    if not path.is_file():
        return False

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                if harness == "claude":
                    if _claude_record_read_skill(record, skill_name):
                        return True
                else:
                    if _antigravity_record_read_skill(record, skill_name):
                        return True
    except OSError:
        return False
    return False


def detect_harness(payload: dict[str, Any], requested: str) -> str:
    if requested != "auto":
        return requested
    if "toolCall" in payload:
        return "antigravity"
    if "tool_name" in payload or "tool_input" in payload:
        return "claude"
    return "antigravity"


def evaluate_hook(
    payload: dict[str, Any],
    *,
    harness: str = "auto",
    skill_name: str = "git-atomic-conventional-c4-commits",
) -> tuple[str, dict[str, Any] | None]:
    resolved_harness = detect_harness(payload, harness)

    if resolved_harness == "antigravity":
        tool_call = payload.get("toolCall")
        if not isinstance(tool_call, dict) or tool_call.get("name") != "run_command":
            return resolved_harness, {"decision": "allow"}
        args = tool_call.get("args")
        cmd = args.get("CommandLine", "") if isinstance(args, dict) else ""
        if not isinstance(cmd, str) or not command_runs_git_commit(cmd):
            return resolved_harness, {"decision": "allow"}
        transcript = payload.get("transcriptPath", "")
        if isinstance(transcript, str) and transcript_read_skill(transcript, skill_name, "antigravity"):
            return resolved_harness, {"decision": "allow"}
        return resolved_harness, {
            "decision": "deny",
            "reason": (
                f"Blocked: read and follow {skill_name}/SKILL.md "
                f"(via read_file on ~/Workspaces/gdr/agentic/skills/git/{skill_name}/SKILL.md) "
                "before running git commit."
            ),
        }

    # Claude Code harness
    if payload.get("tool_name") != "Bash":
        return resolved_harness, None
    tool_input = payload.get("tool_input")
    cmd = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(cmd, str) or not command_runs_git_commit(cmd):
        return resolved_harness, None
    transcript = payload.get("transcript_path", "")
    if isinstance(transcript, str) and transcript_read_skill(transcript, skill_name, "claude"):
        return resolved_harness, None
    return resolved_harness, {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked: load and follow the {skill_name} skill "
                f"(via Skill tool or Read on ~/.claude/skills/{skill_name}/SKILL.md) "
                "before running git commit."
            ),
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PreToolUse gate for git commit skill loading.")
    parser.add_argument("--harness", choices=("auto", "antigravity", "claude"), default="auto")
    parser.add_argument("--skill", default="git-atomic-conventional-c4-commits")
    args = parser.parse_args(argv)

    raw_stdin = sys.stdin.read()
    try:
        payload = json.loads(raw_stdin) if raw_stdin.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    _, response = evaluate_hook(payload, harness=args.harness, skill_name=args.skill)
    if response is not None:
        print(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
