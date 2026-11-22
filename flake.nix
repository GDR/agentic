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
      agenticLib = import ./nix/mcp.nix { lib = nixpkgs.lib; };
    in
    {
      lib = agenticLib;

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
