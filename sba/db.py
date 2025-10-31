import sqlite3, time
DB_PATH = "sba.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
  ip TEXT PRIMARY KEY, mac TEXT, hostname TEXT,
  priority INTEGER DEFAULT 2, last_seen REAL
);
CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT, ts REAL, bytes_rx INTEGER, bytes_tx INTEGER
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, level TEXT, message TEXT
);
"""

def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def upsert_device(ip, mac, hostname, priority=2):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO devices(ip,mac,hostname,priority,last_seen) VALUES(?,?,?,?,?) "
                 "ON CONFLICT(ip) DO UPDATE SET mac=excluded.mac, hostname=excluded.hostname, "
                 "priority=excluded.priority, last_seen=excluded.last_seen",
                 (ip,mac,hostname,priority,ts))
    conn.commit(); conn.close()

def insert_usage(ip, rx, tx):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO usage(ip,ts,bytes_rx,bytes_tx) VALUES(?,?,?,?)", (ip,ts,rx,tx))
    conn.commit(); conn.close()

def set_priority(ip, pr):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE devices SET priority=? WHERE ip=?", (pr, ip))
    conn.commit(); conn.close()

def list_devices():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT ip,mac,hostname,priority,last_seen FROM devices")
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows

def recent_usage(limit=200):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT ip,ts,bytes_rx,bytes_tx FROM usage ORDER BY ts DESC LIMIT ?", (limit,))
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows

def log_event(level, message):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO events(ts,level,message) VALUES(?,?,?)", (ts, level, message))
    conn.commit(); conn.close()
