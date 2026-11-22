#!/usr/bin/env python3
"""Validate Agent Skills (agentskills.io) structure, YAML frontmatter, and relative links."""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"\A[a-z0-9]+(-[a-z0-9]+)*\Z")
TOP_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")
FRONTMATTER_DELIM_RE = re.compile(r"^---[ \t]*$")
BLOCK_HEADER_RE = re.compile(r"^([>|])(?:([+-])([1-9])?|([1-9])([+-])?)?$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
ASCII_PUNCT_ESCAPE_RE = re.compile(r'\\([!"#$%&\'()*+,\-./:;<=>?@[\\\]^_`{|}~])')


def _strip_inline_comment(val: str) -> str:
    """Strip YAML inline '# ...' comments outside quotes."""
    in_single = False
    in_double = False
    idx = 0
    n = len(val)
    while idx < n:
        ch = val[idx]
        if in_double:
            if ch == "\\" and idx + 1 < n:
                idx += 2
                continue
            if ch == '"':
                in_double = False
        elif in_single:
            if ch == "'":
                if idx + 1 < n and val[idx + 1] == "'":
                    idx += 2
                    continue
                in_single = False
        else:
            if ch == '"':
                in_double = True
            elif ch == "'":
                in_single = True
            elif ch == "#" and (idx == 0 or val[idx - 1].isspace()):
                return val[:idx].strip()
        idx += 1
    return val.strip()


def _parse_quoted_scalar(
    first_line_rest: str, fm_lines: list[str], start_idx: int
) -> tuple[str, int]:
    """Parse a single- or multi-line YAML quoted scalar and return (value, next_index)."""
    quote = first_line_rest[0]
    collected_lines = [first_line_rest]
    idx = start_idx

    def _try_finish(text: str) -> tuple[bool, str]:
        out: list[str] = []
        pos = 1
        n = len(text)
        while pos < n:
            ch = text[pos]
            if quote == '"':
                if ch == "\\":
                    if pos + 1 >= n:
                        return False, ""
                    nxt = text[pos + 1]
                    escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}
                    out.append(escapes.get(nxt, nxt))
                    pos += 2
                    continue
                if ch == '"':
                    trailing = text[pos + 1 :].strip()
                    if trailing and not trailing.startswith("#"):
                        raise ValueError(f"Unexpected trailing characters after quoted value: {trailing!r}")
                    return True, "".join(out)
                out.append(ch)
                pos += 1
            else:
                if ch == "'":
                    if pos + 1 < n and text[pos + 1] == "'":
                        out.append("'")
                        pos += 2
                        continue
                    trailing = text[pos + 1 :].strip()
                    if trailing and not trailing.startswith("#"):
                        raise ValueError(f"Unexpected trailing characters after quoted value: {trailing!r}")
                    return True, "".join(out)
                out.append(ch)
                pos += 1
        return False, ""

    done, parsed = _try_finish(first_line_rest)
    if done:
        return parsed, idx + 1

    # Multi-line quoted scalar: fold indented continuation lines
    j = idx + 1
    while j < len(fm_lines):
        nxt_line = fm_lines[j]
        if nxt_line.strip() == "":
            collected_lines.append("")
            j += 1
            continue
        if not nxt_line[0].isspace():
            break
        collected_lines.append(nxt_line.strip())
        joined = _fold_lines(collected_lines)
        done, parsed = _try_finish(joined)
        if done:
            return parsed, j + 1
        j += 1

    raise ValueError(f"Unterminated {quote}-quoted scalar in frontmatter")


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
    """Parse YAML frontmatter delimited by --- lines, including block and multi-line scalars."""
    if text.startswith("\ufeff"):
        raise ValueError("Unexpected UTF-8 BOM; save SKILL.md as UTF-8 without BOM")

    lines = text.splitlines()
    if not lines or not FRONTMATTER_DELIM_RE.match(lines[0]):
        raise ValueError("Missing opening '---' YAML frontmatter delimiter on line 1")

    end_idx = None
    for idx in range(1, len(lines)):
        if FRONTMATTER_DELIM_RE.match(lines[idx]):
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

        if raw[0].isspace():
            raise ValueError(f"Unexpected indented frontmatter line {i + 2}: {raw!r}")

        m = TOP_KEY_RE.match(raw)
        if not m:
            raise ValueError(f"Malformed frontmatter line {i + 2}: {raw!r}")

        key, raw_rest = m.group(1), m.group(2).strip()
        if raw_rest.startswith(('"', "'")):
            val, i = _parse_quoted_scalar(raw_rest, fm_lines, i)
            data[key] = val
            continue

        rest = _strip_inline_comment(raw_rest)
        block_match = BLOCK_HEADER_RE.match(rest)
        if block_match:
            style = block_match.group(1)
            explicit_digit = block_match.group(3) or block_match.group(4)
            indent: int | None = int(explicit_digit) if explicit_digit else None
            block_lines: list[str] = []
            i += 1
            while i < len(fm_lines):
                blk = fm_lines[i]
                if blk.strip() == "":
                    block_lines.append("")
                    i += 1
                    continue
                leading = len(blk) - len(blk.lstrip(" "))
                if indent is not None:
                    if leading < indent:
                        break
                elif leading == 0:
                    break
                else:
                    indent = leading
                block_lines.append(blk[indent:] if leading >= indent else blk.lstrip(" "))
                i += 1
            # Trim trailing empty lines from block scalar
            while block_lines and block_lines[-1] == "":
                block_lines.pop()
            if style == ">":
                data[key] = _fold_lines(block_lines).strip()
            else:
                data[key] = "\n".join(block_lines).strip()
            continue
        if rest.startswith((">", "|")):
            raise ValueError(f"Invalid block scalar header on line {i + 2}: {rest!r}")

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

        # Plain scalar: fold any indented continuation lines per YAML plain scalar rules
        plain_lines = [rest]
        i += 1
        while i < len(fm_lines):
            nxt = fm_lines[i]
            if nxt.strip() == "":
                look = i + 1
                while look < len(fm_lines) and fm_lines[look].strip() == "":
                    look += 1
                if (
                    look < len(fm_lines)
                    and fm_lines[look][0].isspace()
                    and not fm_lines[look].lstrip().startswith("#")
                ):
                    plain_lines.append("")
                    i += 1
                    continue
                break
            if nxt.lstrip().startswith("#") or not nxt[0].isspace():
                break
            plain_lines.append(_strip_inline_comment(nxt.strip()))
            i += 1
        while plain_lines and plain_lines[-1] == "":
            plain_lines.pop()
        data[key] = _fold_lines(plain_lines).strip()

    return data, body


def _strip_inline_code(line: str) -> str:
    """Remove inline code spans (`...`, ``...``, etc.) of arbitrary backtick length."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        # Outside inline code, backslash escapes backticks/backslashes per CommonMark
        if line[i] == "\\" and i + 1 < n:
            out.append(line[i : i + 2])
            i += 2
            continue
        if line[i] != "`":
            out.append(line[i])
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        tick_len = j - i
        k = j
        found = -1
        while k < n:
            if line[k] == "`":
                m = k
                while m < n and line[m] == "`":
                    m += 1
                if (m - k) == tick_len:
                    found = m
                    break
                k = m
            else:
                k += 1
        if found != -1:
            i = found
        else:
            out.append(line[i:j])
            i = j
    return "".join(out)


def _unescape_link_target(target: str) -> str:
    """Unescape backslash-escaped ASCII punctuation in Markdown link destinations."""
    return ASCII_PUNCT_ESCAPE_RE.sub(r"\1", target)


def _extract_links_from_line(cleaned: str) -> list[str]:
    """Extract markdown link destinations supporting nested brackets, <...>, and balanced parens."""
    targets: list[str] = []
    i = 0
    n = len(cleaned)
    while i < n:
        if cleaned[i] != "[":
            i += 1
            continue
        j = i + 1
        bracket_depth = 1
        while j < n:
            if cleaned[j] == "\\" and j + 1 < n:
                j += 2
                continue
            if cleaned[j] == "[":
                bracket_depth += 1
            elif cleaned[j] == "]":
                bracket_depth -= 1
                if bracket_depth == 0:
                    break
            j += 1
        if j >= n or j + 1 >= n or cleaned[j + 1] != "(":
            i += 1
            continue

        pos = j + 2
        while pos < n and cleaned[pos].isspace():
            pos += 1
        if pos >= n:
            i += 1
            continue

        target = ""
        valid = False
        if cleaned[pos] == "<":
            end_angle = pos + 1
            while end_angle < n:
                if cleaned[end_angle] == "\\" and end_angle + 1 < n:
                    end_angle += 2
                    continue
                if cleaned[end_angle] == ">":
                    break
                end_angle += 1
            if end_angle < n and cleaned[end_angle] == ">":
                target = cleaned[pos + 1 : end_angle].strip()
                pos = end_angle + 1
                in_q = ""
                while pos < n:
                    ch = cleaned[pos]
                    if in_q:
                        if ch == "\\" and pos + 1 < n:
                            pos += 2
                            continue
                        if ch == in_q:
                            in_q = ""
                    else:
                        if ch in ('"', "'"):
                            in_q = ch
                        elif ch == ")":
                            valid = True
                            pos += 1
                            break
                    pos += 1
        else:
            start = pos
            depth = 0
            while pos < n:
                ch = cleaned[pos]
                if ch == "\\" and pos + 1 < n:
                    pos += 2
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    if depth == 0:
                        target = cleaned[start:pos].strip()
                        valid = True
                        pos += 1
                        break
                    depth -= 1
                elif ch.isspace():
                    target = cleaned[start:pos].strip()
                    in_q = ""
                    p_depth = depth
                    while pos < n:
                        c2 = cleaned[pos]
                        if in_q:
                            if c2 == "\\" and pos + 1 < n:
                                pos += 2
                                continue
                            if c2 == in_q:
                                in_q = ""
                        else:
                            if c2 in ('"', "'"):
                                in_q = c2
                            elif c2 == "(":
                                p_depth += 1
                            elif c2 == ")":
                                if p_depth == 0:
                                    valid = True
                                    pos += 1
                                    break
                                p_depth -= 1
                        pos += 1
                    break
                pos += 1

        if valid:
            label_inner = cleaned[i + 1 : j]
            if "[" in label_inner:
                targets.extend(_extract_links_from_line(label_inner))
            if target:
                targets.append(_unescape_link_target(target))
            i = pos
        else:
            i += 1
    return targets


def extract_markdown_links(body: str) -> list[tuple[int, str]]:
    """Extract markdown link targets outside fenced code blocks and inline code."""
    results: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for lineno, line in enumerate(body.splitlines(), start=1):
        fm = FENCE_RE.match(line)
        if fm:
            fence_seq, info = fm.group(1), fm.group(2)
            marker = fence_seq[0]
            if not in_fence:
                if not (marker == "`" and "`" in info):
                    in_fence = True
                    fence_char = marker
                    fence_len = len(fence_seq)
                    continue
            elif marker == fence_char and len(fence_seq) >= fence_len and not info.strip():
                in_fence = False
                fence_char = ""
                fence_len = 0
                continue
        if in_fence:
            continue

        cleaned = _strip_inline_code(line)
        for target in _extract_links_from_line(cleaned):
            results.append((lineno, target))
    return results


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if skill_md.is_symlink() and not skill_md.exists():
        return [f"{skill_dir.name}: SKILL.md is a broken symlink"]
    if not skill_md.is_file():
        return [f"{skill_dir.name}: missing SKILL.md"]

    try:
        skill_root = skill_dir.resolve(strict=True)
        skill_md_real = skill_md.resolve(strict=True)
    except OSError as exc:
        return [f"{skill_dir.name}/SKILL.md: cannot resolve path: {exc}"]

    if not skill_md_real.is_relative_to(skill_root):
        return [f"{skill_dir.name}/SKILL.md: symlink resolves outside skill directory"]

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

    for _, target in extract_markdown_links(body):
        if target.startswith("#") or SCHEME_RE.match(target):
            continue
        if target.startswith("/"):
            errors.append(
                f"{skill_dir.name}/SKILL.md: relative link '{target}' escapes skill directory"
            )
            continue
        rel_path = target.split("#", 1)[0].split("?", 1)[0]
        # Strip runtime {baseDir}/ placeholder used by portable skills so internal
        # references validate statically while still rejecting rooted/parent escapes.
        if rel_path.startswith("{baseDir}/"):
            rel_path = rel_path[len("{baseDir}/") :]
            if rel_path.startswith("/"):
                errors.append(
                    f"{skill_dir.name}/SKILL.md: relative link '{target}' escapes skill directory"
                )
                continue
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


def _check_entry_dir(p: Path, root: Path, label: str) -> tuple[bool, list[str]]:
    if p.is_symlink() and not p.exists():
        return False, [f"{label}: broken symlink in skills directory"]
    if not p.is_dir():
        return False, [f"{label}: unexpected non-directory entry in skills directory"]
    try:
        p_real = p.resolve(strict=True)
    except OSError as exc:
        return False, [f"{label}: cannot resolve directory: {exc}"]
    if not p_real.is_relative_to(root):
        return False, [f"{label}: directory symlink resolves outside skills directory"]
    return True, []


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

    skills_root = skills_dir.resolve(strict=True)
    skill_dirs: list[Path] = []
    all_errors: list[str] = []

    for p in sorted(skills_dir.iterdir(), key=lambda x: x.name):
        if p.name in (".gitkeep", ".DS_Store") or p.name.startswith("."):
            if p.is_symlink() and not p.exists():
                all_errors.append(f"{p.name}: broken symlink in skills directory")
            continue
        ok, errs = _check_entry_dir(p, skills_root, p.name)
        if not ok:
            all_errors.extend(errs)
            continue

        skill_marker = p / "SKILL.md"
        if skill_marker.exists() or skill_marker.is_symlink():
            skill_dirs.append(p)
            continue

        if not (1 <= len(p.name) <= 64) or not NAME_RE.match(p.name):
            all_errors.append(
                f"{p.name}: category directory must match ^[a-z0-9]+(-[a-z0-9]+)*$ (1-64 chars)"
            )
            continue

        for sub in sorted(p.iterdir(), key=lambda x: x.name):
            if sub.name in (".gitkeep", ".DS_Store") or sub.name.startswith("."):
                if sub.is_symlink() and not sub.exists():
                    all_errors.append(f"{p.name}/{sub.name}: broken symlink in category directory")
                continue
            label = f"{p.name}/{sub.name}"
            sub_ok, sub_errs = _check_entry_dir(sub, skills_root, label)
            if not sub_ok:
                all_errors.extend(sub_errs)
                continue
            if not sub.name.startswith(f"{p.name}-"):
                all_errors.append(
                    f"{label}: skill directory under category '{p.name}' must start with '{p.name}-'"
                )
            sub_marker = sub / "SKILL.md"
            if not (sub_marker.exists() or sub_marker.is_symlink()):
                all_errors.append(f"{label}: missing SKILL.md (max nesting is skills/<category>/<skill>)")
                continue
            skill_dirs.append(sub)

    if not skill_dirs and not all_errors:
        print(f"No skills found under {skills_dir}", file=sys.stderr)
        return 1

    seen_leaf: dict[str, Path] = {}
    for skill_dir in skill_dirs:
        prev = seen_leaf.get(skill_dir.name)
        if prev is not None:
            all_errors.append(
                f"duplicate skill name '{skill_dir.name}': "
                f"{prev.relative_to(skills_dir)} and {skill_dir.relative_to(skills_dir)}"
            )
        else:
            seen_leaf[skill_dir.name] = skill_dir
        all_errors.extend(validate_skill(skill_dir))

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    names = ", ".join(sorted(d.name for d in skill_dirs))
    print(f"Validated {len(skill_dirs)} skills: {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
