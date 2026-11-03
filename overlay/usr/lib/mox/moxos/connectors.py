"""MOX Connectors: one list of MCP servers shared by every AI tool on the system."""
import json
import shutil
from pathlib import Path

from .common import USER_DIR, write_private

FILE = USER_DIR / "mcp.json"


# Connectors that need no account, key or sign-up.
STARTER = {
    "files": "npx -y @modelcontextprotocol/server-filesystem {documents}",
    "memory": "npx -y @modelcontextprotocol/server-memory",
    "thinking": "npx -y @modelcontextprotocol/server-sequential-thinking",
    "browser": "npx -y @playwright/mcp",
}
STARTER_PYTHON = {"fetch": "uvx mcp-server-fetch", "git": "uvx mcp-server-git", "time": "uvx mcp-server-time"}


def setup():
    """Add every no-account connector. Your own connectors stay as they are."""
    existing = load()["mcpServers"]
    wanted = dict(STARTER)
    if shutil.which("uvx"):
        wanted.update(STARTER_PYTHON)
    added = []
    documents = Path.home() / "Documents"
    documents.mkdir(exist_ok=True)
    for name, target in wanted.items():
        if name not in existing:
            add(name, target.format(documents=documents))
            added.append(name)
    return added


def load():
    return json.loads(FILE.read_text()) if FILE.exists() else {"mcpServers": {}}


def add(name, target, env=None):
    data = load()
    if target.startswith(("http://", "https://")):
        entry = {"type": "http", "url": target}
    else:
        parts = target.split()
        entry = {"command": parts[0], "args": parts[1:]}
    if env:
        entry["env"] = dict(pair.split("=", 1) for pair in env)
    data["mcpServers"][name] = entry
    write_private(FILE, json.dumps(data, indent=2))


def remove(name):
    data = load()
    existed = data["mcpServers"].pop(name, None) is not None
    write_private(FILE, json.dumps(data, indent=2))
    return existed
