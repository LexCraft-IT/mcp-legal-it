"""Console entry point (`mcp-legal-it`)."""
from __future__ import annotations

import argparse
import os
import sys

# FastMCP asks PyPI for a newer release every time it prints its startup
# banner. This server contacts only the hosts listed in mcp_legal_it/lib/_egress.py, so
# the check is off unless the operator turns it back on. It has to be set
# before fastmcp is imported: its settings are read once, at import time.
os.environ.setdefault("FASTMCP_CHECK_FOR_UPDATES", "off")

from mcp_legal_it._profilo import ProfiloSconosciuto  # noqa: E402
from mcp_legal_it.cli_version import package_version  # noqa: E402  re-export
from mcp_legal_it import _update_check  # noqa: E402

try:
    from mcp_legal_it.server import mcp  # noqa: E402  (module-level for patching in tests)
except ProfiloSconosciuto as exc:  # an unknown LEGAL_PROFILE: a message, not a traceback
    sys.exit(f"mcp-legal-it: {exc}")

__all__ = ["main", "package_version", "mcp"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-legal-it", description="MCP server for Italian legal tools.")
    parser.add_argument(
        "--version", action="version", version=package_version(),
        help="show the package version and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Start the MCP server; transport and bind address come from the environment.

    MCP_TRANSPORT: stdio (default) | http | sse
    MCP_HOST / MCP_PORT / MCP_PATH: used by http and sse
    LEGAL_PROFILE: tool profile, read by mcp_legal_it.server at import time
    LEGAL_UPDATE_CHECK: on for the daily new-version notice (the .mcpb sets it), off by default
    """
    _build_parser().parse_args(argv)
    # Before run: the notice goes in the instructions a client reads at initialize
    # and on stderr, never in a tool answer (LI-045, LI-096).
    _update_check.apply(mcp, package_version())
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    path = os.environ.get("MCP_PATH", "/mcp")
    if transport == "http":
        mcp.run(transport="http", host=host, port=port, path=path)
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
