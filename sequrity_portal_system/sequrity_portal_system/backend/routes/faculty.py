from datetime import date
from flask import Blueprint, request, jsonify, session
import db
import config as cfg
from security import err, login_required
from services import face_service as fs

bp = Blueprint("faculty", __name__, url_prefix="/api/faculty")


def roster(subject, division=None):
    sql = """SELECT u.id, u.name, s.roll_no, s.prn, s.division FROM users u JOIN students s ON s.user_id = u.id
             WHERE u.role='student' AND u.status='approved' AND u.is_active=1 AND u.department=? AND s.year=?"""
    args = [subject["department"], subject["year"]]
    if division and division != "All":
        sql += " AND s.division=?"
        args.append(division)
    return db.many(sql + " ORDER BY s.roll_no", args)


@bp.get("/subjects")
@login_required("faculty", "hod")
def subjects():
    rows = db.many("SELECT * FROM subjects WHERE faculty_id=? OR ?='hod' ORDER BY name", (session["uid"], session["role"]))
    out = []
    for r in rows:
        divs = [x["division"] for x in db.many(
            """SELECT DISTINCT s.division FROM students s JOIN users u ON u.id = s.user_id
               WHERE u.department=? AND s.year=? AND u.status='approved' ORDER BY 1""", (r["department"], r["year"]))]
        out.append(dict(id=r["id"], name=r["name"], department=r["department"], year=r["year"], divisions=divs))
    return jsonify(subjects=out)


@bp.post("/attendance/detect")
@login_required("faculty", "hod")
def detect():
    sub = db.one("SELECT * FROM subjects WHERE id=?", (request.form.get("subject_id"),))
    if not sub:
        return err("Choose a subject.")
    files = request.files.getlist("photos")
    if not 1 <= len(files) <= 3:
        return err("Add 1 to 3 class photos.")
    students = roster(sub, request.form.get("division"))
    if not students:
        return err("No approved students found for this class yet.")
    ids = {s["id"] for s in students}
    res = fs.engine.class_attendance(fs.read_images(files), allowed_users=ids)
    items = [dict(id=s["id"], name=s["name"], roll_no=s["roll_no"], prn=s["prn"],
                  present=s["id"] in res["present"], confidence=round(res["present"].get(s["id"], 0) * 100))
             for s in students]
    return jsonify(items=items, faces_found=res["faces_found"], unmatched=res["unmatched"])


@bp.post("/attendance/save")
@login_required("faculty", "hod")
def save():
    d = request.get_json(silent=True) or {}
    sub = db.one("SELECT * FROM subjects WHERE id=?", (d.get("subject_id"),))
    marks = d.get("marks") or []
    if not sub or not marks:
        return err("Nothing to save.")
    valid = {s["id"] for s in roster(sub, d.get("division"))}
    sid = db.run("INSERT INTO class_sessions (subject_id, faculty_id, division, held_on, topic, photo_count) VALUES (?,?,?,?,?,?)",
                 (sub["id"], session["uid"], d.get("division"), date.today().isoformat(), (d.get("topic") or "")[:80], int(d.get("photos") or 0)))
    n = 0
    for m in marks:
        if m.get("student_id") not in valid:
            continue
        db.run("INSERT OR REPLACE INTO attendance (session_id, student_id, present, source, confidence, edited_by) VALUES (?,?,?,?,?,?)",
               (sid, m["student_id"], 1 if m.get("present") else 0, "manual" if m.get("edited") else "ai",
                (m.get("confidence") or 0) / 100.0, session["uid"] if m.get("edited") else None))
        n += 1
    db.audit(session["uid"], "attendance_saved", f"{sub['name']} · {n} students")
    present = sum(1 for m in marks if m.get("present") and m.get("student_id") in valid)
    return jsonify(ok=True, present=present, absent=n - present)


@bp.get("/students")
@login_required("faculty")
def students():
    q = f"%{(request.args.get('q') or '').strip().lower()}%"
    rows = db.many("""SELECT u.id,u.name,u.department,s.prn,s.roll_no,
                      (SELECT ROUND(100.0*SUM(a.present)/COUNT(a.id)) FROM attendance a WHERE a.student_id=u.id) AS att
                      FROM users u JOIN students s ON s.user_id=u.id
                      WHERE u.status='approved' AND u.is_active=1 AND (lower(u.name) LIKE ? OR lower(s.prn) LIKE ? OR lower(s.roll_no) LIKE ?)
                      ORDER BY s.roll_no LIMIT 300""", (q, q, q))
    return jsonify(items=[dict(id=r["id"], name=r["name"], department=r["department"], prn=r["prn"], roll_no=r["roll_no"], att=r["att"]) for r in rows])


@bp.get("/issues")
@login_required("faculty")
def issues():
    rows = db.many("""SELECT i.id, i.note, i.status, u.name, sub.name AS subject, cs.held_on
                      FROM attendance_issues i JOIN attendance a ON a.id=i.attendance_id
                      JOIN class_sessions cs ON cs.id=a.session_id JOIN subjects sub ON sub.id=cs.subject_id
                      JOIN users u ON u.id=i.student_id
                      WHERE cs.faculty_id=? ORDER BY (i.status='open') DESC, i.id DESC LIMIT 100""", (session["uid"],))
    return jsonify(items=[dict(r) for r in rows])


@bp.post("/issues/<int:iid>")
@login_required("faculty")
def resolve(iid):
    action = (request.get_json(silent=True) or {}).get("action")
    row = db.one("""SELECT i.*, cs.faculty_id FROM attendance_issues i JOIN attendance a ON a.id=i.attendance_id
                    JOIN class_sessions cs ON cs.id=a.session_id WHERE i.id=?""", (iid,))
    if not row or row["faculty_id"] != session["uid"] or action not in ("accept", "reject"):
        return err("Cannot update this request.", 404)
    if row["status"] != "open":
        return err("Already answered.")
    if action == "accept":
        db.run("UPDATE attendance SET present=1, source='manual', edited_by=? WHERE id=?", (session["uid"], row["attendance_id"]))
    db.run("UPDATE attendance_issues SET status=?, resolved_by=? WHERE id=?",
           ("accepted" if action == "accept" else "rejected", session["uid"], iid))
    db.audit(session["uid"], "issue_" + action, f"issue {iid}")
    return jsonify(ok=True)
