import platform, subprocess, shlex
from .config import TC_DRY_RUN, PRIORITY_BANDWIDTH
from .db import log_event

def _run_cmd(cmd_list, dry_run=TC_DRY_RUN):
    # cmd_list- list form for subprocess (no shell), or single string if shell true
    if dry_run:
        print("[DRY RUN] ", " ".join(cmd_list) if isinstance(cmd_list, list) else cmd_list)
        log_event("DEBUG", f"DRY RUN: {' '.join(cmd_list) if isinstance(cmd_list, list) else cmd_list}")
        return 0, "DRY"
    try:
        res = subprocess.check_output(cmd_list, stderr=subprocess.STDOUT, text=True)
        return 0, res
    except subprocess.CalledProcessError as e:
        log_event("ERROR", f"Command failed: {cmd_list} | {e.output}")
        return e.returncode, e.output

def _ps_run(ps_command):
    return _run_cmd(["powershell", "-Command", ps_command], dry_run=TC_DRY_RUN)

def apply_shaping_windows(ip: str, priority:int):
    # map priority to kbps
    kbps = PRIORITY_BANDWIDTH.get(priority, 20000)  # kbps
    bits_per_sec = int(kbps * 1000)  # convert to bits/sec for PowerShell param
    policy_name = f"SBA_{ip.replace('.','_')}"
    # New-NetQosPolicy cmd
    ps = f"New-NetQosPolicy -Name '{policy_name}' -IPDstPrefix '{ip}/32' -ThrottleRateActionBitsPerSecond {bits_per_sec}"
    rc, out = _ps_run(ps)
    if rc == 0:
        log_event("INFO", f"Applied Windows QoS {policy_name} -> {bits_per_sec}bps for {ip}")
    return rc, out

def remove_shaping_windows(ip: str):
    policy_name = f"SBA_{ip.replace('.','_')}"
    ps = f"Remove-NetQosPolicy -Name '{policy_name}' -Confirm:$false"
    rc, out = _ps_run(ps)
    if rc == 0:
        log_event("INFO", f"Removed Windows QoS {policy_name}")
    return rc, out

def set_limit(ip: str, priority:int, iface=None):
    osn = platform.system().lower()
    if osn.startswith("windows"):
        return apply_shaping_windows(ip, priority)
    else:
        # call linux shaper
        return apply_shaping_linux(iface or "eth0", ip, PRIORITY_BANDWIDTH.get(priority,20000), int(ip.split('.')[-1]) )
