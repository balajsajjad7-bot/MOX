"""MOX Connectors: one list of MCP servers shared by every AI tool on the system."""
import json

from .common import USER_DIR, write_private

FILE = USER_DIR / "mcp.json"


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
