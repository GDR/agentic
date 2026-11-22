[doc('List available recipes')]
default:
	@just --list

[doc('Validate all SKILL.md manifests and relative links')]
validate:
	python3 scripts/validate.py

[doc('Verify vendored upstream files match upstream.json hashes (offline)')]
verify-upstream:
	python3 scripts/upstream.py verify

[doc('Fetch pinned upstream sources and verify recorded hashes')]
[positional-arguments]
sync-upstream *names:
	python3 scripts/upstream.py sync "$@"

[doc('Bump pinned upstream SHAs to latest HEAD (review git diff before committing)')]
[positional-arguments]
bump-upstream *names:
	python3 scripts/upstream.py bump "$@"

[doc('Run skill validation, upstream integrity verification, and Nix flake checks')]
check: validate verify-upstream
	nix flake check

[doc('Scaffold a new skill under skills/<name>')]
[positional-arguments]
new name:
	@python3 -c 'import pathlib, re, sys; name = sys.argv[1]; \
		assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) and len(name) <= 64, "Invalid skill name"; \
		d = pathlib.Path("skills") / name; \
		assert not d.exists(), f"Skill already exists: {d}"; \
		d.mkdir(parents=True); \
		(d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: >-\n  Describe what {name} does and when the agent should activate it.\n---\n\n# {name}\n\nInstructions here.\n", encoding="utf-8"); \
		print(f"Created {d}/SKILL.md")' "$1"

[doc('Format Nix files')]
fmt:
	nix fmt
