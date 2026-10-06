"""Flask app: serves the website AND the API, so you only start one thing."""
from datetime import timedelta
from flask import Flask, redirect, jsonify
import config as cfg
import db
from security import secret_key


def create_app():
    app = Flask(__name__, static_folder=str(cfg.FRONTEND_DIR), static_url_path="")
    app.config.update(SECRET_KEY=secret_key(), PERMANENT_SESSION_LIFETIME=timedelta(hours=cfg.SESSION_HOURS),
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      MAX_CONTENT_LENGTH=cfg.MAX_UPLOAD_MB * 1024 * 1024, JSON_SORT_KEYS=False)
    created = db.init_db()
    for role, email, pw in created:
        print(f"  first-run account  {role:9} {email}  password: {pw}")
    app.teardown_appcontext(db.close_db)

    from routes import auth, register, student, security_gate, faculty, hod
    for m in (auth, register, student, security_gate, faculty, hod):
        app.register_blueprint(m.bp)

    from services import face_service
    face_service.reload_gallery()

    @app.get("/")
    def home():
        return redirect("/auth/login.html")

    @app.after_request
    def headers(r):
        r.headers["Permissions-Policy"] = "camera=(self)"
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "same-origin"
        if r.mimetype in ("text/html", "text/css", "application/javascript", "text/javascript"):
            r.headers["Cache-Control"] = "no-cache"
        return r

    @app.errorhandler(413)
    def too_big(_):
        return jsonify(error=f"Upload is too large (limit {cfg.MAX_UPLOAD_MB} MB)."), 413

    @app.errorhandler(500)
    def boom(e):
        app.logger.exception(e)
        orig = getattr(e, "original_exception", None) or e
        msg = "Something went wrong on the server."
        if cfg.SHOW_ERRORS:
            msg += f" ({type(orig).__name__}: {str(orig)[:300]})"
        return jsonify(error=msg), 500
    return app
