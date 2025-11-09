# Bandwidth Allocator

A lightweight, host-based system designed to monitor, analyze, and manage bandwidth usage across devices in a Local Area Network (LAN). It automatically classifies devices into priority levels of **High**, **Normal**, **Low**, and **Blocked**, using short-term traffic statistics and anomaly detection.  
It then enforces bandwidth limits using **OS-level tools** (`tc` on Linux and PowerShell NetQos on Windows). A modern web dashboard (Flask + Plotly) allows real-time monitoring, manual overrides, and visualization of network performance metrics.


## Features
- Real-time packet capture and per-device bandwidth tracking  
- Automatic classification using statistical anomaly detection (2σ rule)  
- Hysteresis-based stability (prevents rapid priority flapping)  
- Per-device shaping using:
  - `tc` (Linux)
  - `New-NetQosPolicy` (Windows)
- Port-aware shaping (DNS/SSH/HTTPS/NTP always prioritized)  
- SQLite database for persistent usage history, logs, and config  
- Flask REST API + interactive dashboard (Plotly)  

## Navigate

- [Bandwidth Allocator](#bandwidth-allocator)
  - [Features](#features)
  - [Navigate](#navigate)
  - [Architecture Overview](#architecture-overview)
    - [System Modules](#system-modules)
    - [Data Flow](#data-flow)
  - [Requirements](#requirements)
    - [Software](#software)
    - [Install dependencies](#install-dependencies)
  - [System Tools](#system-tools)
  - [Quick Start](#quick-start)
    - [Clone and Setup](#clone-and-setup)
    - [Run](#run)
  - [Configuration (config.py)](#configuration-configpy)
  - [Working](#working)
    - [Monitoring](#monitoring)
    - [Smart Allocator](#smart-allocator)
    - [Shaper](#shaper)
    - [Metrics](#metrics)
  - [File Overview](#file-overview)
  - [Test](#test)
    - [Admin/Root](#adminroot)
    - [Without requiring admin/root privileges](#without-requiring-adminroot-privileges)
  - [Performance Metrics](#performance-metrics)
  - [Troubleshooting](#troubleshooting)
  - [Security \& Ethical Notes](#security--ethical-notes)



## Architecture Overview

### System Modules
1. **Discovery**: Scans ARP table, performs reverse DNS lookups, updates device list.  
2. **Monitor**: Captures packets using Scapy (or simulated traffic), aggregates bytes per IP, and writes usage samples to DB.  
3. **Smart Allocator**: Consumes recent usage data, classifies devices using thresholds and anomaly detection, and triggers shaping.  
4. **Database (SQLite)**: Stores device data, usage samples, events, and configuration.  
5. **Shaper**: Applies bandwidth limits at the OS level.  
6. **API & Dashboard**: Flask API exposes endpoints for dashboard to fetch metrics and issue admin actions.

### Data Flow
The data processing in SBA begins with packet capture and proceeds through several sequential steps. Captured packets are analyzed to calculate per-interval aggregates of transmitted and received bytes for each connected device. These aggregated statistics are stored in the usage table of the SQLite database. The Smart Allocator periodically retrieves recent samples from the database to determine device priority levels using statistical rules and thresholds. Once new priorities are computed, the database is updated accordingly, and the Shaper component enforces corresponding bandwidth limits using system-level commands. The web dashboard continuously polls the API to retrieve the latest usage, metrics, and event data, updating visualizations in real time. All administrative actions and events are recorded to ensure complete auditability and transparency.


## Requirements

### Software
- Python **3.9+**
- Flask  
- Flask-CORS  
- Plotly  
- Scapy *(optional, for live packet capture)*  

### Install dependencies
```cmd
pip install flask flask-cors plotly scapy
```


## System Tools

**Linux**: `tc` (iproute2 package)  
**Windows**: PowerShell with `New-NetQosPolicy`  
**(Optional)**: `iperf3` for performance testing

## Quick Start

### Clone and Setup
```bash
git clone https://github.com/dshryn/bandwidth-allocator
cd bandwidth-allocator
python -m venv venv
source venv/bin/activate # linux/mac
venv\Scripts\activate # windows
pip install -r requirements.txt
```

### Run
```cmd
python app.py
```

## Configuration (config.py)

| Variable | Description |
|-----------|--------------|
| `AUTO_MODE` | Enables or disables automatic classification |
| `HIGH_THRESHOLD` | Byte threshold used to determine **High priority** traffic |
| `LOW_THRESHOLD` | Byte threshold used to determine **Low priority** traffic |
| `PRIORITY_RATES` | Bandwidth mapping for each priority level (e.g., `{1: 100000, 2: 20000, 3: 5000}` in kbps) |
| `TC_DRY_RUN` | When `True`, prints shaping commands instead of executing them (useful for demo/testing) |
| `DEFAULT_IFACE` | Default network interface used for monitoring (e.g., `eth0`, `wlan0`) |


## Working

### Monitoring
- Captures packets using **Scapy** (if installed) or generates simulated data for testing and demos.  
- Aggregates transmitted and received bytes per device at regular intervals (defined in `config.py`).  
- Stores the aggregated results in the **`usage`** table within the SQLite database for analysis and visualization.  



### Smart Allocator
- Reads the most recent samples from a **10-sample sliding window** for each device.  
- Uses two thresholds to classify network usage:
  - If `recent < HIGH_THRESHOLD` → **High priority**  
  - If `recent > LOW_THRESHOLD` → **Low priority**  
  - Otherwise → **Normal priority**
- Applies a **2σ (two standard deviation)** anomaly detection rule — if a device’s current usage exceeds `avg + 2×stddev`, it is flagged as an abnormal spike and downgraded to Low priority.  
- Implements **hysteresis** using a 3-sample deque to confirm demotions, preventing rapid priority oscillations.  



### Shaper
- **Linux:** Uses `tc` (Traffic Control) with HTB classes and u32 filters to enforce per-IP bandwidth limits.  
- **Windows:** Uses PowerShell’s `New-NetQosPolicy` to throttle specific IP prefixes.  
- Includes **port-aware filtering**, ensuring essential services like DNS, SSH, HTTPS, and NTP always retain higher priority.  
- When `TC_DRY_RUN = True`, all shaping commands are **printed and logged instead of executed**, enabling safe demonstrations without requiring admin privileges.  


### Metrics
| Metric | Description |
|--------|--------------|
| **Throughput (Mbps)** | Calculated as total bytes in the last 5 seconds converted to bits per second and then to Mbps. |
| **Delay (ms)** | Average Round-Trip Time (RTT) to the default gateway measured via `ping`. |
| **Packet Loss (%)** | Derived from packet loss percentage reported by `ping` statistics. |
| **Congestion (%)** | Percentage of devices currently marked as Low priority. |


## File Overview

| File | Description |
|------|--------------|
| **`app.py`** | Entry point of the project. Initializes the Flask app, starts the Monitor thread, and serves the dashboard. |
| **`api.py`** | Contains all REST API endpoints for device listing, usage history, metrics, priority updates, and blocking/unblocking. |
| **`monitor.py`** | Handles packet capture (via Scapy or simulator), byte aggregation per device, and Smart Allocator logic. |
| **`db.py`** | Defines the SQLite database schema, provides insert/query helper functions, and computes performance metrics. |
| **`shaper.py`** | Implements system-level bandwidth enforcement using `tc` (Linux) or PowerShell `New-NetQosPolicy` (Windows). |
| **`discovery.py`** | Performs ARP-based LAN device discovery and reverse DNS resolution to populate the device list. |
| **`dashboard.html`** | Frontend dashboard built with Plotly and JavaScript. Displays live charts, metrics, and device controls. |
| **`config.py`** | Contains global configuration values such as thresholds, interface names, and demo mode (`TC_DRY_RUN`). |


## Test

### Admin/Root

1. Install tc or enable PowerShell QoS.
2. Run iperf3 between hosts to generate traffic.
3. Observe dashboard metrics adjusting in real-time.
4. Compare throughput and RTT before/after shaping.

### Without requiring admin/root privileges

1. Open the `config.py` file and set:
   ```python
   TC_DRY_RUN = 1
   ```
   This ensures that all shaping commands are printed and logged instead of being executed.
2. Run as directed in above points.
3. Click on “Scan LAN” to automatically discover active devices on the network.
4. Toggle Smart Auto Mode ON from the dashboard to enable automatic bandwidth allocation.
5. Observe the simulated network traffic, device priorities, and live metrics updating on the dashboard.


## Performance Metrics

| Metric | Formula / Source |
|---------|------------------|
| **Throughput (Mbps)** | `(bytes over last 5 seconds × 8) / 1e6` |
| **Delay (ms)** | Average Round-Trip Time (RTT) measured using `ping` to the gateway |
| **Packet Loss (%)** | Percentage of packets lost as reported by `ping` results |
| **Congestion (%)** | `(Number of Low-priority devices / Total devices) × 100` |


## Troubleshooting

| Problem | Cause | Fix |
|----------|--------|-----|
| **“Permission denied” for `tc`** | Not running as root/admin | Use `sudo` or enable `TC_DRY_RUN = True` in `config.py` |
| **Scapy not found** | Missing package dependency | Install using `pip install scapy` |
| **Dashboard blank or not updating** | JavaScript error or Flask API not running | Restart Flask server and refresh the browser |
| **Database locked** | SQLite concurrency issue due to multiple writes | Enable WAL mode (`PRAGMA journal_mode=WAL;`) or restart the app |

---

## Security & Ethical Notes

- SBA captures only **metadata** such as IP headers and packet sizes — **no payload inspection** is performed.  
- The system is designed strictly for **educational, demo, or trusted LAN** use cases.  
- Avoid deploying on **production or public networks** without proper authorization.  
- Always **protect the Flask dashboard** with authentication or restrict access through local network settings if used outside lab environments.  
- All events and administrative actions are logged for **accountability and transparency**.  





