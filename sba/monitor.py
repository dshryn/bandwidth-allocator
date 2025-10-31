import time, threading
from collections import defaultdict
import platform
from .db import insert_usage, log_event

USE_SCAPY = False
try:
    from scapy.all import sniff, IP
    USE_SCAPY = True
except Exception:
    USE_SCAPY = False

class Monitor:
    def __init__(self, iface=None, interval=1.0):
        self.iface = iface
        self.interval = interval
        self.counts = defaultdict(lambda: {"rx":0,"tx":0})
        self._stop = threading.Event()
        self._thread = None

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
            # fallback simulator
            import random
            while not self._stop.is_set():
                self.counts["192.168.0.2"]["rx"] += random.randint(1000,10000)
                self.counts["192.168.0.3"]["tx"] += random.randint(1000,9000)
                time.sleep(self.interval)
                self._flush()
            return

        while not self._stop.is_set():
            sniff(iface=self.iface, prn=self._proc, timeout=self.interval, store=False)
            self._flush()

    def _flush(self):
        # write counts to db and reset counters
        for ip, c in list(self.counts.items()):
            insert_usage(ip, c.get("rx",0), c.get("tx",0))
            # db historic logs
            self.counts[ip] = {"rx":0,"tx":0}

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._stop.clear()
        self._thread = threading.Thread(target=self._sniff_loop, daemon=True)
        self._thread.start()
        log_event("INFO", "Monitor started")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        log_event("INFO", "Monitor stopped")
