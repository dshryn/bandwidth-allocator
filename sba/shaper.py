# sba/shaper.py
import platform
import subprocess
from .config import TC_DRY_RUN, PRIORITY_BANDWIDTH, DEFAULT_IFACE, PORT_PRIORITIES
from .db import log_event

def _run_cmd(cmd_list, dry_run=TC_DRY_RUN):
    cmd_str = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
    if dry_run:
        print("[DRY RUN]", cmd_str)
        log_event("DEBUG", f"DRY RUN: {cmd_str}")
        return 0, "DRY"
    try:
        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
        log_event("INFO", f"Executed: {cmd_str}")
        return 0, result.stdout
    except subprocess.CalledProcessError as e:
        log_event("ERROR", f"Command failed ({cmd_str}): {e.stderr.strip() or e.output.strip()}")
        return e.returncode, e.stderr.strip() or e.output.strip()
    except FileNotFoundError:
        log_event("ERROR", f"Command not found: {cmd_list[0]}")
        return 1, "Command not found"

def _ps_run(ps_command):
    return _run_cmd(["powershell", "-Command", ps_command], dry_run=TC_DRY_RUN)

def apply_shaping_windows(ip: str, priority: int):
    kbps = PRIORITY_BANDWIDTH.get(priority, 20000)
    if kbps == 0:
        bits_per_sec = 1
    else:
        bits_per_sec = int(kbps * 1000)
    policy_name = f"SBA_{ip.replace('.', '_')}"
    
    remove_shaping_windows(ip) 
    
    ps = f"New-NetQosPolicy -Name '{policy_name}' -IPDstPrefix '{ip}/32' -ThrottleRateActionBitsPerSecond {bits_per_sec}"
    rc, out = _ps_run(ps)
    log_event("INFO" if rc == 0 else "ERROR", f"Windows QoS applied for {ip} at {bits_per_sec} bps")
    return rc, out

def remove_shaping_windows(ip: str):
    policy_name = f"SBA_{ip.replace('.', '_')}"
    ps = f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false -ErrorAction SilentlyContinue"
    rc, out = _ps_run(ps)
    if rc == 0:
        log_event("INFO", f"Removed Windows QoS policy: {policy_name}")
    return rc, out

# --- Linux Shaping (Bidirectional + Port Awareness) ---

def _clear_linux_shaping(iface, ip, flow_id):
    # Clear device-specific filters and classes (prio 1)
    _run_cmd(["tc", "filter", "del", "dev", iface, "parent", "1:", "prio", "1", "u32", "match", "ip", "src", ip], dry_run=TC_DRY_RUN)
    _run_cmd(["tc", "class", "del", "dev", iface, "parent", "1:", "classid", f"1:{flow_id}"], dry_run=TC_DRY_RUN)
    
    # Clear port-specific filters (prio 0)
    for port in PORT_PRIORITIES.keys():
        _run_cmd(["tc", "filter", "del", "dev", iface, "parent", "1:", "prio", "0", "u32", "match", "ip", "src", ip, "match", "ip", "dport", str(port), "0xffff"], dry_run=TC_DRY_RUN)
        _run_cmd(["tc", "filter", "del", "dev", iface, "parent", "1:", "prio", "0", "u32", "match", "ip", "src", ip, "match", "ip", "sport", str(port), "0xffff"], dry_run=TC_DRY_RUN)

    # Simplified Ingress cleanup 
    _run_cmd(["tc", "filter", "del", "dev", iface, "parent", "ffff:", "prio", "1", "u32", "match", "ip", "dst", ip], dry_run=TC_DRY_RUN) 
    
    log_event("INFO", f"Cleared existing Linux tc shaping for {ip} on {iface}")


def apply_shaping_linux(iface, ip, kbps, flow_id):
    _clear_linux_shaping(iface, ip, flow_id)
    
    rate = f"{max(1, kbps)}kbit"
    high_rate = f"{PRIORITY_BANDWIDTH.get(1, 100000)}kbit"
    
    # --- Egress (Upload) Shaping Setup ---
    # 1. Setup root qdisc if not present
    _run_cmd(["tc", "qdisc", "add", "dev", iface, "root", "handle", "1:", "htb", "default", "30"], dry_run=TC_DRY_RUN)
    
    # 2. Add Class for Critical Ports (ID 1:10, uses High Rate)
    _run_cmd(["tc", "class", "add", "dev", iface, "parent", "1:", "classid", "1:10", "htb", "rate", high_rate], dry_run=TC_DRY_RUN)
    
    # 3. Add Filters for Critical Ports (Prio 0 - highest priority)
    for port, name in PORT_PRIORITIES.items():
        # Match Egress: SOURCE IP + DESTINATION PORT (Outbound)
        _run_cmd([
            "tc", "filter", "add", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "0", "u32",
            "match", "ip", "src", ip,
            "match", "ip", "dport", str(port), "0xffff",
            "flowid", "1:10"
        ])
        # Match Egress: SOURCE IP + SOURCE PORT (Inbound response on egress)
        _run_cmd([
            "tc", "filter", "add", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "0", "u32",
            "match", "ip", "src", ip,
            "match", "ip", "sport", str(port), "0xffff",
            "flowid", "1:10"
        ])

    # 4. Add Class for Device's General Traffic (ID 1:flow_id, uses calculated rate)
    _run_cmd(["tc", "class", "add", "dev", iface, "parent", "1:", "classid", f"1:{flow_id}", "htb", "rate", rate])

    # 5. Add Filter for Device's General Traffic (Prio 1 - lower priority, default catch-all)
    _run_cmd([
        "tc", "filter", "add", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "1", "u32",
        "match", "ip", "src", ip, "flowid", f"1:{flow_id}"
    ])
    
    # --- Ingress (Download) Setup (Simplified) ---
    _run_cmd(["tc", "qdisc", "add", "dev", iface, "handle", "ffff:", "ingress"], dry_run=TC_DRY_RUN)

    # Ingress Filter (Prio 1)
    _run_cmd([
        "tc", "filter", "add", "dev", iface, "protocol", "ip", "parent", "ffff:", "prio", "1", "u32",
        "match", "ip", "dst", ip, "flowid", f"1:{flow_id}" 
    ], dry_run=TC_DRY_RUN) 
    
    log_event("INFO", f"Applied Linux tc shaping on {iface} for {ip} → {rate} (Protocol Aware)")
    return 0, "Linux shaping applied"


def set_limit(ip: str, priority: int, iface=None):
    osn = platform.system().lower()
    iface = iface or DEFAULT_IFACE
    if osn.startswith("windows"):
        return apply_shaping_windows(ip, priority)
    else:
        kbps = PRIORITY_BANDWIDTH.get(priority, 20000)
        flow_id = int(ip.split(".")[-1]) if "." in ip else 100 
        return apply_shaping_linux(iface, ip, kbps, flow_id)