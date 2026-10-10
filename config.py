import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Automatically load .env if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)
    except ImportError:
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

class Config:
    """Base configuration settings for TruthLens AI."""
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "truthlens-dev-secret-key-change-in-prod")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")

    # Database Directory & Absolute Cross-Platform URI
    DATABASE_DIR = BASE_DIR / "database"
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    
    _raw_db_url = os.getenv("DATABASE_URL")
    if not _raw_db_url or _raw_db_url.strip() in ("", "sqlite:///database/truthlens.db", "sqlite:///database\\truthlens.db"):
        _db_path = (DATABASE_DIR / "truthlens.db").resolve().as_posix()
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{_db_path}"
    elif _raw_db_url.startswith("sqlite:///") and not _raw_db_url.startswith("sqlite:///:memory:"):
        _rel_path = _raw_db_url[len("sqlite:///"):]
        _path_obj = Path(_rel_path)
        if not _path_obj.is_absolute():
            _path_obj = (BASE_DIR / _path_obj).resolve()
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{_path_obj.as_posix()}"
    else:
        SQLALCHEMY_DATABASE_URI = _raw_db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Input constraints
    MIN_INPUT_LENGTH = int(os.getenv("MIN_INPUT_LENGTH", "5"))
    MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "10000"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024))) # 10 MB

    # Model & AI Pipeline
    MODEL_PATH = os.getenv("MODEL_PATH", str((BASE_DIR / "models" / "production").resolve()))
    EXPLANATION_CONFIDENCE_THRESHOLD = float(os.getenv("EXPLANATION_CONFIDENCE_THRESHOLD", "0.60"))
    CLASSES = ["False", "Misleading", "Reliable"]
    MODEL_NAME = "distilbert-base-uncased"
    APP_VERSION = "1.0.0"

    # Evidence Configuration
    DEFAULT_EVIDENCE_PROVIDER = os.getenv("EVIDENCE_PROVIDER", "Wikipedia (Public API)")
    GOOGLE_FACT_CHECK_API_KEY = os.getenv("GOOGLE_FACT_CHECK_API_KEY") or os.getenv("GOOGLE_FACTCHECK_API_KEY") or ""

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
