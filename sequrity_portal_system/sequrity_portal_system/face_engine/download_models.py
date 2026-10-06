"""Run once:  python face_engine/download_models.py   (the server also does this by itself on first use)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from face_engine.models import ensure_models
ensure_models()
print("Models are ready.")
