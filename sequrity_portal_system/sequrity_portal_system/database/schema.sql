-- Student Security System - database schema (SQLite; plain SQL, also works on MySQL/PostgreSQL with tiny changes)
-- Created automatically by backend/db.py the first time the server starts. Safe to run again.
PRAGMA foreign_keys = ON;

-- Everyone who can sign in: HOD, faculty, security and students
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    role          TEXT NOT NULL CHECK (role IN ('hod','faculty','security','student')),
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    mobile        TEXT,
    password_hash TEXT NOT NULL,
    department    TEXT,                       -- students, faculty, HOD
    gate          TEXT,                       -- security officers
    status        TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('pending','approved','rejected')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    in_campus     INTEGER NOT NULL DEFAULT 0, -- updated by gate scans
    last_seen     TEXT,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Extra fields only students have
CREATE TABLE IF NOT EXISTS students (
    user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    prn         TEXT NOT NULL UNIQUE,
    roll_no     TEXT NOT NULL,
    year        TEXT NOT NULL,
    division    TEXT NOT NULL,
    id_card     TEXT,                         -- file name of the virtual ID card image
    dup_note    TEXT,                         -- set when the face looks like an existing account
    consent_at  TEXT,
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT
);

-- Face data. `embedding` is the 128-number face vector, ENCRYPTED (Fernet). Raw photos are not stored.
CREATE TABLE IF NOT EXISTS face_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    embedding  BLOB NOT NULL,
    pose       TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS subjects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    department TEXT NOT NULL,
    year       TEXT NOT NULL,
    faculty_id INTEGER REFERENCES users(id)
);

-- One row each time a faculty member takes attendance
CREATE TABLE IF NOT EXISTS class_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id),
    faculty_id  INTEGER NOT NULL REFERENCES users(id),
    division    TEXT,
    held_on     TEXT NOT NULL,                -- YYYY-MM-DD
    topic       TEXT,
    photo_count INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS attendance (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES class_sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id),
    present    INTEGER NOT NULL,
    source     TEXT NOT NULL DEFAULT 'ai' CHECK (source IN ('ai','manual')),
    confidence REAL,
    edited_by  INTEGER REFERENCES users(id),
    UNIQUE (session_id, student_id)
);

-- A student says "I was present but marked absent"
CREATE TABLE IF NOT EXISTS attendance_issues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    attendance_id INTEGER NOT NULL REFERENCES attendance(id) ON DELETE CASCADE,
    student_id    INTEGER NOT NULL REFERENCES users(id),
    note          TEXT,
    status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','accepted','rejected')),
    resolved_by   INTEGER REFERENCES users(id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every gate scan: who scanned, who was recognised, how sure, was liveness passed
CREATE TABLE IF NOT EXISTS scan_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_by      INTEGER REFERENCES users(id),
    matched_user_id INTEGER REFERENCES users(id),
    direction       TEXT CHECK (direction IN ('entry','exit')),
    result          TEXT NOT NULL,            -- match | no_match | uncertain | not_live | not_approved | visitor
    score           REAL,
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT NOT NULL,
    purpose    TEXT NOT NULL,                 -- register | password
    code_hash  TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id   INTEGER REFERENCES users(id),
    action     TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_role      ON users(role, status, is_active);
CREATE INDEX IF NOT EXISTS idx_students_class  ON students(year, division);
CREATE INDEX IF NOT EXISTS idx_face_user       ON face_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_attendance_stu  ON attendance(student_id);
CREATE INDEX IF NOT EXISTS idx_scan_time       ON scan_log(created_at);
CREATE INDEX IF NOT EXISTS idx_otp_email       ON otp_codes(email, purpose);
