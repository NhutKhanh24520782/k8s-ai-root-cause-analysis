import os
from pydantic import BaseModel


class Settings(BaseModel):
    APP_NAME: str = "ai-rca-api"
    APP_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("PORT", "8080"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # Path to serialized model artifacts directory
    MODEL_DIR: str = os.getenv("MODEL_DIR", "ml/models")

    # In-memory history buffer capacity for temporal rolling feature computation
    BUFFER_SIZE: int = int(os.getenv("BUFFER_SIZE", "20"))

    # Confidence threshold below which a warning/flag is raised
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.60"))


settings = Settings()
