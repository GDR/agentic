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
          renderdoc-mcp = pkgs.callPackage ./nix/renderdoc-mcp.nix { };
        }
      );

      checks = forAllSystems (
        system:
        import ./nix/checks.nix {
          pkgs = pkgsFor system;
          lib = nixpkgs.lib;
          inherit layout;
          root = ./.;
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
