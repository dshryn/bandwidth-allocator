import platform, subprocess, shlex
from .config import TC_DRY_RUN
from .db import log_event

def _run(cmd, use_shell=False):
    if TC_DRY_RUN:
        print("[DRY RUN]", cmd)
        log_event("DEBUG", f"DRY RUN: {cmd}")
        return 0, ""
    try:
        res = subprocess.check_output(cmd if use_shell else shlex.split(cmd), text=True, stderr=subprocess.STDOUT)
        return 0, res
    except subprocess.CalledProcessError as e:
        log_event("ERROR", f"Command failed: {cmd} | {e.output}")
        return e.returncode, e.output

def apply_shaping_linux(iface, ip, rate_kbps, class_id):
    # egress shaping using htb
    _run(f"tc qdisc replace dev {iface} root handle 1: htb default 30")
    _run(f"tc class replace dev {iface} parent 1: classid 1:{class_id} htb rate {rate_kbps}kbps ceil {rate_kbps}kbps")
    _run(f"tc filter replace dev {iface} protocol ip parent 1: prio 1 u32 match ip dst {ip} flowid 1:{class_id}")
    log_event("INFO", f"Applied linux shaping {ip} {rate_kbps}kbps on {iface}")

def setup_ifb_ingress(iface):
    _run("modprobe ifb numifbs=1")
    _run("ip link add ifb0 type ifb")
    _run(f"ip link set dev ifb0 up")
    _run(f"tc qdisc add dev {iface} ingress")
    _run(f"tc filter add dev {iface} parent ffff: protocol ip u32 match u32 0 0 action mirred egress redirect dev ifb0")
    _run(f"tc qdisc add dev ifb0 root handle 1: htb default 30")
    log_event("INFO","IFB setup done")

def apply_shaping_windows(iface, ip, rate_kbps):
    # placeholder using powerShell NetQoSPolicy - requires admin (sample)
    # create throttle with Set-NetQosPolicy or using netsh traffic filters; dry run-
    ps = f"New-NetQosPolicy -Name 'SBA_{ip}' -IPDstPrefix {ip}/32 -ThrottleRateActionBitsPerSecond {rate_kbps*1000}"
    cmd = ["powershell","-Command", ps]
    return _run(cmd, use_shell=False)

def set_limit(ip, priority, iface="eth0"):
    # map priorities to kbps
    policy = {1:100000, 2:20000, 3:5000}
    rate = policy.get(priority, 20000)
    osn = platform.system().lower()
    class_id = int(ip.split(".")[-1]) if "." in ip else 100
    if osn.startswith("windows"):
        apply_shaping_windows(iface, ip, rate)
    else:
        apply_shaping_linux(iface, ip, rate, class_id)
