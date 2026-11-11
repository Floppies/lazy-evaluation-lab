"""Typed semantic events for runtime instrumentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from lazy_lab.source import SourceSpan
from .references import ObjectId


class SemanticEventKind(StrEnum):
    # Core semantic work
    FUNCTION_APPLIED = "FUNCTION_APPLIED"
    BETA_REDUCED = "BETA_REDUCED"
    LET_ACTIVATED = "LET_ACTIVATED"
    PRIMITIVE_REDUCED = "PRIMITIVE_REDUCED"
    CONDITIONAL_SELECTED = "CONDITIONAL_SELECTED"
    CASE_ALTERNATIVE_SELECTED = "CASE_ALTERNATIVE_SELECTED"
    SEQ_REDUCED = "SEQ_REDUCED"
    VARIABLE_LOOKED_UP = "VARIABLE_LOOKED_UP"

    # Call-by-Need lifecycle
    THUNK_CREATED = "THUNK_CREATED"
    THUNK_DEMANDED = "THUNK_DEMANDED"
    THUNK_FORCE_STARTED = "THUNK_FORCE_STARTED"
    THUNK_UPDATED = "THUNK_UPDATED"
    SHARED_RESULT_HIT = "SHARED_RESULT_HIT"
    BLACKHOLE_DETECTED = "BLACKHOLE_DETECTED"


class OriginKind(StrEnum):
    SOURCE = "SOURCE"
    GENERATED = "GENERATED"
    INTERNAL = "INTERNAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class EventOrigin:
    kind: OriginKind = OriginKind.UNKNOWN
    source_spans: tuple[SourceSpan, ...] = ()


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    kind: SemanticEventKind
    origin: EventOrigin = field(
        default_factory=EventOrigin
    )
    object_id: ObjectId | None = None
