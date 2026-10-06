"""Start the system:   python backend/run.py     then open http://localhost:5000"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
import config as cfg

if __name__ == "__main__":
    app = create_app()
    # Load the face models now, so any problem is shown here at start-up and not during a registration.
    from services import face_service
    try:
        face_service.engine._load()
        print(f"  Face engine ready. Eye check method: {face_service.engine.eye_method}")
    except Exception as ex:
        print("\n  !! FACE ENGINE COULD NOT START:", type(ex).__name__, "-", ex)
        print("  Registration and scanning will fail until this is fixed.\n")
    print(f"\n  {cfg.COLLEGE_NAME} Student Security System")
    print("  Open  http://localhost:5000  in your browser (camera works on localhost)\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
