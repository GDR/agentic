#!/usr/bin/env python3
"""Validate Agent Skills (agentskills.io) structure, YAML frontmatter, and relative links."""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TOP_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")
# Match markdown links not preceded by '!' (images) or wait - images could also be relative assets,
# so validating both [label](target) and ![alt](target) outside code blocks is helpful.
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _unquote(val: str) -> str:
    if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
        return val[1:-1]
    return val


def _fold_lines(lines: list[str]) -> str:
    """Join YAML folded scalar lines while preserving blank-line paragraph breaks."""
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line == "":
            if current:
                paragraphs.append(current)
                current = []
            else:
                paragraphs.append([])
        else:
            current.append(line)
    if current:
        paragraphs.append(current)
    return "\n".join(" ".join(p) for p in paragraphs)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter delimited by --- lines, including block scalars (> / |)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Missing opening '---' YAML frontmatter delimiter on line 1")

    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx is None:
        raise ValueError("Missing closing '---' YAML frontmatter delimiter")

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :])

    data: dict[str, str] = {}
    i = 0
    while i < len(fm_lines):
        raw = fm_lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        # Ignore unexpected indented lines outside an active block
        if raw[0].isspace():
            i += 1
            continue

        m = TOP_KEY_RE.match(raw)
        if not m:
            raise ValueError(f"Malformed frontmatter line {i + 2}: {raw!r}")

        key, rest = m.group(1), m.group(2).strip()
        if rest in (">", ">-", "|", "|-"):
            style = rest[0]
            block_lines: list[str] = []
            indent: int | None = None
            i += 1
            while i < len(fm_lines):
                blk = fm_lines[i]
                if blk.strip() == "":
                    block_lines.append("")
                    i += 1
                    continue
                leading = len(blk) - len(blk.lstrip(" "))
                if leading == 0:
                    break
                if indent is None:
                    indent = leading
                block_lines.append(blk[min(indent, leading) :] if leading >= indent else blk.lstrip(" "))
                i += 1
            # Trim leading/trailing empty lines from block scalar
            while block_lines and block_lines[-1] == "":
                block_lines.pop()
            if style == ">":
                data[key] = _fold_lines(block_lines).strip()
            else:
                data[key] = "\n".join(block_lines).strip()
            continue

        if rest == "":
            # Nested mapping or list (e.g., metadata:); consume indented lines cleanly
            i += 1
            nested_lines: list[str] = []
            while i < len(fm_lines):
                nxt = fm_lines[i]
                if nxt.strip() == "" or nxt[0].isspace() or nxt.lstrip().startswith("-"):
                    nested_lines.append(nxt)
                    i += 1
                else:
                    break
            data[key] = "\n".join(nested_lines).strip()
            continue

        data[key] = _unquote(rest)
        i += 1

    return data, body


def extract_markdown_links(body: str) -> list[tuple[int, str]]:
    """Extract markdown link targets outside fenced code blocks and inline code."""
    results: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    for lineno, line in enumerate(body.splitlines(), start=1):
        fm = FENCE_RE.match(line)
        if fm:
            marker = fm.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_char = marker
            elif marker == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue

        cleaned = INLINE_CODE_RE.sub("", line)
        for match in LINK_RE.finditer(cleaned):
            raw_target = match.group(1).strip()
            if not raw_target:
                continue
            if raw_target.startswith("<") and ">" in raw_target:
                target = raw_target[1 : raw_target.index(">")].strip()
            else:
                # Strip optional markdown link title: path/to/file.md "title"
                target = raw_target.split(None, 1)[0]
            results.append((lineno, target))
    return results


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"]

    try:
        text = skill_md.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
    except Exception as exc:  # noqa: BLE001
        return [f"{skill_dir.name}/SKILL.md: {exc}"]

    name = fm.get("name", "").strip()
    if not name:
        errors.append(f"{skill_dir.name}/SKILL.md: missing required 'name' field")
    else:
        if name != skill_dir.name:
            errors.append(
                f"{skill_dir.name}/SKILL.md: frontmatter name '{name}' does not match folder name '{skill_dir.name}'"
            )
        if not (1 <= len(name) <= 64) or not NAME_RE.match(name):
            errors.append(
                f"{skill_dir.name}/SKILL.md: name '{name}' must be 1-64 chars matching ^[a-z0-9]+(-[a-z0-9]+)*$"
            )

    desc = fm.get("description", "").strip()
    if not desc:
        errors.append(f"{skill_dir.name}/SKILL.md: missing required 'description' field")
    elif len(desc) > 1024:
        errors.append(
            f"{skill_dir.name}/SKILL.md: description exceeds 1024 chars ({len(desc)} chars)"
        )

    skill_root = skill_dir.resolve()
    for _, target in extract_markdown_links(body):
        if target.startswith("#") or target.startswith("/") or SCHEME_RE.match(target):
            continue
        rel_path = target.split("#", 1)[0].split("?", 1)[0]
        if not rel_path:
            continue
        resolved = (skill_dir / rel_path).resolve()
        try:
            resolved.relative_to(skill_root)
        except ValueError:
            errors.append(
                f"{skill_dir.name}/SKILL.md: relative link '{target}' escapes skill directory"
            )
            continue
        if not resolved.exists():
            errors.append(
                f"{skill_dir.name}/SKILL.md: broken relative link '{target}'"
            )

    return errors


def main(argv: list[str]) -> int:
    if len(argv) > 2:
        print("Usage: validate.py [skills_dir]", file=sys.stderr)
        return 2

    skills_dir = (
        Path(argv[1])
        if len(argv) == 2
        else Path(__file__).resolve().parent.parent / "skills"
    )
    if not skills_dir.is_dir():
        print(f"Skills directory not found: {skills_dir}", file=sys.stderr)
        return 1

    skill_dirs = sorted(
        p for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    if not skill_dirs:
        print(f"No skills found under {skills_dir}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    for skill_dir in skill_dirs:
        all_errors.extend(validate_skill(skill_dir))

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    names = ", ".join(d.name for d in skill_dirs)
    print(f"Validated {len(skill_dirs)} skills: {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
