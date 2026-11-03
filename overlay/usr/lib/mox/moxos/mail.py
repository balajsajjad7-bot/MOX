"""MOX Quantum Mail: post-quantum sealed email between MOX users.

Messages and attachments are sealed with age 1.3 hybrid keys
(ML-KEM-768 + X25519). Only the people you seal to can open them, and a
future quantum computer can't break the key exchange. The sealed text
travels inside ordinary email, so any mail server can carry it.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAIL_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "mox/mail"
IDENTITY = MAIL_DIR / "identity.txt"
CONTACTS = MAIL_DIR / "contacts.json"
ARMOR = re.compile(r"-----BEGIN AGE ENCRYPTED FILE-----.*?-----END AGE ENCRYPTED FILE-----", re.S)
CARD_HEAD = "MOX QUANTUM MAIL KEY"
NOTICE = ("This message is sealed with MOX Quantum Mail (post-quantum ML-KEM-768 + X25519).\n"
          "Open it in MOX Mail. Nobody else, including mail servers, can read it.\n\n")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class MailError(Exception):
    pass


def _tool(name):
    """Prefer the age 1.3 build MOX installs in /usr/local/bin."""
    for folder in ("/usr/local/bin", "/usr/bin"):
        path = Path(folder) / name
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return shutil.which(name)


def pq_ready():
    keygen = _tool("age-keygen")
    if not keygen or not _tool("age"):
        return False
    done = subprocess.run([keygen, "--help"], capture_output=True, text=True)
    return "-pq" in done.stdout + done.stderr


def _need_pq():
    if not pq_ready():
        raise MailError("Quantum Mail needs age 1.3 or newer. Run: sudo mox get quantum-mail")


def _private_dir():
    MAIL_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(MAIL_DIR, 0o700)


def has_identity():
    return IDENTITY.exists()


def create_identity():
    _need_pq()
    if IDENTITY.exists():
        raise MailError("You already have a Quantum Mail key. Back up " + str(IDENTITY))
    _private_dir()
    old = os.umask(0o077)
    try:
        done = subprocess.run([_tool("age-keygen"), "-pq", "-o", str(IDENTITY)], capture_output=True, text=True)
    finally:
        os.umask(old)
    if done.returncode != 0:
        raise MailError(done.stderr.strip() or "Couldn't create the key")
    return my_key()


def my_key():
    if not IDENTITY.exists():
        raise MailError("Create your Quantum Mail key first: mox mail setup")
    done = subprocess.run([_tool("age-keygen"), "-y", str(IDENTITY)], capture_output=True, text=True)
    if done.returncode != 0:
        raise MailError(done.stderr.strip() or "Couldn't read your key")
    return done.stdout.strip()


def check_key(key):
    key = "".join(key.split())
    if key.startswith("age1pq1") and len(key) > 1000:
        return key
    if key.startswith("age1"):
        raise MailError("That key isn't quantum-safe. Ask them to make a MOX Quantum Mail key.")
    raise MailError("That doesn't look like a Quantum Mail key.")


# Contacts -----------------------------------------------------------------

def contacts():
    try:
        return json.loads(CONTACTS.read_text())
    except (OSError, ValueError):
        return {}


def _save_contacts(data):
    _private_dir()
    tmp = CONTACTS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(CONTACTS)


def add_contact(email, key, name=""):
    email = email.strip().lower()
    if not EMAIL.match(email):
        raise MailError("Enter a valid email address.")
    data = contacts()
    data[email] = {"name": name.strip() or email, "key": check_key(key)}
    _save_contacts(data)
    return data[email]


def remove_contact(email):
    data = contacts()
    if data.pop(email.strip().lower(), None) is None:
        raise MailError("No contact with that address.")
    _save_contacts(data)


def card(email, name=""):
    """A text block to send to people so they can write to you."""
    lines = [CARD_HEAD, f"name: {name or email}", f"email: {email}", "key:"]
    key = my_key()
    lines += [key[i:i + 76] for i in range(0, len(key), 76)]
    return "\n".join(lines) + "\n"


def read_card(text):
    if CARD_HEAD not in text:
        raise MailError("Paste a whole MOX Quantum Mail key card.")
    body = text.split(CARD_HEAD, 1)[1]
    fields, key_lines, in_key = {}, [], False
    for line in body.splitlines():
        line = line.strip().lstrip(">").strip()
        if in_key:
            if not line or ":" in line:
                break
            key_lines.append(line)
        elif line.startswith("key:"):
            in_key = True
            rest = line[4:].strip()
            if rest:
                key_lines.append(rest)
        elif ":" in line:
            name, value = line.split(":", 1)
            fields[name.strip()] = value.strip()
    if "email" not in fields or not key_lines:
        raise MailError("The key card is incomplete.")
    return add_contact(fields["email"], "".join(key_lines), fields.get("name", ""))


# Sealing ------------------------------------------------------------------

def _recipients(to):
    data = contacts()
    keys = []
    for item in to:
        item = item.strip()
        if item.lower() in data:
            keys.append(data[item.lower()]["key"])
        elif "@" in item:
            raise MailError(f"Add {item} as a contact first. Ask them for their key card.")
        else:
            keys.append(check_key(item))
    if not keys:
        raise MailError("Choose at least one contact.")
    if IDENTITY.exists():
        keys.append(my_key())  # so you can read your own sent mail
    return sorted(set(keys))


def _age(args, data, recipients=None):
    _need_pq()
    with tempfile.TemporaryDirectory() as folder:
        cmd = [_tool("age")] + args
        if recipients is not None:
            path = Path(folder) / "to.txt"
            path.write_text("\n".join(recipients) + "\n")
            cmd += ["-R", str(path)]
        done = subprocess.run(cmd, input=data, capture_output=True)
    if done.returncode != 0:
        message = done.stderr.decode(errors="replace").strip()
        if "no identity matched" in message:
            message = "This message wasn't sealed for your key."
        raise MailError(message or "age failed")
    return done.stdout


def seal(text, to):
    """Seal a message. Returns email-ready text."""
    data = text.encode() if isinstance(text, str) else text
    armored = _age(["-e", "-a"], data, _recipients(to)).decode()
    return NOTICE + armored


def unseal(text):
    match = ARMOR.search(text.replace("\r\n", "\n"))
    if not match:
        raise MailError("No sealed message found. Paste the whole email.")
    block = "\n".join(line.lstrip("> ").rstrip() for line in match.group(0).splitlines())
    if not IDENTITY.exists():
        raise MailError("Create your Quantum Mail key first: mox mail setup")
    return _age(["-d", "-i", str(IDENTITY)], (block + "\n").encode()).decode(errors="replace")


def _free(path):
    """Never overwrite: pick 'name (2).ext' when the file exists."""
    path = Path(path)
    number = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


def seal_file(path, to, out=None):
    path = Path(path)
    out = Path(out) if out else _free(path.with_name(path.name + ".age"))
    out.write_bytes(_age(["-e"], path.read_bytes(), _recipients(to)))
    return out


def unseal_file(path, out=None):
    path = Path(path)
    if not IDENTITY.exists():
        raise MailError("Create your Quantum Mail key first: mox mail setup")
    if out is None:
        out = _free(path.with_suffix("") if path.suffix == ".age" else path.with_name(path.name + ".opened"))
    out = Path(out)
    out.write_bytes(_age(["-d", "-i", str(IDENTITY)], path.read_bytes()))
    return out


# Your own mail server -------------------------------------------------------

def dns_records(domain, ip):
    domain = domain.strip().lower().rstrip(".")
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain):
        raise MailError("Enter a domain like example.com")
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip.strip()):
        raise MailError("Enter the server's public IPv4 address")
    host = f"mail.{domain}"
    return [
        ("A", host, ip.strip()),
        ("MX", domain, f"10 {host}"),
        ("TXT", domain, f"v=spf1 mx a:{host} -all"),
        ("TXT", f"_dmarc.{domain}", f"v=DMARC1; p=quarantine; rua=mailto:postmaster@{domain}"),
        ("TXT", f"mail._domainkey.{domain}", "copy the DKIM record from the Stalwart admin (Domains > DNS records)"),
        ("PTR", ip.strip(), f"{host} (set this at your server provider)"),
    ]
