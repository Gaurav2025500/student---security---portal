from flask import Blueprint, request, jsonify, session
import db
import config as cfg
from security import err, login_required

bp = Blueprint("student", __name__, url_prefix="/api/student")


def subject_rows(uid):
    return db.many("""SELECT sub.id, sub.name,
                             COALESCE(SUM(a.present),0) AS attended, COUNT(a.id) AS total
                      FROM subjects sub
                      JOIN users u ON u.id = ? 
                      JOIN students s ON s.user_id = u.id AND s.year = sub.year AND u.department = sub.department
                      LEFT JOIN class_sessions cs ON cs.subject_id = sub.id
                      LEFT JOIN attendance a ON a.session_id = cs.id AND a.student_id = u.id
                      GROUP BY sub.id ORDER BY sub.name""", (uid,))


def pct(att, tot):
    return round(100 * att / tot) if tot else 0


@bp.get("/attendance")
@login_required("student")
def attendance():
    subs = [dict(id=r["id"], name=r["name"], attended=r["attended"], total=r["total"], pct=pct(r["attended"], r["total"]))
            for r in subject_rows(session["uid"])]
    att, tot = sum(s["attended"] for s in subs), sum(s["total"] for s in subs)
    return jsonify(overall=pct(att, tot), subjects=subs, low=[s["name"] for s in subs if s["total"] and s["pct"] < cfg.LOW_ATTENDANCE])


@bp.get("/attendance/<int:sid>")
@login_required("student")
def subject_detail(sid):
    sub = db.one("SELECT * FROM subjects WHERE id=?", (sid,))
    if not sub:
        return err("Subject not found.", 404)
    rows = db.many("""SELECT a.id, a.present, cs.held_on, cs.topic,
                             (SELECT status FROM attendance_issues i WHERE i.attendance_id = a.id ORDER BY i.id DESC LIMIT 1) AS issue
                      FROM attendance a JOIN class_sessions cs ON cs.id = a.session_id
                      WHERE a.student_id=? AND cs.subject_id=? ORDER BY cs.held_on DESC, cs.id DESC""", (session["uid"], sid))
    att = sum(r["present"] for r in rows)
    return jsonify(name=sub["name"], attended=att, total=len(rows), pct=pct(att, len(rows)),
                   dates=[dict(attendance_id=r["id"], date=r["held_on"], topic=r["topic"] or "Class", present=bool(r["present"]),
                               issue=r["issue"]) for r in rows])


@bp.get("/profile")
@login_required("student")
def profile():
    r = db.one("""SELECT u.id,u.name,u.email,u.mobile,u.department,s.prn,s.roll_no,s.year,s.division,
                         (SELECT COUNT(*) FROM face_templates f WHERE f.user_id=u.id) AS photos
                  FROM users u JOIN students s ON s.user_id=u.id WHERE u.id=?""", (session["uid"],))
    return jsonify(dict(r))


@bp.post("/report-issue")
@login_required("student")
def report_issue():
    d = request.get_json(silent=True) or {}
    a = db.one("SELECT * FROM attendance WHERE id=? AND student_id=?", (d.get("attendance_id"), session["uid"]))
    if not a or a["present"]:
        return err("This class cannot be reported.")
    if db.one("SELECT 1 FROM attendance_issues WHERE attendance_id=? AND status='open'", (a["id"],)):
        return err("You already reported this class.")
    db.run("INSERT INTO attendance_issues (attendance_id, student_id, note) VALUES (?,?,?)",
           (a["id"], session["uid"], (d.get("note") or "")[:300]))
    return jsonify(ok=True)
