#!/bin/bash
set -e

# Register the MCP server with the Gemini CLI
echo "Registering MCP server at http://mcp-server:8000/sse..."
gemini mcp add arbitrage-engine http://mcp-server:8000/sse --type sse || echo "Registration failed or already installed."

# Start the application
echo "Starting Strategic Arbitrage Bot..."
exec python src/monitor.py
