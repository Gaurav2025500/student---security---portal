"""Public student sign-up: e-mail OTP, then details + face photos + virtual ID card image."""
import re
import uuid
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
import config as cfg
import db
import otp
from security import err, make_ticket, read_ticket, strong_password
from services import face_service as fs

bp = Blueprint("register", __name__, url_prefix="/api/register")


def college_email_ok(email):
    return any(email.lower().endswith("@" + d) for d in cfg.EMAIL_DOMAINS)


@bp.post("/send-otp")
def send_otp():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    if not college_email_ok(email):
        return err(f"Use your college e-mail (ends with @{cfg.EMAIL_DOMAINS[0]}).")
    if db.one("SELECT 1 FROM users WHERE lower(email)=?", (email,)):
        return err("An account with this e-mail already exists. Try signing in.")
    try:
        code = otp.issue(email, "register", d.get("name", ""))
    except ValueError as e:
        return err(str(e), 429)
    return jsonify(ok=True, dev_otp=code)


@bp.post("/verify-otp")
def verify_otp():
    d = request.get_json(silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    ok, msg = otp.check(email, "register", d.get("code") or "")
    if not ok:
        return err(msg)
    return jsonify(ok=True, ticket=make_ticket(email))


def validate_student_fields(f, need_password=True):
    """Shared by self sign-up and HOD registration. Returns (clean dict, error text)."""
    c = {k: (f.get(k) or "").strip() for k in ("name", "prn", "roll_no", "department", "year", "division", "mobile", "email")}
    if not all(c[k] for k in ("name", "prn", "roll_no", "department", "year", "division", "mobile", "email")):
        return None, "Please fill every detail."
    c["prn"], c["email"], c["division"] = c["prn"].upper(), c["email"].lower(), c["division"].upper()
    if not re.fullmatch(r"[A-Z0-9]{6,20}", c["prn"]):
        return None, "PRN should be 6 to 20 letters or numbers."
    if c["department"] not in cfg.DEPARTMENTS or c["year"] not in cfg.YEARS:
        return None, "Choose a department and year from the list."
    if not re.fullmatch(r"[6-9]\d{9}", c["mobile"]):
        return None, "Enter a valid 10-digit mobile number."
    if not college_email_ok(c["email"]):
        return None, f"Use your college e-mail (ends with @{cfg.EMAIL_DOMAINS[0]})."
    if need_password and not strong_password(f.get("password") or ""):
        return None, "Password needs at least 8 characters with letters and numbers."
    return c, None


def enroll_or_error(files):
    """Run the face engine on uploaded photos. Returns (result, error response)."""
    if not 3 <= len(files) <= 5:
        return None, err("Send 3 to 5 face photos.")
    result = fs.engine.enroll(fs.read_images(files))
    if not result["ok"]:
        msgs = sorted({m for r in result["reports"] for m in r["messages"]})
        return None, err(result["message"], 422, tips=msgs)
    return result, None


def duplicate_note(result):
    hits = fs.engine.find_duplicates(result["vectors"])
    if not hits:
        return None
    uid, score = hits[0]
    other = db.one("SELECT u.name, s.prn FROM users u LEFT JOIN students s ON s.user_id=u.id WHERE u.id=?", (uid,))
    return f"Face looks like {other['name']} ({other['prn'] or 'staff'}), {round(score * 100)}% similar." if other else None


@bp.post("/student")
def student():
    f = request.form
    c, e = validate_student_fields(f)
    if e:
        return err(e)
    if not read_ticket(f.get("ticket", ""), c["email"]):
        return err("Verify your e-mail first.", 403)
    if f.get("consent") != "1":
        return err("Please accept the consent box.")
    if db.one("SELECT 1 FROM students WHERE prn=?", (c["prn"],)):
        return err("This PRN is already registered. Contact your HOD if this is a mistake.")
    if db.one("SELECT 1 FROM users WHERE lower(email)=?", (c["email"],)):
        return err("This e-mail is already registered.")
    card = request.files.get("id_card")
    if not card:
        return err("Upload the front image of your virtual ID card.")
    result, bad = enroll_or_error(request.files.getlist("photos"))
    if bad:
        return bad
    name = fs.save_id_card(card, f"{uuid.uuid4().hex}.jpg")
    if not name:
        return err("The ID card file is not a readable image.")
    note = duplicate_note(result)
    uid = db.run("""INSERT INTO users (role,name,email,mobile,password_hash,department,status)
                    VALUES ('student',?,?,?,?,?,'pending')""",
                 (c["name"], c["email"], c["mobile"], generate_password_hash(f["password"]), c["department"]))
    db.run("""INSERT INTO students (user_id,prn,roll_no,year,division,id_card,dup_note,consent_at)
              VALUES (?,?,?,?,?,?,?,?)""", (uid, c["prn"], c["roll_no"], c["year"], c["division"], name, note, db.now_iso()))
    fs.store_enrollment(uid, result)
    fs.reload_gallery(db.get_db())
    db.audit(uid, "student_registered", c["prn"])
    return jsonify(ok=True, message="Registration sent. Your HOD will approve it.")
