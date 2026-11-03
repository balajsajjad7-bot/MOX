"""Writes Asterisk's phone settings from the dialer's settings."""
import subprocess


def render(db):
    host = db.get_setting("trunk_host")
    user = db.get_setting("trunk_user")
    password = db.get_setting("trunk_pass")
    out = [
        "[transport-ws]\ntype=transport\nprotocol=ws\nbind=127.0.0.1:5098\n",
        "[transport-udp]\ntype=transport\nprotocol=udp\nbind=0.0.0.0:5060\n",
    ]
    for row in db.all("SELECT sip_user, sip_pass FROM users WHERE sip_user IS NOT NULL AND active=1"):
        name, secret = row["sip_user"], row["sip_pass"]
        out.append(
            f"[{name}]\ntype=endpoint\ncontext=mox-agents\ndisallow=all\nallow=ulaw,alaw\nwebrtc=yes\n"
            f"dtls_auto_generate_cert=yes\ntransport=transport-ws\nauth={name}-auth\naors={name}\n"
            f"[{name}-auth]\ntype=auth\nauth_type=userpass\nusername={name}\npassword={secret}\n"
            f"[{name}]\ntype=aor\nmax_contacts=1\nremove_existing=yes\n"
        )
    if host:
        out.append(
            f"[trunk]\ntype=endpoint\ncontext=mox-inbound\ndisallow=all\nallow=ulaw,alaw\ntransport=transport-udp\n"
            f"outbound_auth=trunk-auth\naors=trunk\nfrom_user={user}\nfrom_domain={host}\ndirect_media=no\n"
            f"[trunk-auth]\ntype=auth\nauth_type=userpass\nusername={user}\npassword={password}\n"
            f"[trunk]\ntype=aor\ncontact=sip:{host}\nqualify_frequency=60\n"
            f"[trunk-identify]\ntype=identify\nendpoint=trunk\nmatch={host}\n"
            f"[trunk-register]\ntype=registration\ntransport=transport-udp\noutbound_auth=trunk-auth\n"
            f"server_uri=sip:{host}\nclient_uri=sip:{user}@{host}\nretry_interval=60\n"
        )
    return "\n".join(out)


def apply(db, path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(render(db))
    subprocess.run(["asterisk", "-rx", "module reload res_pjsip.so"], check=False, capture_output=True)
