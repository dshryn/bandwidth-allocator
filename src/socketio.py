# sba/socketio.py
from flask_socketio import SocketIO

# This is the global, uninitialized socketio object
# app.py will call .init_app(app) on it
socketio = SocketIO(async_mode="eventlet", cors_allowed_origins="*")