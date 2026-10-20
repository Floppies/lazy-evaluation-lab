
"""Persistent lexical environments with name-based lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .references import (
    HeapReference,
    ImmediateBoolean,
    ImmediateInteger,
    RuntimeRef,
)


class UnboundNameError(LookupError):
    """Raised when a runtime binding is absent from the lexical chain."""


@dataclass(frozen=True, slots=True, eq=False)
class Environment:
    bindings: Mapping[str, RuntimeRef] = field(default_factory=dict)
    parent: Environment | None = None

    def __post_init__(self) -> None:
        if self.parent is not None and not isinstance(
            self.parent, Environment
        ):
            raise TypeError(
                "Environment parent must be an Environment or None"
            )

        snapshot = dict(self.bindings)

        for name, reference in snapshot.items():
            if not isinstance(name, str) or not name:
                raise ValueError(
                    "Binding names must be non-empty strings"
                )

            if not isinstance(
                reference,
                (ImmediateInteger, ImmediateBoolean, HeapReference),
            ):
                raise TypeError(
                    f"Invalid runtime reference for {name!r}"
                )

        object.__setattr__(
            self, "bindings", MappingProxyType(snapshot)
        )

    def extend(
        self, bindings: Mapping[str, RuntimeRef]
    ) -> Environment:
        """Return a child scope without modifying this environment."""
        return Environment(bindings=bindings, parent=self)

    def lookup(self, name: str) -> RuntimeRef:
        """Return the nearest binding without forcing it."""
        current: Environment | None = self

        while current is not None:
            if name in current.bindings:
                return current.bindings[name]

            current = current.parent

        raise UnboundNameError(
            f"Unbound runtime name: {name!r}"
        )
