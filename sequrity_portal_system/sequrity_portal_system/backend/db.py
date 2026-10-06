"""SQLite helpers. The database file and tables are created automatically on first start."""
import sqlite3
from datetime import datetime
from flask import g
from werkzeug.security import generate_password_hash
import config as cfg


def connect():
    cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def one(sql, args=()):
    return get_db().execute(sql, args).fetchone()


def many(sql, args=()):
    return get_db().execute(sql, args).fetchall()


def run(sql, args=()):
    cur = get_db().execute(sql, args)
    get_db().commit()
    return cur.lastrowid


def audit(actor_id, action, detail=""):
    run("INSERT INTO audit_log (actor_id, action, detail) VALUES (?,?,?)", (actor_id, action, detail))


def init_db():
    """Create tables, and the first HOD / faculty / security accounts if the database is new."""
    con = connect()
    con.executescript(cfg.SCHEMA_PATH.read_text(encoding="utf-8"))
    created = []
    if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        def add(role, d, **extra):
            cur = con.execute(
                "INSERT INTO users (role,name,email,password_hash,department,gate,status) VALUES (?,?,?,?,?,?, 'approved')",
                (role, d["name"], d["email"], generate_password_hash(d["password"]), d.get("department"), d.get("gate")))
            created.append((role, d["email"], d["password"]))
            return cur.lastrowid
        add("hod", cfg.DEFAULT_HOD)
        fid = add("faculty", cfg.DEFAULT_FACULTY)
        add("security", cfg.DEFAULT_SECURITY)
        for s in cfg.DEFAULT_SUBJECTS:
            con.execute("INSERT INTO subjects (name, department, year, faculty_id) VALUES (?,?,?,?)",
                        (s, cfg.DEFAULT_HOD["department"], "3rd Year", fid))
        con.commit()
    con.close()
    return created


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
