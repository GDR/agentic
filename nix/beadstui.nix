{
  lib,
  buildGoModule,
  fetchFromGitHub,
}:
buildGoModule rec {
  pname = "beadstui";
  version = "0.1.2";

  src = fetchFromGitHub {
    owner = "seanmartinsmith";
    repo = "beadstui";
    tag = "v${version}";
    hash = "sha256-7FXyBhvVS/qEfL8C4NsyLPnAKrA1ofbFf8V/Nxz4vCg=";
  };

  vendorHash = null;

  subPackages = [ "cmd/bt" ];

  ldflags = [
    "-s"
    "-w"
    "-X github.com/seanmartinsmith/beadstui/pkg/version.version=v${version}"
  ];

  # Upstream tests require live/fixture terminal environments outside the Nix sandbox.
  doCheck = false;

  meta = {
    description = "Graph-aware task management TUI for Beads projects";
    homepage = "https://github.com/seanmartinsmith/beadstui";
    license = {
      fullName = "MIT License (with OpenAI/Anthropic Rider)";
    };
    mainProgram = "bt";
  };
}
