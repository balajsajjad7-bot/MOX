"""Ready-made settings for phone carriers, so you only enter your login."""
import re
import subprocess

PRESETS = [
    {"id": "callcentric", "name": "Callcentric", "host": "sip.callcentric.net", "register": True,
     "user": "1777 followed by your account number", "password": "Your SIP password"},
    {"id": "telnyx", "name": "Telnyx", "host": "sip.telnyx.com", "register": True,
     "user": "From your Credentials connection, under Auth Detail", "password": "From the same connection"},
    {"id": "zadarma", "name": "Zadarma", "host": "sip.zadarma.com", "register": True,
     "user": "Your SIP number", "password": "From SIP Connection in your account"},
    {"id": "voipms", "name": "VoIP.ms", "host": "atlanta.voip.ms", "register": True,
     "user": "Your main account or sub-account", "password": "Your SIP password. Change the server to your nearest VoIP.ms city"},
    {"id": "twilio", "name": "Twilio Elastic SIP", "host": "", "register": False,
     "user": "From your trunk's credential list", "password": "From the same list. The server is your trunk's name.pstn.twilio.com"},
    {"id": "custom", "name": "Other SIP carrier", "host": "", "register": True,
     "user": "From your carrier", "password": "From your carrier"},
]
NOTE = ("Google Voice can't connect here. Personal accounts have no SIP login, and business SIP Link "
        "needs a certified hardware gateway. Forward your Google Voice number to a line above instead.")


def registration_state():
    """Ask Asterisk whether the carrier accepted the login."""
    try:
        done = subprocess.run(["asterisk", "-rx", "pjsip show registrations"], capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return parse_registration(done.stdout)


def parse_registration(text):
    for line in text.splitlines():
        if line.strip().startswith("trunk-register/"):
            match = re.search(r"\b(Registered|Rejected|Unregistered|Stopped)\b", line)
            return match.group(1).lower() if match else "unknown"
    return "none"
