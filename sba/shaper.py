# sba/shaper.py
import platform
import subprocess
from .config import TC_DRY_RUN, PRIORITY_BANDWIDTH, DEFAULT_IFACE
from .db import log_event

def _run_cmd(cmd_list, dry_run=TC_DRY_RUN):
    cmd_str = " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list
    if dry_run:
        print("[DRY RUN]", cmd_str)
        log_event("DEBUG", f"DRY RUN: {cmd_str}")
        return 0, "DRY"
    try:
        result = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT, text=True)
        log_event("INFO", f"Executed: {cmd_str}")
        return 0, result
    except subprocess.CalledProcessError as e:
        log_event("ERROR", f"Command failed ({cmd_str}): {e.output}")
        return e.returncode, e.output

def _ps_run(ps_command):
    return _run_cmd(["powershell", "-Command", ps_command], dry_run=TC_DRY_RUN)

def apply_shaping_windows(ip: str, priority: int):
    kbps = PRIORITY_BANDWIDTH.get(priority, 20000)
    # If blocked (kbps == 0) set a policy that throttles to 1 bit (effectively blocked) or remove routes
    if kbps == 0:
        bits_per_sec = 1
    else:
        bits_per_sec = int(kbps * 1000)
    policy_name = f"SBA_{ip.replace('.', '_')}"
    ps = f"New-NetQosPolicy -Name '{policy_name}' -IPDstPrefix '{ip}/32' -ThrottleRateActionBitsPerSecond {bits_per_sec}"
    rc, out = _ps_run(ps)
    log_event("INFO" if rc == 0 else "ERROR", f"Windows QoS applied for {ip} at {bits_per_sec} bps")
    return rc, out

def remove_shaping_windows(ip: str):
    policy_name = f"SBA_{ip.replace('.', '_')}"
    ps = f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false"
    rc, out = _ps_run(ps)
    if rc == 0:
        log_event("INFO", f"Removed Windows QoS policy: {policy_name}")
    return rc, out

def apply_shaping_linux(iface, ip, kbps, flow_id):
    # kbps=0 -> set very low rate or create blackhole (we use 1kbit)
    rate = f"{max(1, kbps)}kbit"
    cmds = [
        ["tc", "qdisc", "add", "dev", iface, "root", "handle", "1:", "htb", "default", "30"],
        ["tc", "class", "add", "dev", iface, "parent", "1:", "classid", f"1:{flow_id}", "htb", "rate", rate],
        ["tc", "filter", "add", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "1", "u32",
         "match", "ip", "dst", ip, "flowid", f"1:{flow_id}"]
    ]
    for cmd in cmds:
        _run_cmd(cmd)
    log_event("INFO", f"Applied Linux tc shaping on {iface} for {ip} → {rate}")
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
