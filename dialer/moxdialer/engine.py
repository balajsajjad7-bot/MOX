"""The dial engine: places calls and joins answered customers to free agents."""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from dataclasses import dataclass, field

import aiohttp

from . import compliance, lookup
from .coach import CallCoach

log = logging.getLogger("moxdialer.engine")
RING_SECONDS = 20
OFFLINE, PAUSED, READY, INCALL, WRAPUP = "offline", "paused", "ready", "incall", "wrapup"


@dataclass
class Agent:
    user_id: int
    name: str
    sip_user: str
    role: str = "agent"
    status: str = OFFLINE
    campaign_id: int | None = None
    channel: str = ""
    bridge: str = ""
    since: float = field(default_factory=time.time)
    call_id: int | None = None
    snoop: str = ""
    pause_code: str = ""
    log_id: int | None = None
    held: bool = False


@dataclass
class Call:
    id: int
    channel: str
    campaign_id: int | None
    lead_id: int | None
    phone: str
    agent_id: int | None = None   # set for manual calls and once connected
    answered: bool = False
    connected: bool = False
    recording: str = ""
    ending: bool = False
    inbound: bool = False
    held_since: float = 0.0
    third: str = ""
    third_joined: bool = False


class Engine:
    def __init__(self, db, ari, notify):
        self.db = db
        self.ari = ari
        self.notify = notify        # async (user_id or None, dict)
        self.agents = {}
        self.calls = {}
        self.queue = []
        self.coach = CallCoach(db, ari, notify)

    # ---- Agents ------------------------------------------------------------
    def agent_for(self, user):
        agent = self.agents.get(user["id"])
        if agent is None:
            agent = Agent(user["id"], user["username"], user["sip_user"], user["role"])
            self.agents[user["id"]] = agent
        return agent

    def set_status(self, agent, status):
        now = time.time()
        if agent.log_id:
            self.db.run("UPDATE agent_log SET ended=? WHERE id=?", now, agent.log_id)
        agent.status = status
        agent.since = now
        agent.log_id = None if status == OFFLINE else self.db.run(
            "INSERT INTO agent_log(user_id,status,code,started) VALUES(?,?,?,?)", agent.user_id, status, agent.pause_code if status == PAUSED else "", now)

    async def push(self, agent):
        await self.notify(agent.user_id, {"type": "agent", "status": agent.status, "campaign_id": agent.campaign_id, "call_id": agent.call_id})
        await self.notify(None, {"type": "live"})

    async def agent_ready(self, agent, campaign_id):
        if agent.status == OFFLINE:
            raise ValueError("Connect your phone first.")
        if agent.status == INCALL:
            raise ValueError("Finish the call first.")
        if agent.call_id and self.db.one("SELECT 1 x FROM calls WHERE id=? AND disposition=''", agent.call_id):
            raise ValueError("Choose a result for the last call first.")
        if not self.db.one("SELECT 1 x FROM campaigns WHERE id=?", campaign_id):
            raise ValueError("Choose a campaign.")
        agent.campaign_id = campaign_id
        agent.call_id = None
        self.set_status(agent, READY)
        await self.push(agent)

    async def agent_pause(self, agent, code=""):
        if agent.status == READY:
            agent.pause_code = code
            self.set_status(agent, PAUSED)
            await self.push(agent)

    async def dial_manual(self, agent, phone, campaign_id):
        if agent.status not in (READY, PAUSED):
            raise ValueError("Connect your phone and finish any call first.")
        number = compliance.normalize_phone(phone)
        if not number:
            raise ValueError("That phone number isn't valid.")
        if self.db.is_dnc(number):
            raise ValueError("That number is on the do-not-call list.")
        campaign = self.db.one("SELECT * FROM campaigns WHERE id=?", campaign_id) if campaign_id else None
        lead = self.db.one("SELECT * FROM leads WHERE phone=? AND campaign_id=?", number, campaign_id) if campaign_id else None
        self.set_status(agent, INCALL)
        await self.place(number, campaign, lead, agent)
        await self.push(agent)

    async def dial_lead(self, lead, campaign):
        await self.place(lead["phone"], campaign, lead, None)

    async def place(self, number, campaign, lead, agent):
        now = time.time()
        call_id = self.db.run(
            "INSERT INTO calls(campaign_id,lead_id,agent_id,phone,started) VALUES(?,?,?,?,?)",
            campaign["id"] if campaign else None, lead["id"] if lead else None, agent.user_id if agent else None, number, now,
        )
        channel = f"mox-{call_id}"
        call = Call(call_id, channel, campaign["id"] if campaign else None, lead["id"] if lead else None, number, agent.user_id if agent else None)
        self.calls[channel] = call
        if agent:
            agent.call_id = call_id
        if lead:
            self.db.run("UPDATE leads SET status='calling', attempts=attempts+1 WHERE id=?", lead["id"])
        caller_id = (campaign or {}).get("caller_id") or self.db.get_setting("caller_id")
        endpoint = self.db.get_setting("dial_string", "PJSIP/{number}@trunk").format(number=number)
        try:
            await self.ari.call(
                "POST", "/channels", endpoint=endpoint, app=self.ari.app, appArgs="customer", channelId=channel,
                callerId=caller_id or None, timeout=RING_SECONDS,
            )
        except (RuntimeError, aiohttp.ClientError) as error:
            log.warning("Couldn't place call: %s", error)
            await self.finish(call, "failed")

    # ---- Asterisk events ---------------------------------------------------
    async def handle(self, event):
        kind = event.get("type")
        channel = event.get("channel", {})
        if kind == "StasisStart":
            args = event.get("args", [])
            if args[:1] == ["coach"]:
                return
            if args[:1] == ["agent"]:
                await self.agent_connected(args[1], channel["id"])
            elif args[:1] == ["customer"]:
                await self.answered(channel["id"])
            elif args[:1] == ["snoop"]:
                await self.snoop_started(int(args[1]), channel["id"])
            elif args[:1] == ["third"]:
                await self.third_answered(int(args[1]), channel["id"])
            elif args[:1] == ["inbound"]:
                await self.inbound(channel, args[1] if len(args) > 1 else "")
        elif kind == "StasisEnd":
            await self.left(channel["id"])
        elif kind == "ChannelDestroyed":
            await self.destroyed(channel["id"], event.get("cause", 0))
        elif kind == "PlaybackFinished":
            target = event["playback"].get("target_uri", "").split(":", 1)[-1]
            call = self.calls.get(target)
            if call and call.ending:
                await self.ari.quiet("DELETE", f"/channels/{target}")

    async def send_lookup(self, user_id, call):
        details = await lookup.lookup(self.db, call.phone)
        if details:
            await self.notify(user_id, {"type": "lookup", "call_id": call.id, **details})

    async def inbound(self, channel, did):
        campaign = self.db.one("SELECT * FROM campaigns WHERE did=? AND did!=''", did)
        number = compliance.normalize_phone(channel.get("caller", {}).get("number", "")) or channel.get("caller", {}).get("number", "unknown")
        lead = self.db.one("SELECT * FROM leads WHERE phone=? ORDER BY id DESC LIMIT 1", number)
        call_id = self.db.run("INSERT INTO calls(campaign_id,lead_id,phone,direction,started,answered) VALUES(?,?,?,'in',?,?)",
                              campaign["id"] if campaign else None, lead["id"] if lead else None, number, time.time(), time.time())
        call = Call(call_id, channel["id"], campaign["id"] if campaign else None, lead["id"] if lead else None, number, answered=True, inbound=True, held_since=time.time())
        self.calls[channel["id"]] = call
        await self.ari.quiet("POST", f"/channels/{channel['id']}/answer")
        agent = self.free_agent(call.campaign_id)
        if agent:
            await self.connect(call, agent)
        else:
            self.queue.append(channel["id"])
            await self.ari.quiet("POST", f"/channels/{channel['id']}/moh")
            await self.notify(None, {"type": "live"})

    async def serve_queue(self):
        now = time.time()
        for channel in list(self.queue):
            call = self.calls.get(channel)
            if call is None:
                self.queue.remove(channel)
                continue
            agent = self.free_agent(call.campaign_id)
            if agent:
                self.queue.remove(channel)
                await self.ari.quiet("DELETE", f"/channels/{channel}/moh")
                await self.connect(call, agent)
            elif now - call.held_since > 300:
                self.queue.remove(channel)
                await self.abandon(call)

    async def agent_connected(self, sip_user, channel):
        user = self.db.one("SELECT * FROM users WHERE sip_user=? AND active=1", sip_user)
        if not user:
            await self.ari.quiet("DELETE", f"/channels/{channel}")
            return
        agent = self.agent_for(user)
        if agent.channel:
            await self.ari.quiet("DELETE", f"/channels/{agent.channel}")
        bridge = await self.ari.call("POST", "/bridges", type="mixing", name=f"agent-{agent.user_id}")
        agent.channel, agent.bridge = channel, bridge["id"]
        await self.ari.call("POST", f"/bridges/{agent.bridge}/addChannel", channel=channel)
        self.set_status(agent, PAUSED)
        await self.push(agent)

    async def answered(self, channel):
        call = self.calls.get(channel)
        if call is None:
            await self.ari.quiet("DELETE", f"/channels/{channel}")
            return
        call.answered = True
        self.db.run("UPDATE calls SET answered=? WHERE id=?", time.time(), call.id)
        agent = self.agents.get(call.agent_id) if call.agent_id else self.free_agent(call.campaign_id)
        if agent is None:
            await self.abandon(call)
            return
        await self.connect(call, agent)

    def free_agent(self, campaign_id):
        ready = [a for a in self.agents.values() if a.status == READY and a.bridge and (campaign_id is None or a.campaign_id == campaign_id)]
        return min(ready, key=lambda a: a.since) if ready else None

    async def connect(self, call, agent):
        call.agent_id = agent.user_id
        call.connected = True
        agent.call_id = call.id
        self.set_status(agent, INCALL)
        self.db.run("UPDATE calls SET agent_id=? WHERE id=?", agent.user_id, call.id)
        await self.ari.call("POST", f"/bridges/{agent.bridge}/addChannel", channel=call.channel)
        if self.db.get_setting("record_calls", "1") == "1":
            name = f"mox-call-{call.id}"
            try:
                await self.ari.call("POST", f"/bridges/{agent.bridge}/record", name=name, format="wav", ifExists="overwrite")
                call.recording = name
                self.db.run("UPDATE calls SET recording=? WHERE id=?", name, call.id)
            except RuntimeError as error:
                log.warning("Recording didn't start: %s", error)
        lead = self.db.one("SELECT * FROM leads WHERE id=?", call.lead_id) if call.lead_id else None
        campaign = self.db.one("SELECT * FROM campaigns WHERE id=?", call.campaign_id) if call.campaign_id else None
        await self.notify(agent.user_id, {"type": "call", "call_id": call.id, "phone": call.phone, "lead": lead, "inbound": call.inbound})
        await self.coach.start(call, agent.user_id, lead, campaign)
        asyncio.create_task(self.send_lookup(agent.user_id, call))
        await self.push(agent)

    async def abandon(self, call):
        """No agent is free: play the required message, then hang up."""
        call.ending = True
        self.db.run("UPDATE calls SET outcome='abandoned' WHERE id=?", call.id)
        media = self.db.get_setting("abandon_media", "sound:vm-nobodyavail")
        try:
            await self.ari.call("POST", f"/channels/{call.channel}/play", media=media)
        except RuntimeError:
            await self.ari.quiet("DELETE", f"/channels/{call.channel}")

    async def left(self, channel):
        if channel in self.calls:
            await self.destroyed(channel, 16)
            return
        for agent in self.agents.values():
            if agent.channel == channel:
                await self.agent_gone(agent)
                return

    async def agent_gone(self, agent):
        bridge, agent.channel, agent.bridge = agent.bridge, "", ""
        if agent.call_id:
            for call in self.calls.values():
                if call.id == agent.call_id:
                    await self.ari.quiet("DELETE", f"/channels/{call.channel}")
        if bridge:
            await self.ari.quiet("DELETE", f"/bridges/{bridge}")
        self.set_status(agent, OFFLINE)
        await self.push(agent)

    async def destroyed(self, channel, cause):
        call = self.calls.get(channel)
        if call is None:
            return
        if call.connected:
            outcome = "answered"
        elif call.ending:
            outcome = "abandoned"
        elif call.answered:
            outcome = "answered"
        else:
            outcome = {17: "busy", 18: "noanswer", 19: "noanswer", 21: "failed", 34: "failed"}.get(cause, "noanswer")
        await self.finish(call, outcome)

    async def finish(self, call, outcome):
        self.calls.pop(call.channel, None)
        await self.coach.stop(call.id)
        if call.third:
            await self.ari.quiet("DELETE", f"/channels/{call.third}")
        now = time.time()
        if call.recording:
            await self.ari.quiet("POST", f"/recordings/live/{call.recording}/stop")
        self.db.run("UPDATE calls SET ended=?, outcome=? WHERE id=?", now, outcome, call.id)
        if call.lead_id:
            lead = self.db.one("SELECT * FROM leads WHERE id=?", call.lead_id)
            if lead and lead["status"] != "dnc":
                if outcome == "answered":
                    self.db.run("UPDATE leads SET status='contacted' WHERE id=?", lead["id"])
                else:
                    delay = compliance.retry_delay(outcome, lead["attempts"])
                    if delay is None:
                        self.db.run("UPDATE leads SET status='done' WHERE id=?", lead["id"])
                    else:
                        self.db.run("UPDATE leads SET status='new', next_at=? WHERE id=?", now + delay, lead["id"])
        agent = self.agents.get(call.agent_id) if call.agent_id else None
        if agent and agent.call_id == call.id and agent.status == INCALL:
            if outcome == "answered":
                self.set_status(agent, WRAPUP)
            else:
                agent.call_id = None
                self.db.run("UPDATE calls SET disposition=? WHERE id=?", outcome, call.id)
                self.set_status(agent, PAUSED)
            await self.push(agent)
        await self.notify(None, {"type": "live"})

    def active_call(self, agent):
        return next((call for call in self.calls.values() if call.id == agent.call_id), None)

    async def hold(self, agent, on):
        call = self.active_call(agent)
        if not call or not call.connected:
            raise ValueError("There's no call to hold.")
        if on:
            await self.ari.call("POST", f"/bridges/{agent.bridge}/removeChannel", channel=call.channel)
            await self.ari.call("POST", f"/channels/{call.channel}/moh")
        else:
            await self.ari.call("DELETE", f"/channels/{call.channel}/moh")
            await self.ari.call("POST", f"/bridges/{agent.bridge}/addChannel", channel=call.channel)
        agent.held = on
        await self.push(agent)

    async def send_digits(self, agent, digits):
        call = self.active_call(agent)
        if not call or not re.fullmatch(r"[0-9*#]{1,32}", digits):
            raise ValueError("Enter digits for a live call.")
        await self.ari.call("POST", f"/channels/{call.channel}/dtmf", dtmf=digits)

    async def add_party(self, agent, phone):
        """Three-way call or warm transfer."""
        call = self.active_call(agent)
        number = compliance.normalize_phone(phone)
        if not call or not call.connected or not number:
            raise ValueError("Enter a valid number during a live call.")
        if self.db.is_dnc(number):
            raise ValueError("That number is on the do-not-call list.")
        call.third = f"mox-third-{call.id}"
        endpoint = self.db.get_setting("dial_string", "PJSIP/{number}@trunk").format(number=number)
        await self.ari.call("POST", "/channels", endpoint=endpoint, app=self.ari.app, appArgs=f"third,{agent.user_id}", channelId=call.third,
                            callerId=self.db.get_setting("caller_id") or None, timeout=RING_SECONDS)

    async def third_answered(self, agent_id, channel):
        agent = self.agents.get(agent_id)
        call = self.active_call(agent) if agent else None
        if agent and agent.bridge and call:
            await self.ari.call("POST", f"/bridges/{agent.bridge}/addChannel", channel=channel)
            call.third_joined = True
        else:
            await self.ari.quiet("DELETE", f"/channels/{channel}")

    async def drop_party(self, agent):
        call = self.active_call(agent)
        if call and call.third:
            await self.ari.quiet("DELETE", f"/channels/{call.third}")
            call.third = ""
            call.third_joined = False

    async def leave_transfer(self, agent):
        """Finish a warm transfer: the customer stays with the third party."""
        call = self.active_call(agent)
        if not call or not call.third_joined:
            raise ValueError("Wait for the other person to answer first.")
        bridge = await self.ari.call("POST", "/bridges", type="mixing", name=f"transfer-{call.id}")
        await self.ari.call("POST", f"/bridges/{agent.bridge}/removeChannel", channel=f"{call.channel},{call.third}")
        await self.ari.call("POST", f"/bridges/{bridge['id']}/addChannel", channel=f"{call.channel},{call.third}")
        call.connected = False
        await self.coach.stop(call.id)
        self.set_status(agent, WRAPUP)
        self.db.run("UPDATE calls SET notes=notes||? WHERE id=?", " Transferred.", call.id)
        await self.push(agent)

    async def hangup(self, agent):
        for call in list(self.calls.values()):
            if call.id == agent.call_id:
                await self.ari.quiet("DELETE", f"/channels/{call.channel}")

    async def disposition(self, agent, call_id, disposition, notes, callback_at):
        row = self.db.one("SELECT * FROM calls WHERE id=? AND agent_id=?", call_id, agent.user_id)
        if not row:
            raise ValueError("That call isn't yours.")
        self.db.run("UPDATE calls SET disposition=?, notes=? WHERE id=?", disposition, notes, call_id)
        if disposition == "dnc":
            self.db.add_dnc(row["phone"], "Requested on call")
        elif disposition == "callback" and row["lead_id"]:
            self.db.run("UPDATE leads SET status='new', next_at=? WHERE id=?", callback_at or time.time() + 86400, row["lead_id"])
        if agent.call_id == call_id:
            agent.call_id = None
        if agent.status == WRAPUP:
            self.set_status(agent, PAUSED)
        await self.push(agent)
        asyncio.create_task(self.send_to_modo(call_id))

    async def send_to_modo(self, call_id):
        url = self.db.get_setting("modo_webhook")
        if not url:
            return
        call = self.db.one(
            "SELECT c.*, u.username agent, m.name campaign, l.first_name, l.last_name, l.data FROM calls c LEFT JOIN users u ON u.id=c.agent_id "
            "LEFT JOIN campaigns m ON m.id=c.campaign_id LEFT JOIN leads l ON l.id=c.lead_id WHERE c.id=?", call_id)
        body = json.dumps({"event": "call.completed", "call": call}).encode()
        secret = self.db.get_setting("modo_secret").encode()
        signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, data=body, headers={"content-type": "application/json", "x-mox-signature": signature}, timeout=aiohttp.ClientTimeout(total=10))
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            log.warning("Modo didn't accept the call: %s", error)

    # ---- Supervisor listening ----------------------------------------------
    async def monitor(self, supervisor, agent_id, mode):
        target = self.agents.get(agent_id)
        if supervisor.status == OFFLINE:
            raise ValueError("Connect your phone first.")
        if not target or not target.channel or target.status != INCALL:
            raise ValueError("That agent isn't on a call.")
        await self.stop_monitor(supervisor)
        await self.ari.call(
            "POST", f"/channels/{target.channel}/snoop", spy="both", whisper={"whisper": "out", "barge": "both"}.get(mode, "none"),
            app=self.ari.app, appArgs=f"snoop,{supervisor.user_id}",
        )

    async def snoop_started(self, supervisor_id, channel):
        supervisor = self.agents.get(supervisor_id)
        if supervisor and supervisor.bridge:
            supervisor.snoop = channel
            await self.ari.call("POST", f"/bridges/{supervisor.bridge}/addChannel", channel=channel)
        else:
            await self.ari.quiet("DELETE", f"/channels/{channel}")

    async def stop_monitor(self, supervisor):
        if supervisor.snoop:
            await self.ari.quiet("DELETE", f"/channels/{supervisor.snoop}")
            supervisor.snoop = ""

    # ---- Dial loop ---------------------------------------------------------
    def pick_leads(self, campaign, count, now):
        rows = self.db.all(
            "SELECT * FROM leads WHERE campaign_id=? AND status='new' AND next_at<=? ORDER BY next_at, id LIMIT ?",
            campaign["id"], time.time(), max(count * 25, 100),
        )
        picked = []
        for lead in rows:
            if self.db.is_dnc(lead["phone"]):
                self.db.run("UPDATE leads SET status='dnc' WHERE id=?", lead["id"])
                continue
            zones = compliance.lead_zones(lead["timezone"], lead["state"])
            if compliance.in_calling_hours(zones, campaign["start_hour"], campaign["end_hour"], now):
                picked.append(lead)
                if len(picked) == count:
                    break
        return picked

    async def tick(self):
        await self.serve_queue()
        now = compliance.utcnow()
        for campaign in self.db.all("SELECT * FROM campaigns WHERE active=1 AND mode!='manual'"):
            ready = sum(1 for a in self.agents.values() if a.status == READY and a.campaign_id == campaign["id"] and a.bridge)
            flight = sum(1 for c in self.calls.values() if c.campaign_id == campaign["id"] and not c.connected and not c.ending and c.agent_id is None)
            answered, abandoned = self.db.rate_counts(campaign["id"])
            rate = compliance.abandon_rate(answered, abandoned)
            count = compliance.calls_to_place(campaign["mode"], ready, flight, campaign["ratio"], rate)
            if count:
                for lead in self.pick_leads(campaign, count, now):
                    await self.dial_lead(lead, campaign)

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Dial loop failed")
            await asyncio.sleep(1)

    def live(self):
        now = time.time()
        agents = []
        for agent in self.agents.values():
            if agent.status == OFFLINE:
                continue
            call = self.active_call(agent)
            agents.append({
                "id": agent.user_id, "name": agent.name, "status": agent.status, "seconds": int(now - agent.since), "campaign_id": agent.campaign_id,
                "pause_code": agent.pause_code if agent.status == PAUSED else "", "phone": call.phone if call else "", "held": agent.held,
                "direction": "in" if call and call.inbound else "out" if call else "",
            })
        return {
            "agents": agents,
            "ringing": sum(1 for c in self.calls.values() if not c.answered),
            "queue": [{"phone": self.calls[c].phone, "seconds": int(now - self.calls[c].held_since)} for c in self.queue if c in self.calls],
            "coach": self.coach.enabled(),
        }
