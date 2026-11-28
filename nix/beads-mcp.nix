{
  lib,
  fetchurl,
  python3Packages,
  beads,
}:
let
  fastmcp1 = python3Packages.fastmcp.override {
    fastmcp-slim = python3Packages.fastmcp-slim.override {
      mcp = python3Packages.mcp_1;
    };
  };
in
python3Packages.buildPythonApplication rec {
  pname = "beads-mcp";
  version = "1.3.4";
  format = "wheel";

  src = fetchurl {
    url = "https://files.pythonhosted.org/packages/9b/6e/9dd996052d510380a4362a081668686b73525ef70cee48b601fa0205a72b/beads_mcp-${version}-py3-none-any.whl";
    sha256 = "f3ccbe66eedd32d288ee4f96f8ac4e1304e74b1fe76c5ba58f68b14c481cd739";
  };

  pythonRelaxDeps = [
    "fastmcp"
    "pydantic"
    "pydantic-settings"
  ];

  dependencies = with python3Packages; [
    fastmcp1
    pydantic
    pydantic-settings
  ];

  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    (lib.makeBinPath [ beads ])
  ];

  # Wheel does not bundle upstream test suite.
  doCheck = false;

  meta = {
    description = "MCP server for the beads (bd) issue tracker";
    homepage = "https://github.com/gastownhall/beads";
    license = lib.licenses.mit;
    mainProgram = "beads-mcp";
  };
}
