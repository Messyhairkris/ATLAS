"""Standalone entry for the Crew MCP server, for launchers that run a script
path from an arbitrary working directory (Crush's mcp_stdio_wrapper.py).
Equivalent to `python -m crew serve` from the repo root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crew.server import main  # noqa: E402

if __name__ == "__main__":
    main()
