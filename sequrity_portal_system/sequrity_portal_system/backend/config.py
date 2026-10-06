"""Backend settings. Edit this file to change college details. Secrets go in environment variables (see README)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DB_PATH = Path(os.getenv("UIVP_DB", ROOT_DIR / "database" / "campus.db"))
SCHEMA_PATH = ROOT_DIR / "database" / "schema.sql"
STORAGE_DIR = BACKEND_DIR / "storage"          # profile photos, ID card images, secret keys

COLLEGE_NAME = "VIT Pune"
COLLEGE_FULL_NAME = "Vishwakarma Institute of Technology, Pune"
EMAIL_DOMAINS = ["vit.edu"]                    # students must register with an address ending in @vit.edu
DEPARTMENTS = ["Computer Engineering", "Information Technology", "Electronics & Telecommunication",
               "Mechanical Engineering", "Civil Engineering", "Artificial Intelligence & Data Science",
               "Chemical Engineering", "Instrumentation & Control"]
YEARS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]

# Registration OTP e-mail. If SMTP_HOST is empty the code is printed in the server console instead.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@vit.edu")
# While developing (no SMTP) the sign-up page can show the code on screen. Set UIVP_SHOW_OTP=0 for real use.
SHOW_OTP_ON_SCREEN = os.getenv("UIVP_SHOW_OTP", "1") == "1" and not SMTP_HOST

OTP_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
SESSION_HOURS = 8
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_MINUTES = 5
MAX_UPLOAD_MB = 25
LOW_ATTENDANCE = 75
# Show the real error reason on the page while you build and test. Set UIVP_SHOW_ERRORS=0 for real use.
SHOW_ERRORS = os.getenv("UIVP_SHOW_ERRORS", "1") == "1"

# First-run accounts (change these passwords after you sign in!)
DEFAULT_HOD = dict(name="Dr. R. Kulkarni", email="hod@vit.edu", password="Hod@12345", department="Computer Engineering")
DEFAULT_FACULTY = dict(name="Prof. S. Iyer", email="faculty@vit.edu", password="Faculty@123", department="Computer Engineering")
DEFAULT_SECURITY = dict(name="V. Naik", email="security@vit.edu", password="Security@123", gate="Gate A")
DEFAULT_SUBJECTS = ["Data Structures", "Database Systems", "Computer Networks", "Operating Systems"]
