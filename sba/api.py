# sba/api.py
import sqlite3
from flask import Blueprint, jsonify, request
from .db import init_db, list_devices, recent_usage, set_priority, upsert_device, log_event, list_events, usage_history, block_device, unblock_device, list_blocked, metrics_summary
from .shaper import set_limit
from .config import AUTO_MODE

bp = Blueprint("api", __name__)

@bp.route("/init", methods=["POST"])
def init():
    init_db()
    return jsonify({"ok": True})

@bp.route("/devices", methods=["GET"])
def devices():
    return jsonify({"devices": list_devices()})

@bp.route("/discover", methods=["POST"])
def discover():
    from .discovery import scan
    try:
        scan()
        return jsonify({"ok": True, "devices": list_devices()})
    except Exception as e:
        log_event("ERROR", f"Discovery failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@bp.route("/usage", methods=["GET"])
def usage():
    return jsonify({"usage": recent_usage(200)})

@bp.route("/set_priority", methods=["POST"])
def set_prio():
    try:
        data = request.json
        ip = data["ip"]
        pr = int(data["priority"])
        set_priority(ip, pr)
        set_limit(ip, pr, iface=data.get("iface"))
        log_event("INFO", f"Priority set {ip} -> {pr}")
        return jsonify({"ok": True, "message": f"Priority updated for {ip}"})
    except Exception as e:
        log_event("ERROR", f"Priority update failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

# events
@bp.route("/events", methods=["GET"])
def events():
    return jsonify({"events": list_events(50)})

# history per device
@bp.route("/history", methods=["GET"])
def history():
    ip = request.args.get("ip")
    if not ip:
        return jsonify({"ok": False, "error": "ip required"}), 400
    rows = usage_history(ip, limit=500)
    return jsonify({"ok": True, "history": rows})

# metrics summary
@bp.route("/metrics", methods=["GET"])
def metrics():
    return jsonify({"metrics": metrics_summary()})

# blocking endpoints
@bp.route("/block", methods=["POST"])
def block():
    try:
        data = request.json
        ip = data["ip"]
        reason = data.get("reason", "admin_block")
        block_device(ip, reason)
        # set priority 0 and apply shaping (0 -> blocked)
        set_priority(ip, 0)
        set_limit(ip, 0)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@bp.route("/unblock", methods=["POST"])
def unblock():
    try:
        data = request.json
        ip = data["ip"]
        unblock_device(ip)
        # revert to normal (2)
        set_priority(ip, 2)
        set_limit(ip, 2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@bp.route("/blocked", methods=["GET"])
def blocked():
    return jsonify({"blocked": list_blocked()})

# auto-mode toggle (simple toggle endpoint)
@bp.route("/auto_toggle", methods=["POST"])
def auto_toggle():
    try:
        data = request.json
        desired = bool(data.get("auto", True))
        # update runtime config (monitored by module on next use)
        from . import config
        config.AUTO_MODE = desired
        log_event("INFO", f"AUTO_MODE set to {desired}")
        return jsonify({"ok": True, "auto": desired})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
