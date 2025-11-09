import sqlite3, time
import subprocess, platform
import socket
import re

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
CREATE TABLE IF NOT EXISTS blocked_devices (
  ip TEXT PRIMARY KEY, reason TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS config ( 
  key TEXT PRIMARY KEY, value TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_ip_ts ON usage(ip, ts);
"""

def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def set_config(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)", (key, str(value)))
    conn.commit(); conn.close()
    
def get_config(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT value FROM config WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def upsert_device(ip, mac, hostname, priority=2):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO devices(ip,mac,hostname,priority,last_seen) VALUES(?,?,?,?,?) "
                 "ON CONFLICT(ip) DO UPDATE SET mac=excluded.mac, hostname=excluded.hostname, "
                 "priority=excluded.priority, last_seen=excluded.last_seen",
                 (ip, mac, hostname, priority, ts))
    conn.commit(); conn.close()

def insert_usage(ip, rx, tx):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO usage(ip,ts,bytes_rx,bytes_tx) VALUES(?,?,?,?)", (ip, ts, rx, tx))
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

def usage_history(ip, limit=200):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT ts,bytes_rx,bytes_tx FROM usage WHERE ip=? ORDER BY ts DESC LIMIT ?", (ip, limit))
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows[::-1]

def log_event(level, message):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO events(ts,level,message) VALUES(?,?,?)", (ts, level, message))
    conn.commit(); conn.close()

def list_events(limit=50):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT ts,level,message FROM events ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows

def block_device(ip, reason="blocked"):
    ts = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO blocked_devices(ip,reason,ts) VALUES(?,?,?)", (ip, reason, ts))
    conn.commit(); conn.close()
    log_event("INFO", f"Device blocked: {ip} ({reason})")

def unblock_device(ip):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM blocked_devices WHERE ip=?", (ip,))
    conn.commit()
    conn.close()
    log_event("INFO", f"Device unblocked: {ip}")

def list_blocked():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT ip,reason,ts FROM blocked_devices")
    rows = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    conn.close()
    return rows

def get_default_gateway():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip.rsplit('.', 1)[0] + '.1'
    except Exception:
        return "192.168.1.1" 

def ping_gateway(gateway_ip):
    if platform.system().lower().startswith("windows"):
        cmd = ["ping", "-n", "4", "-w", "1000", gateway_ip]
        packet_loss_regex = r"Lost = (\d+)"
        delay_regex = r"Average = (\d+)"
    else: 
        cmd = ["ping", "-c", "4", "-W", "1", gateway_ip]
        packet_loss_regex = r"(\d+)% packet loss"
        delay_regex = r"min/avg/max/mdev = [\d.]+/([\d.]+)/"
    
    delay_ms = 0
    packet_loss_percent = 100
    
    try:
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=5)
        loss_match = re.search(packet_loss_regex, output)
        if loss_match:
            if platform.system().lower().startswith("windows"):
                lost_count = int(loss_match.group(1))
                packet_loss_percent = (lost_count / 4) * 100
            else:
                packet_loss_percent = float(loss_match.group(1))

        delay_match = re.search(delay_regex, output)
        if delay_match:
            delay_ms = float(delay_match.group(1))
            
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
        
    return delay_ms, packet_loss_percent

def metrics_summary():
    conn = sqlite3.connect(DB_PATH)
    ts_now = time.time()
    
    total = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    one_hour = ts_now - 3600
    active = conn.execute("SELECT COUNT(*) FROM devices WHERE last_seen>?",(one_hour,)).fetchone()[0]
    blocked = conn.execute("SELECT COUNT(*) FROM blocked_devices").fetchone()[0]

    five_seconds_ago = ts_now - 5
    throughput_rows = conn.execute("SELECT bytes_rx, bytes_tx FROM usage WHERE ts>?", (five_seconds_ago,)).fetchall()
    total_bytes_5s = sum(r[0] + r[1] for r in throughput_rows)
    
    avg_bytes_per_sample_row = conn.execute("SELECT AVG(bytes_rx+bytes_tx) FROM usage WHERE ts>?", (ts_now-300,)).fetchone()
    avg_bytes_per_sample = avg_bytes_per_sample_row[0] or 0
    
    throughput_bps = (total_bytes_5s / max(1, ts_now - five_seconds_ago)) * 8 
    throughput_mbps = round(throughput_bps / 1024 / 1024, 2)
    
    low_priority_count = conn.execute("SELECT COUNT(*) FROM devices WHERE priority=3").fetchone()[0]
    congestion_percent = round((low_priority_count / max(1, total)) * 100, 1)

    gateway_ip = get_default_gateway()
    delay_ms, packet_loss_percent = ping_gateway(gateway_ip)
    
    conn.close()
    
    return {
        "total_devices": total,
        "active_devices": active,
        "blocked_devices": blocked,
        "avg_bytes_per_sample": int(avg_bytes_per_sample),
        

        "throughput_mbps": throughput_mbps,
        "delay_ms": round(delay_ms, 1),
        "packet_loss_percent": round(packet_loss_percent, 1),
        "congestion_percent": congestion_percent
    }