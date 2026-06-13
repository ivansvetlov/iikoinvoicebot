#!/usr/bin/env python3
"""Legacy entrypoint — delegates to mcp_bridge.run_stdio_server()."""

from mcp_bridge import run_stdio_server

if __name__ == "__main__":
    run_stdio_server()
