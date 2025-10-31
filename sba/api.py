from flask import Blueprint, jsonify, request
from .db import init_db, list_devices, recent_usage, set_priority, upsert_device, log_event
from .shaper import set_limit
bp = Blueprint("api", __name__)

@bp.route("/init", methods=["POST"])
def init():
    init_db()
    return jsonify({"ok":True})

@bp.route("/devices", methods=["GET"])
def devices():
    return jsonify({"devices": list_devices()})

@bp.route("/discover", methods=["POST"])
def discover():
    from .discovery import scan
    scan()
    return jsonify({"ok":True, "devices": list_devices()})

@bp.route("/usage", methods=["GET"])
def usage():
    return jsonify({"usage": recent_usage(200)})

@bp.route("/set_priority", methods=["POST"])
def set_prio():
    data = request.json
    ip = data["ip"]
    pr = int(data["priority"])
    set_priority(ip, pr)
    # call shaper
    set_limit(ip, pr, iface=data.get("iface"))
    log_event("INFO", f"Priority set {ip} -> {pr}")
    return jsonify({"ok":True})
