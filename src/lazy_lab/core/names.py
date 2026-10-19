from __future__ import annotations

import re
from collections.abc import Iterable


_PREFIX_PATTERN = re.compile(r"[a-z][a-zA-Z0-9_]*\Z")

_CORE_IDENTIFIER_PATTERN = re.compile(
    r"(?:[a-z][a-zA-Z0-9_]*|\$[a-z][a-zA-Z0-9_]*)\Z"
)

_RESERVED_NAMES = {"if", "then", "else", "let", "in"}


class FreshNameSupply:
    """Generate collision-free Core identifiers within one lowering run."""

    def __init__(self, reserved: Iterable[str] = ()) -> None:
        self._used: set[str] = set()
        self._next_index: dict[str, int] = {}

        for name in reserved:
            self.reserve(name)

    def reserve(self, name: str) -> None:
        """Prevent an existing Core identifier from being generated."""
        if (
            type(name) is not str
            or _CORE_IDENTIFIER_PATTERN.fullmatch(name) is None
            or name in _RESERVED_NAMES
        ):
            raise ValueError(f"Invalid Core identifier: {name!r}")

        self._used.add(name)

    def fresh(self, prefix: str = "arg") -> str:
        """Return a unique compiler-generated identifier."""
        if (
            type(prefix) is not str
            or _PREFIX_PATTERN.fullmatch(prefix) is None
        ):
            raise ValueError(f"Invalid fresh-name prefix: {prefix!r}")

        index = self._next_index.get(prefix, 0)

        while True:
            candidate = f"${prefix}{index}"
            index += 1

            if candidate not in self._used:
                self._used.add(candidate)
                self._next_index[prefix] = index
                return candidate