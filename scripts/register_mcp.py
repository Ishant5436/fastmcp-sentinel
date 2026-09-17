#!/usr/bin/env python3
"""Universal 6-Target FastMCP-Sentinel Registration Script."""

import os
import json
import asyncio
from pathlib import Path
from fastmcp_sentinel.server import mcp

SERVER_NAME = "fastmcp-sentinel"
SERVER_CONFIG = {
    "command": "/Users/ishantpanchal/fastmcp-sentinel/venv/bin/python",
    "args": ["-m", "fastmcp_sentinel.cli", "serve"],
    "env": {
        "PYTHONPATH": "/Users/ishantpanchal/fastmcp-sentinel/src"
    }
}

CONFIG_FILES = [
    os.path.expanduser("~/.gemini/antigravity/mcp_config.json"),
    os.path.expanduser("~/.gemini/config/mcp_config.json"),
    os.path.expanduser("~/.gemini/antigravity-ide/mcp_config.json"),
    os.path.expanduser("~/.gemini/antigravity-cli/mcp_config.json"),
    os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json"),
    os.path.expanduser("~/.claude.json"),
]

SCHEMA_DIR = Path(os.path.expanduser("~/.gemini/antigravity-cli/mcp")) / SERVER_NAME


async def register():
    print("=" * 70)
    print("  REGISTERING FASTMCP-SENTINEL ACROSS 6 MCP TARGETS")
    print("=" * 70)

    # 1. Update all 6 JSON config files
    for path_str in CONFIG_FILES:
        path = Path(path_str)
        if not path.exists():
            print(f"  [WARN] Skipping non-existent path: {path}")
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "mcpServers" not in data:
                data["mcpServers"] = {}

            data["mcpServers"][SERVER_NAME] = SERVER_CONFIG

            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            print(f"  [PASS] Registered in: {path}")
        except Exception as e:
            print(f"  [FAIL] Failed to update {path}: {e}")

    # 2. Write tool JSON schemas and instructions.md
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    tools = await mcp.list_tools()

    for t in tools:
        tool_file = SCHEMA_DIR / f"{t.name}.json"
        tool_schema = {
            "name": t.name,
            "description": t.description.strip(),
            "parameters": t.inputSchema,
        }
        with open(tool_file, "w", encoding="utf-8") as f:
            json.dump(tool_schema, f, indent=2)
        print(f"  [PASS] Tool Schema Generated: {tool_file.name}")

    instructions_file = SCHEMA_DIR / "instructions.md"
    with open(instructions_file, "w", encoding="utf-8") as f:
        f.write("""# FastMCP-Sentinel MCP Instructions
Always call `sentinel_validate_calldata` and `sentinel_simulate_transaction` before authorizing any Web3 transaction or executing onchain state changes.
Use `sentinel_rpc_cache` to retrieve static network parameters (chainId, gasPrice, blockNumber).
Enforce budget safety with `sentinel_agent_guard`.
Verify C++ safety guarantees with `sentinel_audit_invariants`.
""")
    print(f"  [PASS] Instructions Generated: {instructions_file.name}")

    print("-" * 70)
    print("  6-TARGET REGISTRATION COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(register())
