"""Glue between the database and the face_engine package."""
import sys
import cv2
import config as cfg
sys.path.insert(0, str(cfg.ROOT_DIR))
from face_engine import FaceEngine                    # noqa: E402
from face_engine.engine import decode_image          # noqa: E402
import db                                             # noqa: E402
from security import encrypt_vec, decrypt_vec         # noqa: E402

engine = FaceEngine()
PHOTO_DIR = cfg.STORAGE_DIR / "photos"
IDCARD_DIR = cfg.STORAGE_DIR / "idcards"


def reload_gallery(con=None):
    """Load every enrolled face (approved + pending, so double registrations are caught) into memory."""
    own = con is None
    con = con or db.connect()
    rows = con.execute("""SELECT f.user_id, f.embedding FROM face_templates f JOIN users u ON u.id = f.user_id
                          WHERE u.is_active = 1 AND u.status IN ('approved','pending')""").fetchall()
    engine.gallery.load([(r["user_id"], decrypt_vec(r["embedding"])) for r in rows])
    if own:
        con.close()


def store_enrollment(user_id, result):
    """Save the encrypted vectors and the one profile photo of an accepted enrollment."""
    db.run("DELETE FROM face_templates WHERE user_id=?", (user_id,))
    for vec, pose in zip(result["vectors"], result["poses"]):
        db.run("INSERT INTO face_templates (user_id, embedding, pose) VALUES (?,?,?)", (user_id, encrypt_vec(vec), pose))
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    (PHOTO_DIR / f"{user_id}.jpg").write_bytes(result["profile_photo"])


def read_images(files):
    return [decode_image(f.read()) for f in files]


def save_id_card(file_storage, name):
    """Re-encode the ID card image (drops hidden metadata) and keep it for the HOD to check."""
    img = decode_image(file_storage.read())
    if img is None:
        return None
    IDCARD_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(IDCARD_DIR / name), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return name
