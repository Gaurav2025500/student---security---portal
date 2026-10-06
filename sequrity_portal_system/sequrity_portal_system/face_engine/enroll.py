"""Step 4 - registration. Takes 3-5 photos of one person and returns the vectors to store.
Rejects bad photos with a clear reason instead of silently saving a weak template."""
import cv2
import numpy as np
from . import config as C
from .quality import assess, explain


def square_crop(img, face, size=256, pad=0.45):
    H, W = img.shape[:2]
    x, y, w, h = face.box
    cx, cy, s = x + w / 2, y + h / 2, max(w, h) * (1 + pad)
    x0, y0 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
    x1, y1 = int(min(W, cx + s / 2)), int(min(H, cy + s / 2))
    crop = img[y0:y1, x0:x1]
    ok, buf = cv2.imencode(".jpg", cv2.resize(crop, (size, size)), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return buf.tobytes() if ok else None


def enroll(detector, embedder, eyes, images):
    """images: list of BGR arrays (or None for unreadable files)."""
    reports, good = [], []
    for i, img in enumerate(images):
        rep = dict(index=i, accepted=False, issues=[])
        if img is None:
            rep["issues"] = ["unreadable_image"]
        else:
            faces = detector.detect(img)
            if not faces:
                rep["issues"] = ["no_face"]
            else:
                face = faces[0]
                if any(f.area > 0.35 * face.area for f in faces[1:]):
                    rep["issues"].append("multiple_people")
                q = assess(img, face)
                rep["issues"] += q["issues"]
                e = eyes.analyze(img, face)
                if C.ENROLL_REQUIRE_OPEN_EYES and not e["is_open"]:
                    rep["issues"].append("eyes_closed")
                rep["pose"] = q["pose"]
                if not rep["issues"]:
                    good.append(dict(i=i, vec=embedder.embed(img, face), pose=q["pose"], blur=q["blur"],
                                     photo=square_crop(img, face)))
                    rep["accepted"] = True
        rep["messages"] = explain(rep["issues"])
        reports.append(rep)

    def fail(msg):
        return dict(ok=False, message=msg, vectors=[], poses=[], profile_photo=None, reports=reports)

    if len(good) < C.ENROLL_MIN_PHOTOS:
        return fail(f"Only {len(good)} of {len(images)} photos were usable. At least {C.ENROLL_MIN_PHOTOS} good photos are needed.")
    good = sorted(good, key=lambda g: -g["blur"])[:C.ENROLL_MAX_PHOTOS]

    # all photos must show the same person; drop one outlier if that fixes it
    def same_person(items):
        V = np.stack([g["vec"] for g in items])
        return V.shape[0] < 2 or (V @ V.T)[np.triu_indices(len(items), 1)].min() >= C.ENROLL_SELF_SIMILARITY

    while not same_person(good):
        if len(good) <= C.ENROLL_MIN_PHOTOS:
            return fail("The photos do not look like the same person. Retake all photos.")
        V = np.stack([g["vec"] for g in good])
        good.pop(int(np.argmin((V @ V.T).sum(axis=1))))

    if not any(g["pose"] == "front" for g in good):
        return fail("Include at least one photo looking straight at the camera.")
    front = next(g for g in good if g["pose"] == "front")
    return dict(ok=True, message="Face photos accepted.", vectors=[g["vec"] for g in good],
                poses=[g["pose"] for g in good], profile_photo=front["photo"], reports=reports)
