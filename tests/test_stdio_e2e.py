"""End-to-end: spawn `fastmcp-sentinel serve` and talk to it over MCP stdio."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import fastmcp_sentinel

# Run the server from wherever this process imported the package (source tree or installed wheel).
PKG_ROOT = str(Path(fastmcp_sentinel.__file__).resolve().parent.parent)


@pytest.mark.anyio
async def test_stdio_server_roundtrip():
    env = {**os.environ, "PYTHONPATH": PKG_ROOT, "SENTINEL_LOG_LEVEL": "WARNING"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "fastmcp_sentinel.cli", "serve"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        assert "authorize" in (init.instructions or "")

        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert tools["sentinel_validate_calldata"].annotations.readOnlyHint is True
        assert tools["sentinel_agent_guard"].inputSchema["properties"]["action"]["enum"]

        ok = await session.call_tool(
            "sentinel_validate_calldata",
            {"to_address": "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640", "calldata_hex": "0xa9059cbb"},
        )
        assert not ok.isError
        assert json.loads(ok.content[0].text)["function_selector"] == "0xa9059cbb"

        denied = await session.call_tool("sentinel_agent_guard", {"action": "reset"})
        assert denied.isError
        assert "disabled" in denied.content[0].text

        bad_action = await session.call_tool("sentinel_rpc_cache", {"action": "drop_all"})
        assert bad_action.isError
