import uuid
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash
import config as cfg
import db
from mailer import send_mail
from security import err, login_required, temp_password
from services import face_service as fs
from routes.register import validate_student_fields, enroll_or_error, duplicate_note, college_email_ok

bp = Blueprint("hod", __name__, url_prefix="/api/hod")
ROLE_LABEL = {"student": "student", "faculty": "faculty", "security": "security"}


@bp.get("/stats")
@login_required("hod")
def stats():
    c = lambda sql, *a: db.one(sql, a)[0]
    students = c("SELECT COUNT(*) FROM users WHERE role='student' AND status='approved' AND is_active=1")
    per = db.many("""SELECT u.id, u.name, s.roll_no, u.department,
                     ROUND(100.0*SUM(a.present)/COUNT(a.id)) AS att FROM users u JOIN students s ON s.user_id=u.id
                     JOIN attendance a ON a.student_id=u.id WHERE u.status='approved' GROUP BY u.id""")
    by = {}
    for r in per:
        by.setdefault(r["department"], []).append(r["att"])
    return jsonify(
        students=students, faculty=c("SELECT COUNT(*) FROM users WHERE role='faculty' AND is_active=1"),
        security=c("SELECT COUNT(*) FROM users WHERE role='security' AND is_active=1"),
        on_campus=c("SELECT COUNT(*) FROM users WHERE in_campus=1"),
        pending=c("SELECT COUNT(*) FROM users WHERE status='pending'"),
        by_department=[dict(department=k, pct=round(sum(v) / len(v))) for k, v in by.items()],
        low=[dict(name=r["name"], roll_no=r["roll_no"], department=r["department"], att=r["att"])
             for r in per if r["att"] < cfg.LOW_ATTENDANCE][:20])


@bp.get("/people")
@login_required("hod")
def people():
    role = request.args.get("type", "student")
    if role not in ROLE_LABEL:
        return err("Unknown type.")
    q = f"%{(request.args.get('q') or '').strip().lower()}%"
    dept = request.args.get("department") or None
    rows = db.many("""SELECT u.id,u.name,u.email,u.mobile,u.department,u.gate,u.is_active,u.in_campus,
                             s.prn,s.roll_no,s.year,s.division
                      FROM users u LEFT JOIN students s ON s.user_id=u.id
                      WHERE u.role=? AND u.status='approved' AND (lower(u.name) LIKE ? OR lower(COALESCE(s.prn,'')) LIKE ?
                            OR lower(COALESCE(s.roll_no,'')) LIKE ? OR lower(u.email) LIKE ?) AND (? IS NULL OR u.department=?)
                      ORDER BY u.name LIMIT 500""", (role, q, q, q, q, dept, dept))
    return jsonify(items=[dict(r) for r in rows])


@bp.put("/people/<int:uid>")
@login_required("hod")
def edit(uid):
    u = db.one("SELECT * FROM users WHERE id=? AND role!='hod'", (uid,))
    if not u:
        return err("Person not found.", 404)
    d = request.get_json(silent=True) or {}
    if d.get("email") and (not college_email_ok(d["email"]) or db.one("SELECT 1 FROM users WHERE lower(email)=lower(?) AND id!=?", (d["email"], uid))):
        return err("That e-mail is not allowed or is already used.")
    if d.get("prn") and db.one("SELECT 1 FROM students WHERE prn=? AND user_id!=?", (d["prn"].upper(), uid)):
        return err("That PRN already belongs to someone else.")
    for col in ("name", "email", "mobile", "department", "gate"):
        if d.get(col) is not None and (col != "department" or d[col] in cfg.DEPARTMENTS):
            db.run(f"UPDATE users SET {col}=? WHERE id=?", (d[col].strip(), uid))
    if u["role"] == "student":
        for col in ("prn", "roll_no", "year", "division"):
            if d.get(col):
                db.run(f"UPDATE students SET {col}=? WHERE user_id=?", (d[col].strip().upper() if col in ("prn", "division") else d[col].strip(), uid))
    db.audit(session["uid"], "edit_person", f"{u['name']} (id {uid})")
    return jsonify(ok=True)


@bp.post("/people/<int:uid>/active")
@login_required("hod")
def set_active(uid):
    on = 1 if (request.get_json(silent=True) or {}).get("active") else 0
    u = db.one("SELECT name FROM users WHERE id=? AND role!='hod'", (uid,))
    if not u:
        return err("Person not found.", 404)
    db.run("UPDATE users SET is_active=? WHERE id=?", (on, uid))
    fs.reload_gallery(db.get_db())
    db.audit(session["uid"], "activate" if on else "deactivate", u["name"])
    return jsonify(ok=True)


@bp.post("/people/<int:uid>/reset-password")
@login_required("hod")
def reset_pw(uid):
    u = db.one("SELECT name,email FROM users WHERE id=? AND role!='hod'", (uid,))
    if not u:
        return err("Person not found.", 404)
    pw = temp_password()
    db.run("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), uid))
    send_mail(u["email"], f"{cfg.COLLEGE_NAME} new password", f"Hello {u['name']},\n\nYour new temporary password is {pw}. Change it after you sign in.\n")
    db.audit(session["uid"], "reset_password", u["name"])
    return jsonify(ok=True, temp_password=pw)


@bp.post("/users")
@login_required("hod")
def create_user():
    """HOD registers a student, faculty member or security officer."""
    f = request.form
    kind = f.get("type")
    if kind not in ROLE_LABEL:
        return err("Choose Faculty, Security or Student.")
    pw = temp_password()
    result = None
    if kind == "student":
        c, e = validate_student_fields(f, need_password=False)
        if e:
            return err(e)
        if db.one("SELECT 1 FROM students WHERE prn=?", (c["prn"],)):
            return err("This PRN is already registered.")
    else:
        c = {k: (f.get(k) or "").strip() for k in ("name", "email", "mobile", "department", "gate")}
        c["email"] = c["email"].lower()
        if not c["name"] or not college_email_ok(c["email"]):
            return err(f"Enter the name and a college e-mail (@{cfg.EMAIL_DOMAINS[0]}).")
        if kind == "faculty" and c["department"] not in cfg.DEPARTMENTS:
            return err("Choose a department.")
    if db.one("SELECT 1 FROM users WHERE lower(email)=?", (c["email"],)):
        return err("This e-mail is already registered.")
    if kind in ("student", "faculty"):
        result, bad = enroll_or_error(request.files.getlist("photos"))
        if bad:
            return bad
    uid = db.run("""INSERT INTO users (role,name,email,mobile,password_hash,department,gate,status,created_by)
                    VALUES (?,?,?,?,?,?,?,'approved',?)""",
                 (kind, c["name"], c["email"], c.get("mobile"), generate_password_hash(pw),
                  c.get("department") if kind != "security" else None, c.get("gate") if kind == "security" else None, session["uid"]))
    if kind == "student":
        card = request.files.get("id_card")
        name = fs.save_id_card(card, f"{uuid.uuid4().hex}.jpg") if card else None
        db.run("""INSERT INTO students (user_id,prn,roll_no,year,division,id_card,dup_note,consent_at,approved_by,approved_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?)""", (uid, c["prn"], c["roll_no"], c["year"], c["division"], name,
                                                  duplicate_note(result), db.now_iso(), session["uid"], db.now_iso()))
    if result:
        fs.store_enrollment(uid, result)
        fs.reload_gallery(db.get_db())
    send_mail(c["email"], f"Your {cfg.COLLEGE_NAME} account", f"Hello {c['name']},\n\nYour account is ready.\nSign in with {c.get('prn') or c['email']} and the temporary password {pw}. Change it after you sign in.\n")
    db.audit(session["uid"], f"register_{kind}", c["name"])
    return jsonify(ok=True, temp_password=pw)


@bp.get("/pending")
@login_required("hod")
def pending():
    rows = db.many("""SELECT u.id,u.name,u.email,u.department,s.prn,s.roll_no,s.year,s.division,s.dup_note,u.created_at
                      FROM users u JOIN students s ON s.user_id=u.id WHERE u.status='pending' ORDER BY u.id""")
    return jsonify(items=[dict(r) for r in rows])


@bp.post("/pending/<int:uid>")
@login_required("hod")
def decide(uid):
    action = (request.get_json(silent=True) or {}).get("action")
    u = db.one("SELECT u.name, s.id_card FROM users u JOIN students s ON s.user_id=u.id WHERE u.id=? AND u.status='pending'", (uid,))
    if not u or action not in ("approve", "reject"):
        return err("Request not found.", 404)
    if action == "approve":
        db.run("UPDATE users SET status='approved' WHERE id=?", (uid,))
        db.run("UPDATE students SET approved_by=?, approved_at=? WHERE user_id=?", (session["uid"], db.now_iso(), uid))
    else:
        db.run("UPDATE users SET status='rejected' WHERE id=?", (uid,))
        db.run("DELETE FROM face_templates WHERE user_id=?", (uid,))
        for p in (fs.PHOTO_DIR / f"{uid}.jpg", fs.IDCARD_DIR / (u["id_card"] or "x")):
            p.unlink(missing_ok=True)
    fs.reload_gallery(db.get_db())
    db.audit(session["uid"], action, u["name"])
    return jsonify(ok=True)


@bp.get("/audit")
@login_required("hod")
def audit():
    rows = db.many("""SELECT a.created_at, a.action, a.detail, COALESCE(u.name,'System') AS who FROM audit_log a
                      LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 200""")
    return jsonify(items=[dict(r) for r in rows])
