"""Step 1 - find faces. Uses YuNet, which returns a face box plus 5 landmarks:
right eye, left eye, nose tip, right mouth corner, left mouth corner."""
import threading
from dataclasses import dataclass, field
import cv2
import numpy as np
from . import config as C


@dataclass
class Face:
    box: tuple                 # (x, y, w, h) in the coordinates of the photo you passed in
    lm: np.ndarray             # 5x2 landmarks, same coordinates as box
    score: float
    row: np.ndarray            # raw 15-number detector row, in the coordinates of `src`
    src: object = field(default=None, repr=False)  # image `row` belongs to (set for tiled class photos)

    @property
    def area(self):
        return self.box[2] * self.box[3]


class FaceDetector:
    def __init__(self, model_path):
        self._det = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), C.DETECT_SCORE, C.NMS_IOU, 5000)
        self._lock = threading.Lock()

    def _raw(self, img, score):
        h, w = img.shape[:2]
        with self._lock:
            self._det.setInputSize((w, h))
            self._det.setScoreThreshold(float(score))
            _, rows = self._det.detect(img)
        return [] if rows is None else [np.asarray(r, dtype=np.float32) for r in rows]

    @staticmethod
    def _to_face(row, src=None, offset=(0, 0), scale=1.0):
        x, y, w, h = row[:4]
        lm = row[4:14].reshape(5, 2)
        ox, oy = offset
        box = (int(round(x / scale + ox)), int(round(y / scale + oy)), int(round(w / scale)), int(round(h / scale)))
        lm = lm / scale + np.array([ox, oy], dtype=np.float32)
        return Face(box=box, lm=lm.astype(np.float32), score=float(row[14]), row=row, src=src)

    def detect(self, img, score=None):
        """Faces in one photo, biggest first."""
        rows = self._raw(img, C.DETECT_SCORE if score is None else score)
        faces = [self._to_face(r) for r in rows]
        return sorted(faces, key=lambda f: -f.area)

    def detect_group(self, img):
        """Class photo: run on the whole photo and on 4 overlapping, enlarged tiles
        so small faces at the back are found, then merge duplicates."""
        h, w = img.shape[:2]
        k = min(1.0, C.GROUP_MAX_SIDE / max(h, w))
        base = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1.0 else img
        H, W = base.shape[:2]
        found = [self._to_face(r, src=base) for r in self._raw(base, C.GROUP_DETECT_SCORE)]
        tw, th = int(W * 0.6), int(H * 0.6)
        for ox in (0, W - tw):
            for oy in (0, H - th):
                tile = base[oy:oy + th, ox:ox + tw]
                s = float(np.clip(C.GROUP_MAX_SIDE / max(tw, th), 1.0, 2.5))
                big = cv2.resize(tile, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC) if s > 1.0 else tile
                for r in self._raw(big, C.GROUP_DETECT_SCORE):
                    found.append(self._to_face(r, src=big, offset=(ox, oy), scale=s))
        if not found:
            return [], base
        boxes = [list(f.box) for f in found]
        scores = [f.score for f in found]
        keep = cv2.dnn.NMSBoxes(boxes, scores, C.GROUP_DETECT_SCORE, 0.35)
        keep = np.array(keep).reshape(-1).tolist()
        return [found[i] for i in keep], base
