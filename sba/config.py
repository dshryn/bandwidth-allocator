TC_DRY_RUN = 1  

DEFAULT_IFACE = "Ethernet" 

PRIORITY_BANDWIDTH = {
    0: 0,       # blocked -> 0 kbps
    1: 100000,  # High = 100 Mbps
    2: 20000,   # Normal = 20 Mbps
    3: 5000     # Low = 5 Mbps
}

PORT_PRIORITIES = {
    53: "DNS",       # DNS (UDP/TCP)
    22: "SSH",       # Secure Shell (TCP)
    123: "NTP",      # Network Time Protocol (UDP)
    443: "HTTPS",    # Web/Streaming (TCP)
}

AUTO_MODE = True

AUTO_THRESHOLDS = {

    "high_threshold": 20000,   # < 20,000 bytes -> High (Stable Low Usage)
    "low_threshold": 500000,   # > 500,000 bytes -> Low (Heavy Usage)
    
    "anomaly_spike_factor": 5
}

def load_auto_mode():
    from .db import get_config
    global AUTO_MODE
    AUTO_MODE = get_config("auto_mode", "True").lower() == "true"
    return AUTO_MODE