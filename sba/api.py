import sqlite3
from flask import Blueprint, jsonify, request
from .db import init_db, list_devices, recent_usage, set_priority, upsert_device, log_event, list_events, usage_history, block_device, unblock_device, list_blocked, metrics_summary, set_config
from .shaper import set_limit
from .config import load_auto_mode

bp = Blueprint("api", __name__)

@bp.route("/init", methods=["POST"])
def init():
    init_db()
    load_auto_mode()
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

@bp.route("/events", methods=["GET"])
def events():
    return jsonify({"events": list_events(50)})

@bp.route("/history", methods=["GET"])
def history():
    ip = request.args.get("ip")
    if not ip:
        return jsonify({"ok": False, "error": "ip required"}), 400
    rows = usage_history(ip, limit=500)
    return jsonify({"ok": True, "history": rows})

@bp.route("/metrics", methods=["GET"])
def metrics():
    return jsonify({"metrics": metrics_summary()})

@bp.route("/block", methods=["POST"])
def block():
    try:
        data = request.json
        ip = data["ip"]
        reason = data.get("reason", "admin_block")
        block_device(ip, reason)
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
        set_priority(ip, 2)
        set_limit(ip, 2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@bp.route("/blocked", methods=["GET"])
def blocked():
    return jsonify({"blocked": list_blocked()})

@bp.route("/auto_toggle", methods=["POST", "GET"])
def auto_toggle():
    from . import config
    
    if request.method == "GET":
        return jsonify({"ok": True, "auto": config.AUTO_MODE})
        
    try:
        data = request.json
        desired = bool(data.get("auto", True))
        
        config.AUTO_MODE = desired
        set_config("auto_mode", str(desired)) 
        
        log_event("INFO", f"AUTO_MODE set to {desired}")
        return jsonify({"ok": True, "auto": desired})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500