"""Calling rules the dial engine must follow. All of this is pure and testable."""
import math
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EARLIEST_HOUR = 8
LATEST_HOUR = 21
ABANDON_LIMIT = 3.0
STATE_ZONES = {
    "CT": "America/New_York", "DC": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "IN": "America/New_York", "KY": "America/New_York", "MA": "America/New_York",
    "MD": "America/New_York", "ME": "America/New_York", "MI": "America/New_York", "NC": "America/New_York",
    "NH": "America/New_York", "NJ": "America/New_York", "NY": "America/New_York", "OH": "America/New_York",
    "PA": "America/New_York", "RI": "America/New_York", "SC": "America/New_York", "VA": "America/New_York",
    "VT": "America/New_York", "WV": "America/New_York", "AL": "America/Chicago", "AR": "America/Chicago",
    "IA": "America/Chicago", "IL": "America/Chicago", "KS": "America/Chicago", "LA": "America/Chicago",
    "MN": "America/Chicago", "MO": "America/Chicago", "MS": "America/Chicago", "ND": "America/Chicago",
    "NE": "America/Chicago", "OK": "America/Chicago", "SD": "America/Chicago", "TN": "America/Chicago",
    "TX": "America/Chicago", "WI": "America/Chicago", "AZ": "America/Phoenix", "CO": "America/Denver",
    "ID": "America/Denver", "MT": "America/Denver", "NM": "America/Denver", "UT": "America/Denver",
    "WY": "America/Denver", "CA": "America/Los_Angeles", "NV": "America/Los_Angeles", "OR": "America/Los_Angeles",
    "WA": "America/Los_Angeles", "AK": "America/Anchorage", "HI": "Pacific/Honolulu",
}
# These states cross time zones, so the westernmost zone is used to avoid calling too early
# and the easternmost is checked for calling too late.
SPLIT_STATES = {
    "AK": ("America/Anchorage", "America/Adak"), "FL": ("America/New_York", "America/Chicago"),
    "ID": ("America/Denver", "America/Los_Angeles"), "IN": ("America/New_York", "America/Chicago"),
    "KS": ("America/Chicago", "America/Denver"), "KY": ("America/New_York", "America/Chicago"),
    "MI": ("America/New_York", "America/Chicago"), "ND": ("America/Chicago", "America/Denver"),
    "NE": ("America/Chicago", "America/Denver"), "OR": ("America/Los_Angeles", "America/Boise"),
    "SD": ("America/Chicago", "America/Denver"), "TN": ("America/New_York", "America/Chicago"),
    "TX": ("America/Chicago", "America/Denver"),
}


def normalize_phone(text, country="1"):
    """Return digits with country code, or "" if it isn't a usable number."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) == 10 and country == "1":
        digits = "1" + digits
    return digits if 8 <= len(digits) <= 15 else ""


def lead_zones(timezone, state):
    """All time zones a lead could be in. An empty list means it can't be dialed."""
    if timezone:
        try:
            ZoneInfo(timezone)
            return [timezone]
        except (ZoneInfoNotFoundError, ValueError):
            return []
    code = (state or "").strip().upper()
    if code in SPLIT_STATES:
        return list(SPLIT_STATES[code])
    return [STATE_ZONES[code]] if code in STATE_ZONES else []


def in_calling_hours(zones, start_hour, end_hour, now):
    """True only if every possible zone is inside the allowed window."""
    if not zones:
        return False
    first = max(start_hour, EARLIEST_HOUR)
    last = min(end_hour, LATEST_HOUR)
    for zone in zones:
        hour = now.astimezone(ZoneInfo(zone)).hour
        if not first <= hour < last:
            return False
    return True


def abandon_rate(answered, abandoned):
    return round(abandoned * 100 / answered, 2) if answered else 0.0


def calls_to_place(mode, ready_agents, in_flight, ratio, rate):
    """How many new calls to start this second."""
    if mode == "manual" or ready_agents <= 0:
        return 0
    effective = 1.0
    if mode == "predictive" and rate < ABANDON_LIMIT:
        effective = min(max(ratio, 1.0), 4.0)
    return max(math.ceil(ready_agents * effective) - in_flight, 0)


def retry_delay(outcome, attempts, max_attempts=3):
    """Seconds until the next try, or None to stop calling this lead."""
    if attempts >= max_attempts:
        return None
    return {"busy": 900, "noanswer": 3600, "failed": 3600, "abandoned": 3600}.get(outcome)


def utcnow():
    return datetime.now(ZoneInfo("UTC"))
