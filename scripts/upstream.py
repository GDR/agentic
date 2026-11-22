#!/usr/bin/env python3
"""Manage commit-SHA and SHA-256 pinned upstream Agent Skills and rules."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IGNORED_DIR_NAMES = {"__pycache__", ".git"}
IGNORED_FILE_NAMES = {".DS_Store"}


class UpstreamError(Exception):
    """Raised when manifest validation, integrity checks, or sync fails."""

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


@dataclass(frozen=True)
class MappingRule:
    src: str
    to: str


@dataclass(frozen=True)
class FetchedBlob:
    dest: str
    src_path: str
    data: bytes
    sha256: str
    executable: bool


def validate_rel_posix(raw: Any, field: str, allow_empty: bool = False) -> str:
    if not isinstance(raw, str) or "\x00" in raw or "\\" in raw:
        raise UpstreamError(f"{field} must be a valid POSIX relative path: {raw!r}")
    if raw.startswith("/"):
        raise UpstreamError(f"{field} must be relative (no leading '/'): {raw!r}")
    parts = [p for p in raw.split("/") if p]
    if not parts:
        if allow_empty and raw == "":
            return ""
        raise UpstreamError(f"{field} must not be empty: {raw!r}")
    if any(p in (".", "..") for p in parts):
        raise UpstreamError(f"{field} must not contain '.' or '..': {raw!r}")
    normalized = "/".join(parts)
    if normalized != raw:
        raise UpstreamError(f"{field} must be normalized without '//' or trailing '/': {raw!r}")
    return normalized


def normalize_manifest(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise UpstreamError("upstream.json must be a JSON object with version == 1")
    sources = data.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise UpstreamError("upstream.json 'sources' must be a non-empty object")

    seen_dest_files: dict[str, str] = {}
    for src_name, spec in sources.items():
        if not isinstance(src_name, str) or not src_name or "/" in src_name:
            raise UpstreamError(f"Invalid source name: {src_name!r}")
        if not isinstance(spec, dict):
            raise UpstreamError(f"Source {src_name!r} must be an object")

        repo = spec.get("repo")
        if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
            raise UpstreamError(f"Source {src_name!r}: invalid repo {repo!r}")

        rev = spec.get("rev")
        if not isinstance(rev, str) or not SHA40_RE.fullmatch(rev):
            raise UpstreamError(
                f"Source {src_name!r}: rev must be a 40-char lowercase hex commit SHA, got {rev!r}"
            )

        mappings = spec.get("mappings")
        if not isinstance(mappings, list) or not mappings:
            raise UpstreamError(f"Source {src_name!r}: mappings must be a non-empty list")
        for idx, m in enumerate(mappings):
            if not isinstance(m, dict):
                raise UpstreamError(f"Source {src_name!r}: mapping[{idx}] must be an object")
            validate_rel_posix(m.get("from"), f"{src_name}.mappings[{idx}].from")
            validate_rel_posix(m.get("to"), f"{src_name}.mappings[{idx}].to")

        exclude = spec.get("exclude", [])
        if not isinstance(exclude, list) or not all(isinstance(p, str) and p for p in exclude):
            raise UpstreamError(f"Source {src_name!r}: exclude must be a list of non-empty strings")

        files = spec.get("files")
        if not isinstance(files, dict):
            raise UpstreamError(f"Source {src_name!r}: files must be an object")
        for dest, digest in files.items():
            norm_dest = validate_rel_posix(dest, f"{src_name}.files key")
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                raise UpstreamError(
                    f"Source {src_name!r}: invalid sha256 for {norm_dest!r}: {digest!r}"
                )
            owner = seen_dest_files.get(norm_dest)
            if owner is not None:
                raise UpstreamError(
                    f"Destination path {norm_dest!r} claimed by both {owner!r} and {src_name!r}"
                )
            seen_dest_files[norm_dest] = src_name

    return data


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise UpstreamError(f"Cannot read manifest {manifest_path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UpstreamError(f"Invalid JSON in {manifest_path}: {exc}") from exc
    return normalize_manifest(data)


def write_manifest_atomic(manifest_path: Path, data: dict[str, Any]) -> None:
    payload = json.dumps(data, indent=2) + "\n"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=manifest_path.parent,
        prefix=f".{manifest_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, manifest_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_no_symlink_components(root: Path, rel_path: str) -> Path:
    root_resolved = root.resolve(strict=True)
    cur = root
    for part in rel_path.split("/"):
        cur = cur / part
        if cur.is_symlink():
            raise UpstreamError(f"Symlink not permitted inside vendored path: {cur}")
    if cur.exists():
        resolved = cur.resolve(strict=True)
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise UpstreamError(f"Path escapes repository root: {cur}") from exc
    return cur


def matches_exclude(rel_to_mapping: str, patterns: list[str]) -> bool:
    pure = PurePosixPath(rel_to_mapping)
    name = pure.name
    for pat in patterns:
        norm_pat = pat.strip("/")
        if not norm_pat:
            continue
        if norm_pat.endswith("/**"):
            prefix = norm_pat[:-3].rstrip("/")
            if rel_to_mapping == prefix or rel_to_mapping.startswith(prefix + "/"):
                return True
        if "/" in norm_pat:
            if fnmatch.fnmatchcase(rel_to_mapping, norm_pat):
                return True
        else:
            if fnmatch.fnmatchcase(name, norm_pat) or fnmatch.fnmatchcase(rel_to_mapping, norm_pat):
                return True
    return False


def http_get_bytes(url: str) -> bytes:
    headers = {
        "User-Agent": "agentic-upstream/1.0",
        "Accept": "application/vnd.github+json",
    }
    # Only send GitHub tokens to api.github.com so credentials never leak on raw/third-party hosts.
    if urllib.parse.urlsplit(url).hostname == "api.github.com":
        token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="replace").strip()
        raise UpstreamError(f"HTTP {exc.code} fetching {url}: {body}", http_status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise UpstreamError(f"Network error fetching {url}: {exc.reason}") from exc


def fetch_tree_blobs_via_git(repo: str, rev: str) -> dict[str, tuple[str, str]]:
    """Fetch pinned commit tree via partial git fetch when REST API is rate-limited."""
    remote_url = f"https://github.com/{repo}.git"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    with tempfile.TemporaryDirectory(prefix="agentic-tree-") as tmpdir:
        try:
            subprocess.run(
                ["git", "-C", tmpdir, "init", "-q", "--bare"],
                check=True,
                capture_output=True,
                timeout=20,
                env=env,
            )
            subprocess.run(
                ["git", "-C", tmpdir, "fetch", "-q", "--depth=1", "--filter=blob:none", remote_url, rev],
                check=True,
                capture_output=True,
                timeout=60,
                env=env,
            )
            res = subprocess.run(
                ["git", "-C", tmpdir, "ls-tree", "-r", "-z", rev],
                check=True,
                capture_output=True,
                timeout=30,
                env=env,
            )
            out: dict[str, tuple[str, str]] = {}
            for rec in res.stdout.split(b"\x00"):
                if not rec:
                    continue
                meta_raw, path_raw = rec.split(b"\t", 1)
                mode, etype, _oid = meta_raw.decode("ascii").split(" ", 2)
                path = path_raw.decode("utf-8")
                out[path] = (etype, mode)
            return out
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise UpstreamError(f"git tree fallback failed for {repo}@{rev[:7]}: {exc}") from exc


def fetch_tree_blobs(repo: str, rev: str) -> dict[str, tuple[str, str]]:
    """Return {repo_rel_path: (type, mode)} for tree at pinned commit rev."""
    url = f"https://api.github.com/repos/{repo}/git/trees/{rev}?recursive=1"
    try:
        payload = json.loads(http_get_bytes(url).decode("utf-8"))
    except UpstreamError as exc:
        if exc.http_status in (403, 429):
            print(
                f"Note: GitHub API returned HTTP {exc.http_status} for {repo}@{rev[:7]}; falling back to treeless git fetch",
                file=sys.stderr,
            )
            return fetch_tree_blobs_via_git(repo, rev)
        raise
    if payload.get("truncated"):
        raise UpstreamError(
            f"GitHub git tree response for {repo}@{rev[:7]} was truncated; aborting incomplete sync"
        )
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise UpstreamError(f"Unexpected tree payload for {repo}@{rev[:7]}")
    out: dict[str, tuple[str, str]] = {}
    for entry in tree:
        path = entry.get("path")
        etype = entry.get("type")
        mode = entry.get("mode", "")
        if isinstance(path, str) and isinstance(etype, str):
            out[path] = (etype, mode)
    return out


def resolve_mapping_blobs(
    repo: str,
    rev: str,
    spec: dict[str, Any],
    tree_entries: dict[str, tuple[str, str]],
) -> list[FetchedBlob]:
    excludes: list[str] = list(spec.get("exclude", []))
    raw_targets: dict[str, tuple[str, bool]] = {}

    for m in spec["mappings"]:
        src = m["from"]
        to = m["to"]
        matched = 0

        if src in tree_entries and tree_entries[src][0] != "tree":
            etype, mode = tree_entries[src]
            if etype != "blob" or mode == "120000":
                raise UpstreamError(
                    f"{repo}@{rev[:7]}: exact mapping {src!r} is not a regular blob (type={etype}, mode={mode})"
                )
            if to in raw_targets:
                raise UpstreamError(f"Duplicate mapped destination {to!r} in source")
            raw_targets[to] = (src, mode == "100755")
            matched = 1
        else:
            prefix = src + "/"
            for path, (etype, mode) in sorted(tree_entries.items()):
                if not path.startswith(prefix):
                    continue
                if etype != "blob":
                    continue
                if mode == "120000":
                    # Never vendor upstream symlinks silently
                    continue
                rel = path[len(prefix) :]
                if matches_exclude(rel, excludes):
                    continue
                dest = f"{to}/{rel}"
                if dest in raw_targets:
                    raise UpstreamError(f"Duplicate mapped destination {dest!r} in source")
                raw_targets[dest] = (path, mode == "100755")
                matched += 1

        if matched == 0:
            raise UpstreamError(
                f"{repo}@{rev[:7]}: mapping {src!r} -> {to!r} matched 0 files"
            )

    fetched: list[FetchedBlob] = []
    for dest in sorted(raw_targets):
        src_path, executable = raw_targets[dest]
        quoted_path = urllib.parse.quote(src_path, safe="/")
        raw_url = f"https://raw.githubusercontent.com/{repo}/{rev}/{quoted_path}"
        data = http_get_bytes(raw_url)
        fetched.append(
            FetchedBlob(
                dest=dest,
                src_path=src_path,
                data=data,
                sha256=sha256_bytes(data),
                executable=executable,
            )
        )
    return fetched


def write_file_atomic(target: Path, data: bytes, executable: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, 0o755 if executable else 0o644)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def prune_empty_parents(start_dir: Path, stop_at: Path) -> None:
    cur = start_dir
    stop_resolved = stop_at.resolve(strict=True)
    while cur != stop_at:
        try:
            if cur.resolve(strict=True) == stop_resolved:
                break
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent


def resolve_remote_head(repo: str) -> str:
    remote_url = f"https://github.com/{repo}.git"
    try:
        res = subprocess.run(
            ["git", "ls-remote", remote_url, "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if res.returncode == 0 and res.stdout.strip():
            sha = res.stdout.strip().split()[0].lower()
            if SHA40_RE.fullmatch(sha):
                return sha
    except (OSError, subprocess.SubprocessError):
        pass

    # Fallback: GitHub commits API
    url = f"https://api.github.com/repos/{repo}/commits?per_page=1"
    commits = json.loads(http_get_bytes(url).decode("utf-8"))
    if isinstance(commits, list) and commits and isinstance(commits[0].get("sha"), str):
        sha = commits[0]["sha"].lower()
        if SHA40_RE.fullmatch(sha):
            return sha
    raise UpstreamError(f"Could not resolve HEAD commit SHA for {repo}")


def cmd_verify(manifest_path: Path, root: Path) -> int:
    manifest = load_manifest(manifest_path)
    sources = manifest["sources"]
    errors: list[str] = []
    all_recorded: set[str] = set()
    dir_roots: set[str] = set()

    for src_name, spec in sources.items():
        files: dict[str, str] = spec["files"]
        if not files:
            errors.append(f"{src_name}: recorded 'files' map is empty (run sync --write-lock)")
            continue

        for m in spec["mappings"]:
            to = m["to"]
            if any(dest.startswith(to + "/") for dest in files):
                dir_roots.add(to)

        for dest, expected_sha in files.items():
            all_recorded.add(dest)
            try:
                target = ensure_no_symlink_components(root, dest)
            except UpstreamError as exc:
                errors.append(f"{src_name}: {exc}")
                continue
            if not target.is_file():
                errors.append(f"{src_name}: missing vendored file {dest}")
                continue
            actual_sha = sha256_bytes(target.read_bytes())
            if actual_sha != expected_sha:
                errors.append(
                    f"{src_name}: sha256 mismatch for {dest}: expected {expected_sha}, got {actual_sha}"
                )

    # Check for unexpected/rogue files inside vendored directory mappings
    for dir_rel in sorted(dir_roots):
        try:
            dir_abs = ensure_no_symlink_components(root, dir_rel)
        except UpstreamError as exc:
            errors.append(str(exc))
            continue
        if not dir_abs.is_dir():
            errors.append(f"Missing vendored directory: {dir_rel}")
            continue
        for cur_root, dirnames, filenames in os.walk(dir_abs, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIR_NAMES)
            cur_path = Path(cur_root)
            for dname in dirnames:
                dp = cur_path / dname
                if dp.is_symlink():
                    errors.append(f"Unexpected symlink inside vendored directory: {dp}")
            for fname in sorted(filenames):
                if fname in IGNORED_FILE_NAMES:
                    continue
                fp = cur_path / fname
                if fp.is_symlink():
                    errors.append(f"Unexpected symlink inside vendored directory: {fp}")
                    continue
                rel = fp.relative_to(root).as_posix()
                if rel not in all_recorded:
                    errors.append(f"Unrecorded file inside vendored directory: {rel}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(f"Verified {len(sources)} upstream sources ({len(all_recorded)} files)")
    return 0


def sync_source(
    src_name: str,
    spec: dict[str, Any],
    root: Path,
    write_lock: bool,
) -> dict[str, str]:
    repo = spec["repo"]
    rev = spec["rev"]
    tree_entries = fetch_tree_blobs(repo, rev)
    blobs = resolve_mapping_blobs(repo, rev, spec, tree_entries)
    new_files = {blob.dest: blob.sha256 for blob in blobs}
    old_files: dict[str, str] = dict(spec.get("files", {}))

    if not write_lock:
        if not old_files:
            raise UpstreamError(
                f"{src_name}: upstream.json has no pinned file hashes; run sync --write-lock first"
            )
        if new_files != old_files:
            old_keys = set(old_files)
            new_keys = set(new_files)
            missing = sorted(old_keys - new_keys)
            extra = sorted(new_keys - old_keys)
            changed = sorted(k for k in (old_keys & new_keys) if old_files[k] != new_files[k])
            details = []
            if missing:
                details.append(f"missing={missing}")
            if extra:
                details.append(f"extra={extra}")
            if changed:
                details.append(f"changed={changed}")
            raise UpstreamError(
                f"{src_name}@{rev[:7]} hash verification failed ({'; '.join(details)})"
            )

    # Validate destination paths have no symlinks before mutating disk
    for blob in blobs:
        ensure_no_symlink_components(root, blob.dest)

    # Remove files that were previously recorded under this source and no longer exist
    removed = sorted(set(old_files) - set(new_files))
    for old_rel in removed:
        old_abs = root / old_rel
        if old_abs.is_symlink():
            raise UpstreamError(f"Refusing to remove symlink {old_abs}")
        if old_abs.is_file():
            old_abs.unlink()
            prune_empty_parents(old_abs.parent, root)

    for blob in blobs:
        write_file_atomic(root / blob.dest, blob.data, blob.executable)

    return new_files


def select_sources(manifest: dict[str, Any], names: list[str]) -> list[str]:
    all_names = list(manifest["sources"].keys())
    if not names:
        return all_names
    unknown = [n for n in names if n not in manifest["sources"]]
    if unknown:
        raise UpstreamError(f"Unknown upstream source(s): {', '.join(unknown)}")
    return names


def cmd_sync(manifest_path: Path, root: Path, names: list[str], write_lock: bool) -> int:
    manifest = load_manifest(manifest_path)
    selected = select_sources(manifest, names)

    for src_name in selected:
        spec = manifest["sources"][src_name]
        new_files = sync_source(src_name, spec, root, write_lock=write_lock)
        if write_lock:
            # Flush each synced source incrementally so mid-batch failures never leave unhashed files.
            spec["files"] = new_files
            normalize_manifest(manifest)
            write_manifest_atomic(manifest_path, manifest)
        print(f"Synced {src_name} ({spec['repo']}@{spec['rev'][:7]}): {len(new_files)} files")

    return cmd_verify(manifest_path, root)


def cmd_bump(manifest_path: Path, root: Path, names: list[str]) -> int:
    manifest = load_manifest(manifest_path)
    selected = select_sources(manifest, names)
    bumped: list[str] = []

    for src_name in selected:
        spec = manifest["sources"][src_name]
        repo = spec["repo"]
        old_rev = spec["rev"]
        new_rev = resolve_remote_head(repo)
        if new_rev == old_rev:
            print(f"{src_name} ({repo}): up to date at {old_rev[:7]}")
            continue
        print(f"{src_name} ({repo}): {old_rev[:7]} -> {new_rev[:7]}")
        print(f"  Compare: https://github.com/{repo}/compare/{old_rev}..{new_rev}")
        spec["rev"] = new_rev
        spec["files"] = sync_source(src_name, spec, root, write_lock=True)
        bumped.append(src_name)

    if bumped:
        normalize_manifest(manifest)
        write_manifest_atomic(manifest_path, manifest)
        rc = cmd_verify(manifest_path, root)
        if rc != 0:
            return rc
        print("Updated upstream.json locally. Review 'git diff' and run 'just check' before committing.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Manage commit-SHA and SHA-256 pinned upstream skills/rules."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd_name in ("verify", "sync", "bump"):
        sp = sub.add_parser(cmd_name)
        sp.add_argument(
            "--manifest",
            type=Path,
            default=default_root / "upstream.json",
            help="Path to upstream.json manifest",
        )
        sp.add_argument(
            "--root",
            type=Path,
            default=default_root,
            help="Repository root directory",
        )
        if cmd_name in ("sync", "bump"):
            sp.add_argument("sources", nargs="*", help="Optional source names to target")
        if cmd_name == "sync":
            sp.add_argument(
                "--write-lock",
                action="store_true",
                help="Record fetched file hashes into upstream.json",
            )
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            return cmd_verify(args.manifest, args.root)
        if args.command == "sync":
            return cmd_sync(args.manifest, args.root, args.sources, write_lock=args.write_lock)
        if args.command == "bump":
            return cmd_bump(args.manifest, args.root, args.sources)
    except UpstreamError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
