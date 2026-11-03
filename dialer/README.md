# MOX Dialer

A call center dialer built on Asterisk, the phone engine VICIdial also uses. Modo stays your CRM.

## Install

On MOX, run `mox get dialer`. On an Ubuntu server, copy this folder over and run `sudo ./install.sh`. The installer prints the address and the admin password.

Then open **Settings**, add your SIP provider's server, username and password, and add your agents under **Team**.

## What it does

- Manual, progressive and predictive outbound dialing
- Inbound calls with a queue, routed by campaign number
- Browser phone, hold, keypad digits, three-way calls and warm transfers
- Pause reasons, wrap-up results, callbacks and lead search
- Campaigns, CSV lead upload, scripts, and recycling finished leads
- Live monitor with agent timers, queue, campaign numbers, listen, whisper and barge
- Call recording, call reports and agent time reports
- AI Coach: hears the customer, then suggests what to say and what to avoid
- Number lookup through your Twilio account: registered caller name in the US, plus line type and carrier
- Do-not-call list, calling hours by the lead's time zone, and abandoned-call protection

Not built yet: answering machine detection, phone menus (IVR), multiple carriers, custom result codes and lead-list import rules.

Predictive dialing drops to one call per free agent when a campaign's 30-day abandoned rate reaches 3%. Leads with no valid state or time zone are never dialed.

Calling rules are safeguards, not legal advice. Check TCPA, Do Not Call and state rules with a lawyer before calling.

## Connect to Modo

Add a Modo webhook URL and secret in **Settings**. After each call, MOX Dialer sends JSON with the call, agent, campaign and result, signed in the `X-MOX-Signature` header using HMAC-SHA256. The open link can use `{phone}`.

## Network

Open TCP 8443, UDP 5060 and UDP 10000-20000. The installer uses a self-signed certificate. Replace it with a real one for agents, because browsers need trusted HTTPS for a smooth microphone setup.
