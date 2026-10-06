"""Eye check. Tells whether both eyes are open or closed in a photo.

Best method:  MediaPipe Face Mesh -> Eye Aspect Ratio (EAR), the standard blink measure.
              EAR = (vertical eye gaps) / (eye width). Open ~0.25-0.35, closed < 0.19.
Fallback:     if MediaPipe is not installed, OpenCV eye detectors on the eye area from the
              YuNet landmarks. Works, but is weaker in poor light. Install MediaPipe for best results.

Real iris recognition needs infrared hardware, so it is not used here."""
import threading
import cv2
import numpy as np
from . import config as C

_R = (33, 160, 158, 133, 153, 144)    # right eye: corner, top, top, corner, bottom, bottom
_L = (362, 385, 387, 263, 373, 380)


def _ear(pts, idx):
    p = [pts[i] for i in idx]
    v = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    return float(v / (2.0 * np.linalg.norm(p[0] - p[3]) + 1e-6))


class EyeAnalyzer:
    def __init__(self, use_mediapipe=True):
        self.method = "haar"
        self._mesh = None
        self._lock = threading.Lock()
        if use_mediapipe:
            try:
                import mediapipe as mp
                if hasattr(mp, "solutions"):
                    self._mesh = mp.solutions.face_mesh.FaceMesh(
                        static_image_mode=True, max_num_faces=1, refine_landmarks=False, min_detection_confidence=0.3)
                    self.method = "mediapipe"
            except Exception:
                self._mesh = None
        self._haar = self._load_cascade()

    @staticmethod
    def _load_cascade():
        """OpenCV's own eye detector file. Fails loudly (at server start) if this OpenCV build does not ship it."""
        try:
            base = cv2.data.haarcascades
        except AttributeError:
            base = ""
        for name in ("haarcascade_eye_tree_eyeglasses.xml", "haarcascade_eye.xml"):
            c = cv2.CascadeClassifier(base + name)
            if not c.empty():
                return c
        raise RuntimeError(
            f"The eye-detector file is missing from your OpenCV (version {cv2.__version__}). "
            'Fix:  pip uninstall -y mediapipe opencv-contrib-python opencv-python opencv-python-headless   '
            'then:  pip install "opencv-python>=4.8,<5" "numpy<2"')

    # ---------- MediaPipe (EAR) ----------
    def _mesh_ear(self, img, face):
        H, W = img.shape[:2]
        x, y, w, h = face.box
        pad = 0.35
        x0, y0 = max(0, int(x - pad * w)), max(0, int(y - pad * h))
        x1, y1 = min(W, int(x + w * (1 + pad))), min(H, int(y + h * (1 + pad)))
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        with self._lock:
            res = self._mesh.process(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if not res.multi_face_landmarks:
            return None
        ch, cw = crop.shape[:2]
        pts = np.array([[p.x * cw, p.y * ch] for p in res.multi_face_landmarks[0].landmark])
        return _ear(pts, _R), _ear(pts, _L)

    # ---------- OpenCV fallback ----------
    def _haar_open(self, gray, center, eye_d):
        cx, cy = int(center[0]), int(center[1])
        hw, hh = int(0.36 * eye_d), int(0.30 * eye_d)
        roi = gray[max(0, cy - hh):cy + hh, max(0, cx - hw):cx + hw]
        if roi.shape[0] < 6 or roi.shape[1] < 6:
            return 0.0
        k = max(1.0, 64.0 / roi.shape[1])
        roi = cv2.resize(roi, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
        roi = cv2.equalizeHist(roi)
        found = self._haar.detectMultiScale(roi, 1.08, 3, minSize=(18, 12))
        std = float(roi.std())
        return float(0.65 * (len(found) > 0) + 0.35 * min(1.0, std / 55.0))

    def analyze(self, img, face):
        """Returns dict(left, right, mean, method, is_open, is_closed)."""
        left = right = None
        method = self.method
        if self._mesh is not None:
            r = self._mesh_ear(img, face)
            if r is not None:
                right, left = r
            else:
                method = "haar"
        if left is None:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            eye_d = float(np.linalg.norm(face.lm[1] - face.lm[0]))
            right = self._haar_open(gray, face.lm[0], eye_d)
            left = self._haar_open(gray, face.lm[1], eye_d)
            method = "haar"
        mean = (left + right) / 2.0
        closed_thr, open_thr = (C.EAR_CLOSED, C.EAR_OPEN) if method == "mediapipe" else (C.HAAR_CLOSED, C.HAAR_OPEN)
        return dict(left=left, right=right, mean=mean, method=method,
                    is_open=mean >= open_thr, is_closed=mean < closed_thr)
