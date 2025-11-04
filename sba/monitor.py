# sba/monitor.py
import time, threading, platform
from collections import defaultdict, deque
from .db import insert_usage, log_event, list_devices, usage_history, set_priority
from .shaper import set_limit
from .config import AUTO_MODE, AUTO_THRESHOLDS

USE_SCAPY = False
try:
    from scapy.all import sniff, IP
    USE_SCAPY = True
except Exception:
    USE_SCAPY = False

class Monitor:
    def __init__(self, iface=None, interval=2.0):
        self.iface = iface
        self.interval = interval
        self.counts = defaultdict(lambda: {"rx": 0, "tx": 0})
        self._stop = threading.Event()
        self._thread = None
        # keep short history per ip to detect spikes
        self.recent_totals = defaultdict(lambda: deque(maxlen=5))

    def _proc(self, pkt):
        try:
            if IP in pkt:
                src = pkt[IP].src
                dst = pkt[IP].dst
                l = len(pkt)
                self.counts[src]["tx"] += l
                self.counts[dst]["rx"] += l
        except Exception:
            pass

    def _sniff_loop(self):
        if not USE_SCAPY:
            # simulation fallback
            import random
            while not self._stop.is_set():
                self.counts["192.168.0.2"]["rx"] += random.randint(1000, 10000)
                self.counts["192.168.0.3"]["tx"] += random.randint(1000, 9000)
                time.sleep(self.interval)
                self._flush()
            return

        while not self._stop.is_set():
            sniff(iface=self.iface, prn=self._proc, timeout=self.interval, store=False)
            self._flush()

    def _flush(self):
        # write counts to db and reset counters
        for ip, c in list(self.counts.items()):
            total = c.get("rx", 0) + c.get("tx", 0)
            insert_usage(ip, c.get("rx", 0), c.get("tx", 0))
            # update rolling history
            self.recent_totals[ip].append(total)
            # reset counters
            self.counts[ip] = {"rx": 0, "tx": 0}
        # smart allocator step
        if AUTO_MODE:
            self._smart_allocator()

    def _smart_allocator(self):
        try:
            devices = list_devices()
            # thresholds
            high_threshold = AUTO_THRESHOLDS.get("high_threshold", 200000)
            low_threshold = AUTO_THRESHOLDS.get("low_threshold", 1000000)
            spike_factor = AUTO_THRESHOLDS.get("anomaly_spike_factor", 5)

            for d in devices:
                ip = d["ip"]
                # compute recent average
                hist = list(self.recent_totals[ip]) if ip in self.recent_totals else []
                recent = hist[-1] if hist else 0
                avg = int(sum(hist)/len(hist)) if hist else 0
                # anomaly detection: sudden spike compared to avg
                if avg > 0 and recent > avg * spike_factor:
                    # anomaly - throttle and log
                    set_priority(ip, 3)
                    set_limit(ip, 3)
                    log_event("ALERT", f"Anomaly detected (spike) {ip} avg={avg} recent={recent}")
                    continue

                # normal auto policy
                if recent < high_threshold:
                    new_pr = 1  # High
                elif recent > low_threshold:
                    new_pr = 3  # Low
                else:
                    new_pr = 2  # Normal

                if new_pr != d["priority"]:
                    set_priority(ip, new_pr)
                    set_limit(ip, new_pr)
                    log_event("AUTO", f"Smart allocator set {ip} -> {['','High','Normal','Low'][new_pr]}")
        except Exception as e:
            log_event("ERROR", f"Smart allocator failed: {e}")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._sniff_loop, daemon=True)
        self._thread.start()
        log_event("INFO", "Monitor started (Smart Allocator {})".format("ON" if AUTO_MODE else "OFF"))

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        log_event("INFO", "Monitor stopped")
