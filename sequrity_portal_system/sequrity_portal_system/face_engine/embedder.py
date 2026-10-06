"""Step 3 - turn an aligned face into 128 numbers (SFace). Two faces of the same person
give vectors that point the same way (cosine similarity close to 1)."""
import threading
import cv2
import numpy as np


class FaceEmbedder:
    def __init__(self, model_path):
        self._rec = cv2.FaceRecognizerSF.create(str(model_path), "")
        self._lock = threading.Lock()

    def embed(self, img, face):
        src = face.src if face.src is not None else img
        with self._lock:
            aligned = self._rec.alignCrop(src, face.row)          # rotate + crop to 112x112 using the eye landmarks
            f1 = self._rec.feature(aligned)
            f2 = self._rec.feature(cv2.flip(aligned, 1))          # mirrored copy: averaging both is more stable
        v = (f1 + f2).reshape(-1).astype(np.float32)
        return v / (np.linalg.norm(v) + 1e-9)


def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
