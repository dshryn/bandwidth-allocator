import subprocess, platform, socket
import concurrent.futures 
from .db import upsert_device, log_event

def _resolve_and_upsert(ip, mac):
    hostname = ""
    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except Exception:
        pass
    
    upsert_device(ip, mac, hostname, priority=2)
    log_event("INFO", f"Discovered device {ip} {mac} {hostname}")
    return (ip, mac, hostname)

def arp_parse_windows():
    out = subprocess.check_output(["arp", "-a"], text=True)
    devices_info = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0][0].isdigit():
            ip = parts[0]
            mac = parts[1].replace('-', ':')
            devices_info.append((ip, mac))
    return devices_info

def arp_parse_linux():
    out = subprocess.check_output(["arp", "-an"], text=True)
    devices_info = []
    for line in out.splitlines():
        if "(" in line and ")" in line and " at " in line:
            ip = line.split("(")[1].split(")")[0]
            mac = line.split(" at ")[1].split()[0]
            devices_info.append((ip, mac))
    return devices_info

def scan(cidr=None):
    osname = platform.system().lower()
    
    devices_to_resolve = arp_parse_windows() if osname.startswith("windows") else arp_parse_linux()
    
    resolved_devices = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_device = {
            executor.submit(_resolve_and_upsert, ip, mac): (ip, mac)
            for ip, mac in devices_to_resolve
        }
        
        for future in concurrent.futures.as_completed(future_to_device):
            try:
                resolved_devices.append(future.result())
            except Exception as exc:
                log_event("ERROR", f"Hostname resolution generated an exception: {exc}")
                
    return resolved_devices