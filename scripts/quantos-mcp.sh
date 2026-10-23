#!/bin/sh
# Start the QuantOS MCP server (stdio) on the VM; Claude Code runs this over SSH.
cd /home/ubuntu/quantos && exec .venv/bin/python -u mcp_server/quantos_mcp.py
