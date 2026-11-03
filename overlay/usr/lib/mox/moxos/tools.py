"""MOX Tools: install open source tools from GitHub into ~/Tools."""
import json
import re
import shutil
import subprocess
from pathlib import Path

FOLDER = Path.home() / "Tools"
BIN = Path.home() / ".local/bin"


class ToolError(Exception):
    pass


def parse(source):
    match = re.match(r"^(?:https://github\.com/)?([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*?)(?:\.git)?/?$", source.strip())
    if not match:
        raise ToolError("Use owner/name, or a github.com link.")
    return match[1], match[2]


def kind(path):
    if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists() or (path / "setup.py").exists():
        return "python"
    if (path / "package.json").exists():
        return "node"
    if (path / "go.mod").exists():
        return "go"
    if (path / "Cargo.toml").exists():
        return "rust"
    if (path / "Makefile").exists():
        return "make"
    return "files"


def _run(command, cwd):
    if subprocess.run(command, cwd=cwd, check=False).returncode != 0:
        raise ToolError("Setup failed: " + " ".join(command))


def _link(target, name):
    BIN.mkdir(parents=True, exist_ok=True)
    link = BIN / name
    link.unlink(missing_ok=True)
    link.symlink_to(target)


def install(source):
    owner, name = parse(source)
    FOLDER.mkdir(exist_ok=True)
    path = FOLDER / name
    if path.exists():
        _run(["git", "pull", "--ff-only"], path)
    else:
        _run(["git", "clone", "--depth", "1", f"https://github.com/{owner}/{name}", str(path)], FOLDER)
    style = kind(path)
    if style == "python":
        _run(["python3", "-m", "venv", ".venv"], path)
        if (path / "requirements.txt").exists():
            _run([".venv/bin/pip", "install", "-r", "requirements.txt"], path)
        if (path / "pyproject.toml").exists() or (path / "setup.py").exists():
            _run([".venv/bin/pip", "install", "."], path)
            program = path / ".venv/bin" / name
            if program.exists():
                _link(program, name)
    elif style == "node":
        _run(["npm", "install", "--ignore-scripts"], path)
        data = json.loads((path / "package.json").read_text())
        target = data.get("bin")
        target = next(iter(target.values()), None) if isinstance(target, dict) else target
        if target:
            (path / target).chmod(0o755)
            _link(path / target, name)
    elif style == "go":
        _run(["go", "build", "-o", name, "."], path)
        _link(path / name, name)
    elif style == "rust":
        _run(["cargo", "build", "--release"], path)
        program = path / "target/release" / name
        if program.exists():
            _link(program, name)
    elif style == "make":
        _run(["make"], path)
    return path, style


def installed():
    return sorted(item.name for item in FOLDER.iterdir() if (item / ".git").is_dir()) if FOLDER.is_dir() else []


def remove(name):
    path = FOLDER / Path(name).name
    if not (path / ".git").is_dir():
        raise ToolError(f"No tool named {name}.")
    shutil.rmtree(path)
    (BIN / path.name).unlink(missing_ok=True)
