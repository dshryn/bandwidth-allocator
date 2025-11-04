# sba/config.py
# Global configuration for Smart Bandwidth Allocator

TC_DRY_RUN = 1  # 1 = dry run (no real shaping), 0 = execute shaping commands

DEFAULT_IFACE = "Ethernet"  # adjust for your machine ("Wi-Fi", "eth0", ...)

PRIORITY_BANDWIDTH = {
    0: 0,        # blocked -> 0 kbps
    1: 100000,   # High = 100 Mbps
    2: 20000,    # Normal = 20 Mbps
    3: 5000      # Low = 5 Mbps
}

# Smart auto-allocation (toggleable)
AUTO_MODE = True

# thresholds (bytes per monitoring interval) for auto decisions
AUTO_THRESHOLDS = {
    "high_threshold": 200000,   # < this -> High
    "low_threshold": 1000000,   # > this -> Low
    "anomaly_spike_factor": 5   # sudden spike factor threshold
}
