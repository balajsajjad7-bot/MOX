"""MOX Dialer web server."""
import argparse
import asyncio
import csv
import io
import json
import logging
import os
import secrets
import ssl
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from . import compliance, pjsip
from .ari import Ari
from .db import DB, check_password
from .engine import Engine, OFFLINE

WEB = Path(__file__).resolve().parent.parent / "web"
ROLES_STAFF = ("admin", "supervisor")
DISPOSITIONS = ("sale", "interested", "callback", "not_interested", "wrong_number", "voicemail", "dnc")
SETTING_KEYS = ("trunk_host", "trunk_user", "caller_id", "record_calls", "modo_webhook", "modo_open_url", "abandon_media", "coach_enabled", "stt_model", "llm_model", "twilio_sid")
SECRET_KEYS = ("trunk_pass", "modo_secret", "stt_key", "llm_key", "twilio_token")
PAUSE_CODES = ("Break", "Lunch", "Meeting", "Training", "Bathroom", "Technical")
log = logging.getLogger("moxdialer")


def fail(status, message):
    return web.json_response({"error": message}, status=status)


@web.middleware
async def security(request, handler):
    response = await handler(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src 'self' ws: wss:; media-src 'self' blob:; style-src 'self'; script-src 'self'; img-src 'self' data:"
    return response


class App:
    def __init__(self, db, ari, sip_conf, cookie_secure, ari_ws):
        self.db = db
        self.ari = ari
        self.sip_conf = sip_conf
        self.cookie_secure = cookie_secure
        self.ari_ws = ari_ws
        self.sessions = {}
        self.sockets = {}
        self.fails = {}
        self.engine = Engine(db, ari, self.notify)

    # ---- helpers -----------------------------------------------------------
    async def notify(self, user_id, message):
        targets = self.sockets.get(user_id, set()) if user_id else [s for group in self.sockets.values() for s in group]
        for socket in list(targets):
            try:
                await socket.send_json(message)
            except (ConnectionError, RuntimeError):
                pass

    def user(self, request):
        session = self.sessions.get(request.cookies.get("mox_session", ""))
        if not session or session["expires"] < time.time():
            return None
        return self.db.one("SELECT * FROM users WHERE id=? AND active=1", session["user_id"])

    def need(self, request, *roles):
        user = self.user(request)
        if user is None:
            raise web.HTTPUnauthorized(text=json.dumps({"error": "Please sign in."}), content_type="application/json")
        if roles and user["role"] not in roles:
            raise web.HTTPForbidden(text=json.dumps({"error": "You don't have access to this."}), content_type="application/json")
        return user

    # ---- sign in -----------------------------------------------------------
    async def login(self, request):
        body = await request.json()
        username = str(body.get("username", ""))
        address = request.remote or ""
        count, last = self.fails.get(address, (0, 0))
        if count >= 8 and time.time() - last < 300:
            return fail(429, "Too many tries. Wait five minutes.")
        user = self.db.one("SELECT * FROM users WHERE username=? AND active=1", username)
        if not user or not check_password(str(body.get("password", "")), user["pass_hash"]):
            self.fails[address] = (count + 1, time.time())
            return fail(401, "Wrong username or password.")
        self.fails.pop(address, None)
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {"user_id": user["id"], "expires": time.time() + 43200}
        response = web.json_response(self.public_user(user))
        response.set_cookie("mox_session", token, httponly=True, secure=self.cookie_secure, samesite="Strict", max_age=43200)
        return response

    async def logout(self, request):
        self.sessions.pop(request.cookies.get("mox_session", ""), None)
        response = web.json_response({"ok": True})
        response.del_cookie("mox_session")
        return response

    def public_user(self, user):
        agent = self.engine.agents.get(user["id"])
        return {
            "id": user["id"], "username": user["username"], "role": user["role"], "sip_user": user["sip_user"],
            "sip_pass": user["sip_pass"], "status": agent.status if agent else OFFLINE, "modo_open_url": self.db.get_setting("modo_open_url"),
            "pause_codes": PAUSE_CODES,
        }

    async def me(self, request):
        return web.json_response(self.public_user(self.need(request)))

    # ---- settings and people ----------------------------------------------
    async def get_settings(self, request):
        self.need(request, "admin")
        data = {key: self.db.get_setting(key) for key in SETTING_KEYS}
        for key in SECRET_KEYS:
            data[key + "_set"] = bool(self.db.get_setting(key))
        return web.json_response(data)

    async def save_settings(self, request):
        self.need(request, "admin")
        body = await request.json()
        for key in SETTING_KEYS:
            if key in body:
                self.db.set_setting(key, str(body[key]).replace("\n", "").strip())
        for key in SECRET_KEYS:
            if body.get(key):
                self.db.set_setting(key, str(body[key]).replace("\n", ""))
        pjsip.apply(self.db, self.sip_conf)
        return web.json_response({"ok": True})

    async def users(self, request):
        self.need(request, *ROLES_STAFF)
        return web.json_response(self.db.all("SELECT id, username, role, sip_user, active FROM users ORDER BY id"))

    async def add_user(self, request):
        self.need(request, "admin")
        body = await request.json()
        username, password, role = str(body.get("username", "")).strip(), str(body.get("password", "")), body.get("role")
        if not username or len(password) < 10 or role not in ("admin", "supervisor", "agent"):
            return fail(400, "Enter a username, a role, and a password of at least 10 characters.")
        if self.db.one("SELECT 1 x FROM users WHERE username=?", username):
            return fail(400, "That username is taken.")
        self.db.add_user(username, password, role)
        pjsip.apply(self.db, self.sip_conf)
        return web.json_response({"ok": True})

    async def campaigns(self, request):
        self.need(request)
        rows = self.db.all(
            "SELECT c.*, (SELECT COUNT(*) FROM leads l WHERE l.campaign_id=c.id) leads, "
            "(SELECT COUNT(*) FROM leads l WHERE l.campaign_id=c.id AND l.status='new') remaining FROM campaigns c ORDER BY c.id")
        for row in rows:
            answered, abandoned = self.db.rate_counts(row["id"])
            row["abandon_rate"] = compliance.abandon_rate(answered, abandoned)
        return web.json_response(rows)

    async def save_campaign(self, request):
        self.need(request, "admin")
        body = await request.json()
        mode = body.get("mode", "manual")
        if mode not in ("manual", "progressive", "predictive") or not str(body.get("name", "")).strip():
            return fail(400, "Enter a name and choose a dialing mode.")
        values = (
            str(body["name"]).strip(), mode, float(body.get("ratio", 1.2)), compliance.normalize_phone(str(body.get("caller_id", ""))),
            int(body.get("start_hour", 9)), int(body.get("end_hour", 20)), 1 if body.get("active") else 0, str(body.get("script", "")),
            str(body.get("did", "")).strip(), str(body.get("coach_do", "")), str(body.get("coach_dont", "")),
        )
        if values[6] and not values[3]:
            return fail(400, "A running campaign needs a valid caller ID.")
        if body.get("id"):
            self.db.run("UPDATE campaigns SET name=?,mode=?,ratio=?,caller_id=?,start_hour=?,end_hour=?,active=?,script=?,did=?,coach_do=?,coach_dont=? WHERE id=?", *values, int(body["id"]))
        else:
            self.db.run("INSERT INTO campaigns(name,mode,ratio,caller_id,start_hour,end_hour,active,script,did,coach_do,coach_dont) VALUES(?,?,?,?,?,?,?,?,?,?,?)", *values)
        return web.json_response({"ok": True})

    async def upload_leads(self, request):
        self.need(request, "admin")
        campaign_id = int(request.match_info["id"])
        if not self.db.one("SELECT 1 x FROM campaigns WHERE id=?", campaign_id):
            return fail(404, "Campaign not found.")
        text = await request.text()
        added = skipped = no_zone = 0
        for row in csv.DictReader(io.StringIO(text)):
            row = {str(key).strip().lower(): (value or "").strip() for key, value in row.items() if key}
            phone = compliance.normalize_phone(row.get("phone", ""))
            state, zone = row.get("state", ""), row.get("timezone", "")
            if not phone or self.db.is_dnc(phone):
                skipped += 1
                continue
            if not compliance.lead_zones(zone, state):
                no_zone += 1
            extra = {k: v for k, v in row.items() if k not in ("phone", "first_name", "last_name", "state", "timezone")}
            before = self.db.one("SELECT COUNT(*) n FROM leads WHERE campaign_id=?", campaign_id)["n"]
            self.db.run(
                "INSERT OR IGNORE INTO leads(campaign_id,phone,first_name,last_name,state,timezone,data) VALUES(?,?,?,?,?,?,?)",
                campaign_id, phone, row.get("first_name", ""), row.get("last_name", ""), state.upper(), zone, json.dumps(extra),
            )
            if self.db.one("SELECT COUNT(*) n FROM leads WHERE campaign_id=?", campaign_id)["n"] > before:
                added += 1
            else:
                skipped += 1
        return web.json_response({"added": added, "skipped": skipped, "no_timezone": no_zone})

    async def dnc_add(self, request):
        self.need(request, *ROLES_STAFF)
        text = await request.text()
        added = 0
        for line in text.splitlines():
            phone = compliance.normalize_phone(line)
            if phone:
                self.db.add_dnc(phone, "Imported")
                added += 1
        return web.json_response({"added": added})

    # ---- agent actions -----------------------------------------------------
    async def agent_action(self, request):
        user = self.need(request)
        agent = self.engine.agent_for(user)
        body = await request.json()
        action = request.match_info["action"]
        try:
            if action == "ready":
                await self.engine.agent_ready(agent, int(body.get("campaign_id") or 0))
            elif action == "pause":
                await self.engine.agent_pause(agent, body.get("code") if body.get("code") in PAUSE_CODES else "")
            elif action == "hold":
                await self.engine.hold(agent, bool(body.get("on")))
            elif action == "digits":
                await self.engine.send_digits(agent, str(body.get("digits", "")))
            elif action == "add_party":
                await self.engine.add_party(agent, str(body.get("phone", "")))
            elif action == "drop_party":
                await self.engine.drop_party(agent)
            elif action == "leave_transfer":
                await self.engine.leave_transfer(agent)
            elif action == "dial":
                await self.engine.dial_manual(agent, str(body.get("phone", "")), int(body.get("campaign_id") or 0) or None)
            elif action == "hangup":
                await self.engine.hangup(agent)
            elif action == "disposition":
                if body.get("disposition") not in DISPOSITIONS:
                    return fail(400, "Choose a result.")
                await self.engine.disposition(agent, int(body["call_id"]), body["disposition"], str(body.get("notes", ""))[:2000], body.get("callback_at"))
            else:
                return fail(404, "Unknown action.")
        except ValueError as error:
            return fail(400, str(error))
        return web.json_response({"status": agent.status})

    async def monitor(self, request):
        user = self.need(request, *ROLES_STAFF)
        supervisor = self.engine.agent_for(user)
        body = await request.json()
        try:
            if body.get("mode") == "stop":
                await self.engine.stop_monitor(supervisor)
            else:
                await self.engine.monitor(supervisor, int(body.get("agent_id", 0)), body.get("mode") if body.get("mode") in ("whisper", "barge") else "listen")
        except (ValueError, RuntimeError) as error:
            return fail(400, str(error))
        return web.json_response({"ok": True})

    # ---- reports -----------------------------------------------------------
    async def live(self, request):
        self.need(request, *ROLES_STAFF)
        data = self.engine.live()
        since = time.time() - 86400
        data["campaigns"] = self.db.all(
            "SELECT m.id, m.name, m.mode, m.ratio, m.active, (SELECT COUNT(*) FROM leads l WHERE l.campaign_id=m.id AND l.status='new') left_leads, "
            "(SELECT COUNT(*) FROM calls c WHERE c.campaign_id=m.id AND c.started>=?) calls, (SELECT COUNT(*) FROM calls c WHERE c.campaign_id=m.id AND c.started>=? AND c.disposition='sale') sales FROM campaigns m ORDER BY m.id",
            since, since)
        for row in data["campaigns"]:
            answered, abandoned = self.db.rate_counts(row["id"])
            row["abandon_rate"] = compliance.abandon_rate(answered, abandoned)
        return web.json_response(data)

    async def leads(self, request):
        self.need(request)
        term = "%" + request.query.get("q", "").strip() + "%"
        return web.json_response(self.db.all(
            "SELECT id, campaign_id, phone, first_name, last_name, state, status, attempts, next_at FROM leads WHERE phone LIKE ? OR first_name LIKE ? OR last_name LIKE ? ORDER BY id DESC LIMIT 200",
            term, term, term))

    async def callbacks(self, request):
        user = self.need(request)
        return web.json_response(self.db.all(
            "SELECT l.id, l.phone, l.first_name, l.last_name, l.next_at, c.notes FROM calls c JOIN leads l ON l.id=c.lead_id "
            "WHERE c.agent_id=? AND c.disposition='callback' AND l.status='new' ORDER BY l.next_at LIMIT 100", user["id"]))

    async def recycle(self, request):
        self.need(request, "admin")
        campaign_id = int(request.match_info["id"])
        self.db.run("UPDATE leads SET status='new', attempts=0, next_at=0 WHERE campaign_id=? AND status='done'", campaign_id)
        return web.json_response({"ok": True})

    async def time_report(self, request):
        self.need(request, *ROLES_STAFF)
        since = time.time() - 86400
        return web.json_response(self.db.all(
            "SELECT u.username agent, a.status, a.code, ROUND(SUM(COALESCE(a.ended,?)-a.started)) seconds FROM agent_log a JOIN users u ON u.id=a.user_id "
            "WHERE a.started>=? GROUP BY u.id, a.status, a.code ORDER BY u.username", time.time(), since))

    async def report(self, request):
        self.need(request, *ROLES_STAFF)
        since = time.time() - int(request.query.get("days", 1)) * 86400
        totals = self.db.one(
            "SELECT COUNT(*) calls, SUM(answered IS NOT NULL) answered, SUM(outcome='abandoned') abandoned, SUM(disposition='sale') sales, "
            "SUM(CASE WHEN answered IS NOT NULL AND ended IS NOT NULL THEN ended-answered ELSE 0 END) talk FROM calls WHERE started>=?", since)
        agents = self.db.all(
            "SELECT u.username agent, COUNT(c.id) calls, SUM(c.disposition='sale') sales, SUM(CASE WHEN c.ended IS NOT NULL AND c.answered IS NOT NULL THEN c.ended-c.answered ELSE 0 END) talk "
            "FROM calls c JOIN users u ON u.id=c.agent_id WHERE c.started>=? GROUP BY u.id ORDER BY sales DESC", since)
        recent = self.db.all(
            "SELECT c.id, c.phone, c.started, c.outcome, c.disposition, c.recording, u.username agent FROM calls c LEFT JOIN users u ON u.id=c.agent_id ORDER BY c.id DESC LIMIT 100")
        return web.json_response({"totals": totals, "agents": agents, "recent": recent})

    async def recording(self, request):
        self.need(request, *ROLES_STAFF)
        row = self.db.one("SELECT recording FROM calls WHERE id=?", int(request.match_info["id"]))
        if not row or not row["recording"]:
            return fail(404, "No recording for this call.")
        try:
            async with self.ari.session.get(f"{self.ari.base}/ari/recordings/stored/{row['recording']}/file") as upstream:
                if upstream.status != 200:
                    return fail(404, "The recording file isn't available.")
                return web.Response(body=await upstream.read(), content_type="audio/wav")
        except aiohttp.ClientError:
            return fail(502, "Asterisk isn't reachable.")

    # ---- sockets -----------------------------------------------------------
    async def events(self, request):
        user = self.need(request)
        socket = web.WebSocketResponse(heartbeat=30)
        await socket.prepare(request)
        self.sockets.setdefault(user["id"], set()).add(socket)
        try:
            async for _message in socket:
                pass
        finally:
            self.sockets[user["id"]].discard(socket)
        return socket

    async def sip_proxy(self, request):
        """Carries the browser phone to Asterisk, so only one port is public."""
        self.need(request)
        browser = web.WebSocketResponse(protocols=("sip",), heartbeat=30)
        await browser.prepare(request)
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self.ari_ws, protocols=("sip",)) as upstream:
                async def pump(source, target):
                    async for message in source:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            await target.send_str(message.data)
                        elif message.type == aiohttp.WSMsgType.BINARY:
                            await target.send_bytes(message.data)
                tasks = [asyncio.create_task(pump(browser, upstream)), asyncio.create_task(pump(upstream, browser))]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:
                    task.cancel()
        return browser

    async def index(self, _request):
        return web.FileResponse(WEB / "index.html")


async def background(app):
    state = app["state"]
    await state.ari.start()
    tasks = [asyncio.create_task(state.ari.events(state.engine.handle)), asyncio.create_task(state.engine.run())]
    yield
    for task in tasks:
        task.cancel()
    await state.ari.close()




def build(state):
    app = web.Application(middlewares=[security], client_max_size=64 * 1024 * 1024)
    app["state"] = state
    app.cleanup_ctx.append(background)
    app.add_routes([
        web.get("/", state.index), web.post("/api/login", state.login), web.post("/api/logout", state.logout), web.get("/api/me", state.me),
        web.get("/api/settings", state.get_settings), web.post("/api/settings", state.save_settings),
        web.get("/api/users", state.users), web.post("/api/users", state.add_user),
        web.get("/api/campaigns", state.campaigns), web.post("/api/campaigns", state.save_campaign),
        web.post("/api/campaigns/{id:\\d+}/leads", state.upload_leads), web.post("/api/dnc", state.dnc_add),
        web.post("/api/agent/{action}", state.agent_action), web.post("/api/monitor", state.monitor),
        web.get("/api/leads", state.leads), web.get("/api/callbacks", state.callbacks), web.get("/api/time", state.time_report),
        web.post("/api/campaigns/{id:\\d+}/recycle", state.recycle),
        web.get("/api/live", state.live), web.get("/api/report", state.report), web.get("/api/recordings/{id:\\d+}", state.recording),
        web.get("/ws/events", state.events), web.get("/ws/sip", state.sip_proxy),
        web.static("/static", WEB),
    ])
    return app


def main():
    parser = argparse.ArgumentParser(description="MOX Dialer")
    parser.add_argument("--db", default=os.environ.get("MOX_DIALER_DB", "/var/lib/mox-dialer/dialer.db"))
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    parser.add_argument("--ari", default="http://127.0.0.1:8088")
    parser.add_argument("--sip-conf", default="/etc/asterisk/pjsip_mox.conf")
    parser.add_argument("--create-admin", metavar="USERNAME")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    db = DB(args.db)
    if args.create_admin:
        password = secrets.token_urlsafe(14)
        db.add_user(args.create_admin, password, "admin")
        print(f"Admin {args.create_admin} created. Password: {password}")
        return 0
    ari = Ari(args.ari, os.environ.get("MOX_ARI_USER", "moxdialer"), os.environ["MOX_ARI_PASSWORD"])
    ws = args.ari.replace("http", "ws", 1) + "/ws"
    state = App(db, ari, args.sip_conf, bool(args.cert), ws)
    context = None
    if args.cert:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
    web.run_app(build(state), host=args.host, port=args.port, ssl_context=context, access_log=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
