"""Passwords, login protection, encryption of face vectors, role checks."""
import secrets
import time
from functools import wraps
import numpy as np
from cryptography.fernet import Fernet
from flask import session, jsonify, current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import config as cfg


def _key_file(name, maker):
    cfg.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    p = cfg.STORAGE_DIR / name
    if not p.exists():
        p.write_bytes(maker())
        try:
            p.chmod(0o600)
        except OSError:
            pass
    return p.read_bytes()


def secret_key() -> bytes:
    return _key_file(".secret_key", lambda: secrets.token_hex(32).encode())


def _fernet():
    return Fernet(_key_file(".face_key", Fernet.generate_key))


# --- face vectors are stored encrypted. Keep backend/storage/.face_key safe: without it they cannot be read.
def encrypt_vec(vec) -> bytes:
    return _fernet().encrypt(np.asarray(vec, dtype=np.float32).tobytes())


def decrypt_vec(blob) -> np.ndarray:
    return np.frombuffer(_fernet().decrypt(bytes(blob)), dtype=np.float32)


# --- signed tickets (proof that an e-mail was verified)
def _ser():
    return URLSafeTimedSerializer(secret_key(), salt="uivp-ticket")


def make_ticket(email):
    return _ser().dumps({"email": email})


def read_ticket(token, email, max_age=1800):
    try:
        return _ser().loads(token, max_age=max_age).get("email") == email.lower()
    except (BadSignature, SignatureExpired):
        return False


# --- login throttling (in memory)
_fails = {}


def locked(key):
    f = _fails.get(key)
    return bool(f and f[0] >= cfg.LOGIN_MAX_FAILS and time.time() < f[1])


def note_fail(key):
    n = _fails.get(key, (0, 0))[0] + 1
    _fails[key] = (n, time.time() + cfg.LOGIN_LOCK_MINUTES * 60)


def clear_fails(key):
    _fails.pop(key, None)


# --- role guard
def err(msg, code=400, **extra):
    return jsonify(dict(error=msg, **extra)), code


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "uid" not in session:
                return err("Please sign in.", 401)
            if roles and session.get("role") not in roles:
                return err("You do not have access to this.", 403)
            return fn(*a, **kw)
        return wrapper
    return deco


def strong_password(p):
    return len(p) >= 8 and any(c.isalpha() for c in p) and any(c.isdigit() for c in p)


def temp_password():
    return "Vit@" + secrets.token_hex(3) + str(secrets.randbelow(90) + 10)
