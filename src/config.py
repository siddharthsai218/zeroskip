import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "zeroskip.db"))
JWT_SECRET = os.getenv("JWT_SECRET", "brightloop-super-secret-key-production-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
