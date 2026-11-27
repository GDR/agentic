{
  lib,
  fetchurl,
  python3Packages,
}:
python3Packages.buildPythonApplication rec {
  pname = "ghidra-mcp-bridge";
  version = "7.1.0";
  format = "wheel";

  src = fetchurl {
    url = "https://github.com/bethington/ghidra-mcp/releases/download/v${version}/ghidra_mcp_bridge-${version}-py3-none-any.whl";
    hash = "sha256-y+7o4DmDj22F8ukZOSN2XWt7/rcduKNdF2N3EZhCSGs=";
  };

  dependencies = with python3Packages; [
    mcp_1
    pydantic
  ];

  # Wheel does not bundle upstream test suite.
  doCheck = false;

  meta = {
    description = "MCP-to-HTTP bridge for bethington/ghidra-mcp";
    homepage = "https://github.com/bethington/ghidra-mcp";
    license = lib.licenses.asl20;
    mainProgram = "bridge-mcp-ghidra";
  };
}
