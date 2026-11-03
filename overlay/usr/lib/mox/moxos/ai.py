"""MOX AI: one assistant across Claude, GPT and local models."""
import json
import os
import re
import subprocess
import urllib.error
import urllib.request

from . import hardware, vault
from .common import USER_DIR, confirm, have, write_private

ENV_NAMES = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
SETTINGS = USER_DIR / "ai.json"
DEFAULTS = {"provider": "auto", "anthropic_model": "claude-sonnet-5-5", "openai_model": "gpt-5", "ollama_model": "llama3.2"}
OLLAMA = "http://127.0.0.1:11434"
SYSTEM = (
    "You are MOX AI, built into MOX, an Ubuntu 26.04 based operating system for developers. "
    "Give short, exact answers. When a fix needs commands, put them in one ```bash block. "
    "Never suggest disabling security features unless the user asks. "
    "Security tools are only for systems the user owns or has written permission to test."
)


class AIError(Exception):
    pass


def settings():
    data = dict(DEFAULTS)
    if SETTINGS.exists():
        data.update(json.loads(SETTINGS.read_text()))
    return data


def save_setting(name, value):
    data = settings()
    data[name] = value
    write_private(SETTINGS, json.dumps(data, indent=2))


def get_key(provider):
    return vault.get(ENV_NAMES[provider])


def set_key(provider, key):
    vault.add(ENV_NAMES[provider], key)


def ollama_running():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def choose_provider():
    chosen = settings()["provider"]
    if chosen != "auto":
        return chosen
    for provider in ("anthropic", "openai"):
        if get_key(provider):
            return provider
    if ollama_running():
        return "ollama"
    raise AIError("No AI is set up. Run 'mox ai key anthropic', 'mox ai key openai' or 'mox get ollama'.")


def _post(url, headers, payload, timeout=180):
    request = urllib.request.Request(url, json.dumps(payload).encode(), {"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise AIError(f"The AI service returned {error.code}: {error.read().decode(errors='replace')[:300]}") from error
    except (urllib.error.URLError, OSError) as error:
        raise AIError(f"Couldn't reach the AI service: {error}") from error


def ask(prompt, provider=None):
    provider = provider or choose_provider()
    config = settings()
    if provider == "anthropic":
        key = get_key("anthropic")
        if not key:
            raise AIError("No Claude key. Run 'mox ai key anthropic'.")
        reply = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": config["anthropic_model"], "max_tokens": 2048, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]},
        )
        return "".join(block.get("text", "") for block in reply["content"])
    if provider == "openai":
        key = get_key("openai")
        if not key:
            raise AIError("No OpenAI key. Run 'mox ai key openai'.")
        reply = _post(
            "https://api.openai.com/v1/chat/completions",
            {"authorization": f"Bearer {key}"},
            {"model": config["openai_model"], "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
        )
        return reply["choices"][0]["message"]["content"]
    if provider == "ollama":
        reply = _post(
            OLLAMA + "/api/chat",
            {},
            {"model": config["ollama_model"], "stream": False, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
            timeout=600,
        )
        return reply["message"]["content"]
    raise AIError(f"Unknown AI provider: {provider}")


def command_blocks(text):
    return [block.strip() for block in re.findall(r"```(?:bash|sh|shell)\n(.*?)```", text, re.S) if block.strip()]


def fix(problem):
    """Ask the AI for a fix, then run each suggested block only if the user agrees."""
    report = hardware.text_report(hardware.summary())
    answer = ask(f"My MOX machine:\n{report}\n\nProblem: {problem}")
    print(answer)
    for block in command_blocks(answer):
        print(f"\n--- Suggested commands ---\n{block}\n--------------------------")
        if confirm("Run these commands?"):
            status = subprocess.run(["bash", "-e", "-c", block], check=False).returncode
            print(f"Finished with status {status}.")
            if status:
                return status
    return 0


def status():
    return {
        "provider": settings()["provider"],
        "claude_key": bool(get_key("anthropic")),
        "openai_key": bool(get_key("openai")),
        "ollama_running": ollama_running(),
        "claude_code": have("claude"),
        "codex": have("codex"),
        "llama_cpp": have("llama-cli") or have("llama-server"),
    }
