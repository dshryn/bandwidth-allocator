import subprocess, platform, socket
from .db import upsert_device, log_event

def arp_parse_windows():
    out = subprocess.check_output(["arp", "-a"], text=True)
    devices = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0][0].isdigit():
            ip = parts[0]
            mac = parts[1].replace('-', ':')
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except:
                hostname = ""
            devices.append((ip, mac, hostname))
    return devices

def arp_parse_linux():
    out = subprocess.check_output(["arp", "-an"], text=True)
    devices = []
    for line in out.splitlines():
        if "(" in line and ")" in line and " at " in line:
            ip = line.split("(")[1].split(")")[0]
            mac = line.split(" at ")[1].split()[0]
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except:
                hostname = ""
            devices.append((ip, mac, hostname))
    return devices

def scan(cidr=None):
    osname = platform.system().lower()
    devices = arp_parse_windows() if osname.startswith("windows") else arp_parse_linux()
    for ip, mac, hostname in devices:
        upsert_device(ip, mac, hostname, priority=2)
        log_event("INFO", f"Discovered device {ip} {mac} {hostname}")
    return devices
