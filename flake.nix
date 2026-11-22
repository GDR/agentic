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
    in
    {
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
                python3 ${./scripts/validate.py} ${./skills}
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
        }
      );

      devShells = forAllSystems (
        system:
        let
          pkgs = pkgsFor system;
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python3
              just
              nixfmt
            ];
          };
        }
      );
    };
}
