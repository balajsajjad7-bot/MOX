"""SQLite storage. Every query uses parameters."""
import hashlib
import json
import os
import secrets
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, pass_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','supervisor','agent')), sip_user TEXT UNIQUE, sip_pass TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS campaigns(id INTEGER PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'manual' CHECK(mode IN ('manual','progressive','predictive')),
  ratio REAL DEFAULT 1.2, caller_id TEXT DEFAULT '', start_hour INTEGER DEFAULT 9, end_hour INTEGER DEFAULT 20, active INTEGER DEFAULT 0, script TEXT DEFAULT '', did TEXT DEFAULT '', coach_do TEXT DEFAULT '', coach_dont TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES campaigns(id), phone TEXT NOT NULL, first_name TEXT DEFAULT '',
  last_name TEXT DEFAULT '', state TEXT DEFAULT '', timezone TEXT DEFAULT '', status TEXT DEFAULT 'new', attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0,
  data TEXT DEFAULT '{}', UNIQUE(campaign_id, phone));
CREATE INDEX IF NOT EXISTS leads_pick ON leads(campaign_id, status, next_at);
CREATE TABLE IF NOT EXISTS dnc(phone TEXT PRIMARY KEY, added_at REAL, reason TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, campaign_id INTEGER, lead_id INTEGER, agent_id INTEGER, phone TEXT, direction TEXT DEFAULT 'out',
  started REAL, answered REAL, ended REAL, outcome TEXT DEFAULT '', disposition TEXT DEFAULT '', notes TEXT DEFAULT '', recording TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS calls_time ON calls(started);
CREATE TABLE IF NOT EXISTS lookups(phone TEXT PRIMARY KEY, data TEXT, at REAL);
CREATE TABLE IF NOT EXISTS agent_log(id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT, code TEXT DEFAULT '', started REAL, ended REAL);
"""


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2 ** 14, r=8, p=1).hex()
    return f"{salt}${digest}"


def check_password(password, stored):
    salt = stored.split("$", 1)[0]
    return secrets.compare_digest(hash_password(password, salt), stored)


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        if os.path.exists(path):
            os.chmod(path, 0o600)

    def all(self, sql, *args):
        return [dict(row) for row in self.conn.execute(sql, args)]

    def one(self, sql, *args):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def run(self, sql, *args):
        return self.conn.execute(sql, args).lastrowid

    def get_setting(self, key, default=""):
        row = self.one("SELECT value FROM settings WHERE key=?", key)
        return row["value"] if row else default

    def set_setting(self, key, value):
        self.run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", key, str(value))

    def add_user(self, username, password, role):
        sip_user = str(1000 + (self.one("SELECT COALESCE(MAX(id),0) m FROM users")["m"] + 1))
        return self.run(
            "INSERT INTO users(username,pass_hash,role,sip_user,sip_pass) VALUES(?,?,?,?,?)",
            username, hash_password(password), role, sip_user, secrets.token_urlsafe(24),
        )

    def is_dnc(self, phone):
        return self.one("SELECT 1 x FROM dnc WHERE phone=?", phone) is not None

    def add_dnc(self, phone, reason=""):
        self.run("INSERT OR IGNORE INTO dnc(phone,added_at,reason) VALUES(?,?,?)", phone, time.time(), reason)
        self.run("UPDATE leads SET status='dnc' WHERE phone=?", phone)

    def rate_counts(self, campaign_id, days=30):
        since = time.time() - days * 86400
        row = self.one(
            "SELECT SUM(answered IS NOT NULL) answered, SUM(outcome='abandoned') abandoned FROM calls WHERE campaign_id=? AND started>=?",
            campaign_id, since,
        )
        return row["answered"] or 0, row["abandoned"] or 0

    @staticmethod
    def dumps(value):
        return json.dumps(value, ensure_ascii=False)
