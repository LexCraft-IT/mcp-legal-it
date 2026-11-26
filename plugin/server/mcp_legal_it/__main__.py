"""Entry point: python -m mcp_legal_it"""

import sys

from mcp_legal_it._profilo import ProfiloSconosciuto

try:
    from mcp_legal_it.server import mcp
except ProfiloSconosciuto as exc:  # an unknown LEGAL_PROFILE: a message, not a traceback
    sys.exit(f"mcp-legal-it: {exc}")

from mcp_legal_it.cli_version import package_version  # noqa: E402
from mcp_legal_it import _update_check  # noqa: E402

# The daily new-version notice, as `cli.main` gives it (LEGAL_UPDATE_CHECK, off by default).
_update_check.apply(mcp, package_version())
mcp.run(transport="stdio")
