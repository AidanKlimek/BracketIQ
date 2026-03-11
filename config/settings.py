"""
BracketIQ - Environment Settings
==================================
Loads configuration from .env file.
Never hardcode secrets or user-specific values — they go in .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Request Settings ---
USER_AGENT = os.getenv("USER_AGENT", "BracketIQ/1.0")
ESPN_REQUEST_DELAY = float(os.getenv("ESPN_REQUEST_DELAY", "1.0"))
TORVIK_REQUEST_DELAY = float(os.getenv("TORVIK_REQUEST_DELAY", "1.5"))

# --- Cache ---
CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "6"))
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --- Export ---
EXPORT_DIR = PROJECT_ROOT / os.getenv("EXPORT_DIR", "exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# --- Streamlit ---
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))

# --- Request Headers ---
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}