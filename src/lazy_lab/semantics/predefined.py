
"""Identifiers provided by the language's predefined scope."""

from types import MappingProxyType
from typing import Mapping


PREDEFINED_FUNCTION_ARITIES: Mapping[str, int] = MappingProxyType({
    "seq": 2,
})

PREDEFINED_IDENTIFIERS: frozenset[str] = frozenset(
    PREDEFINED_FUNCTION_ARITIES
)
