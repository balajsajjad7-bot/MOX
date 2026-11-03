"""Number lookup through Twilio: registered caller name, line type and carrier."""
import json
import logging
import time

import aiohttp

log = logging.getLogger("moxdialer.lookup")
URL = "https://lookups.twilio.com/v2/PhoneNumbers/+{phone}"


def summarize(data):
    line = data.get("line_type_intelligence") or {}
    caller = data.get("caller_name") or {}
    return {
        "valid": data.get("valid"),
        "country": data.get("country_code") or "",
        "line_type": line.get("type") or "",
        "carrier": line.get("carrier_name") or "",
        "caller_name": caller.get("caller_name") or "",
    }


async def lookup(db, phone, url=URL):
    """Return number details, keeping each result for 30 days to limit paid lookups."""
    sid, token = db.get_setting("twilio_sid"), db.get_setting("twilio_token")
    if not sid or not token:
        return None
    saved = db.one("SELECT data, at FROM lookups WHERE phone=?", phone)
    if saved and time.time() - saved["at"] < 30 * 86400:
        return json.loads(saved["data"])
    fields = "line_type_intelligence,caller_name" if phone.startswith("1") else "line_type_intelligence"
    try:
        async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(sid, token)) as session:
            async with session.get(url.format(phone=phone), params={"Fields": fields}, timeout=aiohttp.ClientTimeout(total=6)) as response:
                if response.status >= 400:
                    log.warning("Lookup returned %s", response.status)
                    return None
                result = summarize(await response.json())
    except (aiohttp.ClientError, TimeoutError) as error:
        log.warning("Lookup failed: %s", error)
        return None
    db.run("INSERT OR REPLACE INTO lookups(phone,data,at) VALUES(?,?,?)", phone, json.dumps(result), time.time())
    return result
