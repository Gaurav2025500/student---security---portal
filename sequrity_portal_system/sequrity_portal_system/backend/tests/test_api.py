"""End-to-end test of the whole backend with FAKE faces (no models, no camera needed).
Run:  python backend/tests/test_api.py"""
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
tmp = tempfile.mkdtemp()
os.environ["UIVP_DB"] = str(Path(tmp) / "t.db")

import cv2
import config as cfg
cfg.STORAGE_DIR = Path(tmp) / "storage"
from face_engine.engine import FaceEngine
from face_engine.tests.fakes import FakeDetector, FakeEmbedder, FakeEyes, GroupDetector, SrcEmbedder, make_img, person_vec
from services import face_service as fs
fs.PHOTO_DIR, fs.IDCARD_DIR = cfg.STORAGE_DIR / "photos", cfg.STORAGE_DIR / "idcards"

class Det(GroupDetector):          # single-face detect from FakeDetector, group faces from GroupDetector
    pass
class Emb(FakeEmbedder):
    def embed(self, img, face):
        src = face.src if face.src is not None else img
        return person_vec(int(src[src.shape[0] // 2, src.shape[1] // 2, 0]) - 100, noise=0.10)
fs.engine = FaceEngine(Det(), Emb(), FakeEyes())

from app import create_app
app = create_app()
c = app.test_client()
fails = []


def ok(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"   {extra}"))
    if not cond:
        fails.append(name)


def png(img):
    return io.BytesIO(cv2.imencode(".png", img)[1].tobytes())


def login(kind, ident, pw):
    return c.post("/api/auth/login", json=dict(kind=kind, identifier=ident, password=pw))


def logout():
    c.post("/api/auth/logout")


# ---------- sign-in basics ----------
ok("home redirects to login page", c.get("/").status_code == 302 and "/auth/login.html" in c.get("/").location)
ok("login page is served", c.get("/auth/login.html").status_code == 200)
ok("meta has VIT Pune and no college list", c.get("/api/meta").json["college"] == "VIT Pune")
ok("wrong password rejected", login("admin", "hod@vit.edu", "nope").status_code == 401)
ok("api blocked when signed out", c.get("/api/hod/stats").status_code == 401)

# ---------- student self-registration ----------
r = c.post("/api/register/send-otp", json=dict(email="x@gmail.com"))
ok("non-college e-mail refused", r.status_code == 400)
r = c.post("/api/register/send-otp", json=dict(email="aditi.sharma@vit.edu", name="Aditi"))
code = r.json.get("dev_otp")
ok("otp issued (dev shows it)", r.status_code == 200 and code)
ok("wrong otp refused", c.post("/api/register/verify-otp", json=dict(email="aditi.sharma@vit.edu", code="000000")).status_code == 400)
ticket = c.post("/api/register/verify-otp", json=dict(email="aditi.sharma@vit.edu", code=code)).json["ticket"]


def reg_form(**over):
    f = dict(name="Aditi Sharma", prn="PRN24CS0142", roll_no="CS-042", department="Computer Engineering", year="3rd Year",
             division="B", mobile="9876543210", email="aditi.sharma@vit.edu", password="Secret123", ticket=ticket, consent="1")
    f.update(over)
    f["photos"] = [(png(make_img(42, yaw=y, seed=i)), f"p{i}.png") for i, y in enumerate((0.0, 0.2, -0.2))]
    f["id_card"] = (png(make_img(42, seed=9)), "idcard.png")
    return f

r = c.post("/api/register/student", data=reg_form(consent="0"), content_type="multipart/form-data")
ok("consent required", r.status_code == 400)
bad = reg_form(); bad["photos"] = bad["photos"][:2]
ok("only 2 photos refused", c.post("/api/register/student", data=bad, content_type="multipart/form-data").status_code == 400)
nocard = reg_form(); del nocard["id_card"]
r = c.post("/api/register/student", data=nocard, content_type="multipart/form-data")
ok("ID card image required", r.status_code == 400 and "ID card" in r.json["error"], r.json)
r = c.post("/api/register/student", data=reg_form(mobile="12345"), content_type="multipart/form-data")
ok("bad mobile refused", r.status_code == 400)
r = c.post("/api/register/student", data=reg_form(), content_type="multipart/form-data")
ok("student registered (pending)", r.status_code == 200, r.json)
r = c.post("/api/register/student", data=reg_form(), content_type="multipart/form-data")
ok("same PRN cannot register twice", r.status_code == 400)
r = login("student", "PRN24CS0142", "Secret123")
ok("pending student cannot sign in yet", r.status_code == 403)

# a second person registers with the SAME face -> flagged for HOD
c.post("/api/register/send-otp", json=dict(email="isha@vit.edu"))
code2 = c.post("/api/register/send-otp", json=dict(email="isha2@vit.edu")).json["dev_otp"]
t2 = c.post("/api/register/verify-otp", json=dict(email="isha2@vit.edu", code=code2)).json["ticket"]
r = c.post("/api/register/student", data=reg_form(name="Isha Wagh", prn="PRN24IT0051", email="isha2@vit.edu", ticket=t2, department="Information Technology", roll_no="IT-051"),
           content_type="multipart/form-data")
ok("second registration accepted", r.status_code == 200, r.json)

# ---------- HOD ----------
ok("HOD signs in", login("admin", "hod@vit.edu", "Hod@12345").json.get("redirect") == "hod/dashboard.html")
pend = c.get("/api/hod/pending").json["items"]
ok("two registrations waiting", len(pend) == 2)
dup = [p for p in pend if p["prn"] == "PRN24IT0051"][0]
ok("duplicate face is flagged", dup["dup_note"] and "Aditi" in dup["dup_note"], dup)
aditi = [p for p in pend if p["prn"] == "PRN24CS0142"][0]
ok("HOD can open the ID card image", c.get(f"/api/idcard/{aditi['id']}").status_code == 200)
ok("HOD approves", c.post(f"/api/hod/pending/{aditi['id']}", json=dict(action="approve")).status_code == 200)
ok("HOD rejects the duplicate", c.post(f"/api/hod/pending/{dup['id']}", json=dict(action="reject")).status_code == 200)
st = c.get("/api/hod/stats").json
ok("stats count 1 student, 0 pending", st["students"] == 1 and st["pending"] == 0, st)
ok("people list + search", len(c.get("/api/hod/people?type=student&q=aditi").json["items"]) == 1)
ok("edit student", c.put(f"/api/hod/people/{aditi['id']}", json=dict(mobile="9000000001")).status_code == 200)

fac_photos = [(png(make_img(60, yaw=y, seed=i)), f"f{i}.png") for i, y in enumerate((0, 0.2, -0.2))]
r = c.post("/api/hod/users", data=dict(type="faculty", name="Prof. A. Rane", email="a.rane@vit.edu", mobile="9811111111",
                                        department="Computer Engineering", photos=fac_photos), content_type="multipart/form-data")
ok("HOD registers faculty with face photos", r.status_code == 200 and r.json["temp_password"], r.json)
r = c.post("/api/hod/users", data=dict(type="security", name="P. Gaikwad", email="p.gaikwad@vit.edu", mobile="9822222222", gate="Gate B"),
           content_type="multipart/form-data")
ok("HOD registers security", r.status_code == 200)
ok("HOD can reset a password", c.post(f"/api/hod/people/{aditi['id']}/reset-password").json.get("temp_password"))
c.put(f"/api/hod/people/{aditi['id']}", json=dict(mobile="9000000001"))
logout()

# reset made the student's password unknown: set it again through the DB-less path (HOD reset returned temp pw)
login("admin", "hod@vit.edu", "Hod@12345")
tp = c.post(f"/api/hod/people/{aditi['id']}/reset-password").json["temp_password"]
logout()

# ---------- student ----------
ok("student signs in with PRN", login("student", "PRN24CS0142", tp).status_code == 200)
ok("student cannot open HOD api", c.get("/api/hod/stats").status_code == 403)
ok("student cannot open ID cards", c.get(f"/api/idcard/{aditi['id']}").status_code == 403)
a = c.get("/api/student/attendance").json
ok("student sees 4 subjects, 0 classes yet", len(a["subjects"]) == 4 and a["overall"] == 0)
ok("student sees own profile with 3 photos on file", c.get("/api/student/profile").json["photos"] == 3)
ok("student sees own photo", c.get(f"/api/photo/{aditi['id']}").status_code == 200)
ok("student cannot see someone else's photo", c.get(f"/api/photo/{aditi['id'] + 1}").status_code == 403)
r = c.post("/api/auth/password/otp").json
ok("password change otp", bool(r.get("dev_otp")))
r2 = c.post("/api/auth/password/change", json=dict(current=tp, new="NewPass123", otp=r["dev_otp"]))
ok("password changed with otp", r2.status_code == 200, r2.json)
logout()
ok("old password no longer works", login("student", "PRN24CS0142", tp).status_code == 401)

# ---------- faculty: class attendance ----------
ok("faculty signs in", login("admin", "faculty@vit.edu", "Faculty@123").status_code == 200)
subs = c.get("/api/faculty/subjects").json["subjects"]
ok("faculty sees 4 subjects", len(subs) == 4)
sid = subs[3]["id"]
photos = [(png(make_img(42)), "class1.png"), (png(make_img(42, seed=3)), "class2.png")]
r = c.post("/api/faculty/attendance/detect", data=dict(subject_id=sid, division="B", photos=photos), content_type="multipart/form-data")
ok("class photos detect the registered student", r.status_code == 200 and r.json["items"][0]["present"] and r.json["faces_found"] >= 2, r.json)
marks = [dict(student_id=i["id"], present=i["present"], confidence=i["confidence"], edited=False) for i in r.json["items"]]
ok("attendance saved", c.post("/api/faculty/attendance/save", json=dict(subject_id=sid, division="B", marks=marks, topic="Revision", photos=2)).json["present"] == 1)
marks[0].update(present=False, edited=True)
ok("second class saved with manual absent", c.post("/api/faculty/attendance/save", json=dict(subject_id=sid, division="B", marks=marks)).status_code == 200)
ok("faculty student list", len(c.get("/api/faculty/students?q=cs-042").json["items"]) == 1)
ok("faculty cannot use HOD api", c.get("/api/hod/people").status_code == 403)
logout()

# ---------- student sees the result and reports the wrong absence ----------
login("student", "PRN24CS0142", "NewPass123")
a = c.get("/api/student/attendance").json
os_ = [s for s in a["subjects"] if s["id"] == sid][0]
ok("student attendance 1 of 2 = 50%", os_["attended"] == 1 and os_["total"] == 2 and os_["pct"] == 50, os_)
ok("low-attendance warning lists the subject", os_["name"] in a["low"])
det = c.get(f"/api/student/attendance/{sid}").json
absent = [d for d in det["dates"] if not d["present"]][0]
ok("date-wise detail has 2 rows", len(det["dates"]) == 2)
ok("student reports wrong absence", c.post("/api/student/report-issue", json=dict(attendance_id=absent["attendance_id"], note="I was there")).status_code == 200)
ok("cannot report twice", c.post("/api/student/report-issue", json=dict(attendance_id=absent["attendance_id"])).status_code == 400)
logout()
login("admin", "faculty@vit.edu", "Faculty@123")
iss = c.get("/api/faculty/issues").json["items"]
ok("faculty sees the issue", len(iss) == 1 and iss[0]["status"] == "open")
ok("faculty accepts it", c.post(f"/api/faculty/issues/{iss[0]['id']}", json=dict(action="accept")).status_code == 200)
logout()
login("student", "PRN24CS0142", "NewPass123")
ok("attendance is now 2 of 2", c.get(f"/api/student/attendance/{sid}").json["attended"] == 2)
logout()

# ---------- security gate ----------
ok("security signs in", login("admin", "security@vit.edu", "Security@123").status_code == 200)
ok("security cannot take attendance", c.get("/api/faculty/subjects").status_code == 403)


def do_scan(pid, closed=(6, 7), direction="entry"):
    ch = c.get("/api/security/challenge").json
    frames = [(png(make_img(pid, closed=i in closed, seed=i)), f"f{i}.png") for i in range(14)]
    return ch, c.post("/api/security/scan", data=dict(token=ch["token"], direction=direction, frames=frames), content_type="multipart/form-data")

ch, r = do_scan(42)
if ch["type"] != "blink":      # the fake frames only blink; for a head-turn challenge the check should say "not live"
    ok(f"challenge was {ch['type']}: blink frames do not pass a head-turn challenge", r.json["status"] == "not_live")
    ch, r = None, None
    for _ in range(40):
        ch = c.get("/api/security/challenge").json
        if ch["type"] == "blink":
            frames = [(png(make_img(42, closed=i in (6, 7), seed=i)), f"f{i}.png") for i in range(14)]
            r = c.post("/api/security/scan", data=dict(token=ch["token"], direction="entry", frames=frames), content_type="multipart/form-data")
            break
j = r.json
ok("gate scan: live + matched", j.get("status") == "match" and j["name"] == "Aditi Sharma", j)
ok("gate result only has limited fields", set(j) == {"status", "name", "department", "role", "on_campus", "photo", "time", "confidence", "liveness"}, sorted(j))
ok("gate shows on campus after entry", j.get("on_campus") is True)
ok("gate photo is available to security", c.get(j["photo"]).status_code == 200)
for _ in range(40):
    ch = c.get("/api/security/challenge").json
    if ch["type"] == "blink":
        frames = [(png(make_img(99, closed=i in (6, 7), seed=i)), f"f{i}.png") for i in range(14)]
        r = c.post("/api/security/scan", data=dict(token=ch["token"], direction="entry", frames=frames), content_type="multipart/form-data")
        break
ok("gate scan: stranger -> no match", r.json["status"] == "no_match", r.json)
r = c.post("/api/security/scan", data=dict(token=ch["token"], direction="entry", frames=[]), content_type="multipart/form-data")
ok("re-using a challenge is refused", r.status_code == 400)
ok("visitor can be logged", c.post("/api/security/visitor", json=dict(name="Mr. Patil (parent)")).status_code == 200)
items = c.get("/api/security/log").json["items"]
ok("today's log lists scans", len(items) >= 3 and any(i["name"].startswith("Visitor") for i in items), items)
logout()
login("admin", "hod@vit.edu", "Hod@12345")
ok("HOD sees student on campus", c.get("/api/hod/stats").json["on_campus"] == 1)
ok("audit log has entries", len(c.get("/api/hod/audit").json["items"]) > 5)
ok("deactivating removes access", c.post(f"/api/hod/people/{aditi['id']}/active", json=dict(active=False)).status_code == 200)
logout()
ok("deactivated student cannot sign in", login("student", "PRN24CS0142", "NewPass123").status_code == 403)

# brute force lock
for _ in range(6):
    login("admin", "faculty@vit.edu", "wrong")
ok("too many wrong passwords locks the account for a while", login("admin", "faculty@vit.edu", "Faculty@123").status_code == 429)

print("\n%s" % ("ALL BACKEND CHECKS PASSED" if not fails else f"{len(fails)} CHECK(S) FAILED: {fails}"))
sys.exit(1 if fails else 0)
