"""MOX API Vault: every API key in one private place."""
import json
import os
import re
import shlex

from .common import USER_DIR, write_private

STORE = USER_DIR / "api-keys.json"
ENV_FILE = USER_DIR / "api.env"
NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def _save(data):
    write_private(STORE, json.dumps(data, indent=2))
    write_private(ENV_FILE, "".join(f"export {key}={shlex.quote(value)}\n" for key, value in sorted(data.items())))


def add(name, value):
    name = name.upper().replace("-", "_")
    if not NAME.match(name):
        raise ValueError("Use a name like OPENAI_API_KEY.")
    data = load()
    data[name] = value
    _save(data)
    return name


def remove(name):
    data = load()
    existed = data.pop(name.upper(), None) is not None
    _save(data)
    return existed


def get(name):
    return os.environ.get(name) or load().get(name, "")


def masked():
    return {key: (value[:4] + "…" + value[-2:] if len(value) > 8 else "set") for key, value in sorted(load().items())}
