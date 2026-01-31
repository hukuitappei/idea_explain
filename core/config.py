import os
import re

# ------------------------------------------------------------
# Runtime mode flags
# ------------------------------------------------------------

# Treat anything other than "true" (case-insensitive) as False
IS_PRODUCTION = os.getenv("PRODUCTION_MODE", "false").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() == "true"

def _env_csv_set(key: str) -> set[str]:
    raw = os.getenv(key, "")
    return {x.strip().lower() for x in raw.split(",") if x.strip()}

# ------------------------------------------------------------
# Validation patterns
# ------------------------------------------------------------

# Session id / file stem (Windows-friendly) - 1 to 255 chars
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,255}$")

# Node id used in Mermaid/TOON (more permissive length; still safe charset)
NODE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# ------------------------------------------------------------
# Auth (Streamlit OIDC)
# ------------------------------------------------------------

# Public operation should be fail-closed, but this module is loaded at import time.
# We default to False for local dev/test; Streamlit Cloud should set REQUIRE_AUTH=true
# (recommended) or provide an [auth] secrets config which will fail-closed at runtime.
REQUIRE_AUTH = _env_bool("REQUIRE_AUTH", False)

# Optional allowlist (lowercased). Empty => allow any logged-in user.
ALLOWED_EMAILS = _env_csv_set("ALLOWED_EMAILS")  # e.g. "a@x.com,b@y.com"
ALLOWED_EMAIL_DOMAINS = _env_csv_set("ALLOWED_EMAIL_DOMAINS")  # e.g. "example.com,example.org"

# ------------------------------------------------------------
# Persistence / Rate limiting
# ------------------------------------------------------------

SESSION_STORE_BACKEND = os.getenv("SESSION_STORE_BACKEND", "auto").strip().lower()
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
DAILY_LLM_REQUEST_LIMIT = int(os.getenv("DAILY_LLM_REQUEST_LIMIT", "20"))

# ------------------------------------------------------------
# LLM / Ollama defaults
# ------------------------------------------------------------

OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "llama3.2"

# Default backend is "auto" (prefer OpenAI if configured, else Ollama)
DEFAULT_LLM_BACKEND = "auto"
LLM_BACKEND = os.getenv("LLM_BACKEND", DEFAULT_LLM_BACKEND).strip().lower()

# OpenAI-compatible API defaults (for production)
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# LLM request timeout (seconds)
LLM_REQUEST_TIMEOUT_SEC = 120

# ------------------------------------------------------------
# Output size limits (avoid Streamlit rendering issues)
# ------------------------------------------------------------

MAX_TOON_NODES = 30
MAX_TOON_EDGES = 50

# ------------------------------------------------------------
# App behavior limits
# ------------------------------------------------------------

MAX_QUESTION_COUNT = 5
HISTORY_MAX_LENGTH = 50
CONTEXT_HISTORY_MAX_LENGTH = 10
MAX_SESSION_JSON_FILES = 200

# ------------------------------------------------------------
# UI defaults
# ------------------------------------------------------------

FLOWCHART_HEIGHT = 800

