
"""In-memory registry for interactive execution sessions."""

from __future__ import annotations

from dataclasses import dataclass, field

from lazy_lab.visualizer.session import InteractiveSession


class SessionNotFoundError(LookupError):
    """The requested interactive session does not exist."""


@dataclass(slots=True)
class SessionRegistry:
    """Own interactive sessions within one API process."""

    _sessions: dict[str, InteractiveSession] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __len__(self) -> int:
        return len(self._sessions)

    def add(self, session: InteractiveSession) -> None:
        """Register a new interactive session."""
        if not isinstance(session, InteractiveSession):
            raise TypeError("Expected an InteractiveSession")

        if session.session_id in self._sessions:
            raise ValueError("Session already exists")

        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> InteractiveSession:
        """Return an existing session or raise an explicit error."""
        if not isinstance(session_id, str):
            raise TypeError("Session ID must be a string")

        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise SessionNotFoundError(
                f"Session not found: {session_id}"
            ) from exc

    def replace(
        self,
        previous_session_id: str,
        new_session: InteractiveSession,
    ) -> None:
        """Replace a session after an explicit reset."""
        if not isinstance(new_session, InteractiveSession):
            raise TypeError("Expected an InteractiveSession")

        if previous_session_id not in self._sessions:
            raise SessionNotFoundError(
                f"Session not found: {previous_session_id}"
            )

        if new_session.session_id in self._sessions:
            raise ValueError("Replacement session ID already exists")

        del self._sessions[previous_session_id]
        self._sessions[new_session.session_id] = new_session
