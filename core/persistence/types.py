from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.schemas import Flowchart


class RateLimitExceededError(RuntimeError):
    pass


class HistoryStore(ABC):
    """History + TOON persistence for a single user."""

    @abstractmethod
    def list_sessions(self) -> List[str]: ...

    @abstractmethod
    def save_session(self, session_id: str, history: List[Flowchart]) -> None: ...

    @abstractmethod
    def load_session(self, session_id: str) -> List[Flowchart]: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...

    @abstractmethod
    def list_toon_files(self) -> List[str]: ...

    @abstractmethod
    def save_toon_file(self, session_id: str, flowchart: Flowchart) -> None: ...

    @abstractmethod
    def load_toon_file(self, session_id: str) -> Optional[Flowchart]: ...

    @abstractmethod
    def append_toon_log(self, session_id: str, new_flowchart: Flowchart) -> Flowchart: ...

    @abstractmethod
    def cleanup_retention(self) -> int: ...

    @abstractmethod
    def consume_llm_request(self, daily_limit: int) -> int:
        """Consume 1 LLM request for today.

        Returns:
            The consumed count for today (after increment).

        Raises:
            RateLimitExceededError: if daily_limit is exceeded.
        """

