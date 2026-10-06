"""Security gate: live face scan with liveness check."""
from flask import Blueprint, request, jsonify, session
import db
import config as cfg
from security import err, login_required, secret_key
from services import face_service as fs
from face_engine import liveness
from face_engine.engine import decode_image

bp = Blueprint("gate", __name__, url_prefix="/api/security")


@bp.get("/challenge")
@login_required("security")
def challenge():
    return jsonify(liveness.make_challenge(secret_key()))


def _log(result, user_id=None, direction=None, score=None, note=None):
    db.run("INSERT INTO scan_log (scanned_by, matched_user_id, direction, result, score, note, created_at) VALUES (?,?,?,?,?,?,?)",
           (session["uid"], user_id, direction, result, score, note, db.now_iso()))


@bp.post("/scan")
@login_required("security")
def scan():
    direction = request.form.get("direction", "entry")
    if direction not in ("entry", "exit"):
        return err("Choose entry or exit.")
    try:
        kind = liveness.read_challenge(secret_key(), request.form.get("token", ""))
    except ValueError as e:
        return err(str(e), 400)
    files = request.files.getlist("frames")
    if not 6 <= len(files) <= 30:
        return err("Not enough frames were captured. Try again.")
    frames = [decode_image(f.read()) for f in files]
    res = fs.engine.scan(frames, kind)

    if not res["live"]:
        _log("not_live", direction=direction, note="; ".join(res["live_reasons"])[:200])
        return jsonify(status="not_live", reasons=res["live_reasons"])
    if res["decision"] == "no_match":
        _log("no_match", direction=direction, score=res["score"])
        return jsonify(status="no_match")
    if res["decision"] == "uncertain":
        _log("uncertain", direction=direction, score=res["score"])
        return jsonify(status="uncertain")

    u = db.one("""SELECT u.id,u.name,u.role,u.department,u.status,u.is_active FROM users u WHERE u.id=?""", (res["user_id"],))
    if not u or u["status"] != "approved" or not u["is_active"]:
        _log("not_approved", user_id=res["user_id"], direction=direction, score=res["score"])
        return jsonify(status="not_approved")
    inside = 1 if direction == "entry" else 0
    db.run("UPDATE users SET in_campus=?, last_seen=? WHERE id=?", (inside, db.now_iso(), u["id"]))
    _log("match", user_id=u["id"], direction=direction, score=res["score"])
    # security officers only ever see: name, department, one photo, campus status, time
    return jsonify(status="match", name=u["name"], department=u["department"], role=u["role"],
                   on_campus=bool(inside), photo=f"/api/photo/{u['id']}", time=db.now_iso()[11:16],
                   confidence=round(res["score"] * 100), liveness="passed")


@bp.get("/log")
@login_required("security")
def log():
    rows = db.many("""SELECT sl.id, sl.created_at, sl.direction, sl.result, sl.note, u.name, u.department
                      FROM scan_log sl LEFT JOIN users u ON u.id = sl.matched_user_id
                      WHERE date(sl.created_at) = date('now','localtime') ORDER BY sl.id DESC LIMIT 200""")
    label = {"match": None, "no_match": "No match", "uncertain": "Not sure", "not_live": "Failed live check",
             "not_approved": "Not approved", "visitor": "Visitor"}
    out = []
    for r in rows:
        if r["result"] == "match":
            status = "On campus" if r["direction"] == "entry" else "Left campus"
        else:
            status = label.get(r["result"], r["result"])
        out.append(dict(name=r["name"] or ("Visitor: " + (r["note"] or "")) if r["result"] == "visitor" else (r["name"] or "Unknown person"),
                        department=r["department"] or "-", status=status, result=r["result"], time=r["created_at"][11:16]))
    return jsonify(items=out)


@bp.post("/visitor")
@login_required("security")
def visitor():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()[:80]
    if not name:
        return err("Enter the visitor's name.")
    _log("visitor", note=name, direction=d.get("direction") if d.get("direction") in ("entry", "exit") else "entry")
    return jsonify(ok=True)
