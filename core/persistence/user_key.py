from __future__ import annotations

import hashlib


def to_user_dir_key(user_key: str) -> str:
    """Convert a user identifier (email) to a filesystem-safe directory key."""
    raw = (user_key or "").strip().lower().encode("utf-8", errors="ignore")
    # Short stable key (avoid leaking email in paths)
    return hashlib.sha256(raw).hexdigest()[:32]

