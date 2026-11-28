{
  description = "Shared cross-tool Agent Skills repository (agentskills.io)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      pkgsFor = system: import nixpkgs { inherit system; };
      mcpLib = import ./nix/mcp.nix { lib = nixpkgs.lib; };
      beadsLib = import ./nix/beads.nix { lib = nixpkgs.lib; };
      layout = import ./nix/layout.nix { lib = nixpkgs.lib; };
      agenticLib =
        mcpLib
        // beadsLib
        // {
          inherit layout;
        };
    in
    {
      lib = agenticLib;

      homeManagerModules = {
        default = ./nix/home-manager.nix;
        agentic = ./nix/home-manager.nix;
      };

      formatter = forAllSystems (system: (pkgsFor system).nixfmt-tree);

      packages = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          skills = pkgs.runCommand "agentic-skills" { } ''
            mkdir -p "$out"
            cp -a ${./skills}/. "$out/"
          '';
          rea = pkgs.callPackage ./nix/rea.nix { };
          ghidra-mcp-extension = pkgs.callPackage ./nix/ghidra-mcp-extension.nix { };
          ghidra-mcp-bridge = pkgs.callPackage ./nix/ghidra-mcp-bridge.nix { };
          ghidra-mcp = pkgs.ghidra.withExtensions (_: [
            (pkgs.callPackage ./nix/ghidra-mcp-extension.nix { })
          ]);
          bd-board = pkgs.callPackage ./nix/bd-board.nix { };
          beads-mcp = pkgs.callPackage ./nix/beads-mcp.nix { };
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          validate-skills =
            pkgs.runCommand "validate-skills"
              {
                nativeBuildInputs = [ pkgs.python3 ];
              }
              ''
                python3 ${./.}/scripts/validate.py ${./.}/skills
                touch "$out"
              '';

          verify-upstream =
            pkgs.runCommand "verify-upstream"
              {
                nativeBuildInputs = [ pkgs.python3 ];
              }
              ''
                python3 ${./.}/scripts/upstream.py verify --manifest ${./.}/upstream.json --root ${./.}
                touch "$out"
              '';

          test-hooks =
            pkgs.runCommand "test-hooks"
              {
                nativeBuildInputs = [ pkgs.python3 ];
              }
              ''
                python3 -B -m unittest discover -s ${./.}/hooks -p 'test_*.py' -v
                touch "$out"
              '';

          test-mcp =
            pkgs.runCommand "test-mcp"
              {
                nativeBuildInputs = [ pkgs.python3 ];
              }
              ''
                python3 -B -m unittest discover -s ${./.}/mcp -p 'test_*.py' -v
                python3 -B ${./.}/mcp/sync.py --validate-global ${./.}/mcp/global.json
                touch "$out"
              '';

          test-beads =
            pkgs.runCommand "test-beads"
              {
                nativeBuildInputs = [
                  pkgs.python3
                  pkgs.git
                ];
              }
              ''
                python3 -B -m unittest discover -s ${./.}/beads -p 'test_*.py' -v
                touch "$out"
              '';

          test-home-manager =
            let
              hmLib = nixpkgs.lib.extend (
                _: _: {
                  hm.dag.entryAfter = after: data: { inherit after data; };
                }
              );
              stubModule =
                { lib, ... }:
                {
                  options.home = {
                    homeDirectory = lib.mkOption {
                      type = lib.types.str;
                      default = "/home/tester";
                    };
                    file = lib.mkOption {
                      type = lib.types.attrsOf (
                        lib.types.submodule {
                          options.text = lib.mkOption {
                            type = lib.types.str;
                          };
                        }
                      );
                      default = { };
                    };
                    activation = lib.mkOption {
                      type = lib.types.attrsOf lib.types.anything;
                      default = { };
                    };
                  };
                };
              evalHm =
                extraModules:
                (hmLib.evalModules {
                  specialArgs = { inherit pkgs; };
                  modules = [
                    stubModule
                    ./nix/home-manager.nix
                  ]
                  ++ extraModules;
                }).config;
              disabledCfg = evalHm [ ];
              defaultCfg = evalHm [
                { programs.agentic.enable = true; }
              ];
              absCfg = evalHm [
                {
                  programs.agentic = {
                    enable = true;
                    repoPath = "/srv/agentic";
                  };
                }
              ];
              tildeCfg = evalHm [
                {
                  programs.agentic = {
                    enable = true;
                    repoPath = "~/custom/agentic";
                  };
                }
              ];
              defaultHooksJson = builtins.fromJSON (
                builtins.unsafeDiscardStringContext defaultCfg.home.file.".gemini/config/hooks.json".text
              );
              defaultGateCmd =
                (builtins.head (builtins.head defaultHooksJson.commit-skill-gate.PreToolUse).hooks).command;
              defaultHooksFile =
                pkgs.writeText "agentic-default-hooks.json"
                  defaultCfg.home.file.".gemini/config/hooks.json".text;
              absHooksFile =
                pkgs.writeText "agentic-abs-hooks.json"
                  absCfg.home.file.".gemini/config/hooks.json".text;
            in
            assert
              layout.skillCategories == [
                "beads"
                "design"
                "git"
                "security"
              ];
            assert
              layout.watchSubpaths == [
                "rules"
                "skills"
                "skills/beads"
                "skills/design"
                "skills/git"
                "skills/security"
              ];
            assert (builtins.head layout.fanout).recursive == true;
            assert builtins.length layout.links == 5;
            assert disabledCfg.home.file == { };
            assert disabledCfg.home.activation == { };
            assert
              builtins.fromJSON defaultCfg.home.file.".gemini/config/skills.json".text == {
                entries = [
                  { path = "/home/tester/Workspaces/gdr/agentic/skills/beads"; }
                  { path = "/home/tester/Workspaces/gdr/agentic/skills/design"; }
                  { path = "/home/tester/Workspaces/gdr/agentic/skills/git"; }
                  { path = "/home/tester/Workspaces/gdr/agentic/skills/security"; }
                ];
              };
            assert
              builtins.fromJSON absCfg.home.file.".gemini/config/skills.json".text == {
                entries = [
                  { path = "/srv/agentic/skills/beads"; }
                  { path = "/srv/agentic/skills/design"; }
                  { path = "/srv/agentic/skills/git"; }
                  { path = "/srv/agentic/skills/security"; }
                ];
              };
            assert
              builtins.fromJSON tildeCfg.home.file.".gemini/config/skills.json".text == {
                entries = [
                  { path = "/home/tester/custom/agentic/skills/beads"; }
                  { path = "/home/tester/custom/agentic/skills/design"; }
                  { path = "/home/tester/custom/agentic/skills/git"; }
                  { path = "/home/tester/custom/agentic/skills/security"; }
                ];
              };
            assert (builtins.head defaultHooksJson.commit-skill-gate.PreToolUse).matcher == "run_command";
            assert nixpkgs.lib.hasInfix "agentic-commit-skill-gate-antigravity" defaultGateCmd;
            assert defaultCfg.home.activation.agenticClaudeHooks.after == [ "writeBoundary" ];
            pkgs.runCommand "test-home-manager"
              {
                nativeBuildInputs = [ pkgs.python3 ];
              }
              ''
                python3 - "${defaultHooksFile}" "${absHooksFile}" ${nixpkgs.lib.escapeShellArg defaultCfg.home.activation.agenticClaudeHooks.data} << 'EOF'
                import json, re, subprocess, sys, tempfile
                from pathlib import Path

                default_hooks = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
                abs_hooks = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
                act_data = sys.argv[3]

                default_gate_cmd = default_hooks["commit-skill-gate"]["PreToolUse"][0]["hooks"][0]["command"]
                abs_gate_cmd = abs_hooks["commit-skill-gate"]["PreToolUse"][0]["hooks"][0]["command"]

                abs_text = Path(abs_gate_cmd).read_text(encoding="utf-8")
                assert "/srv/agentic/hooks/commit_skill_gate.py" in abs_text, abs_text

                res = subprocess.run([default_gate_cmd], input="{}", text=True, capture_output=True, check=True)
                assert json.loads(res.stdout) == {"decision": "allow"}, res.stdout

                merge_match = re.search(r"(/nix/store/[0-9a-z]+-(?:source/hooks/)?merge_claude_hooks\.py)", act_data)
                assert merge_match, act_data
                merge_script = merge_match.group(1)

                gate_match = re.search(r"(/nix/store/[0-9a-z]+-agentic-commit-skill-gate-claude)", act_data)
                assert gate_match, act_data
                claude_gate = gate_match.group(1)

                with tempfile.TemporaryDirectory() as tmpdir:
                    settings = Path(tmpdir) / ".claude" / "settings.json"
                    settings.parent.mkdir(parents=True)
                    settings.write_text(json.dumps({
                        "permissions": {"deny": ["Bash(git push*)"]},
                        "hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "/bin/true"}]}]},
                    }), encoding="utf-8")
                    subprocess.run(["python3", "-B", merge_script, str(settings), claude_gate], check=True)
                    merged = json.loads(settings.read_text(encoding="utf-8"))
                    assert merged["permissions"] == {"deny": ["Bash(git push*)"]}, merged
                    assert len(merged["hooks"]["PreToolUse"]) == 2, merged
                    assert merged["hooks"]["PreToolUse"][1]["hooks"][0]["command"] == claude_gate, merged
                    subprocess.run(["python3", "-B", merge_script, str(settings), claude_gate], check=True)
                    assert json.loads(settings.read_text(encoding="utf-8")) == merged
                EOF
                touch "$out"
              '';
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
          mcp = agenticLib.mkMcp {
            inherit pkgs;
            servers = {
              nixos = agenticLib.mcp.nixos { inherit pkgs; };
            };
          };
        in
        {
          default = pkgs.mkShell {
            packages =
              (with pkgs; [
                python3
                just
                nixfmt
              ])
              ++ mcp.packages;
            shellHook = mcp.shellHook;
          };
        }
      );
    };
}
