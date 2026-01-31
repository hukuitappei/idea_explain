"""Persistence layer (local files / Postgres).

This package is used by the Streamlit app to support:
- Streamlit Community Cloud (ephemeral filesystem) with external Postgres persistence
- Local development fallback to file-based storage
"""

from .factory import create_history_store

