"""One-time codes sent to the college e-mail (registration and password change)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
import config as cfg
import db
from mailer import send_mail
from security import secret_key


def _h(email, code):
    return hmac.new(secret_key(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def issue(email, purpose, who=""):
    """Create + send a code. Returns the code only when SHOW_OTP_ON_SCREEN is on (development)."""
    email = email.lower()
    last = db.one("SELECT created_at FROM otp_codes WHERE email=? AND purpose=? ORDER BY id DESC LIMIT 1", (email, purpose))
    if last and (datetime.now() - datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S")).total_seconds() < 30:
        raise ValueError("Please wait 30 seconds before asking for another code.")
    code = f"{secrets.randbelow(900000) + 100000}"
    exp = (datetime.now() + timedelta(minutes=cfg.OTP_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    db.run("UPDATE otp_codes SET used=1 WHERE email=? AND purpose=?", (email, purpose))
    db.run("INSERT INTO otp_codes (email, purpose, code_hash, expires_at, created_at) VALUES (?,?,?,?,?)",
           (email, purpose, _h(email, code), exp, db.now_iso()))
    send_mail(email, f"{cfg.COLLEGE_NAME} verification code",
              f"Hello {who},\n\nYour verification code is {code}. It works for {cfg.OTP_MINUTES} minutes.\n"
              f"If you did not ask for it, ignore this e-mail.\n")
    return code if cfg.SHOW_OTP_ON_SCREEN else None


def check(email, purpose, code):
    email = email.lower()
    row = db.one("SELECT * FROM otp_codes WHERE email=? AND purpose=? AND used=0 ORDER BY id DESC LIMIT 1", (email, purpose))
    if not row:
        return False, "Ask for a new code."
    if row["expires_at"] < db.now_iso():
        return False, "This code has expired. Ask for a new one."
    if row["attempts"] >= cfg.OTP_MAX_ATTEMPTS:
        return False, "Too many wrong tries. Ask for a new code."
    if not hmac.compare_digest(row["code_hash"], _h(email, str(code).strip())):
        db.run("UPDATE otp_codes SET attempts = attempts + 1 WHERE id=?", (row["id"],))
        return False, "That code is not correct."
    db.run("UPDATE otp_codes SET used=1 WHERE id=?", (row["id"],))
    return True, ""
