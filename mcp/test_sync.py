#!/usr/bin/env python3
"""Unit tests for mcp/sync.py and mcp/global.json."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
SYNC_PATH = MCP_DIR / "sync.py"
GLOBAL_JSON_PATH = MCP_DIR / "global.json"
sys.path.insert(0, str(MCP_DIR))

import sync  # noqa: E402


class EnvParsingTests(unittest.TestCase):
    def test_parse_env_file_formats_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "env"
            env_path.write_text(
                "\n".join(
                    [
                        "# leading comment",
                        "",
                        "PLAIN=hello_world",
                        "export EXPORTED=from_export # trailing comment",
                        "HASH_NO_SPACE=abc#def",
                        "EMPTY_WITH_COMMENT= # only comment",
                        "SINGLE='literal $VAR # kept\\n'",
                        'DOUBLE="line1\\nline2\\t\\"quoted\\"\\\\end"',
                        "123INVALID=skip_me",
                        "BAD-KEY=skip_me",
                        "NO_EQUALS_LINE",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            parsed = sync.parse_env_file(env_path)
            self.assertEqual(
                parsed,
                {
                    "PLAIN": "hello_world",
                    "EXPORTED": "from_export",
                    "HASH_NO_SPACE": "abc#def",
                    "EMPTY_WITH_COMMENT": "",
                    "SINGLE": "literal $VAR # kept\\n",
                    "DOUBLE": 'line1\nline2\t"quoted"\\end',
                },
            )

    def test_load_merged_env_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            g = root / "global.env"
            p = root / "project.env"
            g.write_text("A=global\nB=global\nC=global\n", encoding="utf-8")
            p.write_text("B=project\nC=project\n", encoding="utf-8")
            merged = sync.load_merged_env(g, p, base_env={"C": "process"})
            self.assertEqual(merged["A"], "global")
            self.assertEqual(merged["B"], "project")
            self.assertEqual(merged["C"], "process")


class GlobalManifestValidationTests(unittest.TestCase):
    def test_repo_global_json_is_valid(self) -> None:
        servers = sync.validate_global_manifest(GLOBAL_JSON_PATH)
        self.assertIn("context7", servers)
        self.assertEqual(servers["context7"]["transport"], "http")

    def test_rejects_both_command_and_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "global.json"
            bad.write_text(
                json.dumps({"mcpServers": {"bad": {"command": "x", "url": "https://x"}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                sync.validate_global_manifest(bad)

    def test_rejects_path_traversal_server_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "global.json"
            bad.write_text(
                json.dumps({"mcpServers": {"../evil": {"url": "https://example.com/mcp"}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                sync.validate_global_manifest(bad)

    def test_rejects_hardcoded_authorization_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "global.json"
            bad.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "api": {
                                "url": "https://example.com/mcp",
                                "headers": {"Authorization": "Bearer secret-token"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                sync.validate_global_manifest(bad)


class HarnessRenderingTests(unittest.TestCase):
    def _write_spec(self, path: Path, spec: dict) -> Path:
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def test_all_five_harnesses_and_preservation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            global_env = root / "global.env"
            global_env.write_text("BEARER_TOK=sec-bearer\nCUSTOM_HDR=sec-custom\n", encoding="utf-8")

            # Pre-seed user settings that must survive merge.
            (root / ".gemini").mkdir()
            (root / ".gemini" / "settings.json").write_text(
                json.dumps({"theme": "dark", "mcpServers": {"manual": {"command": "manual-bin"}}}),
                encoding="utf-8",
            )
            (root / "opencode.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://opencode.ai/config.json",
                        "mcp": {"timeout": {"startup": 5000}, "servers": {"userSrv": {"type": "local", "command": ["u"]}}},
                    }
                ),
                encoding="utf-8",
            )
            (root / ".codex").mkdir()
            (root / ".codex" / "config.toml").write_text(
                'model = "o3"\n\n[mcp_servers.user_keep]\ncommand = "keep"\n',
                encoding="utf-8",
            )

            spec = {
                "harnesses": list(sync.ALL_HARNESSES),
                "projectEnvFile": ".agents/mcp.env",
                "excludeGit": False,
                "servers": {
                    "nixos": {"command": "/nix/store/x-mcp-nixos/bin/mcp-nixos", "args": []},
                    "ghidra": {
                        "command": "bridge-mcp-ghidra",
                        "args": ["--verbose"],
                        "env": {"GHIDRA_MCP_URL": "http://127.0.0.1:8089"},
                    },
                    "remote_api": {
                        "url": "https://api.example.com/mcp",
                        "headers": {"X-Static": "ok"},
                        "bearerTokenEnvVar": "BEARER_TOK",
                        "secretHeaders": {"X-Custom": "CUSTOM_HDR"},
                    },
                },
            }
            spec_path = self._write_spec(root / "spec.json", spec)
            rc = sync.sync_spec(spec_path, root, global_env_path=global_env)
            self.assertEqual(rc, 0)

            # Antigravity: resolved headers and strict 0600 mode
            agy_path = root / ".agents" / "mcp_config.json"
            self.assertEqual(stat.S_IMODE(agy_path.stat().st_mode), 0o600)
            agy = json.loads(agy_path.read_text(encoding="utf-8"))
            self.assertEqual(
                agy["mcpServers"]["nixos"],
                {"command": "/nix/store/x-mcp-nixos/bin/mcp-nixos", "args": []},
            )
            self.assertEqual(
                agy["mcpServers"]["remote_api"]["headers"],
                {
                    "X-Static": "ok",
                    "Authorization": "Bearer sec-bearer",
                    "X-Custom": "sec-custom",
                },
            )

            # Claude Code: type=http + ${VAR}
            claude_path = root / ".mcp.json"
            self.assertEqual(stat.S_IMODE(claude_path.stat().st_mode), 0o644)
            claude = json.loads(claude_path.read_text(encoding="utf-8"))
            self.assertEqual(claude["mcpServers"]["remote_api"]["type"], "http")
            self.assertEqual(
                claude["mcpServers"]["remote_api"]["headers"],
                {
                    "X-Static": "ok",
                    "Authorization": "Bearer ${BEARER_TOK}",
                    "X-Custom": "${CUSTOM_HDR}",
                },
            )

            # Gemini CLI: httpUrl + preserves theme and manual server
            gemini = json.loads((root / ".gemini" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(gemini["theme"], "dark")
            self.assertIn("manual", gemini["mcpServers"])
            self.assertEqual(gemini["mcpServers"]["remote_api"]["httpUrl"], "https://api.example.com/mcp")
            self.assertNotIn("url", gemini["mcpServers"]["remote_api"])

            # OpenCode: mcp.servers + {env:VAR} + oauth=false + preserves timeout & userSrv
            opencode = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
            self.assertEqual(opencode["mcp"]["timeout"], {"startup": 5000})
            self.assertIn("userSrv", opencode["mcp"]["servers"])
            self.assertEqual(
                opencode["mcp"]["servers"]["ghidra"],
                {
                    "type": "local",
                    "command": ["bridge-mcp-ghidra", "--verbose"],
                    "environment": {"GHIDRA_MCP_URL": "http://127.0.0.1:8089"},
                },
            )
            self.assertEqual(
                opencode["mcp"]["servers"]["remote_api"],
                {
                    "type": "remote",
                    "url": "https://api.example.com/mcp",
                    "headers": {
                        "X-Static": "ok",
                        "Authorization": "Bearer {env:BEARER_TOK}",
                        "X-Custom": "{env:CUSTOM_HDR}",
                    },
                    "oauth": False,
                },
            )

            # Codex: valid TOML, preserves outer config, uses bearer_token_env_var + env_http_headers
            codex_text = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
            codex = tomllib.loads(codex_text)
            self.assertEqual(codex["model"], "o3")
            self.assertEqual(codex["mcp_servers"]["user_keep"], {"command": "keep"})
            self.assertEqual(codex["mcp_servers"]["remote_api"]["bearer_token_env_var"], "BEARER_TOK")
            self.assertEqual(
                codex["mcp_servers"]["remote_api"]["env_http_headers"],
                {"X-Custom": "CUSTOM_HDR"},
            )
            self.assertEqual(codex["mcp_servers"]["remote_api"]["http_headers"], {"X-Static": "ok"})

    def test_missing_secret_warns_and_uses_0644(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "harnesses": ["antigravity"],
                "excludeGit": False,
                "servers": {
                    "api": {
                        "url": "https://api.example.com/mcp",
                        "bearerTokenEnvVar": "DEFINITELY_MISSING_TOKEN_XYZ",
                    }
                },
            }
            spec_path = self._write_spec(root / "spec.json", spec)
            old_val = os.environ.pop("DEFINITELY_MISSING_TOKEN_XYZ", None)
            try:
                rc = sync.sync_spec(spec_path, root, global_env_path=root / "missing.env")
            finally:
                if old_val is not None:
                    os.environ["DEFINITELY_MISSING_TOKEN_XYZ"] = old_val
            self.assertEqual(rc, 0)
            agy_path = root / ".agents" / "mcp_config.json"
            self.assertEqual(stat.S_IMODE(agy_path.stat().st_mode), 0o644)
            agy = json.loads(agy_path.read_text(encoding="utf-8"))
            self.assertEqual(agy["mcpServers"]["api"], {"url": "https://api.example.com/mcp"})

    def test_idempotency_and_pruning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec1 = {
                "harnesses": ["antigravity", "claude", "codex"],
                "excludeGit": False,
                "servers": {
                    "a": {"command": "bin-a"},
                    "b": {"command": "bin-b"},
                },
            }
            spec_path = self._write_spec(root / "spec.json", spec1)
            sync.sync_spec(spec_path, root, global_env_path=root / "none.env")

            agy_path = root / ".agents" / "mcp_config.json"
            mtime_before = agy_path.stat().st_mtime_ns
            sync.sync_spec(spec_path, root, global_env_path=root / "none.env")
            self.assertEqual(agy_path.stat().st_mtime_ns, mtime_before)

            # Add manual server in .mcp.json and remove server 'b' + deselect 'codex'
            claude_data = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
            claude_data["mcpServers"]["manual"] = {"command": "keep-me"}
            (root / ".mcp.json").write_text(json.dumps(claude_data), encoding="utf-8")

            spec2 = {
                "harnesses": ["antigravity", "claude"],
                "excludeGit": False,
                "servers": {"a": {"command": "bin-a"}},
            }
            self._write_spec(spec_path, spec2)
            sync.sync_spec(spec_path, root, global_env_path=root / "none.env")

            claude_after = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
            self.assertIn("a", claude_after["mcpServers"])
            self.assertIn("manual", claude_after["mcpServers"])
            self.assertNotIn("b", claude_after["mcpServers"])

            codex_after = (root / ".codex" / "config.toml").read_text(encoding="utf-8")
            self.assertNotIn(sync.CODEX_BEGIN, codex_after)
            self.assertEqual(tomllib.loads(codex_after), {})

    def test_harness_env_override_all(self) -> None:
        resolved = sync.resolve_harnesses(None, ["antigravity"], env={"AGENTIC_MCP_HARNESSES": "all"})
        self.assertEqual(resolved, list(sync.ALL_HARNESSES))
        resolved_csv = sync.resolve_harnesses(None, ["antigravity"], env={"AGENTIC_MCP_HARNESSES": "codex, gemini"})
        self.assertEqual(resolved_csv, ["codex", "gemini"])


class StdioWrapperTests(unittest.TestCase):
    def test_wrapper_least_privilege_and_metachar_safety(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            echo_script = root / "echo_env.py"
            echo_script.write_text(
                "import json, os, sys\n"
                "print(json.dumps({\n"
                "  'argv': sys.argv[1:],\n"
                "  'allowed': os.environ.get('ALLOWED_SECRET'),\n"
                "  'static': os.environ.get('STATIC_VAR'),\n"
                "  'unrelated': os.environ.get('UNRELATED_SECRET'),\n"
                "}))\n",
                encoding="utf-8",
            )
            global_env = root / "global.env"
            global_env.write_text(
                "ALLOWED_SECRET=from_global\nUNRELATED_SECRET=do_not_leak\n",
                encoding="utf-8",
            )
            pwn_marker = root / "pwned"
            project_env = root / ".agents" / "mcp.env"
            project_env.parent.mkdir(parents=True)
            weird_secret = f"$(touch {pwn_marker});'a\"b"
            project_env.write_text(
                f'ALLOWED_SECRET="{weird_secret.replace(chr(34), chr(92) + chr(34))}"\n',
                encoding="utf-8",
            )

            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "harnesses": ["antigravity"],
                        "projectEnvFile": ".agents/mcp.env",
                        "excludeGit": False,
                        "servers": {
                            "wrapped": {
                                "command": sys.executable,
                                "args": [str(echo_script)],
                                "env": {"STATIC_VAR": "hello"},
                                "secretEnv": ["ALLOWED_SECRET"],
                            },
                            "plain": {"command": "echo", "args": ["ok"]},
                        },
                    }
                ),
                encoding="utf-8",
            )

            env_clean = {k: v for k, v in os.environ.items() if k not in {"ALLOWED_SECRET", "UNRELATED_SECRET"}}
            orig_env = os.environ.copy()
            os.environ.clear()
            os.environ.update(env_clean)
            try:
                sync.sync_spec(spec_path, root, global_env_path=global_env)
            finally:
                os.environ.clear()
                os.environ.update(orig_env)

            agy = json.loads((root / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
            # Plain server uses command directly without wrapper.
            self.assertEqual(agy["mcpServers"]["plain"]["command"], "echo")
            wrapper_cmd = agy["mcpServers"]["wrapped"]["command"]
            self.assertTrue(wrapper_cmd.endswith("/.agents/.mcp-wrappers/wrapped"))
            self.assertEqual(stat.S_IMODE(Path(wrapper_cmd).stat().st_mode), 0o700)

            proc = subprocess.run(
                [wrapper_cmd, "--help", "extra"],
                capture_output=True,
                text=True,
                env=env_clean,
                check=True,
            )
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["argv"], ["--help", "extra"])
            self.assertEqual(payload["allowed"], weird_secret)
            self.assertEqual(payload["static"], "hello")
            self.assertIsNone(payload["unrelated"])
            self.assertFalse(pwn_marker.exists())


class GitExcludeAndSymlinkTests(unittest.TestCase):
    def test_standard_git_repo_and_non_git_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Non-git directory succeeds cleanly
            non_git = root / "plain"
            non_git.mkdir()
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps({"harnesses": ["antigravity", "claude"], "servers": {"a": {"command": "a"}}}),
                encoding="utf-8",
            )
            self.assertEqual(sync.sync_spec(spec_path, non_git, global_env_path=root / "none.env"), 0)

            # Standard .git repository
            repo = root / "repo"
            (repo / ".git" / "info").mkdir(parents=True)
            exclude = repo / ".git" / "info" / "exclude"
            exclude.write_text("*.log\n", encoding="utf-8")

            sync.sync_spec(spec_path, repo, global_env_path=root / "none.env")
            content = exclude.read_text(encoding="utf-8")
            self.assertIn("*.log", content)
            self.assertIn("/.agents/mcp_config.json", content)
            self.assertIn("/.mcp.json", content)
            self.assertIn("/.agents/.mcp-managed.json", content)
            self.assertIn("/.agents/.mcp-wrappers/", content)
            self.assertIn("/.agents/mcp.env", content)

            # Running twice is idempotent
            sync.sync_spec(spec_path, repo, global_env_path=root / "none.env")
            self.assertEqual(exclude.read_text(encoding="utf-8").count("# BEGIN agentic-mcp"), 1)

    def test_worktree_commondir_exclude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common = root / "main.git" / "worktrees" / "wt"
            (root / "main.git" / "info").mkdir(parents=True)
            common.mkdir(parents=True)
            (common / "commondir").write_text("../..\n", encoding="utf-8")

            wt = root / "wt"
            wt.mkdir()
            (wt / ".git").write_text(f"gitdir: {common}\n", encoding="utf-8")

            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps({"harnesses": ["claude"], "servers": {"a": {"command": "a"}}}),
                encoding="utf-8",
            )
            sync.sync_spec(spec_path, wt, global_env_path=root / "none.env")
            exclude = (root / "main.git" / "info" / "exclude").read_text(encoding="utf-8")
            self.assertIn("/.mcp.json", exclude)

    def test_refuses_symlink_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "do_not_touch.json"
            target.write_text("KEEP_ME\n", encoding="utf-8")
            (root / ".mcp.json").symlink_to(target)

            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "harnesses": ["claude"],
                        "excludeGit": False,
                        "servers": {"a": {"command": "a"}},
                    }
                ),
                encoding="utf-8",
            )
            sync.sync_spec(spec_path, root, global_env_path=root / "none.env")
            self.assertEqual(target.read_text(encoding="utf-8"), "KEEP_ME\n")


if __name__ == "__main__":
    unittest.main()
