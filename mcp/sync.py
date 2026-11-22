#!/usr/bin/env python3
"""Synchronize project-local MCP configurations across AI coding harnesses."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import stat
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Mapping

ALL_HARNESSES = ("antigravity", "claude", "codex", "opencode", "gemini")
DEFAULT_HARNESSES = ("antigravity", "claude")

HARNESS_PATHS: dict[str, str] = {
    "antigravity": ".agents/mcp_config.json",
    "claude": ".mcp.json",
    "codex": ".codex/config.toml",
    "opencode": "opencode.json",
    "gemini": ".gemini/settings.json",
}

MANAGED_REL_PATH = ".agents/.mcp-managed.json"
WRAPPERS_REL_DIR = ".agents/.mcp-wrappers"

SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ENV_VAR_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TOML_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")

STDIO_FIELDS = frozenset({"command", "args", "env", "secretEnv"})
HTTP_FIELDS = frozenset({"url", "headers", "bearerTokenEnvVar", "secretHeaders"})

CODEX_BEGIN = "# BEGIN agentic-mcp"
CODEX_END = "# END agentic-mcp"

SECRET_HEADER_NAME_RE = re.compile(r"(?:^authorization$|api[-_]?key|token|secret|password)", re.IGNORECASE)


def _warn(msg: str) -> None:
    print(f"agentic-mcp warning: {msg}", file=sys.stderr)


def default_global_env_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(os.path.expanduser(xdg)) if xdg else Path.home() / ".config"
    return base / "agentic" / "env"


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv-style KEY=VALUE file without executing shell code."""
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _warn(f"cannot read env file {path}: {exc}")
        return {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export") and len(line) > 6 and line[6].isspace():
            line = line[6:].lstrip()
        if "=" not in line:
            continue
        raw_key, raw_val = line.split("=", 1)
        key = raw_key.strip()
        if not ENV_VAR_RE.match(key):
            continue
        result[key] = _parse_env_value(raw_val)
    return result


def _parse_env_value(raw_val: str) -> str:
    val = raw_val.lstrip()
    if not val:
        return ""

    quote = val[0]
    if quote == "'":
        end = val.find("'", 1)
        if end != -1:
            return val[1:end]
        return val[1:].rstrip()

    if quote == '"':
        out: list[str] = []
        escapes = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
        i = 1
        n = len(val)
        while i < n:
            ch = val[i]
            if ch == "\\" and i + 1 < n:
                nxt = val[i + 1]
                if nxt in escapes:
                    out.append(escapes[nxt])
                else:
                    out.append("\\" + nxt)
                i += 2
                continue
            if ch == '"':
                return "".join(out)
            out.append(ch)
            i += 1
        return "".join(out)

    # Unquoted: strip trailing '# ...' only when preceded by whitespace.
    for i, ch in enumerate(raw_val):
        if ch == "#" and i > 0 and raw_val[i - 1].isspace():
            return raw_val[:i].strip()
    return raw_val.strip()


def load_merged_env(
    global_env_path: Path | None,
    project_env_path: Path | None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load environment variables with precedence: global file < project file < process env."""
    merged: dict[str, str] = {}
    if global_env_path is not None:
        merged.update(parse_env_file(global_env_path))
    if project_env_path is not None:
        merged.update(parse_env_file(project_env_path))
    merged.update(os.environ if base_env is None else base_env)
    return merged


def _validate_str_dict(obj: Any, label: str, *, match_env_val: bool = False) -> dict[str, str]:
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"{label} must be an object")
    cleaned: dict[str, str] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k or "\n" in k or "\r" in k:
            raise ValueError(f"{label} has invalid key {k!r}")
        if not isinstance(v, str):
            raise ValueError(f"{label}.{k} must be a string")
        if match_env_val and not ENV_VAR_RE.match(v):
            raise ValueError(f"{label}.{k} env var {v!r} must match {ENV_VAR_RE.pattern}")
        cleaned[k] = v
    return cleaned


def validate_server(name: Any, raw_cfg: Any) -> dict[str, Any]:
    """Validate and normalize a single MCP server specification."""
    if not isinstance(name, str) or not SERVER_NAME_RE.match(name):
        raise ValueError(f"invalid server name {name!r}")
    if not isinstance(raw_cfg, dict):
        raise ValueError(f"server {name!r} must be an object")

    has_cmd = "command" in raw_cfg and raw_cfg["command"] is not None
    has_url = "url" in raw_cfg and raw_cfg["url"] is not None
    if has_cmd == has_url:
        raise ValueError(f"server {name!r} must specify exactly one of 'command' or 'url'")

    if has_cmd:
        bad = sorted(k for k in raw_cfg if k not in STDIO_FIELDS)
        if bad:
            raise ValueError(f"stdio server {name!r} has invalid fields: {', '.join(bad)}")
        cmd = raw_cfg["command"]
        if not isinstance(cmd, str) or not cmd.strip():
            raise ValueError(f"server {name!r}.command must be a non-empty string")
        raw_args = raw_cfg.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(a, str) for a in raw_args):
            raise ValueError(f"server {name!r}.args must be a list of strings")
        env = _validate_str_dict(raw_cfg.get("env"), f"server {name!r}.env")
        for ek in env:
            if not ENV_VAR_RE.match(ek):
                raise ValueError(f"server {name!r}.env key {ek!r} must match {ENV_VAR_RE.pattern}")
        raw_secret_env = raw_cfg.get("secretEnv", [])
        if not isinstance(raw_secret_env, list) or not all(
            isinstance(v, str) and ENV_VAR_RE.match(v) for v in raw_secret_env
        ):
            raise ValueError(
                f"server {name!r}.secretEnv must be a list of valid env var names"
            )
        return {
            "transport": "stdio",
            "command": cmd,
            "args": list(raw_args),
            "env": env,
            "secretEnv": list(dict.fromkeys(raw_secret_env)),
        }

    bad = sorted(k for k in raw_cfg if k not in HTTP_FIELDS)
    if bad:
        raise ValueError(f"http server {name!r} has invalid fields: {', '.join(bad)}")
    url = raw_cfg["url"]
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"server {name!r}.url must be a non-empty string")
    headers = _validate_str_dict(raw_cfg.get("headers"), f"server {name!r}.headers")
    bearer = raw_cfg.get("bearerTokenEnvVar")
    if bearer is not None and (not isinstance(bearer, str) or not ENV_VAR_RE.match(bearer)):
        raise ValueError(
            f"server {name!r}.bearerTokenEnvVar {bearer!r} must match {ENV_VAR_RE.pattern}"
        )
    secret_headers = _validate_str_dict(
        raw_cfg.get("secretHeaders"), f"server {name!r}.secretHeaders", match_env_val=True
    )
    return {
        "transport": "http",
        "url": url,
        "headers": headers,
        "bearerTokenEnvVar": bearer,
        "secretHeaders": secret_headers,
    }


def validate_global_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Validate a global MCP manifest, rejecting hardcoded credentials."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
        raise ValueError(f"{path}: root must be an object with an 'mcpServers' object")
    extra_top = sorted(k for k in data if k != "mcpServers")
    if extra_top:
        raise ValueError(f"{path}: unexpected top-level keys: {', '.join(extra_top)}")

    validated: dict[str, dict[str, Any]] = {}
    for name, raw_cfg in data["mcpServers"].items():
        srv = validate_server(name, raw_cfg)
        if srv["transport"] == "stdio":
            if srv["secretEnv"]:
                raise ValueError(f"{path}: global server {name!r} must not declare secretEnv")
            for k in srv["env"]:
                if SECRET_HEADER_NAME_RE.search(k):
                    raise ValueError(
                        f"{path}: global server {name!r}.env.{k} appears to contain a secret"
                    )
        else:
            if srv["bearerTokenEnvVar"] or srv["secretHeaders"]:
                raise ValueError(
                    f"{path}: global server {name!r} must not declare bearerTokenEnvVar or secretHeaders"
                )
            for hk, hv in srv["headers"].items():
                if SECRET_HEADER_NAME_RE.search(hk) or hv.lower().startswith("bearer "):
                    raise ValueError(
                        f"{path}: global server {name!r}.headers.{hk} must not hardcode credentials"
                    )
        validated[name] = srv
    return validated


def resolve_harnesses(
    cli_harnesses: str | None,
    spec_harnesses: Any,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Resolve active harnesses by precedence: CLI > AGENTIC_MCP_HARNESSES > spec > default."""
    environ = os.environ if env is None else env
    raw_env = environ.get("AGENTIC_MCP_HARNESSES", "").strip()

    chosen: list[str]
    if cli_harnesses is not None and cli_harnesses.strip():
        chosen = _parse_harness_csv(cli_harnesses)
    elif raw_env:
        chosen = _parse_harness_csv(raw_env)
    elif spec_harnesses is not None:
        if not isinstance(spec_harnesses, list) or not all(isinstance(h, str) for h in spec_harnesses):
            raise ValueError("spec.harnesses must be a list of harness names")
        chosen = list(dict.fromkeys(spec_harnesses))
    else:
        chosen = list(DEFAULT_HARNESSES)

    unknown = [h for h in chosen if h not in ALL_HARNESSES]
    if unknown:
        raise ValueError(
            f"unknown harness(es): {', '.join(unknown)} (valid: {', '.join(ALL_HARNESSES)})"
        )
    return chosen


def _parse_harness_csv(raw: str) -> list[str]:
    items = [part.strip() for part in raw.split(",") if part.strip()]
    if items == ["all"]:
        return list(ALL_HARNESSES)
    expanded: list[str] = []
    for item in items:
        if item == "all":
            expanded.extend(ALL_HARNESSES)
        else:
            expanded.append(item)
    return list(dict.fromkeys(expanded))


def _atomic_write(path: Path, content: str, mode: int = 0o644) -> bool:
    """Atomically write content with exact mode; refuse symlinks and skip unchanged files."""
    if path.is_symlink():
        _warn(f"refusing to overwrite symlink {path}")
        return False

    if path.exists():
        if not path.is_file():
            _warn(f"refusing to overwrite non-regular file {path}")
            return False
        try:
            existing = path.read_text(encoding="utf-8")
            current_mode = stat.S_IMODE(path.stat().st_mode)
            if existing == content and current_mode == mode:
                return False
        except OSError:
            pass

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return True


def _toml_key(key: str) -> str:
    return key if TOML_BARE_KEY_RE.match(key) else _toml_str(key)


def _toml_str(value: str) -> str:
    escapes = {
        "\\": "\\\\",
        '"': '\\"',
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
    }
    out = ['"']
    for ch in value:
        if ch in escapes:
            out.append(escapes[ch])
        else:
            code = ord(ch)
            if code < 0x20 or code == 0x7F:
                out.append(f"\\u{code:04x}")
            else:
                out.append(ch)
    out.append('"')
    return "".join(out)


def _render_codex_block(effective_servers: dict[str, dict[str, Any]]) -> str:
    lines = [
        CODEX_BEGIN,
        "# Managed by agentic/mcp/sync.py. Edits inside this block are overwritten.",
    ]
    for name in sorted(effective_servers):
        srv = effective_servers[name]
        key = _toml_key(name)
        lines.append(f"[mcp_servers.{key}]")
        if srv["transport"] == "stdio":
            lines.append(f"command = {_toml_str(srv['command'])}")
            args_rendered = ", ".join(_toml_str(a) for a in srv["args"])
            lines.append(f"args = [{args_rendered}]")
            if srv["env"]:
                lines.append(f"[mcp_servers.{key}.env]")
                for ek in sorted(srv["env"]):
                    lines.append(f"{_toml_key(ek)} = {_toml_str(srv['env'][ek])}")
        else:
            lines.append(f"url = {_toml_str(srv['url'])}")
            if srv["bearerTokenEnvVar"]:
                lines.append(f"bearer_token_env_var = {_toml_str(srv['bearerTokenEnvVar'])}")
            if srv["headers"]:
                lines.append(f"[mcp_servers.{key}.http_headers]")
                for hk in sorted(srv["headers"]):
                    lines.append(f"{_toml_key(hk)} = {_toml_str(srv['headers'][hk])}")
            if srv["secretHeaders"]:
                lines.append(f"[mcp_servers.{key}.env_http_headers]")
                for hk in sorted(srv["secretHeaders"]):
                    lines.append(f"{_toml_key(hk)} = {_toml_str(srv['secretHeaders'][hk])}")
    lines.append(CODEX_END)
    return "\n".join(lines)


def _replace_bounded_block(existing: str, begin: str, end: str, block: str | None) -> tuple[str, bool]:
    """Insert, replace, or remove a line-bounded managed block. Returns (text, ok)."""
    lines = existing.splitlines()
    begin_indices = [i for i, line in enumerate(lines) if line.strip() == begin]
    end_indices = [i for i, line in enumerate(lines) if line.strip() == end]

    if not begin_indices and not end_indices:
        if block is None:
            return existing, True
        prefix = existing.rstrip("\n")
        if prefix:
            return f"{prefix}\n\n{block}\n", True
        return f"{block}\n", True

    if len(begin_indices) != 1 or len(end_indices) != 1 or end_indices[0] < begin_indices[0]:
        return existing, False

    b_idx, e_idx = begin_indices[0], end_indices[0]
    before = lines[:b_idx]
    after = lines[e_idx + 1 :]

    if block is None:
        while before and before[-1] == "":
            before.pop()
        while after and after[0] == "":
            after.pop(0)
        if before and after:
            merged_lines = [*before, "", *after]
        else:
            merged_lines = [*before, *after]
        return ("\n".join(merged_lines) + "\n") if merged_lines else "", True

    merged_lines = [*before, *block.splitlines(), *after]
    return "\n".join(merged_lines) + "\n", True


def _sync_codex(
    root: Path,
    effective_servers: dict[str, dict[str, Any]],
    active: bool,
) -> bool:
    path = root / HARNESS_PATHS["codex"]
    if path.is_symlink():
        _warn(f"refusing to overwrite symlink {path}")
        return False

    existing = ""
    if path.exists():
        if not path.is_file():
            _warn(f"refusing to overwrite non-regular file {path}")
            return False
        existing = path.read_text(encoding="utf-8")

    want_block = active and bool(effective_servers)
    if not existing and not want_block:
        return False

    block = _render_codex_block(effective_servers) if want_block else None
    candidate, ok = _replace_bounded_block(existing, CODEX_BEGIN, CODEX_END, block)
    if not ok:
        _warn(f"{path} has malformed {CODEX_BEGIN}/{CODEX_END} markers; skipping without modifying")
        return False

    if candidate == existing and path.exists():
        return True

    try:
        tomllib.loads(candidate)
    except tomllib.TOMLDecodeError as exc:
        _warn(f"refusing to write invalid TOML to {path}: {exc}")
        return False

    _atomic_write(path, candidate, 0o644)
    return want_block


def _sync_wrappers(
    root: Path,
    servers: dict[str, dict[str, Any]],
    prev_wrappers: list[str],
    global_env_path: Path,
    project_env_path: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Create stdio secret wrappers where needed, prune stale ones, and return effective server specs."""
    wrappers_dir = root / WRAPPERS_REL_DIR
    sync_script = str(Path(__file__).resolve())
    python_exe = sys.executable

    effective: dict[str, dict[str, Any]] = {}
    active_wrappers: list[str] = []

    for name in sorted(servers):
        srv = servers[name]
        if srv["transport"] == "stdio" and srv["secretEnv"]:
            wrappers_dir.mkdir(parents=True, exist_ok=True)
            meta_path = wrappers_dir / f"{name}.json"
            wrapper_path = wrappers_dir / name

            meta = {
                "command": srv["command"],
                "args": srv["args"],
                "env": srv["env"],
                "secretEnv": srv["secretEnv"],
                "globalEnvPath": str(global_env_path),
                "projectEnvPath": str(project_env_path),
            }
            _atomic_write(meta_path, json.dumps(meta, indent=2) + "\n", 0o600)

            script = (
                "#!/bin/sh\n"
                f"exec {shlex.quote(python_exe)} -B {shlex.quote(sync_script)} "
                f"--run-stdio {shlex.quote(str(meta_path.resolve()))} -- \"$@\"\n"
            )
            _atomic_write(wrapper_path, script, 0o700)

            active_wrappers.append(name)
            effective[name] = {
                "transport": "stdio",
                "command": str(wrapper_path.resolve()),
                "args": [],
                "env": {},
                "secretEnv": srv["secretEnv"],
                "wrapped": True,
            }
        else:
            effective[name] = {**srv, "wrapped": False}

    # Prune stale wrappers previously created by sync.py.
    for old in set(prev_wrappers) - set(active_wrappers):
        for candidate in (wrappers_dir / old, wrappers_dir / f"{old}.json"):
            if candidate.exists() and not candidate.is_symlink() and candidate.is_file():
                candidate.unlink()

    if wrappers_dir.is_dir() and not wrappers_dir.is_symlink():
        try:
            if not any(wrappers_dir.iterdir()):
                wrappers_dir.rmdir()
        except OSError:
            pass

    return effective, active_wrappers


def _render_json_entry(
    harness: str,
    name: str,
    srv: dict[str, Any],
    merged_env: Mapping[str, str],
) -> tuple[dict[str, Any], bool]:
    """Render one server entry for a JSON harness. Returns (entry, wrote_secret)."""
    if srv["transport"] == "stdio":
        if harness == "opencode":
            entry: dict[str, Any] = {
                "type": "local",
                "command": [srv["command"], *srv["args"]],
            }
            if srv["env"]:
                entry["environment"] = dict(srv["env"])
            return entry, False

        entry = {"command": srv["command"], "args": list(srv["args"])}
        if srv["env"]:
            entry["env"] = dict(srv["env"])
        return entry, False

    # HTTP transport
    if harness == "antigravity":
        headers = dict(srv["headers"])
        wrote_secret = False
        bearer_var = srv["bearerTokenEnvVar"]
        if bearer_var:
            val = merged_env.get(bearer_var, "")
            if val:
                headers["Authorization"] = f"Bearer {val}"
                wrote_secret = True
            else:
                _warn(
                    f"env var {bearer_var} not set for antigravity server {name!r}; omitting Authorization header"
                )
        for hk, var in srv["secretHeaders"].items():
            val = merged_env.get(var, "")
            if val:
                headers[hk] = val
                wrote_secret = True
            else:
                _warn(
                    f"env var {var} not set for antigravity server {name!r} header {hk!r}; omitting header"
                )
        entry = {"url": srv["url"]}
        if headers:
            entry["headers"] = headers
        return entry, wrote_secret

    if harness == "opencode":
        headers = dict(srv["headers"])
        bearer_var = srv["bearerTokenEnvVar"]
        if bearer_var:
            headers["Authorization"] = f"Bearer {{env:{bearer_var}}}"
        for hk, var in srv["secretHeaders"].items():
            headers[hk] = f"{{env:{var}}}"
        entry = {"type": "remote", "url": srv["url"]}
        if headers:
            entry["headers"] = headers
        has_auth = bool(bearer_var or srv["secretHeaders"]) or any(
            k.lower() == "authorization" for k in headers
        )
        if has_auth:
            entry["oauth"] = False
        return entry, False

    # Claude Code and Gemini CLI both use ${VAR} interpolation.
    headers = dict(srv["headers"])
    bearer_var = srv["bearerTokenEnvVar"]
    if bearer_var:
        headers["Authorization"] = f"Bearer ${{{bearer_var}}}"
    for hk, var in srv["secretHeaders"].items():
        headers[hk] = f"${{{var}}}"

    if harness == "claude":
        entry = {"type": "http", "url": srv["url"]}
    else:  # gemini
        entry = {"httpUrl": srv["url"]}
    if headers:
        entry["headers"] = headers
    return entry, False


def _sync_json_harness(
    harness: str,
    root: Path,
    effective_servers: dict[str, dict[str, Any]],
    prev_managed: list[str],
    active: bool,
    merged_env: Mapping[str, str],
) -> list[str] | None:
    """Sync one JSON harness config. Returns updated managed key list, or None if skipped."""
    path = root / HARNESS_PATHS[harness]
    if path.is_symlink():
        _warn(f"refusing to overwrite symlink {path}")
        return None

    prev_set = set(prev_managed)
    if not path.exists():
        if not active or not effective_servers:
            return []
        data: dict[str, Any] = {}
    else:
        if not path.is_file():
            _warn(f"refusing to overwrite non-regular file {path}")
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _warn(f"cannot parse {path}: {exc}; skipping {harness}")
            return None
        if not isinstance(loaded, dict):
            _warn(f"{path} top-level JSON is not an object; skipping {harness}")
            return None
        data = loaded

    if harness == "opencode":
        mcp_obj = data.get("mcp")
        if mcp_obj is None:
            mcp_obj = {}
        elif not isinstance(mcp_obj, dict):
            _warn(f"{path} 'mcp' field is not an object; skipping opencode")
            return None
        container = mcp_obj.get("servers")
        if container is None:
            container = {}
        elif not isinstance(container, dict):
            _warn(f"{path} 'mcp.servers' field is not an object; skipping opencode")
            return None
        servers_map = dict(container)
    else:
        container = data.get("mcpServers")
        if container is None:
            container = {}
        elif not isinstance(container, dict):
            _warn(f"{path} 'mcpServers' field is not an object; skipping {harness}")
            return None
        servers_map = dict(container)

    if not active:
        removed_any = False
        for old_name in prev_set:
            if old_name in servers_map:
                del servers_map[old_name]
                removed_any = True
        if not removed_any:
            return []
        new_data = dict(data)
        if harness == "opencode":
            new_mcp = dict(mcp_obj)
            new_mcp["servers"] = servers_map
            new_data["mcp"] = new_mcp
        else:
            new_data["mcpServers"] = servers_map
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() and servers_map else 0o644
        _atomic_write(path, json.dumps(new_data, indent=2) + "\n", mode)
        return []

    for old_name in prev_set:
        if old_name not in effective_servers and old_name in servers_map:
            del servers_map[old_name]

    wrote_secret = False
    for name in sorted(effective_servers):
        entry, entry_secret = _render_json_entry(harness, name, effective_servers[name], merged_env)
        servers_map[name] = entry
        wrote_secret = wrote_secret or entry_secret

    new_data = dict(data)
    if harness == "opencode":
        new_mcp = dict(mcp_obj)
        new_mcp["servers"] = servers_map
        new_data["mcp"] = new_mcp
    else:
        new_data["mcpServers"] = servers_map

    mode = 0o600 if wrote_secret else 0o644
    _atomic_write(path, json.dumps(new_data, indent=2) + "\n", mode)
    return sorted(effective_servers)


def _find_git_info(start: Path) -> tuple[Path, Path] | None:
    """Return (repo_root, common_git_dir) for standard repos and git worktrees."""
    resolved = start.resolve()
    for candidate in (resolved, *resolved.parents):
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            common = _resolve_commondir(dot_git)
            return candidate, common
        if dot_git.is_file():
            try:
                content = dot_git.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not content.startswith("gitdir:"):
                return None
            raw_gitdir = content.split(":", 1)[1].strip()
            git_dir = Path(raw_gitdir)
            if not git_dir.is_absolute():
                git_dir = (candidate / git_dir).resolve()
            else:
                git_dir = git_dir.resolve()
            return candidate, _resolve_commondir(git_dir)
    return None


def _resolve_commondir(git_dir: Path) -> Path:
    commondir_file = git_dir / "commondir"
    if commondir_file.is_file():
        try:
            raw = commondir_file.read_text(encoding="utf-8").strip()
            if raw:
                target = Path(raw)
                return (target if target.is_absolute() else (git_dir / target)).resolve()
        except OSError:
            pass
    return git_dir


def _sync_git_exclude(
    root: Path,
    active_harnesses: list[str],
    project_env_file: str,
    exclude_git: bool,
) -> None:
    git_info = _find_git_info(root)
    if git_info is None:
        return
    repo_root, common_dir = git_info
    root_resolved = root.resolve()
    try:
        rel_root = root_resolved.relative_to(repo_root)
    except ValueError:
        return

    if rel_root == Path("."):
        prefix = ""
        begin = "# BEGIN agentic-mcp"
        end = "# END agentic-mcp"
    else:
        rel_posix = rel_root.as_posix()
        prefix = f"{rel_posix}/"
        begin = f"# BEGIN agentic-mcp:{rel_posix}"
        end = f"# END agentic-mcp:{rel_posix}"

    exclude_path = common_dir / "info" / "exclude"
    if exclude_path.is_symlink():
        _warn(f"refusing to overwrite symlink {exclude_path}")
        return

    existing = ""
    if exclude_path.exists():
        if not exclude_path.is_file():
            _warn(f"refusing to overwrite non-regular file {exclude_path}")
            return
        existing = exclude_path.read_text(encoding="utf-8")

    block: str | None = None
    if exclude_git:
        patterns: list[str] = [f"/{prefix}{HARNESS_PATHS[h]}" for h in active_harnesses]
        patterns.append(f"/{prefix}{MANAGED_REL_PATH}")
        patterns.append(f"/{prefix}{WRAPPERS_REL_DIR}/")

        env_candidate = Path(project_env_file)
        env_abs = (
            env_candidate if env_candidate.is_absolute() else (root_resolved / env_candidate)
        ).resolve()
        if env_abs.is_relative_to(repo_root):
            env_rel = env_abs.relative_to(repo_root).as_posix()
            patterns.append(f"/{env_rel}")

        deduped = list(dict.fromkeys(patterns))
        block = "\n".join([begin, *deduped, end])

    if not existing and block is None:
        return

    updated, ok = _replace_bounded_block(existing, begin, end, block)
    if not ok:
        _warn(f"{exclude_path} has malformed {begin}/{end} markers; skipping")
        return
    if updated != existing or not exclude_path.exists():
        _atomic_write(exclude_path, updated, 0o644)


def _load_managed_state(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {"harnesses": {}, "wrappers": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"harnesses": {}, "wrappers": []}
    if not isinstance(data, dict):
        return {"harnesses": {}, "wrappers": []}
    harnesses = data.get("harnesses")
    wrappers = data.get("wrappers")
    return {
        "harnesses": harnesses if isinstance(harnesses, dict) else {},
        "wrappers": wrappers if isinstance(wrappers, list) else [],
    }


def sync_spec(
    spec_path: Path,
    root: Path,
    *,
    global_env_path: Path | None = None,
    cli_harnesses: str | None = None,
) -> int:
    """Sync MCP configs in `root` from `spec_path`."""
    raw_spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(raw_spec, dict):
        raise ValueError("spec must be a JSON object")

    raw_servers = raw_spec.get("servers", {})
    if not isinstance(raw_servers, dict):
        raise ValueError("spec.servers must be an object")
    servers = {name: validate_server(name, cfg) for name, cfg in raw_servers.items()}

    active_harnesses = resolve_harnesses(cli_harnesses, raw_spec.get("harnesses"))
    project_env_file = raw_spec.get("projectEnvFile", ".agents/mcp.env")
    if not isinstance(project_env_file, str) or not project_env_file.strip():
        raise ValueError("spec.projectEnvFile must be a non-empty string")
    exclude_git = raw_spec.get("excludeGit", True)
    if not isinstance(exclude_git, bool):
        raise ValueError("spec.excludeGit must be a boolean")

    if not root.exists() or not os.access(root, os.W_OK):
        _warn(f"target directory {root} is not writable; skipping MCP sync")
        return 0

    resolved_global_env = (
        global_env_path if global_env_path is not None else default_global_env_path()
    )
    project_env_candidate = Path(project_env_file)
    resolved_project_env = (
        project_env_candidate
        if project_env_candidate.is_absolute()
        else (root / project_env_candidate)
    )
    merged_env = load_merged_env(resolved_global_env, resolved_project_env)

    managed_path = root / MANAGED_REL_PATH
    prev_state = _load_managed_state(managed_path)
    prev_harnesses: dict[str, list[str]] = {
        k: [x for x in v if isinstance(x, str)]
        for k, v in prev_state["harnesses"].items()
        if isinstance(v, list)
    }
    prev_wrappers = [x for x in prev_state["wrappers"] if isinstance(x, str)]

    try:
        effective_servers, active_wrappers = _sync_wrappers(
            root, servers, prev_wrappers, resolved_global_env, resolved_project_env
        )

        new_harnesses_state: dict[str, list[str]] = {}
        active_set = set(active_harnesses)

        for harness in ALL_HARNESSES:
            is_active = harness in active_set
            prev_list = prev_harnesses.get(harness, [])
            if harness == "codex":
                if is_active or prev_list or (root / HARNESS_PATHS["codex"]).exists():
                    active_codex = _sync_codex(root, effective_servers, is_active)
                    if is_active and active_codex:
                        new_harnesses_state["codex"] = sorted(effective_servers)
                continue

            if not is_active and harness not in prev_harnesses:
                continue

            updated = _sync_json_harness(
                harness, root, effective_servers, prev_list, is_active, merged_env
            )
            if updated is None:
                # Preserve previous managed keys on skipped files so pruning isn't lost later.
                if prev_list:
                    new_harnesses_state[harness] = prev_list
            elif is_active and updated:
                new_harnesses_state[harness] = updated

        _atomic_write(
            managed_path,
            json.dumps(
                {"harnesses": new_harnesses_state, "wrappers": active_wrappers},
                indent=2,
            )
            + "\n",
            0o644,
        )

        _sync_git_exclude(root, active_harnesses, project_env_file, exclude_git)
    except PermissionError as exc:
        _warn(f"permission denied while syncing {root}: {exc}")
        return 0
    return 0


def run_stdio(meta_path: Path, extra_args: list[str]) -> int:
    """Execute a stdio MCP server with whitelisted secrets from env files."""
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    child_env = dict(os.environ)
    for k, v in meta.get("env", {}).items():
        child_env[k] = v

    file_env: dict[str, str] = {}
    global_raw = meta.get("globalEnvPath", "")
    if global_raw:
        file_env.update(parse_env_file(Path(global_raw)))
    project_raw = meta.get("projectEnvPath", "")
    if project_raw:
        file_env.update(parse_env_file(Path(project_raw)))

    for key in meta.get("secretEnv", []):
        if key in os.environ:
            child_env[key] = os.environ[key]
        elif key in file_env:
            child_env[key] = file_env[key]

    command = meta["command"]
    argv = [command, *meta.get("args", []), *extra_args]
    os.execvpe(command, argv, child_env)
    return 127


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else list(argv)

    # Intercept --run-stdio before argparse so extra flags (including --help) pass verbatim.
    if len(args_list) >= 2 and args_list[0] == "--run-stdio":
        meta_path = Path(args_list[1])
        rest = args_list[2:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        return run_stdio(meta_path, rest)

    parser = argparse.ArgumentParser(description="Synchronize local MCP configurations.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--spec", type=Path, help="Path to generated MCP spec JSON.")
    mode.add_argument(
        "--validate-global",
        type=Path,
        help="Validate a global MCP manifest JSON and exit.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Target workspace root directory (defaults to CWD).",
    )
    parser.add_argument(
        "--global-env",
        type=Path,
        default=None,
        help="Override global env file path (defaults to $XDG_CONFIG_HOME/agentic/env).",
    )
    parser.add_argument(
        "--harnesses",
        type=str,
        default=None,
        help="Comma-separated harness list (or 'all') overriding spec and AGENTIC_MCP_HARNESSES.",
    )
    ns = parser.parse_args(args_list)

    try:
        if ns.validate_global is not None:
            validate_global_manifest(ns.validate_global)
            return 0
        return sync_spec(
            ns.spec,
            ns.root,
            global_env_path=ns.global_env,
            cli_harnesses=ns.harnesses,
        )
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
