import logging
import os
import sys
from typing import Any, Dict, Optional

# Allow importing ml.src when run directly from repo root or inside container
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

ML_SRC_DIR = os.path.join(BASE_DIR, "ml", "src")
if ML_SRC_DIR not in sys.path:
    sys.path.insert(0, ML_SRC_DIR)

from ml.src.predict import RCAPredictor
from app.config import settings

logger = logging.getLogger("rca-api.predictor")


class ServicePredictor:
    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir or settings.MODEL_DIR
        self._predictor: Optional[RCAPredictor] = None
        self.is_loaded: bool = False
        self._load_model()

    def _load_model(self):
        try:
            logger.info("Loading model artifacts from %s...", self.model_dir)
            self._predictor = RCAPredictor(model_dir=self.model_dir, buffer_size=settings.BUFFER_SIZE)
            self.is_loaded = True
            logger.info("RCA model successfully loaded.")
        except Exception as e:
            logger.error("Failed to load RCA model from %s: %s", self.model_dir, e)
            self._predictor = None
            self.is_loaded = False

    def predict(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_loaded or self._predictor is None:
            raise RuntimeError("Model is not loaded. Cannot perform prediction.")

        result = self._predictor.predict(snapshot)
        confidence = result.get("confidence", 0.0)
        result["low_confidence_warning"] = bool(confidence < settings.CONFIDENCE_THRESHOLD)
        return result
