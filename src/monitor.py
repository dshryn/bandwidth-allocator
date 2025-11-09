import time, threading, platform
from collections import defaultdict, deque
import math
from .db import insert_usage, log_event, list_devices, usage_history, set_priority
from .shaper import set_limit
from .config import AUTO_THRESHOLDS, load_auto_mode

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
        self.recent_totals = defaultdict(lambda: deque(maxlen=10))
        self.recent_priorities = defaultdict(lambda: deque(maxlen=3))

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
        for ip, c in list(self.counts.items()):
            total = c.get("rx", 0) + c.get("tx", 0)
            insert_usage(ip, c.get("rx", 0), c.get("tx", 0))
            self.recent_totals[ip].append(total)
            self.counts[ip] = {"rx": 0, "tx": 0}

        from . import config
        if config.AUTO_MODE:
            self._smart_allocator()

    def _calculate_stats(self, data):
        if not data:
            return 0, 0
        avg = sum(data) / len(data)
        if len(data) < 2:
            return avg, 0
        variance = sum([(x - avg) ** 2 for x in data]) / len(data)
        stdev = math.sqrt(variance)
        return avg, stdev

    def _smart_allocator(self):
        try:
            devices = list_devices()

            high_threshold = int(AUTO_THRESHOLDS.get("high_threshold", 200000))
            low_threshold = int(AUTO_THRESHOLDS.get("low_threshold", 1000000))

            for d in devices:
                ip = d["ip"]
                current_pr = d["priority"]

                if current_pr == 0:
                    continue

                hist_deque = self.recent_totals.get(ip)
                if not hist_deque:
                    continue

                hist = list(hist_deque)
                recent = hist[-1]

                if recent < high_threshold:
                    new_pr = 1
                elif recent > low_threshold:
                    new_pr = 3
                else:
                    new_pr = 2

                if len(hist) >= 5:
                    avg, stdev = self._calculate_stats(hist[:-1])
                    anomaly_threshold = avg + (2 * stdev)

                    if recent > anomaly_threshold and avg > high_threshold:
                        new_pr = 3
                        log_event("ALERT", f"Anomaly detected (2σ spike) {ip} avg={int(avg)} stdev={int(stdev)} recent={recent}")

                if new_pr != current_pr:
                    self.recent_priorities[ip].append(new_pr)

                    if new_pr < current_pr:
                        counts = self.recent_priorities[ip].count(new_pr)
                        if counts < 2 and len(self.recent_priorities[ip]) == 3:
                            new_pr = current_pr
                            log_event("DEBUG", f"Holding priority for {ip} at {current_pr} (Hysteresis)")

                if new_pr != current_pr:
                    self.recent_priorities[ip].clear()

                    set_priority(ip, new_pr)
                    set_limit(ip, new_pr)
                    log_event("AUTO", f"Smart allocator set {ip} -> {['Blocked','High','Normal','Low'][new_pr]}")
        except Exception as e:
            log_event("ERROR", f"Smart allocator failed: {e}")

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        from .config import load_auto_mode
        current_auto_mode = load_auto_mode()

        self._stop.clear()
        self._thread = threading.Thread(target=self._sniff_loop, daemon=True)
        self._thread.start()
        log_event("INFO", "Monitor started (Smart Allocator {})".format("ON" if current_auto_mode else "OFF"))

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        log_event("INFO", "Monitor stopped")