"""One object the backend talks to. Put the pieces together:
   FaceEngine.enroll(...)          registration
   FaceEngine.scan(...)            security gate: liveness + who is it
   FaceEngine.class_attendance()   faculty: class photos -> who is present
You can pass your own detector/embedder/eyes (used by the tests)."""
import cv2
import numpy as np
from . import config as C
from . import enroll as _enroll
from . import liveness
from .gallery import Gallery
from .quality import assess, explain, pose_label

MAX_SIDE = 1600


def decode_image(data: bytes):
    """bytes -> BGR image (or None). Big photos are shrunk so scans stay fast."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        k = MAX_SIDE / max(h, w)
        img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    return img


class FaceEngine:
    def __init__(self, detector=None, embedder=None, eyes=None):
        self._detector, self._embedder, self._eyes = detector, embedder, eyes
        self.gallery = Gallery()

    # parts are created on first use, so the web server starts fast
    def _load(self):
        if self._detector is None or self._embedder is None:
            from .models import ensure_models
            from .detector import FaceDetector
            from .embedder import FaceEmbedder
            yunet, sface = ensure_models()
            self._detector = self._detector or FaceDetector(yunet)
            self._embedder = self._embedder or FaceEmbedder(sface)
        if self._eyes is None:
            from .eyes import EyeAnalyzer
            self._eyes = EyeAnalyzer()

    @property
    def eye_method(self):
        self._load()
        return getattr(self._eyes, "method", "?")

    # ---------- registration ----------
    def enroll(self, images):
        self._load()
        return _enroll.enroll(self._detector, self._embedder, self._eyes, images)

    def find_duplicates(self, vectors, exclude_user=None):
        hits = {}
        for v in vectors:
            for uid, s in self.gallery.duplicates(v, exclude_user):
                hits[uid] = max(hits.get(uid, 0.0), s)
        return sorted(hits.items(), key=lambda x: -x[1])

    # ---------- security gate ----------
    def scan(self, frames, challenge_kind, allowed_users=None):
        """frames: list of BGR images captured over ~2.5 s (NOT mirrored).
        Returns dict(live, live_reasons, decision, user_id, score, margin, messages)."""
        self._load()
        infos, good = [], []
        for img in frames:
            info = dict(face=False, yaw=0.0, open=False, closed=False, emb=None, thumb=None)
            if img is not None:
                faces = self._detector.detect(img)
                if faces:
                    f = faces[0]
                    others = any(o.area > 0.5 * f.area for o in faces[1:])
                    q = assess(img, f, min_px=60)
                    e = self._eyes.analyze(img, f)
                    x, y, w, h = f.box
                    crop = img[max(0, y):y + h, max(0, x):x + w]
                    if crop.size and not others:
                        info.update(face=True, yaw=q["yaw"], open=e["is_open"], closed=e["is_closed"],
                                    thumb=cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (64, 64)))
                        if q["ok"] or q["issues"] == ["head_turned"]:
                            good.append((q["blur"] * q["size"], img, f, info))
            infos.append(info)
        # embed up to 8 frames spread over the whole recording: this both gives a stable average
        # and lets the liveness check notice if a different person steps in half-way
        vecs = []
        if good:
            for k in np.linspace(0, len(good) - 1, min(8, len(good))).round().astype(int):
                _, img, f, info = good[k]
                info["emb"] = self._embedder.embed(img, f)
                vecs.append(info["emb"])
        live = liveness.evaluate(infos, challenge_kind)
        out = dict(live=live["ok"], live_reasons=live["reasons"], decision="no_match", user_id=None, score=0.0, margin=0.0)
        if not vecs:
            out["live_reasons"] = out["live_reasons"] or ["No clear face found. Move closer and face the camera."]
            return out
        v = np.mean(vecs, axis=0)
        v /= np.linalg.norm(v) + 1e-9
        out.update(self.gallery.identify(v, only=allowed_users))
        out["vector"] = v
        return out

    # ---------- class attendance ----------
    def class_attendance(self, images, allowed_users=None):
        """images: 1-3 class photos. Returns dict(present={user_id: score}, faces_found, unmatched)."""
        self._load()
        present, found, matched = {}, 0, 0
        for img in images:
            if img is None:
                continue
            faces, base = self._detector.detect_group(img)
            faces = [f for f in faces if min(f.box[2], f.box[3]) >= C.MIN_FACE_PX_GROUP]
            found += len(faces)
            vecs = [self._embedder.embed(base, f) for f in faces]
            for fi, uid, score in self.gallery.match_group(vecs, only=allowed_users):
                matched += 1
                present[uid] = max(present.get(uid, 0.0), score)
        return dict(present=present, faces_found=found, unmatched=max(0, found - matched))
