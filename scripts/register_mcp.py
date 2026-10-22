#!/usr/bin/env python3
"""Register FastMCP-Sentinel with locally installed MCP hosts.

Adds a ``fastmcp-sentinel`` entry to each existing host config file, pointing at
the Python interpreter running this script. Each file is backed up (``.bak``)
and rewritten atomically. Use ``--dry-run`` to preview.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

SERVER_NAME = "fastmcp-sentinel"
REPO_ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILES = [
    Path("~/.gemini/antigravity/mcp_config.json"),
    Path("~/.gemini/config/mcp_config.json"),
    Path("~/.gemini/antigravity-ide/mcp_config.json"),
    Path("~/.gemini/antigravity-cli/mcp_config.json"),
    Path("~/Library/Application Support/Claude/claude_desktop_config.json"),
    Path("~/.config/Claude/claude_desktop_config.json"),
    Path("~/.claude.json"),
]

SCHEMA_DIR = Path("~/.gemini/antigravity-cli/mcp").expanduser() / SERVER_NAME


def server_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {"command": sys.executable, "args": ["-m", "fastmcp_sentinel.cli", "serve"]}
    src = REPO_ROOT / "src"
    if (src / "fastmcp_sentinel").is_dir():
        cfg["env"] = {"PYTHONPATH": str(src)}
    return cfg


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


async def register(dry_run: bool) -> int:
    from fastmcp_sentinel.server import INSTRUCTIONS, mcp

    cfg = server_config()
    failures = 0
    for path in (p.expanduser() for p in CONFIG_FILES):
        if not path.exists():
            print(f"  [SKIP] {path} (not found)")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            data.setdefault("mcpServers", {})[SERVER_NAME] = cfg
            if dry_run:
                print(f"  [DRY ] would register in {path}")
                continue
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            atomic_write_json(path, data)
            print(f"  [PASS] Registered in {path}")
        except (OSError, ValueError) as e:
            failures += 1
            print(f"  [FAIL] {path}: {e}")

    if SCHEMA_DIR.parent.exists() and not dry_run:
        SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
        for t in await mcp.list_tools():
            schema = {"name": t.name, "description": (t.description or "").strip(), "parameters": t.inputSchema}
            (SCHEMA_DIR / f"{t.name}.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
        instructions = f"# FastMCP-Sentinel MCP Instructions\n\n{INSTRUCTIONS}"
        (SCHEMA_DIR / "instructions.md").write_text(instructions, encoding="utf-8")
        print(f"  [PASS] Tool schemas written to {SCHEMA_DIR}")

    print(json.dumps({"mcpServers": {SERVER_NAME: cfg}}, indent=2))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    return asyncio.run(register(parser.parse_args().dry_run))


if __name__ == "__main__":
    sys.exit(main())
