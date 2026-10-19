"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# SQLite database file lives at the project root: fitbuddy.db
DATABASE_URL = os.getenv("FITBUDDY_DATABASE_URL", f"sqlite:///{BASE_DIR / 'fitbuddy.db'}")

# Google Gemini credentials. The app degrades to a deterministic local
# generator when no key is present, so it still runs out of the box.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_MODEL_FALLBACK = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-pro")

GOALS = ("weight loss", "muscle gain", "general wellness")
INTENSITIES = ("low", "medium", "high")

LOG_LEVEL = os.getenv("FITBUDDY_LOG_LEVEL", "INFO")
