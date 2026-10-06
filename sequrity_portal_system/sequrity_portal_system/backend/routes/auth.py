import re
from datetime import timedelta
from flask import Blueprint, request, session, jsonify, send_file, abort
from werkzeug.security import check_password_hash, generate_password_hash
import config as cfg
import db
import otp
from security import err, login_required, locked, note_fail, clear_fails, strong_password
from services import face_service as fs

bp = Blueprint("auth", __name__, url_prefix="/api")

HOME = {"student": "student/attendance.html", "faculty": "faculty/take-attendance.html",
        "security": "security/scan.html", "hod": "hod/dashboard.html"}
TAG = {"student": "Student", "faculty": "Faculty", "security": "Security", "hod": "HOD"}


@bp.get("/meta")
def meta():
    return jsonify(college=cfg.COLLEGE_NAME, college_full=cfg.COLLEGE_FULL_NAME, departments=cfg.DEPARTMENTS,
                   years=cfg.YEARS, email_domains=cfg.EMAIL_DOMAINS)


def _me(uid):
    u = db.one("""SELECT u.*, s.prn, s.roll_no, s.year, s.division FROM users u
                  LEFT JOIN students s ON s.user_id = u.id WHERE u.id=?""", (uid,))
    if not u:
        return None
    where = u["gate"] if u["role"] == "security" else u["department"]
    tag = TAG[u["role"]] + (f" · {where}" if where else "")
    return dict(id=u["id"], name=u["name"], role=u["role"], tag=tag, email=u["email"], home=HOME[u["role"]])


@bp.post("/auth/login")
def login():
    d = request.get_json(silent=True) or {}
    kind, ident, pw = d.get("kind", "student"), (d.get("identifier") or "").strip(), d.get("password") or ""
    if not ident or not pw:
        return err("Enter your ID and password.")
    key = ident.lower()
    if locked(key):
        return err(f"Too many wrong attempts. Try again in {cfg.LOGIN_LOCK_MINUTES} minutes.", 429)
    if kind == "student":
        u = db.one("""SELECT u.* FROM users u JOIN students s ON s.user_id = u.id
                      WHERE (upper(s.prn) = upper(?) OR lower(u.email) = lower(?)) AND u.role='student'""", (ident, ident))
    else:
        u = db.one("SELECT * FROM users WHERE lower(email)=lower(?) AND role IN ('hod','faculty','security')", (ident,))
    if not u or not check_password_hash(u["password_hash"], pw):
        note_fail(key)
        return err("ID or password is not correct.", 401)
    if u["status"] == "pending":
        return err("Your registration is waiting for HOD approval.", 403)
    if u["status"] == "rejected" or not u["is_active"]:
        return err("This account is not active. Contact your HOD.", 403)
    clear_fails(key)
    session.clear()
    session.permanent = True
    session["uid"], session["role"] = u["id"], u["role"]
    db.audit(u["id"], "login", u["email"])
    return jsonify(ok=True, redirect=HOME[u["role"]])


@bp.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get("/auth/me")
@login_required()
def me():
    m = _me(session["uid"])
    if not m:
        session.clear()
        return err("Please sign in.", 401)
    return jsonify(m)


@bp.post("/auth/password/otp")
@login_required()
def password_otp():
    u = db.one("SELECT name,email FROM users WHERE id=?", (session["uid"],))
    try:
        code = otp.issue(u["email"], "password", u["name"])
    except ValueError as e:
        return err(str(e), 429)
    return jsonify(ok=True, email=u["email"], dev_otp=code)


@bp.post("/auth/password/change")
@login_required()
def password_change():
    d = request.get_json(silent=True) or {}
    u = db.one("SELECT * FROM users WHERE id=?", (session["uid"],))
    if not check_password_hash(u["password_hash"], d.get("current") or ""):
        return err("Current password is not correct.")
    if not strong_password(d.get("new") or ""):
        return err("New password needs at least 8 characters with letters and numbers.")
    ok, msg = otp.check(u["email"], "password", d.get("otp") or "")
    if not ok:
        return err(msg)
    db.run("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(d["new"]), u["id"]))
    db.audit(u["id"], "password_changed", "")
    return jsonify(ok=True)


# ---- images (access controlled) ----
@bp.get("/photo/<int:uid>")
@login_required()
def photo(uid):
    if session["role"] == "student" and session["uid"] != uid:
        abort(403)
    p = fs.PHOTO_DIR / f"{uid}.jpg"
    if not p.exists():
        abort(404)
    r = send_file(p, mimetype="image/jpeg")
    r.headers["Cache-Control"] = "private, max-age=300"
    return r


@bp.get("/idcard/<int:uid>")
@login_required("hod")
def idcard(uid):
    s = db.one("SELECT id_card FROM students WHERE user_id=?", (uid,))
    if not s or not s["id_card"] or not (fs.IDCARD_DIR / s["id_card"]).exists():
        abort(404)
    return send_file(fs.IDCARD_DIR / s["id_card"], mimetype="image/jpeg")
