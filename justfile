[doc('List available recipes')]
default:
	@just --list

[doc('Validate all SKILL.md manifests and relative links')]
validate:
	python3 scripts/validate.py

[doc('Verify vendored upstream files match upstream.json hashes (offline)')]
verify-upstream:
	python3 scripts/upstream.py verify

[doc('Run hook script unit tests')]
test-hooks:
	python3 -B -m unittest discover -s hooks -p 'test_*.py' -v

[doc('Fetch pinned upstream sources and verify recorded hashes')]
[positional-arguments]
sync-upstream *names:
	python3 scripts/upstream.py sync "$@"

[doc('Bump pinned upstream SHAs to latest HEAD (review git diff before committing)')]
[positional-arguments]
bump-upstream *names:
	python3 scripts/upstream.py bump "$@"

[doc('Run skill validation, upstream verification, hook tests, and Nix flake checks')]
check: validate verify-upstream test-hooks
	nix flake check

[doc('Scaffold a new skill under skills/<name> or skills/<category>/<name>')]
[positional-arguments]
new name:
	@python3 -c 'import pathlib, re, sys; raw = sys.argv[1].strip("/"); parts = raw.split("/"); \
		assert 1 <= len(parts) <= 2, "Use <name> or <category>/<name>"; \
		assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", p) and len(p) <= 64 for p in parts), "Invalid skill path"; \
		d = pathlib.Path("skills").joinpath(*parts); \
		leaf = parts[-1]; \
		assert not d.exists(), f"Skill already exists: {d}"; \
		d.mkdir(parents=True); \
		(d / "SKILL.md").write_text(f"---\nname: {leaf}\ndescription: >-\n  Describe what {leaf} does and when the agent should activate it.\n---\n\n# {leaf}\n\nInstructions here.\n", encoding="utf-8"); \
		print(f"Created {d}/SKILL.md")' "$1"

[doc('Format Nix files')]
fmt:
	nix fmt
