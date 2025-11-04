from flask import Flask, render_template
from flask_cors import CORS
from sba.api import bp as api_bp
from sba.db import init_db
from sba.monitor import Monitor

def create_app():
    app = Flask(__name__)
    CORS(app)
    app.register_blueprint(api_bp, url_prefix="/api")
    init_db()

    @app.route("/")
    def index():
        return render_template("dashboard.html")

    return app

if __name__ == "__main__":
    app = create_app()
    monitor = Monitor(interval=2.0)
    monitor.start()
    app.run(host="0.0.0.0", port=8000, debug=True)
