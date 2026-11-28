{
  lib,
  fetchFromGitHub,
  python3Packages,
}:
python3Packages.buildPythonApplication rec {
  pname = "renderdoc-mcp";
  version = "0.2.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "Linkingooo";
    repo = "renderdoc-mcp";
    rev = "4911c47b78df2a5b2967a98bef827e7ccda6cac4";
    hash = "sha256-JRcSnU7k5QsNF8l8XpO8Y6QlLfqPiBayQGg13nVSI8w=";
  };

  build-system = [ python3Packages.hatchling ];

  dependencies = with python3Packages; [
    mcp_1
  ];

  # Upstream tests require a live RenderDoc replay environment.
  doCheck = false;

  meta = {
    description = "MCP server for RenderDoc graphics debugger frame capture analysis";
    homepage = "https://github.com/Linkingooo/renderdoc-mcp";
    license = lib.licenses.mit;
    mainProgram = "renderdoc-mcp";
  };
}
