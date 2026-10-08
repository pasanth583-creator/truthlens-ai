import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    """Base configuration settings for TruthLens AI."""
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "truthlens-dev-secret-key-change-in-prod")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")

    # Database
    DATABASE_DIR = BASE_DIR / "database"
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_DIR / 'truthlens.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Input constraints
    MIN_INPUT_LENGTH = int(os.getenv("MIN_INPUT_LENGTH", "5"))
    MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "10000"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024))) # 10 MB

    # Model & AI Pipeline
    MODEL_PATH = os.getenv("MODEL_PATH", str(BASE_DIR / "models" / "production"))
    EXPLANATION_CONFIDENCE_THRESHOLD = float(os.getenv("EXPLANATION_CONFIDENCE_THRESHOLD", "0.60"))
    CLASSES = ["False", "Misleading", "Reliable"]
    MODEL_NAME = "distilbert-base-uncased"
    APP_VERSION = "1.0.0"

    # Evidence Configuration
    DEFAULT_EVIDENCE_PROVIDER = os.getenv("EVIDENCE_PROVIDER", "Wikipedia (Public API)")
    GOOGLE_FACT_CHECK_API_KEY = os.getenv("GOOGLE_FACT_CHECK_API_KEY", "")

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False

class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False

config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}
