"use strict";
const app = document.getElementById("app");
const remote = document.getElementById("remote");
let liveTimer = null, coachNote = null, held = false, numberInfo = null;
let me = null, view = "", phone = null, session = null, events = null, current = null;

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "on") Object.entries(value).forEach(([name, fn]) => node.addEventListener(name, fn));
    else if (key === "class") node.className = value;
    else if (key in node && key !== "list") node[key] = value;
    else node.setAttribute(key, value);
  }
  kids.flat().forEach(kid => kid != null && node.append(kid));
  return node;
}
async function api(path, body, raw) {
  const options = body === undefined ? {} : { method: "POST", headers: raw ? {"content-type": "text/plain"} : {"content-type": "application/json"}, body: raw ? body : JSON.stringify(body) };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}
const field = (label, input) => el("label", {}, label, input);
const clock = seconds => { const s = Math.round(seconds || 0); return `${Math.floor(s / 3600)}h ${Math.floor(s / 60) % 60}m`; };
const when = stamp => stamp ? new Date(stamp * 1000).toLocaleString() : "";
function report(node, promise, done) { node.textContent = ""; promise.then(done).catch(error => { node.textContent = error.message; }); }

function login() {
  const user = el("input", {placeholder: "Username", autocomplete: "username", required: true});
  const pass = el("input", {type: "password", placeholder: "Password", autocomplete: "current-password", required: true});
  const error = el("div", {class: "error"});
  app.replaceChildren(el("div", {class: "login"}, el("form", {on: {submit(event) {
    event.preventDefault();
    report(error, api("/api/login", {username: user.value, password: pass.value}), data => { me = data; start(); });
  }}}, el("div", {class: "brand"}, "MOX"), user, pass, el("button", {class: "btn main"}, "Sign in"), error)));
}

const NAV = {
  agent: [["dial", "Dial"], ["callbacks", "Callbacks"]],
  supervisor: [["live", "Monitor"], ["dial", "Dial"], ["leads", "Leads"], ["reports", "Reports"]],
  admin: [["live", "Monitor"], ["dial", "Dial"], ["campaigns", "Campaigns"], ["leads", "Leads"], ["team", "Team"], ["reports", "Reports"], ["settings", "Settings"]],
};
function start() {
  connectEvents();
  go(NAV[me.role][0][0]);
}
function go(name) {
  view = name;
  clearInterval(liveTimer);
  const body = el("section");
  app.replaceChildren(el("div", {class: "shell"}, el("nav", {}, el("div", {class: "brand"}, "MOX"),
    NAV[me.role].map(([key, label]) => el("button", {class: key === name ? "on" : "", on: {click: () => go(key)}}, label)),
    el("button", {on: {click: () => api("/api/logout", {}).then(() => location.reload())}}, "Sign out")), body));
  ({dial, live, campaigns, team, reports, settings, leads, callbacks})[name](body);
}
function connectEvents() {
  events = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`);
  events.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === "agent") { me.status = message.status; if (message.call_id) (current = current || {}).call_id = message.call_id; if (view === "dial") renderAgent(); }
    if (message.type === "lookup") { numberInfo = message; if (view === "dial") renderAgent(); }
    if (message.type === "call") { current = message; coachNote = null; numberInfo = null; held = false; if (view === "dial") renderAgent(); }
    if (message.type === "coach") { coachNote = message; if (view === "dial") renderAgent(); }
  };
  events.onclose = () => setTimeout(connectEvents, 2000);
}

// ---- Browser phone -------------------------------------------------------
function connectPhone(status) {
  if (phone) return;
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const socket = new JsSIP.WebSocketInterface(`${scheme}://${location.host}/ws/sip`);
  socket.via_transport = location.protocol === "https:" ? "wss" : "ws";
  phone = new JsSIP.UA({sockets: [socket], uri: `sip:${me.sip_user}@mox.local`, authorization_user: me.sip_user, password: me.sip_pass, register: true, session_timers: false});
  phone.on("registered", () => {
    status.textContent = "Phone registered. Connecting line…";
    session = phone.call("sip:8000@mox.local", {mediaConstraints: {audio: true, video: false}, pcConfig: {iceServers: [{urls: "stun:stun.l.google.com:19302"}]}, rtcOfferConstraints: {offerToReceiveAudio: true}});
    session.connection.addEventListener("track", event => { remote.srcObject = event.streams[0]; });
    session.on("confirmed", () => { status.textContent = "Line connected."; });
    session.on("failed", event => { status.textContent = `Line failed: ${event.cause}`; closePhone(); });
    session.on("ended", () => { status.textContent = "Line closed."; closePhone(); });
  });
  phone.on("registrationFailed", event => { status.textContent = `Phone couldn't register: ${event.cause}`; closePhone(); });
  phone.start();
}
function closePhone() { if (phone) { phone.stop(); phone = null; session = null; } }

// ---- Agent ---------------------------------------------------------------
let agentArea = null, campaignList = [];
async function dial(body) {
  campaignList = await api("/api/campaigns");
  agentArea = el("div");
  body.append(el("h1", {}, "Dial"), agentArea);
  renderAgent();
}
function renderAgent() {
  if (!agentArea) return;
  const status = me.status || "offline";
  const pick = el("select", {}, campaignList.map(item => el("option", {value: item.id}, item.name)));
  const number = el("input", {placeholder: "Phone number"});
  const line = el("div", {class: "note"}, phone ? "Line connected." : "Your browser will ask to use the microphone.");
  if (["paused", "ready"].includes(status) && !phone) status_note(line);
  const error = el("div", {class: "error"});
  const run = (path, data) => report(error, api(`/api/agent/${path}`, data), result => { me.status = result.status; renderAgent(); });
  const controls = el("div", {class: "row"});
  if (!phone) controls.append(el("button", {class: "btn main", on: {click: () => connectPhone(line)}}, "Connect phone"));
  if (phone && status === "paused") controls.append(el("button", {class: "btn main", on: {click: () => run("ready", {campaign_id: Number(pick.value)})}}, "Go ready"));
  if (phone && status === "ready") {
    const code = el("select", {class: "short"}, el("option", {value: ""}, "Pause reason"), me.pause_codes.map(value => el("option", {value}, value)));
    controls.append(code, el("button", {class: "btn", on: {click: () => run("pause", {code: code.value})}}, "Pause"));
  }
  if (status === "incall") {
    const other = el("input", {class: "short", placeholder: "Transfer number"}), digits = el("input", {class: "short", placeholder: "Keypad digits"});
    controls.append(el("button", {class: "btn bad", on: {click: () => run("hangup", {})}}, "Hang up"),
      el("button", {class: "btn", on: {click: () => { held = !held; run("hold", {on: held}); }}}, held ? "Resume" : "Hold"), digits,
      el("button", {class: "btn", on: {click: () => run("digits", {digits: digits.value})}}, "Send"), other,
      el("button", {class: "btn", on: {click: () => run("add_party", {phone: other.value})}}, "Add caller"),
      el("button", {class: "btn", on: {click: () => run("leave_transfer", {})}}, "Transfer and leave"),
      el("button", {class: "btn", on: {click: () => run("drop_party", {})}}, "Drop caller"));
  }
  const parts = [el("div", {class: "card"}, el("div", {class: "row"}, el("span", {class: `tag ${status}`}, status), line),
    el("div", {class: "form"}, field("Campaign", pick)), el("p"), controls, error)];
  if (["paused", "ready"].includes(status)) parts.push(el("div", {class: "card"}, el("h2", {}, "Manual dial"), el("div", {class: "row"}, number,
    el("button", {class: "btn", on: {click: () => run("dial", {phone: number.value, campaign_id: Number(pick.value)})}}, "Call"))));
  if (current && current.phone && ["incall", "wrapup"].includes(status)) parts.push(leadCard());
  if (coachNote && status === "incall") parts.push(coachCard());
  if (current && current.call_id && status === "wrapup") parts.push(resultCard(error));
  agentArea.replaceChildren(...parts);
}
function status_note(line) { line.textContent = "Reconnect your phone to keep taking calls."; }
function leadCard() {
  const lead = current.lead || {};
  const campaign = campaignList.find(item => item.id === lead.campaign_id);
  const modo = me.modo_open_url ? me.modo_open_url.replace("{phone}", encodeURIComponent(current.phone)) : "";
  return el("div", {class: "card"}, el("div", {class: "lead"}, `${lead.first_name || ""} ${lead.last_name || ""}`.trim() || current.phone),
    el("div", {class: "note"}, current.phone), numberInfo ? el("div", {class: "note"}, [numberInfo.caller_name, numberInfo.line_type, numberInfo.carrier, numberInfo.country].filter(Boolean).join(" · ")) : null, campaign && campaign.script ? el("p", {}, campaign.script) : null,
    modo.startsWith("https://") ? el("a", {class: "btn", href: modo, target: "_blank", rel: "noreferrer"}, "Open in Modo") : null);
}
function coachCard() {
  return el("div", {class: "card coach"}, el("h2", {}, "AI Coach"), el("div", {class: "note"}, `Customer: ${coachNote.heard || ""}`),
    coachNote.say ? el("p", {class: "say"}, `Say: ${coachNote.say}`) : null, coachNote.avoid ? el("p", {class: "avoid"}, `Avoid: ${coachNote.avoid}`) : null,
    coachNote.signal && coachNote.signal !== "neutral" ? el("span", {class: "tag"}, coachNote.signal.replace("_", " ")) : null);
}
async function callbacks(body) {
  const rows = await api("/api/callbacks");
  body.append(el("h1", {}, "My callbacks"), el("div", {class: "card scroll"}, el("table", {}, el("tr", {}, ["Name", "Phone", "When", "Notes"].map(h => el("th", {}, h))),
    rows.map(row => el("tr", {}, el("td", {}, `${row.first_name} ${row.last_name}`), el("td", {}, row.phone), el("td", {}, when(row.next_at)), el("td", {}, row.notes))))));
}
async function leads(body) {
  const search = el("input", {placeholder: "Search by name or phone"}), area = el("div", {class: "card scroll"});
  const load = async () => { const rows = await api(`/api/leads?q=${encodeURIComponent(search.value)}`);
    area.replaceChildren(el("table", {}, el("tr", {}, ["Name", "Phone", "State", "Status", "Attempts"].map(h => el("th", {}, h))),
      rows.map(row => el("tr", {}, el("td", {}, `${row.first_name} ${row.last_name}`), el("td", {}, row.phone), el("td", {}, row.state), el("td", {}, row.status), el("td", {}, String(row.attempts)))))); };
  search.addEventListener("input", load);
  body.append(el("h1", {}, "Leads"), el("div", {class: "card"}, search), area);
  load();
}
function resultCard(error) {
  const choice = el("select", {}, [["sale", "Sale"], ["interested", "Interested"], ["callback", "Call back"], ["not_interested", "Not interested"], ["voicemail", "Voicemail"], ["wrong_number", "Wrong number"], ["dnc", "Do not call"]].map(([value, label]) => el("option", {value}, label)));
  const notes = el("textarea", {placeholder: "Notes"});
  return el("div", {class: "card"}, el("h2", {}, "Call result"), el("div", {class: "form"}, field("Result", choice), el("div", {class: "full"}, notes)), el("p"),
    el("button", {class: "btn main", on: {click: () => report(error, api("/api/agent/disposition", {call_id: current.call_id, disposition: choice.value, notes: notes.value}), result => { me.status = result.status; current = null; renderAgent(); })}}, "Save"));
}

// ---- Live ----------------------------------------------------------------
async function live(body) {
  const line = el("div", {class: "note"}, phone ? "Monitor line connected." : "Connect your line to listen, whisper or barge.");
  const error = el("div", {class: "error"}), area = el("div");
  const connect = el("button", {class: "btn main", on: {click: () => connectPhone(line)}}, "Connect monitor line");
  const stop = el("button", {class: "btn", on: {click: () => report(error, api("/api/monitor", {mode: "stop"}), () => {})}}, "Stop listening");
  body.append(el("h1", {}, "Monitor"), el("div", {class: "card row"}, connect, stop, line), error, area);
  const watch = (agent, mode) => report(error, api("/api/monitor", {agent_id: agent, mode}), () => {});
  const draw = async () => {
    const data = await api("/api/live");
    const count = status => data.agents.filter(a => a.status === status).length;
    area.replaceChildren(el("div", {class: "grid"}, stat(data.agents.length, "Signed in"), stat(count("ready"), "Waiting"), stat(count("incall"), "On call"), stat(count("paused"), "Paused"), stat(count("wrapup"), "Wrap-up"), stat(data.ringing, "Ringing"), stat(data.queue.length, "In queue")), el("p"),
      el("div", {class: "card scroll"}, el("h2", {}, "Agents"), el("table", {}, el("tr", {}, ["Agent", "Status", "Time", "Customer", "Direction", "Reason", ""].map(h => el("th", {}, h))),
        data.agents.map(agent => el("tr", {}, el("td", {}, agent.name), el("td", {}, el("span", {class: `tag ${agent.status}`}, agent.held ? "hold" : agent.status)), el("td", {}, duration(agent.seconds)), el("td", {}, agent.phone), el("td", {}, agent.direction), el("td", {}, agent.pause_code),
          el("td", {class: "actions"}, agent.status === "incall" ? ["listen", "whisper", "barge"].map(mode => el("button", {class: "btn", on: {click: () => watch(agent.id, mode)}}, mode[0].toUpperCase() + mode.slice(1))) : null))))),
      el("div", {class: "card scroll"}, el("h2", {}, "Campaigns today"), el("table", {}, el("tr", {}, ["Campaign", "Mode", "Dial level", "Leads left", "Calls", "Sales", "Abandoned"].map(h => el("th", {}, h))),
        data.campaigns.map(row => el("tr", {}, el("td", {}, row.name), el("td", {}, row.mode), el("td", {}, String(row.ratio)), el("td", {}, String(row.left_leads)), el("td", {}, String(row.calls)), el("td", {}, String(row.sales)), el("td", {class: row.abandon_rate >= 3 ? "avoid" : ""}, `${row.abandon_rate}%`))))),
      data.queue.length ? el("div", {class: "card scroll"}, el("h2", {}, "Inbound queue"), el("table", {}, data.queue.map(item => el("tr", {}, el("td", {}, item.phone), el("td", {}, duration(item.seconds)))))) : "");
  };
  await draw();
  liveTimer = setInterval(() => draw().catch(() => {}), 2000);
}
const duration = seconds => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
const stat = (value, label) => el("div", {class: "card stat"}, el("b", {}, String(value)), el("span", {}, label));

// ---- Campaigns -----------------------------------------------------------
async function campaigns(body) {
  const rows = await api("/api/campaigns");
  const name = el("input"), mode = el("select", {}, ["manual", "progressive", "predictive"].map(value => el("option", {value}, value)));
  const ratio = el("input", {type: "number", step: "0.1", min: "1", max: "4", value: "1.2"}), caller = el("input", {placeholder: "+1 415 555 0100"});
  const from = el("input", {type: "number", value: 9, min: 8, max: 21}), to = el("input", {type: "number", value: 20, min: 8, max: 21});
  const did = el("input", {placeholder: "Inbound number"}), doRules = el("textarea", {placeholder: "What agents should always do"}), dontRules = el("textarea", {placeholder: "What agents must never say"});
  const script = el("textarea"), active = el("select", {}, [["0", "Stopped"], ["1", "Running"]].map(([value, label]) => el("option", {value}, label)));
  const error = el("div", {class: "error"});
  const file = el("input", {type: "file", accept: ".csv"}), target = el("select", {}, rows.map(row => el("option", {value: row.id}, row.name))), upload = el("div", {class: "note"});
  body.append(el("h1", {}, "Campaigns"), el("div", {class: "card scroll"}, el("table", {}, el("tr", {}, ["Name", "Mode", "Status", "Leads", "Left", "Abandoned"].map(h => el("th", {}, h))),
    rows.map(row => el("tr", {}, el("td", {}, row.name), el("td", {}, row.mode), el("td", {}, row.active ? "Running" : "Stopped"), el("td", {}, String(row.leads)), el("td", {}, String(row.remaining)),
      el("td", {}, `${row.abandon_rate}%`))))),
    el("div", {class: "card"}, el("h2", {}, "New campaign"), el("div", {class: "form"}, field("Name", name), field("Dialing", mode), field("Calls per free agent", ratio), field("Caller ID", caller),
      field("Start hour (lead's time)", from), field("End hour (lead's time)", to), field("Status", active), field("Inbound number", did), el("label", {class: "full"}, "Agent script", script), el("label", {class: "full"}, "AI Coach: always do", doRules), el("label", {class: "full"}, "AI Coach: never say", dontRules)), el("p"),
      el("button", {class: "btn main", on: {click: () => report(error, api("/api/campaigns", {name: name.value, mode: mode.value, ratio: ratio.value, caller_id: caller.value, start_hour: from.value, end_hour: to.value, active: active.value === "1", script: script.value, did: did.value, coach_do: doRules.value, coach_dont: dontRules.value}), () => go("campaigns"))}}, "Save"), error),
    el("div", {class: "card"}, el("h2", {}, "Upload leads"), el("p", {class: "note"}, "CSV columns: phone, first_name, last_name, state, timezone. Leads with no state or time zone are never dialed."),
      el("div", {class: "form"}, field("Campaign", target), field("File", file)), el("p"),
      el("button", {class: "btn", on: {click: async () => { if (!file.files[0]) return; report(upload, api(`/api/campaigns/${target.value}/leads`, await file.files[0].text(), true), result => { upload.textContent = `${result.added} added, ${result.skipped} skipped, ${result.no_timezone} with no time zone.`; }); }}}, "Upload"), upload));
}

// ---- Team, reports, settings ---------------------------------------------
async function team(body) {
  const rows = await api("/api/users");
  const user = el("input"), pass = el("input", {type: "password", placeholder: "At least 10 characters"}), role = el("select", {}, ["agent", "supervisor", "admin"].map(value => el("option", {value}, value))), error = el("div", {class: "error"});
  const dnc = el("textarea", {placeholder: "One phone number per line"}), done = el("div", {class: "note"});
  body.append(el("h1", {}, "Team"), el("div", {class: "card scroll"}, el("table", {}, el("tr", {}, ["User", "Role", "Line"].map(h => el("th", {}, h))),
    rows.map(row => el("tr", {}, el("td", {}, row.username), el("td", {}, row.role), el("td", {}, row.sip_user || ""))))),
    el("div", {class: "card"}, el("h2", {}, "Add person"), el("div", {class: "form"}, field("Username", user), field("Password", pass), field("Role", role)), el("p"),
      el("button", {class: "btn main", on: {click: () => report(error, api("/api/users", {username: user.value, password: pass.value, role: role.value}), () => go("team"))}}, "Add"), error),
    el("div", {class: "card"}, el("h2", {}, "Do-not-call list"), dnc, el("p"), el("button", {class: "btn", on: {click: () => report(done, api("/api/dnc", dnc.value, true), result => { done.textContent = `${result.added} numbers added.`; dnc.value = ""; })}}, "Add numbers"), done));
}
async function reports(body) {
  const data = await api("/api/report?days=1"), totals = data.totals;
  const times = await api("/api/time");
  body.append(el("h1", {}, "Today"), el("div", {class: "grid"}, stat(totals.calls || 0, "Calls"), stat(totals.answered || 0, "Answered"), stat(totals.sales || 0, "Sales"), stat(totals.abandoned || 0, "Abandoned"), stat(clock(totals.talk), "Talk time")), el("p"),
    el("div", {class: "card scroll"}, el("h2", {}, "Agents"), el("table", {}, el("tr", {}, ["Agent", "Calls", "Sales", "Talk"].map(h => el("th", {}, h))), data.agents.map(row => el("tr", {}, el("td", {}, row.agent), el("td", {}, String(row.calls)), el("td", {}, String(row.sales || 0)), el("td", {}, clock(row.talk)))))),
    el("div", {class: "card scroll"}, el("h2", {}, "Agent time"), el("table", {}, el("tr", {}, ["Agent", "State", "Reason", "Time"].map(h => el("th", {}, h))), times.map(row => el("tr", {}, el("td", {}, row.agent), el("td", {}, row.status), el("td", {}, row.code), el("td", {}, clock(row.seconds)))))),
    el("div", {class: "card scroll"}, el("h2", {}, "Recent calls"), el("table", {}, el("tr", {}, ["Time", "Phone", "Agent", "Outcome", "Result", "Recording"].map(h => el("th", {}, h))),
      data.recent.map(row => el("tr", {}, el("td", {}, when(row.started)), el("td", {}, row.phone), el("td", {}, row.agent || ""), el("td", {}, row.outcome), el("td", {}, row.disposition), el("td", {}, row.recording ? el("a", {class: "btn", href: `/api/recordings/${row.id}`}, "Play") : null))))));
}
async function settings(body) {
  const data = await api("/api/settings");
  const box = (key, label, type = "text") => { const input = el("input", {type, value: data[key] || ""}); input.dataset.key = key; return field(label, input); };
  const hidden = key => el("input", {type: "password", placeholder: data[`${key}_set`] ? "Saved" : ""});
  const pass = hidden("trunk_pass"), secret = hidden("modo_secret"), sttKey = hidden("stt_key"), llmKey = hidden("llm_key"), twilioToken = hidden("twilio_token");
  const coachOn = el("select", {}, [["0", "Off"], ["1", "On"]].map(([value, label]) => el("option", {value, selected: (data.coach_enabled || "0") === value}, label)));
  const record = el("select", {}, [["1", "On"], ["0", "Off"]].map(([value, label]) => el("option", {value, selected: (data.record_calls || "1") === value}, label)));
  const form = el("div", {class: "form"}, box("twilio_sid", "Twilio Lookup SID"), field("Twilio Lookup token", twilioToken), box("trunk_host", "SIP server"), box("trunk_user", "SIP username"), field("SIP password", pass), box("caller_id", "Default caller ID"), field("Record calls", record));
  const modo = el("div", {class: "form"}, box("modo_webhook", "Modo webhook URL"), field("Webhook secret", secret), box("modo_open_url", "Open-in-Modo link, with {phone}"));
  const coachForm = el("div", {class: "form"}, field("AI Coach", coachOn), field("OpenAI key for speech", sttKey), field("Claude key for coaching", llmKey), box("stt_model", "Speech model"), box("llm_model", "Coaching model"));
  const error = el("div", {class: "error"});
  body.append(el("h1", {}, "Settings"), el("div", {class: "card"}, el("h2", {}, "Phone line"), form), el("div", {class: "card"}, el("h2", {}, "AI Coach"), el("p", {class: "note"}, "Call audio goes to these services. Tell customers about recording and AI where the law requires it."), coachForm), el("div", {class: "card"}, el("h2", {}, "Modo"), modo),
    el("button", {class: "btn main", on: {click: () => {
      const values = {trunk_pass: pass.value, modo_secret: secret.value, stt_key: sttKey.value, llm_key: llmKey.value, twilio_token: twilioToken.value, record_calls: record.value, coach_enabled: coachOn.value};
      [...form.querySelectorAll("[data-key]"), ...modo.querySelectorAll("[data-key]"), ...coachForm.querySelectorAll("[data-key]")].forEach(input => { values[input.dataset.key] = input.value; });
      report(error, api("/api/settings", values), () => go("settings"));
    }}}, "Save"), error);
}

api("/api/me").then(data => { me = data; start(); }).catch(login);
