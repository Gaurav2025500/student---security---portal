"""Step 5 - is a real person in front of the camera right now?

The server picks a random challenge (blink, or turn head left/right) and signs it.
The browser records ~2.5 seconds of frames. We then check:
  1. a face is visible in most frames
  2. it is the same person in every frame
  3. the picture actually moves (a frozen photo does not)
  4. the challenge was really performed (blink = eyes open -> closed -> open)
This stops a casual photo or a paused screen. It is NOT proof against a video replay
or a 3D mask - for higher security add an infrared camera or a dedicated anti-spoof model."""
import hmac
import hashlib
import secrets
import time
import numpy as np
from . import config as C

PROMPTS = {"blink": "Blink once", "turn_left": "Turn your head slightly to your left",
           "turn_right": "Turn your head slightly to your right"}
_USED = {}   # challenge token -> expiry (stops re-using one recording)


def make_challenge(secret: bytes, now=None):
    now = time.time() if now is None else now
    kind = secrets.choice(list(PROMPTS))
    payload = f"{kind}.{int(now + C.CHALLENGE_TTL_SECONDS)}.{secrets.token_hex(4)}"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:24]
    return dict(type=kind, prompt=PROMPTS[kind], token=f"{payload}.{sig}")


def read_challenge(secret: bytes, token: str, now=None, consume=True):
    """Returns the challenge type or raises ValueError."""
    now = time.time() if now is None else now
    try:
        kind, exp, nonce, sig = token.split(".")
        good = hmac.new(secret, f"{kind}.{exp}.{nonce}".encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(sig, good) or kind not in PROMPTS:
            raise ValueError
        if int(exp) < now:
            raise ValueError("expired")
    except Exception:
        raise ValueError("The check expired or is invalid. Scan again.")
    for t in [t for t, e in _USED.items() if e < now]:
        _USED.pop(t, None)
    if token in _USED:
        raise ValueError("This check was already used. Scan again.")
    if consume:
        _USED[token] = int(exp)
    return kind


def _blink_seen(frames):
    """open ... closed (1-6 frames) ... open"""
    seq = [("O" if f["open"] else "C" if f["closed"] else "-") for f in frames if f["face"]]
    state, closed_run = 0, 0
    for s in seq:
        if state == 0 and s == "O":
            state = 1
        elif state == 1 and s == "C":
            state, closed_run = 2, 1
        elif state == 2:
            if s == "C":
                closed_run += 1
                if closed_run > 6:      # eyes shut for too long: not a blink
                    state = 0
            elif s == "O":
                return True
    return False


def evaluate(frames, kind):
    """frames: list of dicts {face, yaw, open, closed, emb, thumb} (one per captured frame)."""
    reasons, n = [], len(frames)
    if n < C.LIVENESS_MIN_FRAMES:
        return dict(ok=False, reasons=["Too few frames captured. Try again."], motion=0.0)
    seen = [f for f in frames if f["face"]]
    if len(seen) / n < C.LIVENESS_MIN_FACE_RATIO:
        reasons.append("Keep your face in the frame during the check.")

    embs = [f["emb"] for f in seen if f.get("emb") is not None]
    if len(embs) >= 2:
        E = np.stack(embs)
        if float((E @ E.T)[np.triu_indices(len(embs), 1)].min()) < C.LIVENESS_SAME_PERSON:
            reasons.append("More than one person appeared during the check.")

    thumbs = [f["thumb"] for f in seen if f.get("thumb") is not None]
    motion = float(np.mean([np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()
                            for a, b in zip(thumbs, thumbs[1:])])) if len(thumbs) >= 2 else 0.0
    if motion < C.LIVENESS_MIN_MOTION:
        reasons.append("No natural movement seen. A still photo cannot be used.")

    if kind == "blink":
        if not _blink_seen(frames):
            reasons.append("Blink was not detected. Look at the camera and blink once.")
    else:
        sign = 1 if kind == "turn_left" else -1
        yaws = [f["yaw"] for f in seen]
        front = any(abs(y) < C.YAW_FRONT for y in yaws)
        turned = any(sign * y > C.YAW_TURN for y in yaws)
        if not (front and turned):
            reasons.append("Head turn was not detected. Start facing the camera, then turn slowly.")
    return dict(ok=not reasons, reasons=reasons, motion=motion)
