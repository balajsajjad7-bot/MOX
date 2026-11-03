"""MOX Bot: answers system questions by itself and uses AI for the rest."""
import json
import re

from . import ai, hardware, health, net, news, shield, vault, vpn
from .common import version

HELP = (
    "I'm MOX Bot. Ask me about hardware, drivers, speed, security, VPN or updates. "
    "Add a Claude or OpenAI key, or run Ollama, and I can answer anything else."
)


def local_answer(text):
    """Answer from this computer without sending anything anywhere."""
    words = text.lower()
    if re.search(r"\b(hi|hello|salam|help|who are you)\b", words):
        return HELP
    if re.search(r"\b(health|ssd|temperature|battery)\b", words):
        return health.text(health.report())
    if re.search(r"\b(hardware|cpu|ram|memory|disk|specs?)\b", words):
        return hardware.text_report(hardware.summary())
    if re.search(r"\bdrivers?\b", words):
        data = hardware.summary()
        missing = ", ".join(item["name"] for item in data["missing_drivers"]) or "none"
        extra = ", ".join(data["available_drivers"]) or "none"
        return f"Devices without a driver: {missing}\nDrivers available to add: {extra}\nRun: mox drivers --install"
    if re.search(r"\b(speed ?test|internet speed)\b", words):
        try:
            result = net.speed_test()
        except OSError as error:
            return f"The speed test couldn't run: {error}"
        return f"Download {result['download_mbps']} Mbps, upload {result['upload_mbps']} Mbps."
    if re.search(r"\b(virus|antivirus|firewall|shield|security)\b", words):
        return json.dumps(shield.status(), indent=2)
    if re.search(r"\bvpn\b", words):
        items = vpn.tunnels()
        return "\n".join(f"{item['name']}: {'connected' if item['active'] else 'off'}" for item in items) or "No MOXWALL tunnel yet. Run: mox vpn make-server YOUR_SERVER_IP"
    if re.search(r"\b(api keys?|keys|vault)\b", words):
        return "\n".join(f"{key}: {value}" for key, value in vault.masked().items()) or "Your API vault is empty. Run: mox api add NAME"
    if re.search(r"\b(news|headlines)\b", words):
        lines = [f"{name}: {items[0]['title']}" for name, items in news.all_sources().items() if items]
        return "\n".join(lines) or "I couldn't reach the news sources."
    if re.search(r"\bversion\b", words):
        return f"MOX {version()}"
    return None


def reply(text):
    answer = local_answer(text)
    if answer is not None:
        return answer
    try:
        return ai.ask(text)
    except ai.AIError as error:
        return f"{error}\n\n{HELP}"


def chat():
    print("MOX Bot. Type 'exit' to leave.")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text.lower() in ("exit", "quit"):
            return 0
        if text:
            print(f"mox> {reply(text)}\n")
