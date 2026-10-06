"""All face-engine settings in one place. Change numbers here, not in the algorithms."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"

# Models (OpenCV Zoo). Downloaded automatically on first run.
YUNET = dict(file="face_detection_yunet_2023mar.onnx", size=232589,
             sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
             url="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx")
SFACE = dict(file="face_recognition_sface_2021dec.onnx", size=38696353,
             sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
             url="https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx")

# Detection
DETECT_SCORE = 0.85          # minimum detector confidence
NMS_IOU = 0.3
GROUP_DETECT_SCORE = 0.70    # class photos: faces are smaller, accept a little less
GROUP_MAX_SIDE = 1920        # class photos are resized so the long side is at most this

# Photo quality (registration + scanning)
MIN_FACE_PX = 90             # face box width/height in pixels
MIN_FACE_PX_GROUP = 28
BLUR_MIN = 45.0              # Laplacian variance of the face crop (lower = blurrier)
BRIGHT_MIN, BRIGHT_MAX = 55, 205
GLARE_MAX = 0.06             # share of near-white pixels in the face
MAX_ABS_YAW = 0.45           # beyond this the head is turned too far to match

# Matching (cosine similarity of 128-d vectors, higher = more alike)
MATCH_THRESHOLD = 0.45       # OpenCV's own default is 0.363; we are stricter on purpose
MATCH_MARGIN = 0.08          # best match must beat the 2nd best person by this much
GROUP_MATCH_THRESHOLD = 0.40 # class photos: lower quality faces
DUPLICATE_THRESHOLD = 0.55   # two different accounts with a face this alike get flagged

# Registration
ENROLL_REQUIRE_OPEN_EYES = True   # set False if the eye check wrongly rejects good photos
ENROLL_MIN_PHOTOS = 3
ENROLL_MAX_PHOTOS = 5
ENROLL_SELF_SIMILARITY = 0.45   # all photos must show the same person

# Eyes / liveness
EAR_CLOSED = 0.19            # MediaPipe eye-aspect-ratio below this = closed
EAR_OPEN = 0.23
HAAR_CLOSED = 0.30           # fallback openness score below this = closed
HAAR_OPEN = 0.42
YAW_TURN = 0.16              # head-turn challenge: nose offset / eye distance
YAW_FRONT = 0.10
LIVENESS_MIN_FRAMES = 6
LIVENESS_MIN_FACE_RATIO = 0.6   # share of frames that must contain a face
LIVENESS_SAME_PERSON = 0.40     # every pair of frames must be at least this alike (strangers are usually < 0.30)
LIVENESS_MIN_MOTION = 0.6       # average pixel change between frames (a frozen photo is ~0)
CHALLENGE_TTL_SECONDS = 60
